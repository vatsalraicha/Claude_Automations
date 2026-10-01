#!/usr/bin/env python3
"""Business-knowledge entries: seed the manifest, verify entry files, render the catalog. Standard library only.

Used by 03-repo-business-knowledge (--kind repo) and 04-confluence-business-knowledge (--kind page).

  python tools/bk.py seed   --kind repo --loop 03-repo-business-knowledge
  python tools/bk.py verify --kind repo --loop 03-repo-business-knowledge --ids repoA,repoB
  python tools/bk.py verify --kind page --loop 04-confluence-business-knowledge --status done
  python tools/bk.py render --kind page --loop 04-confluence-business-knowledge
  python tools/bk.py verify --kind repo --loop 03-repo-business-knowledge --final
  add --no-update to verify without changing the manifest

One entries file per source: <loop>/business/<key>.json

  {
    "source": "<repo name or page id>",
    "verdict": "extracted | no_business_content | needs_human",
    "reason": "required unless verdict is extracted",
    "entries": [
      {
        "type": "rule | term | process | calculation | state | constraint | decision | role | integration | metric | policy",
        "name": "short name",
        "statement": "one to three plain sentences",
        "evidence": [{"where": "path/to/file.py:120", "quote": "verbatim text copied from the source"}],
        "basis": "stated | inferred",
        "confidence": "high | medium | low",
        "related": ["other entry names, systems, tables"],
        "jira_keys": ["ABC-123"]
      }
    ]
  }

Evidence `where`:  repo -> "path:line" inside the repository;  page -> the exact heading the text sits under, or "(top)".
Evidence `quote`:  3 to 40 words copied verbatim from the source. The checker searches for it.
"""
import argparse
import datetime
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

KIT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KIT / "tools"))
from manifest import read_manifest, write_manifest, mark_failed, mark_verified  # noqa: E402
from evidence import (quote_near_line, quote_found, split_json_citation, find_secrets, word_count,  # noqa: E402
                      normalise, repo_dirname)

TYPES = ["rule", "term", "process", "calculation", "state", "constraint", "decision", "role", "integration", "metric", "policy"]
BASIS = {"stated", "inferred"}
CONFIDENCE = {"high", "medium", "low"}
VERDICTS = {"extracted", "no_business_content", "needs_human"}
DEFAULT_SOURCE = {"repo": "02a-repo-docs", "page": "01-confluence-download"}
KEY = {"repo": "repo", "page": "page_id"}
COLUMNS = {
    "repo": ["repo", "status", "attempts", "verdict", "n_entries", "n_inferred", "verified_at", "notes"],
    "page": ["page_id", "title", "last_modified", "md_path", "status", "attempts", "verdict", "n_entries", "n_inferred", "verified_at", "notes"],
}


def file_key(kind, key):
    return repo_dirname(key) if kind == "repo" else key


def validate_entry(entry, where):
    """Shape checks shared by every loop that writes entries. Returns a list of problems."""
    problems = []
    if not isinstance(entry, dict):
        return ["%s is not an object" % where]
    if entry.get("type") not in TYPES:
        problems.append("%s: type must be one of %s" % (where, ", ".join(TYPES)))
    if not 1 <= word_count(entry.get("name")) <= 12:
        problems.append("%s: name must be 1 to 12 words" % where)
    if not 5 <= word_count(entry.get("statement")) <= 90:
        problems.append("%s: statement must be 5 to 90 words" % where)
    if entry.get("basis") not in BASIS:
        problems.append("%s: basis must be stated or inferred" % where)
    if entry.get("confidence") not in CONFIDENCE:
        problems.append("%s: confidence must be high, medium or low" % where)
    if not isinstance(entry.get("related", []), list) or not isinstance(entry.get("jira_keys", []), list):
        problems.append("%s: related and jira_keys must be lists" % where)
    ev = entry.get("evidence")
    if not isinstance(ev, list) or not ev:
        problems.append("%s: at least one evidence item is required" % where)
    else:
        for j, item in enumerate(ev):
            if not isinstance(item, dict) or not str(item.get("where", "")).strip():
                problems.append("%s.evidence[%d]: 'where' missing" % (where, j))
            elif not 3 <= word_count(item.get("quote")) <= 40:
                problems.append("%s.evidence[%d]: quote must be 3 to 40 words copied from the source" % (where, j))
    return problems


def md_headings(md):
    return [normalise(m.group(1)) for m in re.finditer(r"^\s*(?:> ?)*#{1,6}\s+(.*\S)\s*$", md, flags=re.M)]


def check_evidence(kind, key, entries, source_dir, source_row):
    bad = []
    if kind == "repo":
        repo_dir = source_dir / "repos" / repo_dirname(key)
        for i, e in enumerate(entries):
            for j, item in enumerate(e.get("evidence", [])):
                parsed = split_json_citation(item.get("where", ""))
                if parsed is None or parsed[0]:
                    bad.append("entries[%d] '%s': where must be path:line" % (i, e.get("name")))
                    continue
                ok, detail = quote_near_line(repo_dir, parsed[1], parsed[2], item.get("quote", ""))
                if not ok:
                    bad.append("entries[%d] '%s': %s" % (i, e.get("name"), detail))
    else:
        md_file = source_dir / source_row.get("md_path", "")
        if not source_row.get("md_path") or not md_file.exists():
            return ["markdown page not found for %s" % key]
        md = md_file.read_text(encoding="utf-8")
        heads = md_headings(md)
        for i, e in enumerate(entries):
            for j, item in enumerate(e.get("evidence", [])):
                where = str(item.get("where", "")).strip()
                if where != "(top)" and normalise(where.lstrip("# ")) not in heads:
                    bad.append("entries[%d] '%s': heading '%s' is not in the page" % (i, e.get("name"), where))
                if not quote_found(item.get("quote", ""), md):
                    bad.append("entries[%d] '%s': quote not found in the page: \"%s\"" % (i, e.get("name"), str(item.get("quote", ""))[:60]))
    return bad


def check_item(kind, row, loop_dir, source_dir, source_rows):
    """Returns (results, data) where results is a list of (check, ok, detail)."""
    key = row[KEY[kind]]
    fkey = file_key(kind, key)
    f = loop_dir / "business" / (fkey + ".json")
    if not f.exists():
        return [("B1 entries file", False, "business/%s.json not found" % fkey)], None
    try:
        data = json.loads(f.read_text(encoding="utf-8"))
    except ValueError as e:
        return [("B1 entries file", False, "not valid JSON: %s" % e)], None
    res = []
    problems = []
    if not isinstance(data, dict) or str(data.get("source")) != key:
        problems.append("'source' must be '%s'" % key)
    if not isinstance(data, dict) or data.get("verdict") not in VERDICTS:
        problems.append("verdict must be one of %s" % ", ".join(sorted(VERDICTS)))
    if not isinstance(data, dict) or not isinstance(data.get("entries"), list):
        problems.append("'entries' must be a list")
    res.append(("B1 entries file", not problems, "; ".join(problems) or "ok"))
    if problems:
        return res, None
    entries, verdict = data["entries"], data["verdict"]

    if verdict == "extracted":
        ok, detail = bool(entries), "ok" if entries else "verdict is extracted but there are no entries"
    else:
        ok = not entries and word_count(data.get("reason")) >= 8
        detail = "ok" if ok else "verdict %s needs no entries and a reason of at least 8 words saying what the source contains" % verdict
    res.append(("B2 verdict consistent", ok, detail))

    shape = []
    for i, e in enumerate(entries):
        shape += validate_entry(e, "entries[%d]" % i)
    res.append(("B3 entry fields", not shape, "; ".join(shape[:8]) or "%d entries" % len(entries)))

    names = Counter((e.get("type"), normalise(str(e.get("name", "")))) for e in entries if isinstance(e, dict))
    dups = ["%s/%s" % k for k, c in names.items() if c > 1]
    res.append(("B5 no duplicate entries", not dups, ", ".join(dups[:8]) or "ok"))

    if not shape:
        bad = check_evidence(kind, key, entries, source_dir, source_rows.get(key, {}))
        res.append(("B4 evidence found in source", not bad, "; ".join(bad[:8]) or "every quote found"))

    secrets = find_secrets(f.read_text(encoding="utf-8"))
    res.append(("B6 no secrets", not secrets, ", ".join(sorted(set(secrets))) or "ok"))

    chk_file = loop_dir / "checks" / (fkey + ".json")
    need_check = (kind == "repo" and verdict == "extracted") or verdict == "no_business_content"
    if need_check:
        if not chk_file.exists():
            res.append(("B7 independent check", False, "checks/%s.json not found" % fkey))
        else:
            try:
                chk = json.loads(chk_file.read_text(encoding="utf-8"))
                stale = chk_file.stat().st_mtime < f.stat().st_mtime
                if verdict == "no_business_content":
                    ok = chk.get("agrees") is True and word_count(chk.get("reason")) >= 5 and not stale
                    detail = "checker agrees" if ok else "needs {\"agrees\": true, \"reason\": ...} written after the entries file"
                else:
                    sampled = chk.get("sampled", [])
                    known = set(normalise(str(e.get("name", ""))) for e in entries)
                    unknown = [s.get("name", "") for s in sampled if normalise(str(s.get("name", ""))) not in known]
                    failed = [s for s in sampled if s.get("result") != "PASS"]
                    need = min(8, len(entries))
                    ok = len(sampled) >= need and not unknown and len(failed) <= 1 and not stale
                    detail = ("check is older than the entries file" if stale else
                              ("sampled names not in the entries file: %s" % ", ".join(unknown[:5])) if unknown else
                              "%d sampled (need %d), %d failed (max 1)" % (len(sampled), need, len(failed)))
                res.append(("B7 independent check", ok, detail))
            except (ValueError, AttributeError, TypeError) as e:
                res.append(("B7 independent check", False, "checks file unreadable: %s" % e))
    return res, data


def print_results(title, res):
    print(title)
    for name, ok, detail in res:
        print("  %s  %-28s %s" % ("PASS" if ok else "FAIL", name, detail))


# ----------------------------------------------------------------------------- commands

def paths(a):
    loop_dir = (KIT / a.loop).resolve()
    source_dir = (KIT / (a.source or DEFAULT_SOURCE[a.kind])).resolve()
    return loop_dir, source_dir


def cmd_seed(a):
    loop_dir, source_dir = paths(a)
    sfields, srows = read_manifest(str(source_dir / "manifest.csv"))
    key = KEY[a.kind]
    man = loop_dir / "manifest.csv"
    if man.exists():
        fields, rows = read_manifest(str(man))
    else:
        fields, rows = list(COLUMNS[a.kind]), []
    have = set(r[key] for r in rows)
    added, excluded = 0, []
    for s in srows:
        if s.get("status") != "verified":
            excluded.append({key: s[key], "reason": "source status is '%s'" % s.get("status", "")})
            continue
        if s[key] in have:
            continue
        row = {k: "" for k in fields}
        row[key] = s[key]
        for k in ("title", "last_modified", "md_path"):
            if k in fields:
                row[k] = s.get(k, "")
        row["status"], row["attempts"] = "pending", "0"
        rows.append(row)
        added += 1
    write_manifest(str(man), fields, rows)
    (loop_dir / "work").mkdir(exist_ok=True)
    (loop_dir / "work" / "excluded.json").write_text(json.dumps(excluded, indent=2), encoding="utf-8")
    print("added=%d total=%d excluded_because_source_not_verified=%d" % (added, len(rows), len(excluded)))


def load_all(kind, loop_dir, rows):
    out = []
    for r in rows:
        f = loop_dir / "business" / (file_key(kind, r[KEY[kind]]) + ".json")
        if r.get("status") == "verified" and f.exists():
            out.append((r, json.loads(f.read_text(encoding="utf-8"))))
    return out


def entry_block(e, source_label):
    lines = ["### %s" % e.get("name", ""), "",
             "- Type: %s" % e.get("type", ""),
             "- Statement: %s" % e.get("statement", ""),
             "- Source: %s" % source_label,
             "- Basis: %s, confidence %s" % (e.get("basis", ""), e.get("confidence", ""))]
    for item in e.get("evidence", []):
        lines.append('- Evidence: %s — "%s"' % (item.get("where", ""), " ".join(str(item.get("quote", "")).split())))
    if e.get("related"):
        lines.append("- Related: %s" % ", ".join(str(x) for x in e["related"]))
    if e.get("jira_keys"):
        lines.append("- Jira: %s" % ", ".join(str(x) for x in e["jira_keys"]))
    return "\n".join(lines) + "\n"


def cmd_render(a):
    loop_dir, source_dir = paths(a)
    kind, key = a.kind, KEY[a.kind]
    fields, rows = read_manifest(str(loop_dir / "manifest.csv"))
    items = load_all(kind, loop_dir, rows)
    catalog = loop_dir / "catalog"
    catalog.mkdir(exist_ok=True)

    def label(r):
        if kind == "page":
            return "page %s “%s” (last modified %s)" % (r[key], r.get("title", ""), r.get("last_modified", "") or "unknown")
        return "repo %s" % r[key]

    flat = []
    for r, data in items:
        fk = file_key(kind, r[key])
        body = ["# Business knowledge — %s" % label(r), "", "Verdict: %s" % data.get("verdict", "")]
        if data.get("reason"):
            body.append("Reason: %s" % data["reason"])
        body.append("")
        for e in data.get("entries", []):
            body.append(entry_block(e, label(r)))
            flat.append((r, e))
        (loop_dir / "business" / (fk + ".md")).write_text("\n".join(body) + "\n", encoding="utf-8")

    with open(catalog / "all-entries.jsonl", "w", encoding="utf-8") as f:
        for r, e in flat:
            f.write(json.dumps(dict(e, source=r[key], source_kind=kind, source_title=r.get("title", ""),
                                    source_last_modified=r.get("last_modified", "")), ensure_ascii=False) + "\n")

    def write_grouped(path, title, intro, selected):
        L = ["# %s" % title, "", intro, "", "Entries: %d" % len(selected), ""]
        by_type = defaultdict(list)
        for r, e in selected:
            by_type[e.get("type", "")].append((r, e))
        for t in TYPES:
            if by_type[t]:
                L += ["## %s (%d)" % (t.capitalize(), len(by_type[t])), ""]
                for r, e in sorted(by_type[t], key=lambda x: normalise(str(x[1].get("name", "")))):
                    L.append(entry_block(e, label(r)))
        path.write_text("\n".join(L) + "\n", encoding="utf-8")

    write_grouped(catalog / "rules-catalog.md", "Rules catalog", "Every extracted entry except glossary terms, grouped by type.",
                  [(r, e) for r, e in flat if e.get("type") != "term"])
    write_grouped(catalog / "glossary.md", "Glossary", "Business terms and their definitions.",
                  [(r, e) for r, e in flat if e.get("type") == "term"])
    write_grouped(catalog / "inferred-for-review.md", "Inferred entries — for review by someone who knows the domain",
                  "These were inferred from behaviour, not stated in the source. Confirm or correct each one.",
                  [(r, e) for r, e in flat if e.get("basis") == "inferred"])

    L = ["# Sources judged to contain no business knowledge", "",
         "Knowledge is most often lost here. Skim this list and re-open anything that looks wrong.", ""]
    for r, data in items:
        if data.get("verdict") == "no_business_content":
            L.append("- %s — %s" % (label(r), data.get("reason", "")))
    (catalog / "no-business-content.md").write_text("\n".join(L) + "\n", encoding="utf-8")

    groups = defaultdict(list)
    for r, e in flat:
        groups[normalise(str(e.get("name", "")))].append((r, e))
    L = ["# Name collisions", "",
         "The same name used in more than one source. Each group is either the same thing described twice or a "
         "real conflict. Decide each one in conflicts.md.", ""]
    n = 0
    for name in sorted(groups):
        srcs = set(r[key] for r, _ in groups[name])
        if len(srcs) > 1:
            n += 1
            L.append("## %s" % groups[name][0][1].get("name", name))
            L += ["- %s (%s): %s" % (label(r), e.get("type", ""), e.get("statement", "")) for r, e in groups[name]]
            L.append("")
    L.insert(4, "Groups: %d\n" % n)
    (catalog / "name-collisions.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print(json.dumps({"sources": len(items), "entries": len(flat), "collision_groups": n,
                      "inferred": len([1 for _, e in flat if e.get("basis") == "inferred"])}))


def cmd_verify(a):
    loop_dir, source_dir = paths(a)
    kind, key = a.kind, KEY[a.kind]
    man = loop_dir / "manifest.csv"
    fields, rows = read_manifest(str(man))
    _, srows = read_manifest(str(source_dir / "manifest.csv"))
    source_rows = {r[key]: r for r in srows}

    if a.final:
        targets = [r for r in rows if r.get("status") in ("done", "verified")]
    elif a.ids:
        wanted = [x.strip() for x in a.ids.split(",") if x.strip()]
        missing = [w for w in wanted if w not in set(r[key] for r in rows)]
        if missing:
            sys.exit("Not in manifest: %s" % ", ".join(missing))
        targets = [r for r in rows if r[key] in wanted]
    elif a.status:
        targets = [r for r in rows if r.get("status") == a.status]
    else:
        sys.exit("Give one of --ids, --status, --final")

    results, passed, failed = {}, 0, 0
    for row in targets:
        res, data = check_item(kind, row, loop_dir, source_dir, source_rows)
        results[row[key]] = res
        ok = all(c[1] for c in res)
        print_results("%s  %s" % ("PASS" if ok else "FAIL", row[key]), res if not ok or len(targets) <= 10 else [])
        if a.no_update:
            passed, failed = passed + (1 if ok else 0), failed + (0 if ok else 1)
            continue
        if ok:
            passed += 1
            row["verdict"] = data["verdict"]
            row["n_entries"] = str(len(data["entries"]))
            row["n_inferred"] = str(len([e for e in data["entries"] if e.get("basis") == "inferred"]))
            if data["verdict"] == "needs_human":
                row["status"] = "needs_human"
            else:
                mark_verified(row)
        else:
            failed += 1
            mark_failed(row, "; ".join("%s: %s" % (n, d) for n, k, d in res if not k))
    if not a.no_update:
        write_manifest(str(man), fields, rows)
    print("checked=%d passed=%d failed=%d" % (len(targets), passed, failed))

    if a.final:
        catalog = loop_dir / "catalog"
        needed = ["rules-catalog.md", "glossary.md", "inferred-for-review.md", "no-business-content.md",
                  "name-collisions.md", "conflicts.md", "all-entries.jsonl"]
        absent = [n for n in needed if not (catalog / n).exists()]
        open_rows = [r for r in rows if r.get("status") != "verified"]
        accepted = not open_rows and not failed and not absent
        counts = Counter(r.get("status", "") for r in rows)
        verdicts = Counter(r.get("verdict", "") for r in rows if r.get("status") == "verified")
        excluded = []
        if (loop_dir / "work" / "excluded.json").exists():
            excluded = json.loads((loop_dir / "work" / "excluded.json").read_text(encoding="utf-8"))
        L = ["# Verification report — business knowledge (%s)" % kind, "",
             "Generated: %s" % datetime.datetime.now().strftime("%Y-%m-%d %H:%M"), "",
             "RESULT: %s" % ("ACCEPTED" if accepted else "NOT ACCEPTED"), "",
             "ACCEPTED means every source was examined and every statement is backed by a quote found in the source. "
             "It does not mean every piece of knowledge was noticed: review inferred-for-review.md and no-business-content.md.", "",
             "## Counts", "", "- Sources in manifest: %d" % len(rows)]
        L += ["- status %s: %d" % (k or "(blank)", v) for k, v in sorted(counts.items())]
        L += ["- verdict %s: %d" % (k or "(blank)", v) for k, v in sorted(verdicts.items())]
        L += ["- entries: %d (inferred: %d)" % (sum(int(r.get("n_entries") or 0) for r in rows), sum(int(r.get("n_inferred") or 0) for r in rows))]
        L += ["", "## Catalog files missing", ""] + (["- %s" % n for n in absent] or ["None."])
        L += ["", "## Sources not verified (%d)" % len(open_rows), ""]
        L += ["- %s — %s — %s" % (r[key], r.get("status", ""), r.get("notes", "")) for r in open_rows] or ["None."]
        L += ["", "## Sources left out because the earlier loop did not verify them (%d)" % len(excluded), ""]
        L += ["- %s — %s" % (e[key], e["reason"]) for e in excluded] or ["None."]
        out = loop_dir / "outputs" / "verification-report.md"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text("\n".join(L) + "\n", encoding="utf-8")
        print("RESULT: %s  (report: %s)" % ("ACCEPTED" if accepted else "NOT ACCEPTED", out))
        sys.exit(0 if accepted else 1)
    sys.exit(1 if failed else 0)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("command", choices=["seed", "verify", "render"])
    p.add_argument("--kind", required=True, choices=["repo", "page"])
    p.add_argument("--loop", required=True, help="loop folder name, relative to the kit root")
    p.add_argument("--source", help="source loop folder, relative to the kit root (default depends on --kind)")
    p.add_argument("--ids")
    p.add_argument("--status")
    p.add_argument("--final", action="store_true")
    p.add_argument("--no-update", action="store_true")
    a = p.parse_args()
    {"seed": cmd_seed, "verify": cmd_verify, "render": cmd_render}[a.command](a)


if __name__ == "__main__":
    main()
