#!/usr/bin/env python3
"""Jira enrichment helper. Standard library only. Never talks to Jira itself: fetching is done through the connector.

  python jira_tools.py keys                 # find ticket keys in the downloaded pages and the cloned repos
  python jira_tools.py linked               # add parent/epic/linked keys of fetched tickets (one hop only)
  python jira_tools.py verify --ids ABC-1,ABC-2 | --status done | --final   [--no-update]
  python jira_tools.py render               # write enrichment/by-page.md, by-repo.md, tickets.md

Requires project-keys.txt in this folder: one Jira project key per line (ABC, PAY, ...). Only keys with these
prefixes are picked up, which keeps things like UTF-8 and SHA-256 out.

One file per ticket: tickets/<KEY>.json

  {
    "key": "ABC-123", "summary": "...", "type": "Story", "status": "Done", "resolution": "Fixed",
    "created": "2024-01-10", "updated": "2024-02-02", "parent": "ABC-100", "epic": "ABC-90",
    "links": [{"type": "blocks", "key": "ABC-130"}],
    "description": "copied verbatim from Jira",
    "acceptance_criteria": "copied verbatim, or empty",
    "comments": [{"date": "2024-01-20", "body": "copied verbatim; only comments that record a decision, requirement or reason"}],
    "why": "one paragraph: the business need or decision behind this ticket, in plain words",
    "entries": [ same shape as the business-knowledge entries; evidence.where is one of
                 summary | description | acceptance_criteria | comment ]
  }
"""
import argparse
import csv
import datetime
import json
import os
import re
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
KIT = HERE.parent
sys.path.insert(0, str(KIT / "tools"))
from manifest import read_manifest, write_manifest, mark_failed, mark_verified  # noqa: E402
from evidence import quote_found, find_secrets, word_count  # noqa: E402
from bk import validate_entry  # noqa: E402

COLUMNS = ["key", "depth", "n_references", "first_reference", "status", "attempts", "verified_at", "notes"]
SKIP_DIRS = {".git", "node_modules", "vendor", "dist", "build", "target", ".venv", "venv", "__pycache__", ".terraform"}
BINARY_EXT = {"png", "jpg", "jpeg", "gif", "ico", "pdf", "zip", "gz", "tar", "jar", "class", "so", "dll", "exe", "bin",
              "woff", "woff2", "ttf", "parquet", "pyc", "lock"}
WHERE = {"summary", "description", "acceptance_criteria", "comment"}
TERMINAL = {"verified", "not_found", "no_access"}
MANIFEST = HERE / "manifest.csv"


def load_manifest():
    if MANIFEST.exists():
        return read_manifest(str(MANIFEST))
    return list(COLUMNS), []


def project_keys():
    f = HERE / "project-keys.txt"
    if not f.exists():
        sys.exit("project-keys.txt not found. List the Jira project keys, one per line, before running this.")
    keys = [l.strip().upper() for l in f.read_text(encoding="utf-8").split("\n") if l.strip() and not l.startswith("#")]
    if not keys:
        sys.exit("project-keys.txt is empty.")
    return keys


def git(args, cwd):
    try:
        p = subprocess.run(["git"] + args, cwd=str(cwd), capture_output=True, text=True, errors="ignore")
    except OSError:
        return ""
    return p.stdout if p.returncode == 0 else ""


def cmd_keys(a):
    keys = project_keys()
    rx = re.compile(r"(?<![A-Za-z0-9])((?:%s)-[1-9][0-9]{0,6})(?![A-Za-z0-9])" % "|".join(re.escape(k) for k in sorted(keys, key=len, reverse=True)))
    refs = []  # (key, source_kind, source, location)
    pages = KIT / a.pages / "pages"
    if pages.is_dir():
        for f in sorted(pages.glob("*.md")):
            if f.name == "INDEX.md":
                continue
            page_id = f.name.split("-")[0]
            for n, line in enumerate(f.read_text(encoding="utf-8", errors="ignore").split("\n"), 1):
                for m in rx.finditer(line):
                    refs.append((m.group(1), "page", page_id, "line %d" % n))
    repos = KIT / a.repos / "repos"
    if repos.is_dir():
        for repo_dir in sorted(d for d in repos.iterdir() if d.is_dir()):
            repo = repo_dir.name
            for root, dirs, names in os.walk(repo_dir):
                dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS)
                for name in sorted(names):
                    path = Path(root) / name
                    if path.suffix.lower().lstrip(".") in BINARY_EXT:
                        continue
                    try:
                        if path.stat().st_size > 1000000:
                            continue
                        data = path.read_bytes()
                    except OSError:
                        continue
                    if b"\x00" in data[:4096]:
                        continue
                    rel = path.relative_to(repo_dir).as_posix()
                    for n, line in enumerate(data.decode("utf-8", errors="ignore").split("\n"), 1):
                        for m in rx.finditer(line):
                            refs.append((m.group(1), "repo", repo, "%s:%d" % (rel, n)))
            log = git(["log", "--all", "--format=%h%x1f%s%x1f%b%x1e"], repo_dir)
            for record in log.split("\x1e"):
                parts = record.strip().split("\x1f")
                if len(parts) >= 2:
                    for m in rx.finditer(" ".join(parts[1:])):
                        refs.append((m.group(1), "repo", repo, "commit %s" % parts[0]))
            for branch in git(["branch", "-r", "--format=%(refname:short)"], repo_dir).split("\n"):
                for m in rx.finditer(branch.upper()):
                    refs.append((m.group(1), "repo", repo, "branch %s" % branch.strip()))
    with open(HERE / "references.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["key", "source_kind", "source", "location"])
        w.writerows(sorted(set(refs)))
    fields, rows = load_manifest()
    known = {r["key"]: r for r in rows}
    counts = Counter(r[0] for r in set(refs))
    first = {}
    for key, kind, source, location in sorted(set(refs)):
        first.setdefault(key, "%s %s (%s)" % (kind, source, location))
    added = 0
    for key in sorted(counts, key=lambda k: (k.split("-")[0], int(k.split("-")[1]))):
        if key in known:
            known[key]["n_references"] = str(counts[key])
            continue
        row = {k: "" for k in fields}
        row.update(key=key, depth="0", n_references=str(counts[key]), first_reference=first[key], status="pending", attempts="0")
        rows.append(row)
        added += 1
    write_manifest(str(MANIFEST), fields, rows)
    print(json.dumps({"references": len(set(refs)), "distinct_keys": len(counts), "added_to_manifest": added,
                      "pages_scanned": pages.is_dir(), "repos_scanned": repos.is_dir()}))


def linked_keys(ticket):
    out = []
    for k in (ticket.get("parent"), ticket.get("epic")):
        if k:
            out.append(str(k).strip().upper())
    for link in ticket.get("links") or []:
        if isinstance(link, dict) and link.get("key"):
            out.append(str(link["key"]).strip().upper())
    return [k for k in out if re.match(r"^[A-Z][A-Z0-9_]*-\d+$", k)]


def cmd_linked(a):
    fields, rows = load_manifest()
    known = {r["key"]: r for r in rows}
    added = 0
    for r in list(rows):
        f = HERE / "tickets" / (r["key"] + ".json")
        if r.get("depth") != "0" or not f.exists():
            continue
        try:
            ticket = json.loads(f.read_text(encoding="utf-8"))
        except ValueError:
            continue
        for k in linked_keys(ticket):
            if k not in known:
                row = {c: "" for c in fields}
                row.update(key=k, depth="1", n_references="0", first_reference="linked from %s" % r["key"], status="pending", attempts="0")
                rows.append(row)
                known[k] = row
                added += 1
    write_manifest(str(MANIFEST), fields, rows)
    print("added %d linked keys at depth 1 (their own links are not followed)" % added)


def ticket_text(t):
    parts = [t.get("summary", ""), t.get("description", ""), t.get("acceptance_criteria", "")]
    parts += [c.get("body", "") for c in t.get("comments") or [] if isinstance(c, dict)]
    return "\n".join(str(p or "") for p in parts)


def check_ticket(row, known):
    key = row["key"]
    f = HERE / "tickets" / (key + ".json")
    if not f.exists():
        return [("J1 ticket file", False, "tickets/%s.json not found" % key)]
    try:
        t = json.loads(f.read_text(encoding="utf-8"))
    except ValueError as e:
        return [("J1 ticket file", False, "not valid JSON: %s" % e)]
    res, problems = [], []
    if not isinstance(t, dict) or t.get("key") != key:
        problems.append("'key' must be '%s'" % key)
        t = t if isinstance(t, dict) else {}
    for name in ("summary", "type", "status"):
        if not str(t.get(name, "")).strip():
            problems.append("'%s' missing" % name)
    for name in ("description", "acceptance_criteria", "why"):
        if not isinstance(t.get(name), str):
            problems.append("'%s' must be a string (may be empty except why)" % name)
    for name in ("links", "comments", "entries"):
        if not isinstance(t.get(name), list):
            problems.append("'%s' must be a list" % name)
    res.append(("J1 ticket file", not problems, "; ".join(problems[:6]) or "ok"))
    if problems:
        return res

    has_text = word_count(t["description"]) + word_count(t["acceptance_criteria"]) + sum(word_count(c.get("body")) for c in t["comments"] if isinstance(c, dict)) > 0
    need = 15 if has_text else 5
    res.append(("J2 why explained", word_count(t["why"]) >= need,
                "%d words (need %d%s)" % (word_count(t["why"]), need, "" if has_text else "; ticket has no description, say so")))

    shape = []
    for i, e in enumerate(t["entries"]):
        shape += validate_entry(e, "entries[%d]" % i)
        for j, item in enumerate(e.get("evidence", []) if isinstance(e, dict) else []):
            if isinstance(item, dict) and item.get("where") not in WHERE:
                shape.append("entries[%d].evidence[%d]: where must be one of %s" % (i, j, ", ".join(sorted(WHERE))))
    res.append(("J3 entry fields", not shape, "; ".join(shape[:6]) or "%d entries" % len(t["entries"])))

    if not shape:
        text = ticket_text(t)
        bad = ["entries[%d] '%s': quote not found in the ticket text" % (i, e.get("name"))
               for i, e in enumerate(t["entries"]) for item in e.get("evidence", []) if not quote_found(item.get("quote", ""), text)]
        res.append(("J4 quotes found in ticket", not bad, "; ".join(bad[:6]) or "ok"))

    if row.get("depth") == "0":
        absent = [k for k in linked_keys(t) if k not in known]
        res.append(("J5 linked tickets queued", not absent,
                    ("run 'jira_tools.py linked'; not in manifest: %s" % ", ".join(absent[:10])) if absent else "ok"))

    secrets = find_secrets(f.read_text(encoding="utf-8"))
    res.append(("J6 no secrets", not secrets, ", ".join(sorted(set(secrets))) or "ok"))
    return res


def cmd_verify(a):
    fields, rows = load_manifest()
    known = {r["key"]: r for r in rows}
    if a.final:
        targets = [r for r in rows if r.get("status") in ("done", "verified")]
    elif a.ids:
        wanted = [x.strip().upper() for x in a.ids.split(",") if x.strip()]
        missing = [w for w in wanted if w not in known]
        if missing:
            sys.exit("Not in manifest: %s" % ", ".join(missing))
        targets = [known[w] for w in wanted]
    elif a.status:
        targets = [r for r in rows if r.get("status") == a.status]
    else:
        sys.exit("Give one of --ids, --status, --final")
    passed = failed = 0
    results = {}
    for row in targets:
        res = check_ticket(row, known)
        results[row["key"]] = res
        ok = all(c[1] for c in res)
        if not ok or len(targets) <= 10:
            print("%s  %s" % ("PASS" if ok else "FAIL", row["key"]))
            for name, k, detail in res:
                print("  %s  %-26s %s" % ("PASS" if k else "FAIL", name, detail))
        if ok:
            passed += 1
            if not a.no_update:
                mark_verified(row)
        else:
            failed += 1
            if not a.no_update:
                mark_failed(row, "; ".join("%s: %s" % (n, d) for n, k, d in res if not k))
    if not a.no_update:
        write_manifest(str(MANIFEST), fields, rows)
    print("checked=%d passed=%d failed=%d" % (len(targets), passed, failed))
    if a.final:
        needed = ["by-page.md", "by-repo.md", "tickets.md"]
        absent = [n for n in needed if not (HERE / "enrichment" / n).exists()]
        open_rows = [r for r in rows if r.get("status") not in TERMINAL]
        no_note = [r["key"] for r in rows if r.get("status") in ("not_found", "no_access") and not r.get("notes", "").strip()]
        accepted = not open_rows and not failed and not absent and not no_note
        counts = Counter(r.get("status", "") for r in rows)
        L = ["# Verification report — Jira enrichment", "",
             "Generated: %s" % datetime.datetime.now().strftime("%Y-%m-%d %H:%M"), "",
             "RESULT: %s" % ("ACCEPTED" if accepted else "NOT ACCEPTED"), "",
             "## Counts", "", "- Ticket keys in manifest: %d (referenced directly: %d, linked one hop: %d)" % (
                 len(rows), len([r for r in rows if r.get("depth") == "0"]), len([r for r in rows if r.get("depth") == "1"]))]
        L += ["- %s: %d" % (k or "(blank)", v) for k, v in sorted(counts.items())]
        L += ["", "## Enrichment files missing", ""] + (["- %s" % n for n in absent] or ["None."])
        L += ["", "## Tickets not finished (%d)" % len(open_rows), ""]
        L += ["- %s — %s — %s" % (r["key"], r.get("status", ""), r.get("notes", "")) for r in open_rows] or ["None."]
        L += ["", "## Tickets that could not be read", ""]
        L += ["- %s — %s — %s" % (r["key"], r["status"], r.get("notes", "") or "NO NOTE GIVEN") for r in rows if r.get("status") in ("not_found", "no_access")] or ["None."]
        out = HERE / "outputs" / "verification-report.md"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text("\n".join(L) + "\n", encoding="utf-8")
        print("RESULT: %s  (report: %s)" % ("ACCEPTED" if accepted else "NOT ACCEPTED", out))
        sys.exit(0 if accepted else 1)
    sys.exit(1 if failed else 0)


def cmd_render(a):
    fields, rows = load_manifest()
    tickets = {}
    for r in rows:
        f = HERE / "tickets" / (r["key"] + ".json")
        if r.get("status") == "verified" and f.exists():
            tickets[r["key"]] = json.loads(f.read_text(encoding="utf-8"))
    status = {r["key"]: r.get("status", "") for r in rows}
    refs = defaultdict(lambda: defaultdict(list))  # kind -> source -> [(key, location)]
    ref_file = HERE / "references.csv"
    if ref_file.exists():
        with open(ref_file, newline="", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                refs[r["source_kind"]][r["source"]].append((r["key"], r["location"]))
    titles = {}
    pm = KIT / a.pages / "manifest.csv"
    if pm.exists():
        titles = {r["page_id"]: r.get("title", "") for r in read_manifest(str(pm))[1]}
    out_dir = HERE / "enrichment"
    out_dir.mkdir(exist_ok=True)

    def ticket_lines(key, indent=""):
        t = tickets.get(key)
        if t is None:
            return ["%s- **%s** — not available (%s)" % (indent, key, status.get(key, "not in manifest"))]
        lines = ["%s- **%s** — %s (%s, %s)" % (indent, key, t.get("summary", ""), t.get("type", ""), t.get("status", "")),
                 "%s  - Why: %s" % (indent, " ".join(str(t.get("why", "")).split()))]
        related = linked_keys(t)
        if related:
            lines.append("%s  - Linked: %s" % (indent, ", ".join(related)))
        return lines

    for kind, name, heading in (("page", "by-page.md", "Jira context for each Confluence page"),
                                ("repo", "by-repo.md", "Jira context for each repository")):
        L = ["# %s" % heading, ""]
        for source in sorted(refs[kind]):
            label = "%s — %s" % (source, titles.get(source, "")) if kind == "page" else source
            L += ["## %s" % label, ""]
            keys = sorted(set(k for k, _ in refs[kind][source]))
            for key in keys:
                places = [loc for k, loc in refs[kind][source] if k == key]
                L += ticket_lines(key)
                L.append("  - Referenced at: %s%s" % ("; ".join(places[:5]), " …" if len(places) > 5 else ""))
            L.append("")
        (out_dir / name).write_text("\n".join(L) + "\n", encoding="utf-8")
    L = ["# All tickets (%d)" % len(tickets), ""]
    for key in sorted(tickets, key=lambda k: (k.split("-")[0], int(k.split("-")[1]))):
        L += ticket_lines(key) + [""]
    (out_dir / "tickets.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    with open(out_dir / "all-entries.jsonl", "w", encoding="utf-8") as f:
        n = 0
        for key, t in tickets.items():
            for e in t.get("entries", []):
                f.write(json.dumps(dict(e, source=key, source_kind="jira", source_title=t.get("summary", "")), ensure_ascii=False) + "\n")
                n += 1
    print(json.dumps({"tickets": len(tickets), "pages_with_tickets": len(refs["page"]), "repos_with_tickets": len(refs["repo"]), "entries": n}))


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("command", choices=["keys", "linked", "verify", "render"])
    p.add_argument("--pages", default="01-confluence-download", help="Confluence download folder, relative to the kit root")
    p.add_argument("--repos", default="02a-repo-docs", help="repository documentation folder, relative to the kit root")
    p.add_argument("--ids")
    p.add_argument("--status")
    p.add_argument("--final", action="store_true")
    p.add_argument("--no-update", action="store_true")
    a = p.parse_args()
    {"keys": cmd_keys, "linked": cmd_linked, "verify": cmd_verify, "render": cmd_render}[a.command](a)


if __name__ == "__main__":
    main()
