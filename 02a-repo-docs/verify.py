#!/usr/bin/env python3
"""Checker for the repository documentation loop. Standard library only.

This script is the only thing allowed to set status=verified.

Usage:
  python verify.py --manifest manifest.csv --inventory --expected-count 137
  python verify.py --manifest manifest.csv --repo NAME          # check one repo, update its status
  python verify.py --manifest manifest.csv --status done
  python verify.py --manifest manifest.csv --final              # re-check everything, write the report
  add --no-update to check without changing the manifest

Per-repo checks:
  R1 clone exists and is at the commit recorded in the manifest
  R2 docs/<repo>.md exists and has all ten sections, none empty
  R3 the document names the repo and the commit it describes
  R4 coverage: every path in scans/<repo>.json `must_mention` appears in the document
  R5 facts/<repo>.json is valid and matches the schema
  R6 every CI/CD and orchestration file found by the scan is a pipeline in the facts file, or is listed
     under not_pipelines with a reason; every pipeline has a trigger with evidence or no_trigger_found=true
  R7 every citation points to a real file and line; there are enough citations
  R8 no secrets in the document or the facts file
  R9 the independent checker sampled the citations and at most one sampled claim failed
"""
import argparse
import datetime
import json
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
from manifest import read_manifest, write_manifest, mark_failed, mark_verified  # noqa: E402
from evidence import (prose_citations, check_location, split_json_citation, find_secrets,  # noqa: E402
                      repo_dirname)

SECTIONS = [
    "1. Purpose and owners",
    "2. Languages, frameworks and layout",
    "3. Entry points, build, test and run",
    "4. Configuration and environment variables",
    "5. Data stores",
    "6. Interfaces exposed",
    "7. Dependencies consumed",
    "8. Pipelines and triggers",
    "9. Deployment and infrastructure",
    "10. Unknowns and open questions",
]
REPO_KINDS = {"service", "library", "pipeline", "infrastructure", "data", "frontend", "tooling", "docs", "config", "other"}
IO_KINDS = {"api", "package", "image", "topic", "queue", "table", "database", "bucket", "file", "artifact",
            "service", "repo", "workflow", "secret", "other"}
TRIGGER_TYPES = {"push", "pull_request", "tag", "release", "cron", "manual", "upstream", "webhook", "event", "api", "other"}
EXTERNAL = {"yes", "no", "unknown"}


def git_head(repo_dir):
    try:
        p = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(repo_dir), capture_output=True, text=True)
    except OSError:
        return None
    return p.stdout.strip() if p.returncode == 0 else ""


def sections_of(doc):
    """Returns {section title lowercased: body text}."""
    out, current, buf = {}, None, []
    for line in doc.split("\n"):
        m = re.match(r"##\s+(.*\S)\s*$", line)
        if m and not line.startswith("###"):
            if current is not None:
                out[current] = "\n".join(buf).strip()
            current, buf = m.group(1).strip().lower(), []
        elif current is not None:
            buf.append(line)
    if current is not None:
        out[current] = "\n".join(buf).strip()
    return out


def check_facts(facts, row):
    problems = []

    def need(obj, key, typ, where):
        if key not in obj or not isinstance(obj[key], typ):
            problems.append("%s: '%s' missing or wrong type" % (where, key))
            return False
        return True

    if not isinstance(facts, dict):
        return ["facts file is not a JSON object"]
    for key, typ in (("repo", str), ("commit", str), ("kind", str), ("purpose", str), ("owners", list),
                     ("languages", list), ("produces", list), ("consumes", list), ("pipelines", list),
                     ("not_pipelines", list), ("unknowns", list)):
        need(facts, key, typ, "facts")
    if problems:
        return problems
    if facts["repo"] != row["repo"]:
        problems.append("facts.repo is '%s', expected '%s'" % (facts["repo"], row["repo"]))
    if facts["commit"] != row.get("commit_sha", ""):
        problems.append("facts.commit does not match the manifest commit_sha")
    if facts["kind"] not in REPO_KINDS:
        problems.append("facts.kind '%s' not one of %s" % (facts["kind"], sorted(REPO_KINDS)))
    if len(facts["purpose"].split()) < 5 and row.get("clone_status") != "empty":
        problems.append("facts.purpose is too short")
    for group in ("produces", "consumes"):
        for i, item in enumerate(facts[group]):
            where = "%s[%d]" % (group, i)
            if not isinstance(item, dict):
                problems.append("%s is not an object" % where)
                continue
            for key in ("kind", "id", "evidence"):
                if not isinstance(item.get(key), str) or not item.get(key, "").strip():
                    problems.append("%s: '%s' missing" % (where, key))
            if item.get("kind") not in IO_KINDS:
                problems.append("%s: kind '%s' not one of %s" % (where, item.get("kind"), sorted(IO_KINDS)))
            if group == "consumes" and item.get("external") not in EXTERNAL:
                problems.append("%s: 'external' must be yes, no or unknown" % where)
    for i, pipe in enumerate(facts["pipelines"]):
        where = "pipelines[%d]" % i
        if not isinstance(pipe, dict):
            problems.append("%s is not an object" % where)
            continue
        for key in ("name", "system", "definition", "runs"):
            if not isinstance(pipe.get(key), str) or not pipe.get(key, "").strip():
                problems.append("%s: '%s' missing" % (where, key))
        triggers = pipe.get("triggers")
        if not isinstance(triggers, list):
            problems.append("%s: 'triggers' must be a list" % where)
            continue
        if not triggers and pipe.get("no_trigger_found") is not True:
            problems.append("%s: no triggers and no_trigger_found is not true" % where)
        for j, trig in enumerate(triggers):
            if not isinstance(trig, dict) or trig.get("type") not in TRIGGER_TYPES:
                problems.append("%s.triggers[%d]: type must be one of %s" % (where, j, sorted(TRIGGER_TYPES)))
            elif not str(trig.get("evidence", "")).strip():
                problems.append("%s.triggers[%d]: evidence missing" % (where, j))
    for i, item in enumerate(facts["not_pipelines"]):
        if not isinstance(item, dict) or not str(item.get("path", "")).strip() or len(str(item.get("reason", "")).split()) < 3:
            problems.append("not_pipelines[%d]: needs 'path' and a 'reason' of at least three words" % i)
    return problems


def facts_evidence(facts):
    out = []
    for group in ("produces", "consumes"):
        for item in facts.get(group, []):
            if isinstance(item, dict) and item.get("evidence"):
                out.append(item["evidence"])
    for pipe in facts.get("pipelines", []):
        if isinstance(pipe, dict):
            for trig in pipe.get("triggers", []) or []:
                if isinstance(trig, dict) and trig.get("evidence"):
                    out.append(trig["evidence"])
    return out


def check_repo(row, base):
    res = []
    name = repo_dirname(row["repo"])
    repo_dir = base / "repos" / name
    doc_file = base / "docs" / (name + ".md")
    facts_file = base / "facts" / (name + ".json")
    scan_file = base / "scans" / (name + ".json")
    check_file = base / "checks" / (name + ".json")
    empty = row.get("clone_status") == "empty"

    if not repo_dir.is_dir():
        res.append(("R1 clone", False, "repos/%s not found" % name))
        return res
    head = git_head(repo_dir)
    if empty:
        res.append(("R1 clone", True, "empty repository"))
    elif head is None:
        res.append(("R1 clone", True, "git not available; commit not compared"))
    else:
        res.append(("R1 clone", head == row.get("commit_sha", ""), "HEAD %s, manifest %s" % (head[:12], row.get("commit_sha", "")[:12])))

    if not doc_file.exists():
        res.append(("R2 document", False, "docs/%s.md not found" % name))
        return res
    doc = doc_file.read_text(encoding="utf-8")
    facts = None
    if facts_file.exists():
        try:
            facts = json.loads(facts_file.read_text(encoding="utf-8"))
        except ValueError as e:
            res.append(("R5 facts file", False, "not valid JSON: %s" % e))
    else:
        res.append(("R5 facts file", False, "facts/%s.json not found" % name))

    if empty:
        res.append(("R2 document", "empty repository" in doc.lower(), "must state that this is an empty repository"))
        if facts is not None:
            problems = check_facts(facts, row)
            res.append(("R5 facts file", not problems, "; ".join(problems[:6]) or "ok"))
        return res

    secs = sections_of(doc)
    missing = [s for s in SECTIONS if s.lower() not in secs]
    blank = [s for s in SECTIONS if s.lower() in secs and len(secs[s.lower()].split()) < 3]
    res.append(("R2 document", not missing and not blank,
                ("missing sections: %s" % "; ".join(missing)) if missing else
                ("empty sections (write 'None found' plus what was checked): %s" % "; ".join(blank)) if blank else "ten sections present"))

    sha = row.get("commit_sha", "")
    has_repo = re.search(r"^Repo:\s*%s\s*$" % re.escape(row["repo"]), doc, flags=re.M) is not None
    has_commit = bool(sha) and re.search(r"^Commit:\s*%s\s*$" % re.escape(sha), doc, flags=re.M) is not None
    res.append(("R3 repo and commit stated", has_repo and has_commit,
                "ok" if has_repo and has_commit else "document needs the lines 'Repo: %s' and 'Commit: %s'" % (row["repo"], sha)))

    scan = None
    if scan_file.exists():
        scan = json.loads(scan_file.read_text(encoding="utf-8"))
        not_covered = [m for m in scan.get("must_mention", []) if m not in doc and m.rstrip("/") + "`" not in doc]
        stale = scan.get("commit", "") != sha
        res.append(("R4 coverage", not not_covered and not stale,
                    "scan is from another commit; re-run scan_repo.py" if stale else
                    ("not mentioned in the document: %s" % ", ".join(not_covered[:20])) if not_covered
                    else "%d paths covered" % len(scan.get("must_mention", []))))
    else:
        res.append(("R4 coverage", False, "scans/%s.json not found; run scan_repo.py" % name))

    if facts is not None:
        problems = check_facts(facts, row)
        res.append(("R5 facts file", not problems, "; ".join(problems[:6]) or "ok"))
        if not problems and scan is not None:
            found = list(scan.get("ci_cd_files", [])) + [o["path"] for o in scan.get("orchestration_files", [])]
            accounted = set(p.get("definition", "") for p in facts["pipelines"]) | set(n.get("path", "") for n in facts["not_pipelines"])
            unaccounted = [f for f in found if f not in accounted]
            doc_gap = [p.get("name", "") for p in facts["pipelines"] if p.get("definition", "") not in doc]
            res.append(("R6 pipelines accounted for", not unaccounted and not doc_gap,
                        ("in scan but not in facts: %s" % ", ".join(unaccounted[:15])) if unaccounted else
                        ("pipelines in facts but their definition path is not in the document: %s" % ", ".join(doc_gap[:10])) if doc_gap
                        else "%d pipeline files accounted for" % len(found)))

    cites = prose_citations(doc)
    bad = []
    for path, start, end in cites:
        ok, detail = check_location(repo_dir, path, start, end)
        if not ok:
            bad.append(detail)
    if facts is not None and isinstance(facts, dict):
        for ev in facts_evidence(facts):
            parsed = split_json_citation(ev)
            if parsed is None:
                bad.append("facts evidence '%s' is not path:line" % ev)
                continue
            _, path, start, end = parsed
            ok, detail = check_location(repo_dir, path, start, end)
            if not ok:
                bad.append("facts: " + detail)
    file_count = (scan or {}).get("file_count", 0)
    minimum = 3 if file_count < 20 else 8
    enough = len(cites) >= minimum
    res.append(("R7 citations", not bad and enough,
                ("; ".join(bad[:8])) if bad else
                ("only %d citations, need at least %d written as (src: path:line)" % (len(cites), minimum)) if not enough
                else "%d citations resolve" % len(cites)))

    secrets = find_secrets(doc) + (find_secrets(facts_file.read_text(encoding="utf-8")) if facts_file.exists() else [])
    res.append(("R8 no secrets", not secrets, ", ".join(sorted(set(secrets))) or "ok"))

    if not check_file.exists():
        res.append(("R9 independent check", False, "checks/%s.json not found" % name))
    else:
        try:
            chk = json.loads(check_file.read_text(encoding="utf-8"))
            sampled = chk.get("sampled", [])
            need = min(10, len(set(cites)))
            cited = set("%s:%d" % (p, s) for p, s, _ in cites)
            unknown = [s.get("citation", "") for s in sampled if re.sub(r"-\d+$", "", str(s.get("citation", ""))) not in cited]
            failed = [s for s in sampled if s.get("result") != "PASS"]
            stale = check_file.stat().st_mtime < doc_file.stat().st_mtime
            ok = len(sampled) >= need and not unknown and len(failed) <= 1 and not stale
            res.append(("R9 independent check", ok,
                        "check is older than the document; run the checker again" if stale else
                        ("sampled citations not in the document: %s" % ", ".join(unknown[:5])) if unknown else
                        "%d sampled (need %d), %d failed (max 1)" % (len(sampled), need, len(failed))))
        except (ValueError, AttributeError, TypeError) as e:
            res.append(("R9 independent check", False, "checks file unreadable: %s" % e))
    return res


def print_results(title, res):
    print(title)
    for name, ok, detail in res:
        print("  %s  %-28s %s" % ("PASS" if ok else "FAIL", name, detail))


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--manifest", required=True)
    p.add_argument("--repo")
    p.add_argument("--status")
    p.add_argument("--inventory", action="store_true")
    p.add_argument("--expected-count", type=int)
    p.add_argument("--final", action="store_true")
    p.add_argument("--no-update", action="store_true")
    a = p.parse_args()

    manifest = Path(a.manifest).resolve()
    base = manifest.parent
    fields, rows = read_manifest(str(manifest))

    if a.inventory:
        names = [r["repo"] for r in rows]
        dups = [n for n, c in Counter(names).items() if c > 1]
        dirs = Counter(repo_dirname(n).lower() for n in names)
        clash = [n for n, c in dirs.items() if c > 1]
        no_url = [r["repo"] for r in rows if not r.get("clone_url", "").strip()]
        res = [("I1 no duplicate repos", not dups, ", ".join(dups[:10]) or "ok"),
               ("I2 folder names unique", not clash, ", ".join(clash[:10]) or "ok"),
               ("I3 clone_url filled", not no_url, ", ".join(no_url[:10]) or "ok"),
               ("I4 count matches source", a.expected_count is not None and len(rows) == a.expected_count,
                "manifest %d, source %s" % (len(rows), a.expected_count))]
        print_results("Inventory (%d repos)" % len(rows), res)
        ok = all(c[1] for c in res)
        print("INVENTORY: %s" % ("ACCEPTED" if ok else "NOT ACCEPTED"))
        sys.exit(0 if ok else 1)

    if a.final:
        targets = [r for r in rows if r.get("status") in ("done", "verified")]
    elif a.repo:
        targets = [r for r in rows if r["repo"] in [x.strip() for x in a.repo.split(",")]]
        if not targets:
            sys.exit("Not in manifest: %s" % a.repo)
    elif a.status:
        targets = [r for r in rows if r.get("status") == a.status]
    else:
        sys.exit("Give one of --repo, --status, --inventory, --final")

    results, passed, failed = {}, 0, 0
    for row in targets:
        res = check_repo(row, base)
        results[row["repo"]] = res
        ok = all(c[1] for c in res)
        print_results("%s  %s" % ("PASS" if ok else "FAIL", row["repo"]), res if not ok or len(targets) <= 10 else [])
        if ok:
            passed += 1
            if not a.no_update:
                mark_verified(row)
                row["doc_path"] = "docs/%s.md" % repo_dirname(row["repo"])
                row["facts_path"] = "facts/%s.json" % repo_dirname(row["repo"])
        else:
            failed += 1
            if not a.no_update:
                mark_failed(row, "; ".join("%s: %s" % (n, d) for n, k, d in res if not k))
    if not a.no_update:
        write_manifest(str(manifest), fields, rows)
    print("checked=%d passed=%d failed=%d" % (len(targets), passed, failed))

    if a.final:
        counts = Counter(r.get("status", "") for r in rows)
        open_rows = [r for r in rows if r.get("status") != "verified"]
        accepted = not open_rows and not failed
        L = ["# Verification report — repository documentation", "",
             "Generated: %s" % datetime.datetime.now().strftime("%Y-%m-%d %H:%M"), "",
             "RESULT: %s" % ("ACCEPTED" if accepted else "NOT ACCEPTED"), "",
             "## Counts", "", "- Repositories in manifest: %d" % len(rows)]
        L += ["- %s: %d" % (k or "(blank)", v) for k, v in sorted(counts.items())]
        L += ["", "## Repositories that are not verified (%d)" % len(open_rows), ""]
        L += ["- %s — %s — clone: %s — %s" % (r["repo"], r.get("status", ""), r.get("clone_status", ""), r.get("notes", "")) for r in open_rows] or ["None."]
        L += ["", "## Failing a check in this run", ""]
        fails = ["- %s: %s" % (n, "; ".join("%s (%s)" % (c, d) for c, k, d in res if not k))
                 for n, res in results.items() if any(not c[1] for c in res)]
        L += fails or ["None."]
        out = base / "outputs" / "verification-report.md"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text("\n".join(L) + "\n", encoding="utf-8")
        index = ["# Repository index", "", "| Repository | Kind | Purpose | Pipelines | Status |", "|---|---|---|---|---|"]
        for r in rows:
            name = repo_dirname(r["repo"])
            facts_file = base / "facts" / (name + ".json")
            facts = {}
            if facts_file.exists():
                try:
                    facts = json.loads(facts_file.read_text(encoding="utf-8"))
                except ValueError:
                    facts = {}
            link = "[%s](%s.md)" % (r["repo"], name) if (base / "docs" / (name + ".md")).exists() else r["repo"]
            index.append("| %s | %s | %s | %d | %s |" % (link, facts.get("kind", ""), str(facts.get("purpose", "")).replace("|", "/"),
                                                      len(facts.get("pipelines", []) or []), r.get("status", "")))
        (base / "docs").mkdir(exist_ok=True)
        (base / "docs" / "INDEX.md").write_text("\n".join(index) + "\n", encoding="utf-8")
        print("RESULT: %s  (report: %s)" % ("ACCEPTED" if accepted else "NOT ACCEPTED", out))
        sys.exit(0 if accepted else 1)
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
