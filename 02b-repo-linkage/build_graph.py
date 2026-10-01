#!/usr/bin/env python3
"""Cross-repository linkage helper. Standard library only.

  python build_graph.py candidates     # deterministic search across all clones; writes work/candidates/<repo>.json
                                       # and creates/extends manifest.csv (one row per repo)
  python build_graph.py final          # merges links/<repo>.json into graph/edges.csv, pipelines.csv, nodes.csv,
                                       # unresolved.md, isolated.md and graph.mmd

Inputs come from the documentation loop: ../02a-repo-docs/manifest.csv, facts/ and repos/.
Only repositories that are `verified` there are included; the rest are listed in work/excluded.json.
"""
import argparse
import csv
import json
import os
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
KIT = HERE.parent
sys.path.insert(0, str(KIT / "tools"))
from manifest import read_manifest, write_manifest  # noqa: E402
from evidence import repo_dirname  # noqa: E402

SKIP_DIRS = {".git", "node_modules", "vendor", "dist", "build", "target", ".venv", "venv", "__pycache__",
             ".terraform", ".idea", ".vscode", ".gradle", "bower_components", ".next", "coverage", "site-packages"}
SKIP_FILES = {"package-lock.json", "yarn.lock", "pnpm-lock.yaml", "poetry.lock", "go.sum", "Cargo.lock",
              "Gemfile.lock", "composer.lock", "Pipfile.lock"}
BINARY_EXT = {"png", "jpg", "jpeg", "gif", "ico", "pdf", "zip", "gz", "tar", "jar", "war", "class", "so", "dll",
              "exe", "bin", "woff", "woff2", "ttf", "eot", "mp4", "mov", "parquet", "avro", "orc", "pyc", "svg",
              "min.js", "map", "lock"}
MAX_BYTES = 1000000
# Names too generic to search for automatically. They are listed in work/skipped-identifiers.json.
GENERIC = {"common", "utils", "util", "core", "shared", "tools", "infra", "config", "configs", "docs", "tests",
           "test", "scripts", "service", "services", "server", "client", "library", "base", "main", "master",
           "internal", "public", "private", "platform", "backend", "frontend", "deploy", "pipeline", "pipelines",
           "terraform", "ansible", "docker", "python", "example", "examples", "sample", "template", "templates",
           "default", "admin", "users", "data", "models", "model", "events", "event", "status", "health"}
MIN_LEN = 5

# (label, crosses repositories?, regex)
TRIGGER_PATTERNS = [
    ("gha_workflow_run", True, re.compile(r"^\s*workflow_run\s*:")),
    ("gha_repository_dispatch", True, re.compile(r"repository_dispatch|/dispatches\b|createDispatchEvent|createWorkflowDispatch")),
    ("gha_workflow_call", True, re.compile(r"^\s*workflow_call\s*:")),
    ("gha_uses_remote_workflow", True, re.compile(r"uses:\s*[\w.-]+/[\w.-]+/\.github/workflows/")),
    ("gha_workflow_dispatch", False, re.compile(r"^\s*workflow_dispatch\s*:?")),
    ("gha_schedule", False, re.compile(r"^\s*-?\s*cron:\s*['\"]")),
    ("jenkins_build_job", True, re.compile(r"\bbuild\s*\(?\s*job\s*:")),
    ("jenkins_upstream", True, re.compile(r"\bupstream\s*\(|upstreamProjects")),
    ("jenkins_cron", False, re.compile(r"\b(cron|pollSCM)\s*\(?\s*['\"]")),
    ("gitlab_trigger", True, re.compile(r"^\s*trigger\s*:|\bproject:\s*[\w.-]+/[\w.-]+")),
    ("azure_pipeline_resource", True, re.compile(r"^\s*-\s*pipeline\s*:|^\s*-\s*repository\s*:")),
    ("airflow_trigger_dag", True, re.compile(r"TriggerDagRunOperator|ExternalTaskSensor|ExternalTaskMarker")),
    ("airflow_schedule", False, re.compile(r"schedule(_interval)?\s*=")),
    ("aws_event_rule", True, re.compile(r"aws_cloudwatch_event_(rule|target)|aws_scheduler_schedule|AWS::Events::Rule|EventBridge")),
    ("aws_s3_notification", True, re.compile(r"aws_s3_bucket_notification|NotificationConfiguration|s3:ObjectCreated")),
    ("aws_event_source_mapping", True, re.compile(r"aws_lambda_event_source_mapping|EventSourceMapping")),
    ("aws_sns_sqs_subscription", True, re.compile(r"aws_sns_topic_subscription|AWS::SNS::Subscription")),
    ("gcp_trigger", True, re.compile(r"google_cloudbuild_trigger|google_cloud_scheduler_job|google_pubsub_subscription|google_eventarc_trigger")),
    ("azure_trigger", True, re.compile(r"azurerm_eventgrid|azurerm_data_factory_trigger|\"type\"\s*:\s*\"(ScheduleTrigger|BlobEventsTrigger|TumblingWindowTrigger)\"")),
    ("webhook", True, re.compile(r"(?i)\bwebhook")),
    ("k8s_cron", False, re.compile(r"^\s*schedule:\s*['\"]?[\d*/,-]+\s")),
    ("kafka_consumer", True, re.compile(r"@KafkaListener|KafkaConsumer\(|\.subscribe\(\s*\[?['\"]")),
]
TRIGGER_EXT = {"yml", "yaml", "groovy", "py", "tf", "json", "sh", "java", "kt", "ts", "js", "go", "cs", ""}
EDGE_FIELDS = ["from_repo", "to_repo", "kind", "identifier", "evidence_from", "evidence_to", "confidence"]
PIPE_FIELDS = ["repo", "pipeline", "system", "definition", "trigger_type", "trigger_detail", "trigger_source_repo",
               "evidence", "downstream"]


def docs_inputs(docs_dir):
    fields, rows = read_manifest(str(docs_dir / "manifest.csv"))
    included, excluded = [], []
    for r in rows:
        name = repo_dirname(r["repo"])
        facts_file = docs_dir / "facts" / (name + ".json")
        if r.get("status") != "verified":
            excluded.append({"repo": r["repo"], "reason": "documentation status is '%s'" % r.get("status", "")})
        elif not facts_file.exists():
            excluded.append({"repo": r["repo"], "reason": "facts file missing"})
        else:
            included.append((r, json.loads(facts_file.read_text(encoding="utf-8"))))
    return included, excluded


def iter_text_files(repo_dir):
    for root, dirs, names in os.walk(repo_dir):
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS)
        for name in sorted(names):
            if name in SKIP_FILES:
                continue
            path = Path(root) / name
            suffix = path.suffix.lower().lstrip(".")
            if suffix in BINARY_EXT or name.endswith(".min.js"):
                continue
            try:
                if path.stat().st_size > MAX_BYTES:
                    continue
                data = path.read_bytes()
            except OSError:
                continue
            if b"\x00" in data[:4096]:
                continue
            yield path.relative_to(repo_dir).as_posix(), suffix, data.decode("utf-8", errors="ignore")


def token_parts(line):
    out = set()
    for tok in re.findall(r"[A-Za-z0-9_.\-/:@]+", line):
        for seg in re.split(r"[:@]", tok):
            seg = seg.strip(".-/")
            if seg.endswith(".git"):
                seg = seg[:-4]
            if not seg:
                continue
            out.add(seg.lower())
            if "/" in seg:
                parts = [p for p in seg.split("/") if p]
                out.update(p.lower() for p in parts)
                for i in range(len(parts) - 1):
                    out.add((parts[i] + "/" + parts[i + 1]).lower())
    return out


def cmd_candidates(a):
    docs_dir = Path(a.docs).resolve()
    included, excluded = docs_inputs(docs_dir)
    work = HERE / "work"
    (work / "candidates").mkdir(parents=True, exist_ok=True)
    (work / "excluded.json").write_text(json.dumps(excluded, indent=2), encoding="utf-8")

    idmap, skipped = defaultdict(set), []
    producers = defaultdict(set)
    for row, facts in included:
        repo = row["repo"]
        names = {repo, repo.split("/")[-1]}
        for n in names:
            if len(n) < MIN_LEN or n.lower() in GENERIC:
                skipped.append({"repo": repo, "identifier": n, "reason": "too short or too generic to search automatically"})
            else:
                idmap[n.lower()].add((repo, n))
        for item in facts.get("produces", []):
            ident = str(item.get("id", "")).strip()
            if not ident:
                continue
            producers[ident.lower()].add((repo, item.get("kind", "")))
            key = ident.strip("/").lower()
            if len(key) < MIN_LEN or key in GENERIC:
                skipped.append({"repo": repo, "identifier": ident, "reason": "too short or too generic to search automatically"})
            else:
                idmap[key].add((repo, ident))
    (work / "skipped-identifiers.json").write_text(json.dumps(skipped, indent=2), encoding="utf-8")

    man_path = HERE / "manifest.csv"
    if man_path.exists():
        fields, mrows = read_manifest(str(man_path))
    else:
        fields = ["repo", "n_consumes", "n_mentions", "n_cross_trigger_hits", "status", "attempts", "links_path", "verified_at", "notes"]
        mrows = []
    known = {r["repo"]: r for r in mrows}

    for row, facts in included:
        repo = row["repo"]
        repo_dir = docs_dir / "repos" / repo_dirname(repo)
        mentions = {}
        hits = []
        for rel, suffix, text in iter_text_files(repo_dir):
            for n, line in enumerate(text.split("\n"), 1):
                if len(line) > 2000:
                    continue
                for part in token_parts(line):
                    for target, ident in idmap.get(part, ()):
                        if target == repo:
                            continue
                        m = mentions.setdefault((target, ident), {"target_repo": target, "identifier": ident, "count": 0, "samples": []})
                        m["count"] += 1
                        if len(m["samples"]) < 3:
                            m["samples"].append({"path": rel, "line": n, "text": line.strip()[:200]})
                if suffix in TRIGGER_EXT and len(hits) < 300:
                    for label, cross, rx in TRIGGER_PATTERNS:
                        if rx.search(line):
                            hits.append({"pattern": label, "cross_repo": cross, "path": rel, "line": n, "text": line.strip()[:200]})
                            break
        consumes = []
        for item in facts.get("consumes", []):
            ident = str(item.get("id", "")).strip()
            consumes.append(dict(item, producers=[{"repo": r, "kind": k} for r, k in sorted(producers.get(ident.lower(), ())) if r != repo]))
        cand = {"repo": repo, "consumes": consumes,
                "outgoing_mentions": sorted(mentions.values(), key=lambda m: (m["target_repo"], m["identifier"])),
                "trigger_hits": hits, "pipelines": facts.get("pipelines", [])}
        (work / "candidates" / (repo_dirname(repo) + ".json")).write_text(json.dumps(cand, indent=2), encoding="utf-8")
        n_cross = len([h for h in hits if h["cross_repo"]])
        if repo not in known:
            new = {k: "" for k in fields}
            new.update(repo=repo, status="pending", attempts="0")
            mrows.append(new)
            known[repo] = new
        known[repo].update(n_consumes=str(len(consumes)), n_mentions=str(len(mentions)), n_cross_trigger_hits=str(n_cross))
        print("CANDIDATES  %s  consumes=%d mentions=%d trigger_hits=%d (cross-repo %d)" % (repo, len(consumes), len(mentions), len(hits), n_cross))
    write_manifest(str(man_path), fields, mrows)
    print("repos included=%d excluded=%d identifiers searched=%d skipped=%d" % (len(included), len(excluded), len(idmap), len(skipped)))


def cmd_final(a):
    docs_dir = Path(a.docs).resolve()
    included, _ = docs_inputs(docs_dir)
    facts_by_repo = {row["repo"]: facts for row, facts in included}
    fields, mrows = read_manifest(str(HERE / "manifest.csv"))
    graph = HERE / "graph"
    graph.mkdir(exist_ok=True)
    edges, pipes, unresolved, seen = [], [], defaultdict(list), set()
    for r in mrows:
        f = HERE / "links" / (repo_dirname(r["repo"]) + ".json")
        if r.get("status") != "verified" or not f.exists():
            continue
        links = json.loads(f.read_text(encoding="utf-8"))
        repo = r["repo"]
        for c in links.get("consumes", []):
            if c.get("resolution") == "internal":
                key = (repo, c.get("to_repo", ""), c.get("id", ""))
                if key not in seen:
                    seen.add(key)
                    edges.append({"from_repo": repo, "to_repo": c.get("to_repo", ""), "kind": "consumes:" + c.get("kind", ""),
                                  "identifier": c.get("id", ""), "evidence_from": c.get("evidence_from", ""),
                                  "evidence_to": c.get("evidence_to", ""), "confidence": "high" if c.get("evidence_to") else "medium"})
            elif c.get("resolution") == "unresolved":
                unresolved[repo].append(c)
        for e in links.get("edges", []):
            key = (repo, e.get("to_repo", ""), e.get("identifier", ""))
            if key not in seen:
                seen.add(key)
                edges.append(dict({k: e.get(k, "") for k in EDGE_FIELDS}, from_repo=repo))
        system = {p.get("name"): p for p in facts_by_repo.get(repo, {}).get("pipelines", [])}
        for p in links.get("pipelines", []):
            src = system.get(p.get("name"), {})
            down = "; ".join("%s/%s" % (d.get("repo", ""), d.get("pipeline", "")) for d in p.get("downstream", []) or [])
            triggers = p.get("triggers") or [{"type": "none_found", "detail": p.get("searched", ""), "source_repo": "", "evidence": ""}]
            for t in triggers:
                pipes.append({"repo": repo, "pipeline": p.get("name", ""), "system": src.get("system", ""),
                              "definition": p.get("definition", "") or src.get("definition", ""),
                              "trigger_type": t.get("type", ""), "trigger_detail": t.get("detail", ""),
                              "trigger_source_repo": t.get("source_repo", "") or repo, "evidence": t.get("evidence", ""),
                              "downstream": down})
    for name, fieldnames, data in (("edges.csv", EDGE_FIELDS, edges), ("pipelines.csv", PIPE_FIELDS, pipes)):
        with open(graph / name, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=fieldnames)
            w.writeheader()
            w.writerows(data)
    out_deg, in_deg = Counter(e["from_repo"] for e in edges), Counter(e["to_repo"] for e in edges)
    with open(graph / "nodes.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["repo", "kind", "purpose", "depends_on", "depended_on_by", "pipelines"])
        for r in mrows:
            facts = facts_by_repo.get(r["repo"], {})
            w.writerow([r["repo"], facts.get("kind", ""), facts.get("purpose", ""), out_deg[r["repo"]], in_deg[r["repo"]],
                        len(facts.get("pipelines", []))])
    isolated = [r["repo"] for r in mrows if not out_deg[r["repo"]] and not in_deg[r["repo"]]]
    (graph / "isolated.md").write_text(
        "# Repositories with no links found (%d)\n\nAn isolated repository is more often a missed link than a true island. "
        "Each one needs a person to confirm.\n\n%s\n" % (len(isolated), "\n".join("- %s" % i for i in isolated) or "None."),
        encoding="utf-8")
    L = ["# Unresolved references (%d)" % sum(len(v) for v in unresolved.values()), "",
         "Things a repository consumes that could not be matched to any repository and are not known to be third-party.", ""]
    for repo in sorted(unresolved):
        L.append("## %s" % repo)
        L += ["- `%s` (%s) — %s — %s" % (c.get("id", ""), c.get("kind", ""), c.get("evidence_from", ""), c.get("note", "")) for c in unresolved[repo]]
        L.append("")
    (graph / "unresolved.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    pairs = defaultdict(set)
    for e in edges:
        pairs[(e["from_repo"], e["to_repo"])].add(e["kind"].split(":")[0])

    def node(n):
        return re.sub(r"[^A-Za-z0-9_]", "_", n)

    mm = ["graph LR"] + ['    %s["%s"] -->|%s| %s["%s"]' % (node(a_), a_, ", ".join(sorted(k)), node(b_), b_)
                         for (a_, b_), k in sorted(pairs.items())]
    (graph / "graph.mmd").write_text("\n".join(mm) + "\n", encoding="utf-8")
    print(json.dumps({"edges": len(edges), "pipeline_rows": len(pipes), "isolated": len(isolated),
                      "unresolved": sum(len(v) for v in unresolved.values())}))


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("command", choices=["candidates", "final"])
    p.add_argument("--docs", default=str(KIT / "02a-repo-docs"))
    a = p.parse_args()
    {"candidates": cmd_candidates, "final": cmd_final}[a.command](a)


if __name__ == "__main__":
    main()
