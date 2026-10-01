#!/usr/bin/env python3
"""Checker for the repository linkage loop. Standard library only.

This script is the only thing allowed to set status=verified.

Usage:
  python verify.py --repo NAME          # check links/NAME.json, update its status
  python verify.py --status done
  python verify.py --final              # re-check everything, check the graph files, write the report
  add --no-update to check without changing the manifest

Per-repo checks on links/<repo>.json:
  L1 file is valid and matches the schema
  L2 every `consumes` entry of the repo's facts file has a resolution: internal, external or unresolved
  L3 every candidate mention found by build_graph.py has been reviewed: edge or not, with a reason
  L4 every pipeline of the repo has a trigger with evidence, or no_trigger_found with what was searched
  L5 every cross-repository trigger hit is used as evidence or dismissed with a reason
  L6 every evidence citation points to a real file and line in the right clone
  L7 every link marked as an edge has an entry in `edges`
"""
import argparse
import datetime
import json
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
KIT = HERE.parent
sys.path.insert(0, str(KIT / "tools"))
from manifest import read_manifest, write_manifest, mark_failed, mark_verified  # noqa: E402
from evidence import check_location, split_json_citation, repo_dirname  # noqa: E402

RESOLUTIONS = {"internal", "external", "unresolved"}
EDGE_KINDS = {"imports", "calls_api", "triggers", "triggered_by", "reads_data", "writes_data", "uses_image",
              "uses_workflow", "deploys", "config", "submodule", "publishes_to", "subscribes_to", "other"}
CONFIDENCE = {"high", "medium", "low"}
TRIGGER_TYPES = {"push", "pull_request", "tag", "release", "cron", "manual", "upstream", "webhook", "event", "api", "other"}


def words(value):
    return len(str(value or "").split())


def check_repo(row, docs_dir, repos):
    res = []
    repo = row["repo"]
    name = repo_dirname(repo)
    links_file = HERE / "links" / (name + ".json")
    cand_file = HERE / "work" / "candidates" / (name + ".json")
    facts_file = docs_dir / "facts" / (name + ".json")
    if not links_file.exists():
        return [("L1 links file", False, "links/%s.json not found" % name)]
    try:
        links = json.loads(links_file.read_text(encoding="utf-8"))
    except ValueError as e:
        return [("L1 links file", False, "not valid JSON: %s" % e)]
    if not cand_file.exists() or not facts_file.exists():
        return [("L1 links file", False, "candidates or facts file missing; run build_graph.py candidates")]
    cand = json.loads(cand_file.read_text(encoding="utf-8"))
    facts = json.loads(facts_file.read_text(encoding="utf-8"))

    problems, evidence = [], []  # evidence: (value, default_repo, where)
    if not isinstance(links, dict) or links.get("repo") != repo:
        problems.append("'repo' must be '%s'" % repo)
        links = links if isinstance(links, dict) else {}
    for key in ("consumes", "edges", "mentions_reviewed", "pipelines", "trigger_hits_dismissed"):
        if not isinstance(links.get(key), list):
            problems.append("'%s' must be a list" % key)
            links[key] = []
    for i, c in enumerate(links["consumes"]):
        where = "consumes[%d]" % i
        if c.get("resolution") not in RESOLUTIONS:
            problems.append("%s: resolution must be one of %s" % (where, sorted(RESOLUTIONS)))
        if c.get("resolution") == "internal":
            if c.get("to_repo") not in repos or c.get("to_repo") == repo:
                problems.append("%s: to_repo '%s' is not another repository in the manifest" % (where, c.get("to_repo")))
        elif words(c.get("note")) < 4:
            problems.append("%s: external/unresolved needs a note saying what was searched or why it is third-party" % where)
        if not c.get("evidence_from"):
            problems.append("%s: evidence_from missing" % where)
        evidence.append((c.get("evidence_from", ""), repo, where + ".evidence_from"))
        if c.get("evidence_to"):
            evidence.append((c["evidence_to"], c.get("to_repo") or repo, where + ".evidence_to"))
    for i, e in enumerate(links["edges"]):
        where = "edges[%d]" % i
        if e.get("to_repo") not in repos or e.get("to_repo") == repo:
            problems.append("%s: to_repo '%s' is not another repository in the manifest" % (where, e.get("to_repo")))
        if e.get("kind") not in EDGE_KINDS:
            problems.append("%s: kind must be one of %s" % (where, sorted(EDGE_KINDS)))
        if e.get("confidence") not in CONFIDENCE:
            problems.append("%s: confidence must be high, medium or low" % where)
        if not str(e.get("identifier", "")).strip() or not e.get("evidence_from"):
            problems.append("%s: identifier and evidence_from are required" % where)
        evidence.append((e.get("evidence_from", ""), repo, where + ".evidence_from"))
        if e.get("evidence_to"):
            evidence.append((e["evidence_to"], e.get("to_repo") or repo, where + ".evidence_to"))
    for i, m in enumerate(links["mentions_reviewed"]):
        if not isinstance(m.get("is_edge"), bool) or words(m.get("reason")) < 3:
            problems.append("mentions_reviewed[%d]: needs is_edge true/false and a reason" % i)
    for i, p in enumerate(links["pipelines"]):
        where = "pipelines[%d]" % i
        triggers = p.get("triggers") or []
        if not triggers and not (p.get("no_trigger_found") is True and words(p.get("searched")) >= 4):
            problems.append("%s (%s): no trigger, and no_trigger_found/searched not filled" % (where, p.get("name")))
        for j, t in enumerate(triggers):
            tw = "%s.triggers[%d]" % (where, j)
            if t.get("type") not in TRIGGER_TYPES:
                problems.append("%s: type must be one of %s" % (tw, sorted(TRIGGER_TYPES)))
            src = t.get("source_repo") or repo
            if src not in repos:
                problems.append("%s: source_repo '%s' is not in the manifest" % (tw, src))
            if not t.get("evidence"):
                problems.append("%s: evidence missing" % tw)
            evidence.append((t.get("evidence", ""), src, tw + ".evidence"))
        for j, d in enumerate(p.get("downstream") or []):
            if d.get("repo") not in repos:
                problems.append("%s.downstream[%d]: repo '%s' is not in the manifest" % (where, j, d.get("repo")))
            if d.get("evidence"):
                evidence.append((d["evidence"], repo, "%s.downstream[%d].evidence" % (where, j)))
    for i, d in enumerate(links["trigger_hits_dismissed"]):
        if not d.get("path") or not str(d.get("line", "")).isdigit() or words(d.get("reason")) < 3:
            problems.append("trigger_hits_dismissed[%d]: needs path, line and a reason" % i)
    res.append(("L1 links file", not problems, "; ".join(problems[:8]) or "ok"))
    if problems:
        return res

    resolved = set((c.get("kind", ""), str(c.get("id", "")).lower()) for c in links["consumes"])
    missing = ["%s:%s" % (c.get("kind", ""), c.get("id", "")) for c in facts.get("consumes", [])
               if (c.get("kind", ""), str(c.get("id", "")).lower()) not in resolved]
    res.append(("L2 consumes resolved", not missing, ", ".join(missing[:12]) or "%d resolved" % len(facts.get("consumes", []))))

    reviewed = set((m.get("target_repo", ""), str(m.get("identifier", "")).lower()) for m in links["mentions_reviewed"])
    todo = ["%s (%s)" % (m["target_repo"], m["identifier"]) for m in cand.get("outgoing_mentions", [])
            if (m["target_repo"], m["identifier"].lower()) not in reviewed]
    res.append(("L3 mentions reviewed", not todo, ", ".join(todo[:12]) or "%d reviewed" % len(cand.get("outgoing_mentions", []))))

    linked = set(p.get("name", "") for p in links["pipelines"])
    absent = [p.get("name", "") for p in facts.get("pipelines", []) if p.get("name", "") not in linked]
    res.append(("L4 pipelines have triggers", not absent, ("not in links file: %s" % ", ".join(absent[:10])) if absent
                else "%d pipelines" % len(facts.get("pipelines", []))))

    used = set()
    for value, default_repo, _ in evidence:
        parsed = split_json_citation(value)
        if parsed and (parsed[0] or default_repo) == repo:
            for line in range(parsed[2], parsed[3] + 1):
                used.add((parsed[1], line))
    dismissed = set((d["path"], int(d["line"])) for d in links["trigger_hits_dismissed"])
    loose = ["%s:%d (%s)" % (h["path"], h["line"], h["pattern"]) for h in cand.get("trigger_hits", [])
             if h.get("cross_repo") and (h["path"], h["line"]) not in used and (h["path"], h["line"]) not in dismissed]
    res.append(("L5 trigger hits accounted for", not loose, ", ".join(loose[:10]) or "ok"))

    bad = []
    for value, default_repo, where in evidence:
        parsed = split_json_citation(value)
        if parsed is None:
            bad.append("%s: '%s' is not path:line or repo:path:line" % (where, value))
            continue
        target = parsed[0] or default_repo
        if target not in repos:
            bad.append("%s: repository '%s' is not in the manifest" % (where, target))
            continue
        ok, detail = check_location(docs_dir / "repos" / repo_dirname(target), parsed[1], parsed[2], parsed[3])
        if not ok:
            bad.append("%s: %s" % (where, detail))
    res.append(("L6 evidence resolves", not bad, "; ".join(bad[:8]) or "%d citations resolve" % len(evidence)))

    edge_targets = set(e.get("to_repo") for e in links["edges"]) | set(c.get("to_repo") for c in links["consumes"] if c.get("resolution") == "internal")
    no_edge = [m.get("target_repo", "") for m in links["mentions_reviewed"] if m.get("is_edge") and m.get("target_repo") not in edge_targets]
    res.append(("L7 edges recorded", not no_edge, ("marked as edge but no entry in edges: %s" % ", ".join(sorted(set(no_edge))[:10])) if no_edge else "ok"))
    return res


def print_results(title, res):
    print(title)
    for name, ok, detail in res:
        print("  %s  %-30s %s" % ("PASS" if ok else "FAIL", name, detail))


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--repo")
    p.add_argument("--status")
    p.add_argument("--final", action="store_true")
    p.add_argument("--no-update", action="store_true")
    p.add_argument("--docs", default=str(KIT / "02a-repo-docs"))
    a = p.parse_args()

    docs_dir = Path(a.docs).resolve()
    manifest = HERE / "manifest.csv"
    fields, rows = read_manifest(str(manifest))
    repos = set(r["repo"] for r in rows)

    if a.final:
        targets = [r for r in rows if r.get("status") in ("done", "verified")]
    elif a.repo:
        wanted = [x.strip() for x in a.repo.split(",")]
        targets = [r for r in rows if r["repo"] in wanted]
        if not targets:
            sys.exit("Not in manifest: %s" % a.repo)
    elif a.status:
        targets = [r for r in rows if r.get("status") == a.status]
    else:
        sys.exit("Give one of --repo, --status, --final")

    results, passed, failed = {}, 0, 0
    for row in targets:
        res = check_repo(row, docs_dir, repos)
        results[row["repo"]] = res
        ok = all(c[1] for c in res)
        print_results("%s  %s" % ("PASS" if ok else "FAIL", row["repo"]), res if not ok or len(targets) <= 10 else [])
        if ok:
            passed += 1
            if not a.no_update:
                mark_verified(row)
                row["links_path"] = "links/%s.json" % repo_dirname(row["repo"])
        else:
            failed += 1
            if not a.no_update:
                mark_failed(row, "; ".join("%s: %s" % (n, d) for n, k, d in res if not k))
    if not a.no_update:
        write_manifest(str(manifest), fields, rows)
    print("checked=%d passed=%d failed=%d" % (len(targets), passed, failed))

    if a.final:
        graph = HERE / "graph"
        needed = ["edges.csv", "pipelines.csv", "nodes.csv", "unresolved.md", "isolated.md", "graph.mmd", "overview.md"]
        absent = [n for n in needed if not (graph / n).exists()]
        node_gap = []
        if (graph / "nodes.csv").exists():
            text = (graph / "nodes.csv").read_text(encoding="utf-8")
            node_gap = [r["repo"] for r in rows if r["repo"] not in text]
        excluded = []
        if (HERE / "work" / "excluded.json").exists():
            excluded = json.loads((HERE / "work" / "excluded.json").read_text(encoding="utf-8"))
        open_rows = [r for r in rows if r.get("status") != "verified"]
        accepted = not open_rows and not failed and not absent and not node_gap
        counts = Counter(r.get("status", "") for r in rows)
        L = ["# Verification report — repository linkage", "",
             "Generated: %s" % datetime.datetime.now().strftime("%Y-%m-%d %H:%M"), "",
             "RESULT: %s" % ("ACCEPTED" if accepted else "NOT ACCEPTED"), "",
             "## Counts", "", "- Repositories in manifest: %d" % len(rows)]
        L += ["- %s: %d" % (k or "(blank)", v) for k, v in sorted(counts.items())]
        L += ["", "## Graph files missing", ""] + (["- %s" % n for n in absent] or ["None."])
        L += ["", "## Repositories missing from nodes.csv", ""] + (["- %s" % n for n in node_gap] or ["None."])
        L += ["", "## Repositories not verified (%d)" % len(open_rows), ""]
        L += ["- %s — %s — %s" % (r["repo"], r.get("status", ""), r.get("notes", "")) for r in open_rows] or ["None."]
        L += ["", "## Repositories left out because their documentation is not verified (%d)" % len(excluded), ""]
        L += ["- %s — %s" % (e["repo"], e["reason"]) for e in excluded] or ["None."]
        out = HERE / "outputs" / "verification-report.md"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text("\n".join(L) + "\n", encoding="utf-8")
        print("RESULT: %s  (report: %s)" % ("ACCEPTED" if accepted else "NOT ACCEPTED", out))
        sys.exit(0 if accepted else 1)
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
