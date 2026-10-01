#!/usr/bin/env python3
"""Business handbook builder and checker. Standard library only.

Turns the downloaded Confluence pages into one readable handbook, organised by team, in which every
paragraph cites the page it came from.

  python handbook.py tree                      # writes work/tree.md and work/platform-mentions.md
  python handbook.py verify-outline            # checks outline.json; add --write-manifest to create manifest.csv
  python handbook.py verify --area ID[,ID]     # checks chapters/<ID>.md and sets the status
  python handbook.py verify --status done
  python handbook.py assemble                  # writes HANDBOOK.md from the verified chapters
  python handbook.py verify --final            # re-checks everything and writes the report
  add --no-update to verify without changing the manifest

Citations in a chapter:  [p:PAGE_ID]   one or more at the end of every paragraph, list item and table row.

Per-chapter checks:
  H1 chapter file exists, names its area, and has every required section with content
  H2 every paragraph, list item and table row cites at least one page (or says "Not documented ...")
  H3 every cited page is a verified page of the download
  H4 specifics are grounded: every number, acronym, system-style name and quoted phrase in a block appears
     in a page that block cites
  H5 every page assigned to the area is cited or listed under "Pages not used" with a reason
  H6 platforms: each platform in outline.json is covered in the platforms section, with a citation to a page
     that mentions it whenever such a page exists
  H7 depth: the chapter is not a thin summary of a large body of pages
  H8 no secrets
  H9 the independent checker sampled the chapter and at most one sampled block failed
"""
import argparse
import datetime
import json
import re
import sys
from collections import Counter, OrderedDict
from pathlib import Path

HERE = Path(__file__).resolve().parent
KIT = HERE.parent
sys.path.insert(0, str(KIT / "tools"))
from manifest import read_manifest, write_manifest, mark_failed, mark_verified  # noqa: E402
from evidence import normalise, find_secrets, word_count  # noqa: E402

CITE = re.compile(r"\[p:([A-Za-z0-9_-]+)\]")
MAX_WORDS = 40000
MAX_PAGES = 80
KINDS = {"team", "cross-team", "overview"}
SECTIONS = {
    "team": ["1. Why this team exists", "2. People, roles and ownership", "3. What the team delivers",
             "4. Consumers and stakeholders", "5. Processes followed", "6. Platforms and tools",
             "7. Data and reporting", "8. Rules, policies and service levels", "9. History and decisions",
             "10. Gaps, contradictions and stale content", "Pages not used"],
    "overview": ["1. Why it exists", "2. Teams and what each owns", "3. Consumers", "4. Processes followed",
                 "5. Platforms and tools", "6. How work and data flow across teams",
                 "7. Gaps, contradictions and stale content", "Pages not used"],
}
SECTIONS["cross-team"] = SECTIONS["team"]
PLATFORM_SECTION = {"team": "6. Platforms and tools", "cross-team": "6. Platforms and tools", "overview": "5. Platforms and tools"}
ALLOWED_ACRONYMS = set("""API APIS SLA SLAS SLO SLOS KPI KPIS OKR OKRS ETL ELT UI UX ID IDS FAQ PDF CSV SQL JSON XML URL URLS OK
TBD TBC NA QA UAT PR PRS CI CD IT HR BAU POC MVP RACI ADR ADRS PII GDPR SME SMES AI ML BI DB DBA OS VPN SSO MFA
NOTE TODO AND OR NOT USD EUR GBP UTC CET EST PST AM PM""".split())
MANIFEST = HERE / "manifest.csv"
COLUMNS = ["area", "title", "kind", "team", "n_pages", "n_words", "status", "attempts", "verified_at", "notes"]


# ----------------------------------------------------------------------------- sources

def strip_front_matter(md):
    m = re.match(r"---\n.*?\n---\n", md, flags=re.S)
    return md[m.end():] if m else md


class Sources:
    """Verified pages of the Confluence download, with lazily loaded text."""

    def __init__(self, pages_dir, bk_dir):
        self.dir = pages_dir
        _, rows = read_manifest(str(pages_dir / "manifest.csv"))
        self.rows = OrderedDict((r["page_id"], r) for r in rows if r.get("status") == "verified" and r.get("md_path"))
        self.all_ids = set(r["page_id"] for r in rows)
        self._text, self._clean, self._norm, self._nums = {}, {}, {}, {}
        self.verdict = {}
        bk_manifest = bk_dir / "manifest.csv"
        if bk_manifest.exists():
            for r in read_manifest(str(bk_manifest))[1]:
                if r.get("status") == "verified":
                    self.verdict[r["page_id"]] = r.get("verdict", "")

    def text(self, pid):
        if pid not in self._text:
            f = self.dir / self.rows[pid]["md_path"]
            self._text[pid] = strip_front_matter(f.read_text(encoding="utf-8", errors="replace")) if f.exists() else ""
        return self._text[pid]

    def clean(self, pid):
        if pid not in self._clean:
            self._clean[pid] = re.sub(r"\\(.)", r"\1", self.text(pid))
        return self._clean[pid]

    def norm(self, pid):
        if pid not in self._norm:
            self._norm[pid] = normalise(self.text(pid))
        return self._norm[pid]

    def numbers(self, pid):
        if pid not in self._nums:
            self._nums[pid] = set(numbers_in(self.clean(pid)))
        return self._nums[pid]

    def words(self, pid):
        return word_count(self.text(pid))

    def mentions(self, pid, name):
        return re.search(r"(?<![A-Za-z0-9])%s(?![A-Za-z0-9])" % re.escape(name), self.clean(pid)) is not None


def numbers_in(text):
    out = []
    for m in re.finditer(r"(?<![\w.])\d[\d,]*(?:\.\d+)?(?!\w)", text):
        n = m.group(0).replace(",", "").rstrip(".")
        if len(re.sub(r"\D", "", n)) >= 2:
            out.append(n)
    return out


def load_outline():
    f = HERE / "outline.json"
    if not f.exists():
        sys.exit("outline.json not found in %s" % HERE)
    try:
        return json.loads(f.read_text(encoding="utf-8"))
    except ValueError as e:
        sys.exit("outline.json is not valid JSON: %s" % e)


def sources(a):
    return Sources((KIT / a.pages).resolve(), (KIT / a.bk).resolve())


# ----------------------------------------------------------------------------- tree

def cmd_tree(a):
    src = sources(a)
    ids = set(src.rows)
    children = OrderedDict()
    for pid, r in src.rows.items():
        parent = r.get("parent_id", "") if r.get("parent_id", "") in ids else ""
        children.setdefault(parent, []).append(pid)
    subtotal = {}

    def total(pid):
        if pid not in subtotal:
            n, w = 1, src.words(pid)
            for c in children.get(pid, []):
                cn, cw = total(c)
                n, w = n + cn, w + cw
            subtotal[pid] = (n, w)
        return subtotal[pid]

    L = ["# Page tree", "", "Verified pages: %d. Total words: %d." % (len(src.rows), sum(src.words(p) for p in src.rows)), "",
         "Each line: [page id] title — words on the page — pages/words in the whole branch — last modified — loop 04 verdict", ""]

    def walk(parent, depth):
        for pid in children.get(parent, []):
            r = src.rows[pid]
            n, w = total(pid)
            branch = " — branch: %d pages, %d words" % (n, w) if n > 1 else ""
            verdict = (" — 04: %s" % src.verdict[pid]) if pid in src.verdict else ""
            L.append("%s- [%s] %s — %d words%s — %s%s" % ("  " * depth, pid, r.get("title", ""), src.words(pid), branch,
                                                         r.get("last_modified", "") or "date unknown", verdict))
            walk(pid, depth + 1)

    walk("", 0)
    (HERE / "work").mkdir(exist_ok=True)
    (HERE / "work" / "tree.md").write_text("\n".join(L) + "\n", encoding="utf-8")

    outline_file = HERE / "outline.json"
    platforms = []
    if outline_file.exists():
        try:
            platforms = json.loads(outline_file.read_text(encoding="utf-8")).get("platforms", [])
        except ValueError:
            platforms = []
    platforms = platforms or [p.strip() for p in (a.platforms or "").split(",") if p.strip()]
    P = ["# Pages that mention each platform", ""]
    for name in platforms:
        hits = [pid for pid in src.rows if src.mentions(pid, name)]
        P += ["## %s (%d pages)" % (name, len(hits)), ""] + ["- [%s] %s" % (pid, src.rows[pid].get("title", "")) for pid in hits] + [""]
    (HERE / "work" / "platform-mentions.md").write_text("\n".join(P) + "\n", encoding="utf-8")
    print(json.dumps({"pages": len(src.rows), "tree": "work/tree.md", "platforms_indexed": platforms}))


# ----------------------------------------------------------------------------- outline

def check_outline(outline, src):
    res = []
    problems = []
    if not isinstance(outline, dict) or not str(outline.get("organisation", "")).strip():
        problems.append("'organisation' missing")
    areas = outline.get("areas") if isinstance(outline, dict) else None
    if not isinstance(areas, list) or not areas:
        return [("O1 outline shape", False, "'areas' must be a non-empty list")]
    if not isinstance(outline.get("platforms"), list) or not outline.get("platforms"):
        problems.append("'platforms' must list the platforms and tools to cover (for example AWS, Snowflake)")
    res.append(("O1 outline shape", not problems, "; ".join(problems) or "ok"))

    problems = []
    ids = [str(x.get("id", "")) for x in areas if isinstance(x, dict)]
    for i, x in enumerate(areas):
        if not isinstance(x, dict):
            problems.append("areas[%d] is not an object" % i)
            continue
        if not re.match(r"^[a-z0-9][a-z0-9-]*$", str(x.get("id", ""))):
            problems.append("areas[%d]: id must be lowercase letters, digits and hyphens" % i)
        if not str(x.get("title", "")).strip():
            problems.append("areas[%d]: title missing" % i)
        if x.get("kind") not in KINDS:
            problems.append("areas[%d]: kind must be team, cross-team or overview" % i)
        if x.get("kind") == "team" and not str(x.get("team", "")).strip():
            problems.append("areas[%d]: team name missing" % i)
        if not isinstance(x.get("pages"), list):
            problems.append("areas[%d]: pages must be a list of page ids" % i)
    dup = [i for i, n in Counter(ids).items() if n > 1]
    if dup:
        problems.append("duplicate area ids: %s" % ", ".join(dup))
    res.append(("O2 areas well formed", not problems, "; ".join(problems[:8]) or "%d areas" % len(areas)))
    if problems:
        return res

    overviews = [x["id"] for x in areas if x["kind"] == "overview"]
    res.append(("O3 exactly one overview", len(overviews) == 1, "found %d" % len(overviews)))

    assigned = Counter(str(p) for x in areas for p in x["pages"])
    unknown = [p for p in assigned if p not in src.rows]
    twice = [p for p, n in assigned.items() if n > 1]
    missing = [p for p in src.rows if p not in assigned]
    res.append(("O4 every page assigned once", not unknown and not twice and not missing,
                "; ".join(filter(None, [
                    ("not verified pages of the download: %s" % ", ".join(unknown[:10])) if unknown else "",
                    ("assigned to more than one area: %s" % ", ".join(twice[:10])) if twice else "",
                    ("%d pages not assigned to any area, e.g. %s" % (len(missing), ", ".join(missing[:10]))) if missing else ""]))
                or "%d pages assigned" % len(assigned)))
    if unknown:
        return res
    big = []
    for x in areas:
        words = sum(src.words(str(p)) for p in x["pages"])
        if x["kind"] != "overview" and (words > MAX_WORDS or len(x["pages"]) > MAX_PAGES):
            big.append("%s (%d pages, %d words)" % (x["id"], len(x["pages"]), words))
    res.append(("O5 areas small enough to read fully", not big,
                ("split into smaller areas (limit %d pages, %d words): %s" % (MAX_PAGES, MAX_WORDS, "; ".join(big))) if big else "ok"))
    return res


def print_results(title, res):
    print(title)
    for name, ok, detail in res:
        print("  %s  %-34s %s" % ("PASS" if ok else "FAIL", name, detail))


def cmd_verify_outline(a):
    src = sources(a)
    outline = load_outline()
    res = check_outline(outline, src)
    print_results("Outline", res)
    ok = all(c[1] for c in res)
    print("OUTLINE: %s" % ("ACCEPTED" if ok else "NOT ACCEPTED"))
    if ok and a.write_manifest:
        fields, rows = read_manifest(str(MANIFEST)) if MANIFEST.exists() else (list(COLUMNS), [])
        known = {r["area"]: r for r in rows}
        ordered = [x for x in outline["areas"] if x["kind"] != "overview"] + [x for x in outline["areas"] if x["kind"] == "overview"]
        out = []
        for x in ordered:
            row = known.pop(x["id"], None) or dict({k: "" for k in fields}, area=x["id"], status="pending", attempts="0")
            row.update(title=x["title"], kind=x["kind"], team=x.get("team", ""), n_pages=str(len(x["pages"])),
                       n_words=str(sum(src.words(str(p)) for p in x["pages"])))
            out.append(row)
        for row in known.values():  # areas removed from the outline
            row["status"] = "removed"
            out.append(row)
        write_manifest(str(MANIFEST), fields, out)
        print("manifest.csv written: %d areas" % len(ordered))
    sys.exit(0 if ok else 1)


# ----------------------------------------------------------------------------- chapter parsing

SUBHEADS = {}

def parse_chapter(text):
    """Returns (preamble_lines, OrderedDict section_title -> [block text]).

    SUBHEADS[id(sections)] holds, per section, the ### heading each block sits under (parallel list).
    """
    sections = OrderedDict()
    subs = {}
    SUBHEADS[id(sections)] = subs
    preamble, current, block, table = [], None, [], []
    state = {"sub": ""}
    in_fence = None

    def add(text_block):
        if current is not None:
            sections[current].append(text_block)
            subs.setdefault(current, []).append(state["sub"])

    def flush():
        if block:
            add("\n".join(block))
            del block[:]

    def flush_table():
        if table:
            rows = [t for t in table if not re.match(r"^\s*\|?\s*:?-{3,}", t)]
            for row in (rows[1:] if len(table) > len(rows) else rows):  # drop the header when a separator exists
                add(row)
            del table[:]

    for line in text.split("\n"):
        fence = re.match(r"\s*(`{3,}|~{3,})", line)
        if in_fence:
            if fence and fence.group(1)[0] == in_fence:
                in_fence = None
            continue
        if fence:
            in_fence = fence.group(1)[0]
            continue
        if line.startswith("## "):
            flush(); flush_table()
            current = line[3:].strip()
            sections.setdefault(current, [])
            state["sub"] = ""
            continue
        if line.startswith("#"):
            flush(); flush_table()
            if current is None:
                preamble.append(line)
            else:
                state["sub"] = line.lstrip("#").strip()
            continue
        if current is None:
            preamble.append(line)
            continue
        if not line.strip():
            flush(); flush_table()
            continue
        if line.lstrip().startswith("|"):
            flush()
            table.append(line)
            continue
        flush_table()
        item = re.match(r"(\s*)([-*+]|\d+[.)])\s+", line)
        if item and len(item.group(1)) < 2:
            flush()
        block.append(line)
    flush(); flush_table()
    return preamble, sections


def bare(block):
    return re.sub(r"^\s*([-*+]|\d+[.)])\s+", "", block.strip()).strip()


def is_exempt(block):
    b = bare(block).strip("|* _").lower()
    return b.startswith("not documented") or b in ("none", "none.")


def specifics(block):
    """Numbers, acronyms, system-style names and quoted phrases that must be found in a cited page."""
    t = CITE.sub(" ", block)
    t = re.sub(r"\]\([^)]*\)", "]", t)
    t = re.sub(r"^\s*([-*+]|\d+[.)])\s+", "", t)
    out = {"numbers": set(numbers_in(t)), "acronyms": set(), "names": set(), "quotes": set()}
    for m in re.finditer(r"(?<![A-Za-z0-9])[A-Z][A-Z0-9]{1,}s?(?![A-Za-z0-9])", t):
        word = m.group(0)
        base = word[:-1] if word.endswith("s") else word
        if base.upper() not in ALLOWED_ACRONYMS and word.upper() not in ALLOWED_ACRONYMS and not base.isdigit():
            out["acronyms"].add(base)
    for m in re.finditer(r"`([^`]+)`", t):
        out["names"].add(m.group(1))
    for m in re.finditer(r"(?<![A-Za-z0-9])[A-Za-z0-9]+(?:_[A-Za-z0-9]+)+(?![A-Za-z0-9])|(?<![A-Za-z0-9])[A-Z][a-z0-9]+(?:[A-Z][a-z0-9]+)+(?![A-Za-z0-9])", t):
        out["names"].add(m.group(0))
    for m in re.finditer(r"[“\"]([^”\"]{12,})[”\"]", t):
        if word_count(m.group(1)) >= 3:
            out["quotes"].add(m.group(1))
    return out


def check_chapter(area, outline, src, all_rows):
    aid, kind = area["id"], area["kind"]
    f = HERE / "chapters" / (aid + ".md")
    if not f.exists():
        return [("H1 chapter file", False, "chapters/%s.md not found" % aid)]
    text = f.read_text(encoding="utf-8")
    preamble, sections = parse_chapter(text)
    res = []
    required = SECTIONS[kind]
    missing = [s for s in required if s not in sections]
    empty = [s for s in required if s in sections and not sections[s]]
    has_area = any(re.match(r"^Area:\s*%s\s*$" % re.escape(aid), l) for l in preamble)
    res.append(("H1 chapter file", not missing and not empty and has_area,
                ("needs the line 'Area: %s' under the title" % aid) if not has_area else
                ("missing sections: %s" % "; ".join(missing)) if missing else
                ("empty sections (write 'Not documented in the pages for this area.'): %s" % "; ".join(empty)) if empty else "ok"))
    if missing:
        return res

    blocks = [(s, b) for s, bl in sections.items() for b in bl]
    content = [(s, b) for s, b in blocks if s != "Pages not used" and not is_exempt(b)]
    uncited = [bare(b)[:70] for s, b in content if not CITE.search(b)]
    res.append(("H2 every block cites a page", not uncited,
                ("%d blocks without [p:ID], e.g. \"%s\"" % (len(uncited), "\" | \"".join(uncited[:3]))) if uncited else "%d blocks" % len(content)))

    cited_all = set(CITE.findall(text))
    unknown = sorted(c for c in cited_all if c not in src.rows)
    res.append(("H3 cited pages exist", not unknown, ("not verified pages of the download: %s" % ", ".join(unknown[:10])) if unknown else "%d pages cited" % len(cited_all)))

    loose = []
    for s, b in content:
        cited = [c for c in CITE.findall(b) if c in src.rows]
        if not cited:
            continue
        sp = specifics(b)
        nums = set().union(*[src.numbers(c) for c in cited])
        gone = [n for n in sp["numbers"] if n not in nums]
        gone += [x for x in sp["acronyms"] if not any(src.mentions(c, x) for c in cited)]
        gone += [x for x in sp["names"] if not any(normalise(x) in src.norm(c) for c in cited)]
        gone += ['"%s"' % q[:40] for q in sp["quotes"] if not any(normalise(q) in src.norm(c) for c in cited)]
        if gone:
            loose.append("%s -> not in cited pages: %s" % (bare(b)[:50], ", ".join(sorted(gone)[:6])))
    res.append(("H4 specifics grounded in cited pages", not loose, " || ".join(loose[:5]) or "ok"))

    not_used = {}
    bad_items = []
    for b in sections.get("Pages not used", []):
        if is_exempt(b):
            continue
        ids = CITE.findall(b)
        reason = CITE.sub("", bare(b)).strip(" -:—")
        if not ids or word_count(reason) < 3:
            bad_items.append(bare(b)[:60])
        for i in ids:
            not_used[i] = reason
    used = set(c for s, b in content for c in CITE.findall(b))
    assigned = [str(p) for p in area["pages"]]
    uncovered = [p for p in assigned if p not in used and p not in not_used and src.verdict.get(p) != "no_business_content"]
    contradiction = [p for p in not_used if p not in used and src.verdict.get(p) == "extracted"]
    res.append(("H5 every assigned page accounted for", not uncovered and not bad_items and not contradiction,
                "; ".join(filter(None, [
                    ("neither cited nor listed under 'Pages not used': %s" % ", ".join(uncovered[:15])) if uncovered else "",
                    ("'Pages not used' items need [p:ID] and a reason: %s" % " | ".join(bad_items[:3])) if bad_items else "",
                    ("listed as not used but loop 04 found business knowledge on them: %s" % ", ".join(contradiction[:10])) if contradiction else ""]))
                or "%d used, %d not used" % (len(used & set(assigned)), len(assigned) - len(used & set(assigned)))))

    psec = PLATFORM_SECTION[kind]
    scope = list(src.rows) if kind == "overview" else assigned
    gaps = []
    for name in outline.get("platforms", []):
        mentioning = set(p for p in scope if p in src.rows and src.mentions(p, name))
        rx = re.compile(r"(?<![A-Za-z0-9])%s(?![A-Za-z0-9])" % re.escape(name))
        heads = SUBHEADS.get(id(sections), {}).get(psec, [])
        named = [b for i, b in enumerate(sections.get(psec, [])) if rx.search(b) or (i < len(heads) and rx.search(heads[i]))]
        if not named:
            gaps.append("%s is not mentioned in section '%s'" % (name, psec))
        elif mentioning and not any(set(CITE.findall(b)) & mentioning for b in named):
            gaps.append("%s: %d page(s) mention it (e.g. %s) but the section cites none of them" % (name, len(mentioning), ", ".join(sorted(mentioning)[:3])))
    res.append(("H6 platforms covered", not gaps, "; ".join(gaps[:6]) or ("%d platforms" % len(outline.get("platforms", [])))))

    source_words = sum(src.words(p) for p in assigned if p in used)
    need = min(5000, int(0.06 * source_words))
    have = sum(word_count(CITE.sub("", b)) for s, b in content)
    res.append(("H7 depth", have >= need, "%d words written from %d source words (need at least %d)" % (have, source_words, need)))

    secrets = find_secrets(text)
    res.append(("H8 no secrets", not secrets, ", ".join(sorted(set(secrets))) or "ok"))

    chk = HERE / "checks" / (aid + ".json")
    if not chk.exists():
        res.append(("H9 independent check", False, "checks/%s.json not found" % aid))
    else:
        try:
            data = json.loads(chk.read_text(encoding="utf-8"))
            sampled = data.get("sampled", [])
            starts = [normalise(bare(b))[:40] for s, b in content]
            unknown_blocks = [str(s.get("block", ""))[:40] for s in sampled if normalise(bare(str(s.get("block", ""))))[:40] not in starts]
            failed = [s for s in sampled if s.get("result") != "PASS"]
            need_n = min(12, len(content))
            stale = chk.stat().st_mtime < f.stat().st_mtime
            ok = len(sampled) >= need_n and not unknown_blocks and len(failed) <= 1 and not stale
            res.append(("H9 independent check", ok,
                        "check is older than the chapter; run the checker again" if stale else
                        ("sampled blocks not found in the chapter: %s" % " | ".join(unknown_blocks[:3])) if unknown_blocks else
                        "%d sampled (need %d), %d failed (max 1)" % (len(sampled), need_n, len(failed))))
        except (ValueError, AttributeError, TypeError) as e:
            res.append(("H9 independent check", False, "checks file unreadable: %s" % e))
    return res


# ----------------------------------------------------------------------------- verify

def cmd_verify(a):
    src = sources(a)
    outline = load_outline()
    areas = OrderedDict((x["id"], x) for x in outline["areas"])
    fields, rows = read_manifest(str(MANIFEST))
    by_area = {r["area"]: r for r in rows}
    if a.final:
        targets = [r for r in rows if r.get("status") in ("done", "verified")]
    elif a.area:
        wanted = [x.strip() for x in a.area.split(",") if x.strip()]
        missing = [w for w in wanted if w not in by_area or w not in areas]
        if missing:
            sys.exit("Not in manifest/outline: %s" % ", ".join(missing))
        targets = [by_area[w] for w in wanted]
    elif a.status:
        targets = [r for r in rows if r.get("status") == a.status]
    else:
        sys.exit("Give one of --area, --status, --final")

    results, passed, failed = {}, 0, 0
    for row in targets:
        area = areas.get(row["area"])
        if area is None:
            continue
        if area["kind"] == "overview" and not a.final:
            others_open = [r["area"] for r in rows if r["area"] != row["area"] and r.get("status") in ("pending", "done", "failed")]
            if others_open:
                print("SKIPPED  %s  the overview is written and checked last; still open: %s" % (row["area"], ", ".join(others_open[:8])))
                continue
        res = check_chapter(area, outline, src, rows)
        results[row["area"]] = res
        ok = all(c[1] for c in res)
        print_results("%s  %s" % ("PASS" if ok else "FAIL", row["area"]), res if not ok or len(targets) <= 10 else [])
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
    print("checked=%d passed=%d failed=%d" % (len(results), passed, failed))

    if a.final:
        outline_res = check_outline(outline, src)
        cited = set()
        not_used = set()
        for r in rows:
            f = HERE / "chapters" / (r["area"] + ".md")
            if r.get("status") == "verified" and f.exists():
                pre, secs = parse_chapter(f.read_text(encoding="utf-8"))
                for s, bl in secs.items():
                    for b in bl:
                        (not_used if s == "Pages not used" else cited).update(CITE.findall(b))
        untouched = [p for p in src.rows if p not in cited and p not in not_used and src.verdict.get(p) != "no_business_content"]
        open_rows = [r for r in rows if r.get("status") not in ("verified", "removed")]
        book = HERE / "HANDBOOK.md"
        chapters_newer = [r["area"] for r in rows if r.get("status") == "verified" and book.exists()
                          and (HERE / "chapters" / (r["area"] + ".md")).stat().st_mtime > book.stat().st_mtime]
        accepted = (not open_rows and not failed and not untouched and book.exists() and not chapters_newer
                    and all(c[1] for c in outline_res))
        counts = Counter(r.get("status", "") for r in rows)
        L = ["# Verification report — business handbook", "",
             "Generated: %s" % datetime.datetime.now().strftime("%Y-%m-%d %H:%M"), "",
             "RESULT: %s" % ("ACCEPTED" if accepted else "NOT ACCEPTED"), "",
             "ACCEPTED means: every verified page of the download was assigned to a chapter and is either cited or listed as "
             "not used with a reason; every paragraph cites its pages; every number, acronym and system name appears in a "
             "cited page; a sampled independent check passed. It does not mean every sentence is a perfect reading of its "
             "source, or that the pages themselves are current.", "",
             "## Counts", "", "- Chapters: %d" % len([r for r in rows if r.get("status") != "removed"])]
        L += ["- %s: %d" % (k or "(blank)", v) for k, v in sorted(counts.items())]
        L += ["- Pages in the download (verified): %d" % len(src.rows), "- Pages cited in the handbook: %d" % len(cited & set(src.rows)),
              "- Pages listed as not used: %d" % len(not_used - cited),
              "- Pages with no business content according to loop 04: %d" % len([p for p in src.rows if src.verdict.get(p) == "no_business_content"])]
        L += ["", "## Outline checks", ""] + ["- %s — %s — %s" % ("PASS" if ok else "FAIL", n, d) for n, ok, d in outline_res]
        L += ["", "## HANDBOOK.md", "", "- " + ("missing: run 'handbook.py assemble'" if not book.exists() else
                                              ("older than chapters %s: run 'handbook.py assemble' again" % ", ".join(chapters_newer)) if chapters_newer else "present and current")]
        L += ["", "## Pages neither cited nor listed as not used (%d)" % len(untouched), ""]
        L += ["- %s — %s" % (p, src.rows[p].get("title", "")) for p in untouched[:200]] or ["None."]
        L += ["", "## Chapters not verified (%d)" % len(open_rows), ""]
        L += ["- %s — %s — %s" % (r["area"], r.get("status", ""), r.get("notes", "")) for r in open_rows] or ["None."]
        out = HERE / "outputs" / "verification-report.md"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text("\n".join(L) + "\n", encoding="utf-8")
        print("RESULT: %s  (report: %s)" % ("ACCEPTED" if accepted else "NOT ACCEPTED", out))
        sys.exit(0 if accepted else 1)
    sys.exit(1 if failed else 0)


# ----------------------------------------------------------------------------- assemble

def cmd_assemble(a):
    src = sources(a)
    outline = load_outline()
    fields, rows = read_manifest(str(MANIFEST))
    status = {r["area"]: r.get("status", "") for r in rows}
    org = outline["organisation"]
    areas = [x for x in outline["areas"] if x["kind"] == "overview"] + [x for x in outline["areas"] if x["kind"] != "overview"]
    entries = {}
    ef = (KIT / a.bk).resolve() / "catalog" / "all-entries.jsonl"
    if ef.exists():
        for line in ef.read_text(encoding="utf-8").split("\n"):
            if line.strip():
                e = json.loads(line)
                entries.setdefault(str(e.get("source", "")), []).append(e)
    rel = "../%s/" % a.pages

    def link(m):
        pid = m.group(1)
        return "[p:%s](%s%s)" % (pid, rel, src.rows[pid]["md_path"]) if pid in src.rows else m.group(0)

    L = ["# %s — business knowledge handbook" % org, "",
         "Generated %s from the downloaded Confluence pages." % datetime.datetime.now().strftime("%Y-%m-%d"), "",
         "**How to read this.** Every paragraph ends with one or more source markers such as `[p:123456]`. Each one links to "
         "the Markdown copy of the Confluence page the statement came from; the source index at the end gives the page "
         "title and when it was last modified. \"Not documented\" means the pages for that area say nothing about the "
         "topic, not that the answer is no.", "", "## Contents", ""]
    included = [x for x in areas if status.get(x["id"]) == "verified" and (HERE / "chapters" / (x["id"] + ".md")).exists()]
    team = None
    for x in included:
        if x["kind"] != "overview" and x.get("team", "") != team:
            team = x.get("team", "")
            L.append("- **%s**" % (team or "Across teams"))
        L.append("%s- [%s](#%s)" % ("" if x["kind"] == "overview" else "  ", x["title"], x["id"]))
    skipped = [x["id"] for x in areas if x not in included]
    if skipped:
        L += ["", "> Not included because the chapter is not verified yet: %s" % ", ".join(skipped)]
    L.append("")
    cited_in = Counter()
    for x in included:
        text = (HERE / "chapters" / (x["id"] + ".md")).read_text(encoding="utf-8")
        for pid in set(CITE.findall(text)):
            cited_in[pid] += 1
        body = []
        for line in text.split("\n"):
            if re.match(r"^Area:\s", line):
                continue
            if line.startswith("#"):
                line = "#" + line
            body.append(CITE.sub(link, line))
        L += ["---", "", '<a id="%s"></a>' % x["id"], ""] + body
        found = [(p, e) for p in x["pages"] for e in entries.get(str(p), [])]
        if found:
            L += ["", "### Catalogued facts for this area", "",
                  "Taken from loop 04. Each one is backed by a verbatim quote in `04-confluence-business-knowledge/business/`.", ""]
            for p, e in sorted(found, key=lambda t: (str(t[1].get("type", "")), normalise(str(t[1].get("name", ""))))):
                L.append("- **%s** (%s): %s %s" % (e.get("name", ""), e.get("type", ""), e.get("statement", ""), CITE.sub(link, "[p:%s]" % p)))
        L.append("")
    L += ["---", "", "## Source index", "", "| Page | Title | Last modified | Cited in chapters |", "|---|---|---|---|"]
    for pid in sorted(cited_in, key=lambda p: src.rows.get(p, {}).get("title", "")):
        if pid in src.rows:
            r = src.rows[pid]
            L.append("| [p:%s](%s%s) | %s | %s | %d |" % (pid, rel, r["md_path"], r.get("title", "").replace("|", "/"),
                                                         r.get("last_modified", "") or "unknown", cited_in[pid]))
    (HERE / "HANDBOOK.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print(json.dumps({"handbook": "HANDBOOK.md", "chapters_included": len(included), "chapters_skipped": skipped,
                      "pages_cited": len(cited_in), "catalogued_facts_added": sum(len(entries.get(str(p), [])) for x in included for p in x["pages"])}))


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("command", choices=["tree", "verify-outline", "verify", "assemble"])
    p.add_argument("--pages", default="01-confluence-download", help="Confluence download folder, relative to the kit root")
    p.add_argument("--bk", default="04-confluence-business-knowledge", help="loop 04 folder, relative to the kit root (optional input)")
    p.add_argument("--platforms", help="for 'tree' before outline.json exists: comma-separated platform names")
    p.add_argument("--write-manifest", action="store_true")
    p.add_argument("--area")
    p.add_argument("--status")
    p.add_argument("--final", action="store_true")
    p.add_argument("--no-update", action="store_true")
    a = p.parse_args()
    {"tree": cmd_tree, "verify-outline": cmd_verify_outline, "verify": cmd_verify, "assemble": cmd_assemble}[a.command](a)


if __name__ == "__main__":
    main()
