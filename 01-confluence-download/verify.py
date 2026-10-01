#!/usr/bin/env python3
"""Checker for the Confluence download loop. Standard library only.

This script is the only thing allowed to set status=verified. It is deliberately independent of
convert.py: it re-reads the raw file with its own simple logic and compares it with the Markdown.

Usage:
  python verify.py --manifest manifest.csv --inventory --expected-count 412 [--roots 111,222]
  python verify.py --manifest manifest.csv --ids 123,456        # check a batch, update statuses
  python verify.py --manifest manifest.csv --status done        # check every row with this status
  python verify.py --manifest manifest.csv --spot-pick 20       # print random verified page ids
  python verify.py --manifest manifest.csv --spot-compare       # compare spotcheck/<id>.* with raw/<id>.*
  python verify.py --manifest manifest.csv --final              # re-check everything, write the report
  add --no-update to any of these to check without changing the manifest

Per-page checks:
  D1 raw file exists and is not empty (unless empty_body=yes)
  D2 raw file is not truncated (opening and closing tags balance)
  D3 attachments on disk match attachment_count (and sizes, if _attachments.json is present)
  C4 markdown file exists, has front matter, page_id and version match the manifest
  C5 no other page uses the same markdown path
  C6 markdown has at least as many headings, tables, code blocks, images and links as the raw page
  C7 the words of the raw page are present in the markdown (coverage >= --min-coverage)
  C8 every local image/attachment reference points to a file on disk
  C9 every link to another page points to a page in the manifest (with --final: to a file on disk)
  C10 every macro that has no stored content appears as a visible placeholder
  C11 no leftover Confluence markup in the markdown
"""
import argparse
import datetime
import html
import json
import random
import re
import sys
import unicodedata
from collections import Counter
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
from manifest import read_manifest, write_manifest, mark_failed, mark_verified  # noqa: E402

BALANCED = ["table", "ac:structured-macro", "ac:rich-text-body", "ac:plain-text-body", "ac:layout",
            "ac:layout-section", "ac:layout-cell", "ac:link", "ac:image", "ac:task-list", "ul", "ol"]
INVISIBLE_TAGS = ["head", "ac:placeholder", "ac:task-id", "ac:task-uuid", "ac:task-status", "script", "style", "title"]
VISIBLE_PARAMS = {"title"}
# Macros without a body that the converter renders as text instead of a placeholder.
RENDERED_INLINE = {"status", "anchor"}


def slugify(title, maxlen=60):
    s = unicodedata.normalize("NFKD", title or "").encode("ascii", "ignore").decode("ascii")
    s = re.sub(r"[^A-Za-z0-9]+", "-", s).strip("-").lower()
    return s[:maxlen].strip("-") or "page"


def expected_md_name(row):
    return "%s-%s.md" % (row["page_id"], slugify(row.get("title", "")))


def tokens(text):
    return Counter(t.lower() for t in re.findall(r"\w+", text))


def expand_cdata(raw):
    return re.sub(r"<!\[CDATA\[(.*?)\]\]>", lambda m: html.escape(m.group(1), quote=False), raw, flags=re.S)


# ----------------------------------------------------------------------------- raw side

def raw_visible_text(raw):
    text = expand_cdata(raw)
    for tag in INVISIBLE_TAGS:
        text = re.sub(r"<%s\b[^>]*>.*?</%s>" % (tag, tag), " ", text, flags=re.S | re.I)

    def keep_param(m):
        name = re.search(r'ac:name="([^"]*)"', m.group(1))
        return (" " + m.group(2) + " ") if name and name.group(1) in VISIBLE_PARAMS else " "

    text = re.sub(r"<ac:parameter\b([^>]*)>(.*?)</ac:parameter>", keep_param, text, flags=re.S)
    text = re.sub(r"<[^>]+>", " ", text)
    return html.unescape(text)


def raw_counts(raw):
    text = expand_cdata(raw)
    headings = 0
    for m in re.finditer(r"<h([1-6])\b[^>]*>(.*?)</h\1>", text, flags=re.S | re.I):
        inner = m.group(2)
        if re.sub(r"<[^>]+>", "", inner).strip() or re.search(r"<(ac:image|img)\b", inner):
            headings += 1
    images = len(re.findall(r"<ac:image\b", text))
    images += len([t for t in re.findall(r"<img\b[^>]*>", text, flags=re.I) if "emoticon" not in t])
    links = len(re.findall(r"<a\b[^>]*\bhref=", text, flags=re.I))
    for m in re.finditer(r"<ac:link(?![\w:-])[^>]*?(/>|>.*?</ac:link>)", text, flags=re.S):
        if "<ri:user" not in m.group(0):
            links += 1
    return {
        "headings": headings,
        "tables": len(re.findall(r"<table\b", text, flags=re.I)),
        "code_blocks": len(re.findall(r"<ac:plain-text-body\b", text)) + len(re.findall(r"<pre\b", text, flags=re.I)),
        "images": images,
        "links": links,
    }


def tag_balance(raw):
    text = expand_cdata(raw)
    problems = []
    for tag in BALANCED:
        opens = len(re.findall(r"<%s(?![\w:-])(?:[^>]*[^/>])?>" % re.escape(tag), text, flags=re.I))
        closes = len(re.findall(r"</%s\s*>" % re.escape(tag), text, flags=re.I))
        if opens != closes:
            problems.append("%s: %d opened, %d closed" % (tag, opens, closes))
    return problems


class MacroScan(HTMLParser):
    """Counts macros that have no body: these produce nothing in the stored page."""

    def __init__(self):
        HTMLParser.__init__(self, convert_charrefs=True)
        self.stack = []
        self.bodyless = Counter()
        self.param = None

    def _close(self, entry):
        name = entry["name"]
        if entry["body"] or name in RENDERED_INLINE:
            return
        if name == "jira" and entry["params"].get("key", "").strip():
            return
        self.bodyless[name or "unnamed"] += 1

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag in ("ac:structured-macro", "ac:macro"):
            self.stack.append({"name": (a.get("ac:name") or "").lower(), "body": False, "params": {}})
        elif tag in ("ac:rich-text-body", "ac:plain-text-body") and self.stack:
            self.stack[-1]["body"] = True
        elif tag == "ac:parameter" and self.stack:
            self.param = a.get("ac:name", "")
            self.stack[-1]["params"].setdefault(self.param, "")

    def handle_startendtag(self, tag, attrs):
        if tag in ("ac:structured-macro", "ac:macro"):
            self._close({"name": (dict(attrs).get("ac:name") or "").lower(), "body": False, "params": {}})

    def handle_endtag(self, tag):
        if tag in ("ac:structured-macro", "ac:macro") and self.stack:
            self._close(self.stack.pop())
        elif tag == "ac:parameter":
            self.param = None

    def handle_data(self, data):
        if self.param is not None and self.stack:
            self.stack[-1]["params"][self.param] += data


def bodyless_macros(raw):
    scan = MacroScan()
    scan.feed(expand_cdata(raw))
    scan.close()
    return scan.bodyless


# ----------------------------------------------------------------------------- markdown side

def split_front_matter(md):
    m = re.match(r"---\n(.*?)\n---\n", md, flags=re.S)
    if not m:
        return None, md
    meta = {}
    for line in m.group(1).split("\n"):
        if ":" in line:
            k, v = line.split(":", 1)
            try:
                meta[k.strip()] = json.loads(v.strip())
            except ValueError:
                meta[k.strip()] = v.strip()
    return meta, md[m.end():]


def strip_title(body):
    lines = body.lstrip("\n").split("\n")
    if lines and lines[0].startswith("# "):
        return "\n".join(lines[1:])
    return body


def outside_fences(body):
    """Returns (text outside fenced code blocks, number of fenced code blocks)."""
    out, blocks, fence_run = [], 0, None
    for line in body.split("\n"):
        m = re.match(r"\s*(?:> ?)*(`{3,}|~{3,})", line)
        if fence_run is None:
            if m:
                fence_run = m.group(1)
                blocks += 1
            else:
                out.append(line)
        elif m and m.group(1)[0] == fence_run[0] and len(m.group(1)) >= len(fence_run) \
                and not line.strip().lstrip("> ").strip(fence_run[0]):
            fence_run = None
    return "\n".join(out), blocks


def md_counts(body):
    text, blocks = outside_fences(strip_title(body))
    images = len(re.findall(r"!\[", text))
    return {
        "headings": len(re.findall(r"^\s*(?:> ?)*#{1,6} \S", text, flags=re.M)),
        "tables": len(re.findall(r"^\s*(?:> ?)*\|(?: ?:?-{3,}:? ?\|)+\s*$", text, flags=re.M)) + len(re.findall(r"<table\b", text)),
        "code_blocks": blocks,
        "images": images,
        "links": len(re.findall(r"\]\(", text)) - images,
    }


def md_links(body):
    text, _ = outside_fences(body)
    return re.findall(r"(!?)\[(?:[^\]\\]|\\.)*\]\(([^)\s]*)\)", text)


# ----------------------------------------------------------------------------- checks

def check_row(row, rows, base, min_coverage, final):
    """Returns a list of (check, ok, detail)."""
    res = []
    pid = row["page_id"]
    empty_ok = (row.get("empty_body", "") or "").lower() == "yes"

    raw_rel = row.get("raw_path", "")
    raw_file = base / raw_rel if raw_rel else None
    raw = None
    if not raw_file or not raw_file.exists():
        res.append(("D1 raw file", False, "missing: %s" % (raw_rel or "(raw_path empty)")))
    else:
        raw = raw_file.read_text(encoding="utf-8", errors="replace")
        if not raw.strip() and not empty_ok:
            res.append(("D1 raw file", False, "empty, and empty_body is not 'yes'"))
        else:
            res.append(("D1 raw file", True, "%d chars" % len(raw)))
    is_html = bool(raw_file) and raw_file.suffix.lower() != ".md"

    if raw is not None and is_html:
        problems = tag_balance(raw)
        res.append(("D2 raw not truncated", not problems, "; ".join(problems) or "tags balance"))

    count_field = (row.get("attachment_count", "") or "").strip()
    att_dir = base / "attachments" / pid
    on_disk = [f for f in att_dir.iterdir() if f.is_file() and f.name != "_attachments.json"] if att_dir.is_dir() else []
    if count_field.isdigit():
        ok = len(on_disk) == int(count_field)
        detail = "%d on disk, %s expected" % (len(on_disk), count_field)
        listing = att_dir / "_attachments.json"
        if ok and listing.exists():
            try:
                wrong = []
                for item in json.loads(listing.read_text(encoding="utf-8")):
                    f = att_dir / item["filename"]
                    if not f.exists() or (str(item.get("size", "")).isdigit() and f.stat().st_size != int(item["size"])):
                        wrong.append(item["filename"])
                ok = not wrong
                detail += "; size/name mismatch: %s" % ", ".join(wrong) if wrong else "; sizes match"
            except (ValueError, KeyError, TypeError) as e:
                ok, detail = False, "_attachments.json unreadable: %s" % e
        res.append(("D3 attachments", ok, detail))
    else:
        res.append(("D3 attachments", False, "attachment_count is not filled in the manifest"))

    md_rel = row.get("md_path", "")
    md_file = base / md_rel if md_rel else None
    if not md_file or not md_file.exists() or not md_file.read_text(encoding="utf-8").strip():
        res.append(("C4 markdown file", False, "missing or empty: %s" % (md_rel or "(md_path empty)")))
        return res
    md = md_file.read_text(encoding="utf-8")
    meta, body = split_front_matter(md)
    if meta is None:
        res.append(("C4 markdown file", False, "no front matter"))
        return res
    mismatch = [k for k in ("page_id", "version") if str(meta.get(k, "")) != str(row.get(k, ""))]
    name_ok = md_file.suffix == ".md" and md_file.name == expected_md_name(row)
    res.append(("C4 markdown file", not mismatch and name_ok,
                ("front matter differs from manifest: %s" % ", ".join(mismatch)) if mismatch
                else ("file name should be %s" % expected_md_name(row)) if not name_ok else "ok"))

    dup = [r["page_id"] for r in rows if r.get("md_path") == md_rel and r["page_id"] != pid]
    res.append(("C5 unique path", not dup, ("also used by %s" % ", ".join(dup)) if dup else "ok"))

    if raw is not None and is_html:
        rc, mc = raw_counts(raw), md_counts(body)
        lost = ["%s: raw %d, markdown %d" % (k, rc[k], mc[k]) for k in rc if mc[k] < rc[k]]
        res.append(("C6 structure kept", not lost, "; ".join(lost) or json.dumps(rc)))

    if raw is not None:
        want = tokens(raw_visible_text(raw)) if is_html else tokens(raw)
        have = tokens(body)
        total = sum(want.values())
        missing = {t: n - have.get(t, 0) for t, n in want.items() if have.get(t, 0) < n}
        coverage = 1.0 if total == 0 else 1.0 - (sum(missing.values()) / float(total))
        sample = ", ".join(sorted(missing, key=lambda t: -missing[t])[:12])
        res.append(("C7 text kept", coverage >= min_coverage,
                    "coverage %.4f of %d words%s" % (coverage, total, ("; missing: " + sample) if missing else "")))

    by_name = {expected_md_name(r): r for r in rows}
    broken_files, broken_pages, outside = [], [], 0
    for bang, target in md_links(body):
        target = target.split("#")[0]
        if not target:
            continue
        if target.startswith("confluence://"):
            outside += 1
        elif target.startswith("../attachments/"):
            if not (md_file.parent / unquote(target)).exists():
                broken_files.append(unquote(target))
        elif re.match(r"[a-z][a-z0-9+.-]*:", target, flags=re.I) or target.startswith("//"):
            continue
        elif target.endswith(".md"):
            if target not in by_name:
                broken_pages.append(target + " (not a page in the manifest)")
            elif final and not (md_file.parent / target).exists():
                broken_pages.append(target + " (file not on disk)")
    res.append(("C8 local files resolve", not broken_files, "; ".join(broken_files[:8]) or "ok"))
    res.append(("C9 page links resolve", not broken_pages,
                "; ".join(broken_pages[:8]) or "ok (%d links point outside the download)" % outside))

    text_outside, _ = outside_fences(body)
    if raw is not None and is_html:
        need = bodyless_macros(raw)
        missing_ph = ["%s (raw %d, markdown %d)" % (n, c, len(re.findall(r"\[Confluence macro: %s\b" % re.escape(n), text_outside)))
                      for n, c in need.items()
                      if len(re.findall(r"\[Confluence macro: %s\b" % re.escape(n), text_outside)) < c]
        res.append(("C10 macros accounted for", not missing_ph, "; ".join(missing_ph) or "ok"))

    leftover = re.findall(r"</?(?:ac|ri):[a-z-]+", text_outside)
    res.append(("C11 no leftover markup", not leftover, ", ".join(sorted(set(leftover))[:8]) or "ok"))
    return res


def check_inventory(rows, expected, roots):
    res = []
    ids = [r["page_id"] for r in rows]
    dups = [i for i, n in Counter(ids).items() if n > 1]
    res.append(("I1 no duplicate page ids", not dups, ", ".join(dups[:10]) or "ok"))
    blank = [r["page_id"] or "(blank id)" for r in rows if not r["page_id"].strip() or not r.get("title", "").strip()]
    res.append(("I2 id and title filled", not blank, ", ".join(blank[:10]) or "ok"))
    idset = set(ids)
    orphans = [r["page_id"] for r in rows if r.get("parent_id", "") not in idset]
    if roots is None:
        res.append(("I3 page tree closed", bool(rows), "%d rows have a parent outside the manifest: %s. "
                    "Pass --roots with the ids that are expected to be top-level." % (len(orphans), ", ".join(orphans[:10]))))
    else:
        unexpected = [i for i in orphans if i not in roots]
        res.append(("I3 page tree closed", not unexpected,
                    ("parent missing for: %s" % ", ".join(unexpected[:15])) if unexpected else "ok"))
    if expected is None:
        res.append(("I4 count matches source", False, "no --expected-count given"))
    else:
        res.append(("I4 count matches source", len(rows) == expected, "manifest %d, source %d" % (len(rows), expected)))
    names = Counter(expected_md_name(r) for r in rows)
    clash = [n for n, c in names.items() if c > 1]
    res.append(("I5 file names unique", not clash, ", ".join(clash[:10]) or "ok"))
    return res


def print_results(title, res):
    print(title)
    for name, ok, detail in res:
        print("  %s  %-28s %s" % ("PASS" if ok else "FAIL", name, detail))


# ----------------------------------------------------------------------------- report

def final_report(rows, results, base, inventory):
    counts = Counter(r.get("status", "") for r in rows)
    not_verified = [r for r in rows if r.get("status") not in ("verified", "removed_at_source")]
    failures = [(pid, [c for c in res if not c[1]]) for pid, res in results.items() if any(not c[1] for c in res)]
    inv_fail = [c for c in inventory if not c[1]]
    accepted = not not_verified and not failures and not inv_fail
    placeholder_names, outside = Counter(), Counter()
    for r in rows:
        f = base / r.get("md_path", "") if r.get("md_path") else None
        if f and f.exists():
            text = f.read_text(encoding="utf-8")
            placeholder_names.update(re.findall(r"\[Confluence macro: ([A-Za-z0-9_-]+)", text))
            outside.update(unquote(t) for t in re.findall(r"\]\((confluence://[^)\s]*)\)", text))
    L = ["# Verification report — Confluence download", "",
         "Generated: %s" % datetime.datetime.now().strftime("%Y-%m-%d %H:%M"), "",
         "RESULT: %s" % ("ACCEPTED" if accepted else "NOT ACCEPTED"), "",
         "## Counts", "", "- Pages in manifest: %d" % len(rows)]
    L += ["- %s: %d" % (k or "(blank)", v) for k, v in sorted(counts.items())]
    L += ["", "## Inventory checks", ""] + ["- %s — %s — %s" % ("PASS" if ok else "FAIL", n, d) for n, ok, d in inventory]
    L += ["", "## Pages that are not verified (%d)" % len(not_verified), ""]
    L += ["- %s — %s — %s — %s" % (r["page_id"], r.get("title", ""), r.get("status", ""), r.get("notes", "")) for r in not_verified] or ["None."]
    L += ["", "## Pages failing a check in this run (%d)" % len(failures), ""]
    for pid, fails in failures:
        L.append("- %s: %s" % (pid, "; ".join("%s (%s)" % (n, d) for n, _, d in fails)))
    if not failures:
        L.append("None.")
    L += ["", "## Content that exists in Confluence only as a macro (shown as a placeholder in the markdown)", ""]
    L += ["- %s: %d" % (n, c) for n, c in placeholder_names.most_common()] or ["None."]
    L += ["", "## Links to pages that are outside this download (%d distinct)" % len(outside), ""]
    L += ["- %s (%d links)" % (t, c) for t, c in outside.most_common(50)] or ["None."]
    out = base / "outputs" / "verification-report.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(L) + "\n", encoding="utf-8")
    return accepted, out


# ----------------------------------------------------------------------------- main

def normalise(text):
    return re.sub(r"\s+", " ", text).strip()


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--manifest", required=True)
    p.add_argument("--ids")
    p.add_argument("--status")
    p.add_argument("--inventory", action="store_true")
    p.add_argument("--expected-count", type=int)
    p.add_argument("--roots", help="comma-separated page ids expected to have a parent outside the manifest")
    p.add_argument("--spot-pick", type=int)
    p.add_argument("--spot-compare", action="store_true")
    p.add_argument("--final", action="store_true")
    p.add_argument("--min-coverage", type=float, default=0.99)
    p.add_argument("--no-update", action="store_true", help="check only, do not change the manifest")
    a = p.parse_args()

    manifest = Path(a.manifest).resolve()
    base = manifest.parent
    fields, rows = read_manifest(str(manifest))
    by_id = {r["page_id"]: r for r in rows}
    roots = set(x.strip() for x in a.roots.split(",")) if a.roots else None

    if a.spot_pick:
        pool = [r["page_id"] for r in rows if r.get("status") == "verified"]
        print(json.dumps(random.sample(pool, min(a.spot_pick, len(pool)))))
        return

    if a.spot_compare:
        folder = base / "spotcheck"
        files = sorted(f for f in folder.iterdir() if f.is_file()) if folder.is_dir() else []
        if not files:
            sys.exit("No files in spotcheck/. Re-fetch the picked pages to spotcheck/<page_id>.<ext> first.")
        bad = 0
        for f in files:
            row = by_id.get(f.stem)
            raw_file = base / row["raw_path"] if row and row.get("raw_path") else None
            if raw_file is None or not raw_file.exists():
                print("FAIL  %s  no raw file to compare with" % f.stem)
                bad += 1
                continue
            same = normalise(f.read_text(encoding="utf-8", errors="replace")) == \
                normalise(raw_file.read_text(encoding="utf-8", errors="replace"))
            print("%s  %s  %s" % ("PASS" if same else "DIFF", f.stem,
                                  "identical to raw" if same else "differs from raw: compare the live version number with the manifest"))
            bad += 0 if same else 1
        print("spot check: %d compared, %d differ" % (len(files), bad))
        sys.exit(1 if bad else 0)

    live_rows = [r for r in rows if r.get("status") != "removed_at_source"]

    if a.inventory and not a.final:
        res = check_inventory(live_rows, a.expected_count, roots)
        print_results("Inventory (%d rows)" % len(live_rows), res)
        ok = all(c[1] for c in res)
        print("INVENTORY: %s" % ("ACCEPTED" if ok else "NOT ACCEPTED"))
        sys.exit(0 if ok else 1)

    if a.final:
        targets = [r for r in rows if r.get("status") in ("done", "verified")]
    elif a.ids:
        wanted = [i.strip() for i in a.ids.split(",") if i.strip()]
        missing = [i for i in wanted if i not in by_id]
        if missing:
            sys.exit("Not in manifest: %s" % ", ".join(missing))
        targets = [by_id[i] for i in wanted]
    elif a.status:
        targets = [r for r in rows if r.get("status") == a.status]
    else:
        sys.exit("Give one of --ids, --status, --inventory, --spot-pick, --spot-compare, --final")

    results = {}
    passed = failed = 0
    for row in targets:
        res = check_row(row, rows, base, a.min_coverage, a.final)
        results[row["page_id"]] = res
        ok = all(c[1] for c in res)
        print_results("%s  %s  %s" % ("PASS" if ok else "FAIL", row["page_id"], row.get("title", "")),
                      res if not ok or len(targets) <= 25 else [])
        if ok:
            passed += 1
            if not a.no_update:
                mark_verified(row)
        else:
            failed += 1
            if not a.no_update:
                mark_failed(row, "; ".join("%s: %s" % (n, d) for n, k, d in res if not k))
    if not a.no_update:
        write_manifest(str(manifest), fields, rows)
    print("checked=%d passed=%d failed=%d" % (len(targets), passed, failed))

    if a.final:
        inventory = check_inventory(live_rows, a.expected_count, roots)
        accepted, out = final_report(rows, results, base, inventory)
        print("RESULT: %s  (report: %s)" % ("ACCEPTED" if accepted else "NOT ACCEPTED", out))
        sys.exit(0 if accepted else 1)
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
