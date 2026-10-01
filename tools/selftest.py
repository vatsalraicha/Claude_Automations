#!/usr/bin/env python3
"""Self-test for the scripts used by loops 02a, 02b, 03, 04 and 05.

Builds a tiny fake workspace in a temp folder (two git repositories, two pages, three tickets), runs every
script against it, and checks that good work is verified and bad work is rejected.

Run:  python tools/selftest.py
The last line must be "ALL TESTS PASSED". (Loop 01 has its own test: 01-confluence-download/tests/run_tests.py)
"""
import csv
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

KIT = Path(__file__).resolve().parent.parent
PY = sys.executable
FAILED = []


def check(name, cond, detail=""):
    print("%s  %s" % ("ok  " if cond else "FAIL", name))
    if not cond:
        FAILED.append(name)
        if detail:
            print("      " + str(detail).replace("\n", "\n      "))


def run(*args, cwd=None):
    p = subprocess.run([str(a) for a in args], capture_output=True, text=True, cwd=str(cwd) if cwd else None)
    return p.returncode, p.stdout + p.stderr


def py(*args):
    return run(PY, *args)


def write(path, text):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def dump(path, obj):
    write(path, json.dumps(obj, indent=2))


def rows(path, key):
    with open(path, newline="", encoding="utf-8") as f:
        return {r[key]: r for r in csv.DictReader(f)}


def make_repo(folder, files, message):
    for rel, text in files.items():
        write(folder / rel, text)
    env = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@example.com", GIT_COMMITTER_NAME="t",
               GIT_COMMITTER_EMAIL="t@example.com")
    for cmd in (["git", "init", "-q"], ["git", "add", "-A"], ["git", "commit", "-q", "-m", message]):
        p = subprocess.run(cmd, cwd=str(folder), capture_output=True, text=True, env=env)
        if p.returncode != 0:
            return False
    return True


ORDERS = {
    "README.md": "# orders-service\n\nApproves and charges customer orders.\n",
    "Dockerfile": "FROM python:3.12\nCOPY src /app\n",
    "src/app.py": "import billing_lib\n\nMAX_ORDER_TOTAL = 10000  # orders above this need manual approval (PAY-12)\n\n"
                  "def approve(order):\n    if order.total > MAX_ORDER_TOTAL:\n        return \"manual_review\"\n    return billing_lib.charge(order)\n",
    ".github/workflows/ci.yml": "name: ci\non:\n  push:\n    branches: [main]\njobs:\n  test:\n    runs-on: ubuntu-latest\n    steps:\n      - run: pytest\n",
    ".github/workflows/deploy.yml": "name: deploy\non:\n  workflow_run:\n    workflows: [\"ci\"]\n    types: [completed]\njobs:\n  deploy:\n"
                                    "    uses: acme/billing-lib/.github/workflows/release.yml@main\n",
}
BILLING = {
    "README.md": "# billing-lib\n\nShared charging helpers.\n",
    "setup.py": "from setuptools import setup\n\nsetup(name=\"billing_lib\", version=\"1.0\")\n",
    "billing_lib/__init__.py": "def charge(order):\n    return \"charged\"\n",
    ".github/workflows/release.yml": "name: release\non:\n  workflow_call:\njobs:\n  publish:\n    runs-on: ubuntu-latest\n    steps:\n      - run: python -m build\n",
}

DOC = """# {repo}

Repo: {repo}
Commit: {sha}

## 1. Purpose and owners
{purpose} No owners file was found.

## 2. Languages, frameworks and layout
Python. Top level: {layout}

## 3. Entry points, build, test and run
{entry}

## 4. Configuration and environment variables
None found in the repository files.

## 5. Data stores
None found in the repository files.

## 6. Interfaces exposed
{exposed}

## 7. Dependencies consumed
{consumed}

## 8. Pipelines and triggers
{pipelines}

## 9. Deployment and infrastructure
{deploy}

## 10. Unknowns and open questions
Who owns this repository is unknown.
"""


def main():
    try:
        have_git = run("git", "--version")[0] == 0
    except OSError:
        have_git = False
    if not have_git:
        print("NOTE: git is not available on this machine. Loops 02a, 02b, 03 and 05 need it; their tests are skipped.")

    tmp = Path(tempfile.mkdtemp(prefix="knowledge-loops-selftest-"))
    try:
        kit = tmp / "kit"
        ignore = shutil.ignore_patterns("__pycache__", "repos", "docs", "facts", "scans", "checks", "links", "work", "graph",
                                        "business", "catalog", "tickets", "enrichment", "outputs", "manifest*.csv",
                                        "references.csv", "project-keys.txt", "raw", "pages", "attachments",
                                        "chapters", "HANDBOOK.md", "outline.json")
        for name in ("tools", "02a-repo-docs", "02b-repo-linkage", "05-jira-enrichment", "06-business-handbook"):
            shutil.copytree(KIT / name, kit / name, ignore=ignore)
        for name in ("03-repo-business-knowledge", "04-confluence-business-knowledge", "01-confluence-download"):
            (kit / name).mkdir(parents=True)
        if have_git:
            remotes = tmp / "remotes"
            check("fixture: git repositories created",
                  make_repo(remotes / "orders-service", ORDERS, "PAY-7 initial commit")
                  and make_repo(remotes / "billing-lib", BILLING, "initial commit"))

            # ------------------------------------------------------------------ 02a
            d = kit / "02a-repo-docs"
            m = d / "manifest.csv"
            code, out = py(kit / "tools/manifest.py", "init", m, "--columns",
                           "repo,clone_url,archived,default_branch,primary_language,pushed_at,clone_status,commit_sha,size_class,status,attempts,doc_path,facts_path,verified_at,notes")
            write(d / "inventory.jsonl", "\n".join(json.dumps({"repo": n, "clone_url": str(remotes / n)}) for n in ("orders-service", "billing-lib")))
            code, out = py(kit / "tools/manifest.py", "add", m, "--jsonl", d / "inventory.jsonl")
            check("02a: manifest filled", "added=2" in out, out)
            code, out = py(d / "verify.py", "--manifest", m, "--inventory", "--expected-count", 2)
            check("02a: inventory accepted", code == 0, out)
            code, out = py(d / "clone_all.py", "--manifest", m)
            r = rows(m, "repo")
            check("02a: both repositories cloned with a commit recorded",
                  code == 0 and all(r[n]["clone_status"] == "cloned" and len(r[n]["commit_sha"]) == 40 for n in r), out)
            code, out = py(d / "scan_repo.py", "--manifest", m, "--all-cloned")
            scan = json.loads((d / "scans/orders-service.json").read_text())
            check("02a: scan finds both workflows and the Dockerfile",
                  set(scan["ci_cd_files"]) == {".github/workflows/ci.yml", ".github/workflows/deploy.yml"} and "Dockerfile" in scan["build_files"], scan)
            check("02a: scan lists what the document must mention", "src/" in scan["must_mention"] and ".github/workflows/deploy.yml" in scan["must_mention"], scan["must_mention"])

            sha_a, sha_b = r["orders-service"]["commit_sha"], r["billing-lib"]["commit_sha"]
            doc_a = DOC.format(
                repo="orders-service", sha=sha_a, purpose="Approves and charges customer orders (src: README.md:3).",
                layout="`.github/`, `Dockerfile`, `README.md`, `src/`.",
                entry="The entry point is approve in src/app.py (src: src/app.py:5). Tests run with pytest.",
                exposed="A container image built from the Dockerfile.",
                consumed="The billing_lib package (src: src/app.py:1) and pytest.",
                pipelines="`.github/workflows/ci.yml` runs on push to main. `.github/workflows/deploy.yml` runs after ci completes.",
                deploy="Deployment calls the release workflow of billing-lib.")
            facts_a = {"repo": "orders-service", "commit": sha_a, "kind": "service",
                       "purpose": "Approves and charges customer orders through the billing library.", "owners": [], "languages": ["python"],
                       "produces": [{"kind": "image", "id": "orders-service-image", "evidence": "Dockerfile:1"}],
                       "consumes": [{"kind": "package", "id": "billing_lib", "evidence": "src/app.py:1", "external": "no"},
                                    {"kind": "package", "id": "pytest", "evidence": ".github/workflows/ci.yml:9", "external": "yes"}],
                       "pipelines": [{"name": "ci", "system": "github_actions", "definition": ".github/workflows/ci.yml", "runs": "pytest",
                                      "triggers": [{"type": "push", "detail": "main", "evidence": ".github/workflows/ci.yml:3"}]},
                                     {"name": "deploy", "system": "github_actions", "definition": ".github/workflows/deploy.yml",
                                      "runs": "calls the release workflow",
                                      "triggers": [{"type": "upstream", "detail": "after ci", "evidence": ".github/workflows/deploy.yml:3"}]}],
                       "not_pipelines": [], "unknowns": ["owners"]}
            doc_b = DOC.format(
                repo="billing-lib", sha=sha_b, purpose="Shared charging helpers (src: README.md:3).",
                layout="`.github/`, `README.md`, `billing_lib/`, `setup.py`.",
                entry="The charge function (src: billing_lib/__init__.py:1). Built with python -m build.",
                exposed="The billing_lib Python package (src: setup.py:3).",
                consumed="None found in the repository files.",
                pipelines="`.github/workflows/release.yml` is a reusable workflow called by other repositories.",
                deploy="Publishes a Python package build.")
            facts_b = {"repo": "billing-lib", "commit": sha_b, "kind": "library",
                       "purpose": "Shared charging helpers used by other services.", "owners": [], "languages": ["python"],
                       "produces": [{"kind": "package", "id": "billing_lib", "evidence": "setup.py:3"}], "consumes": [],
                       "pipelines": [{"name": "release", "system": "github_actions", "definition": ".github/workflows/release.yml",
                                      "runs": "python -m build", "triggers": [{"type": "upstream", "detail": "workflow_call", "evidence": ".github/workflows/release.yml:3"}]}],
                       "not_pipelines": [], "unknowns": []}
            write(d / "docs/orders-service.md", doc_a.replace("`.github/workflows/deploy.yml` runs after ci completes.", ""))
            dump(d / "facts/orders-service.json", facts_a)
            write(d / "docs/billing-lib.md", doc_b)
            dump(d / "facts/billing-lib.json", facts_b)
            time.sleep(0.05)
            dump(d / "checks/orders-service.json", {"sampled": [{"citation": c, "claim": "x", "result": "PASS"} for c in ("README.md:3", "src/app.py:5", "src/app.py:1")]})
            dump(d / "checks/billing-lib.json", {"sampled": [{"citation": c, "claim": "x", "result": "PASS"} for c in ("README.md:3", "billing_lib/__init__.py:1", "setup.py:3")]})
            py(kit / "tools/manifest.py", "set", m, "orders-service,billing-lib", "status=done")
            code, out = py(d / "verify.py", "--manifest", m, "--repo", "orders-service")
            check("02a: document that omits a workflow file is rejected", code != 0 and "FAIL  R4" in out and "deploy.yml" in out, out)
            write(d / "docs/orders-service.md", doc_a)
            code, out = py(d / "verify.py", "--manifest", m, "--repo", "orders-service")
            check("02a: stale independent check is rejected", code != 0 and "FAIL  R9" in out, out)
            time.sleep(0.05)
            os.utime(d / "checks/orders-service.json", None)
            bad = dict(facts_a, pipelines=facts_a["pipelines"][:1])
            dump(d / "facts/orders-service.json", bad)
            code, out = py(d / "verify.py", "--manifest", m, "--repo", "orders-service", "--no-update")
            check("02a: pipeline missing from the facts file is rejected", "FAIL  R6" in out, out)
            bad = json.loads(json.dumps(facts_a))
            bad["consumes"][0]["evidence"] = "src/app.py:99"
            dump(d / "facts/orders-service.json", bad)
            code, out = py(d / "verify.py", "--manifest", m, "--repo", "orders-service", "--no-update")
            check("02a: citation to a line that does not exist is rejected", "FAIL  R7" in out, out)
            dump(d / "facts/orders-service.json", facts_a)
            code, out = py(d / "verify.py", "--manifest", m, "--status", "failed")
            code2, out2 = py(d / "verify.py", "--manifest", m, "--status", "done")
            r = rows(m, "repo")
            check("02a: complete, cited documents are verified", r["orders-service"]["status"] == "verified" and r["billing-lib"]["status"] == "verified", out + out2)
            code, out = py(d / "verify.py", "--manifest", m, "--final")
            check("02a: final report ACCEPTED", code == 0 and "RESULT: ACCEPTED" in (d / "outputs/verification-report.md").read_text(), out)

            # ------------------------------------------------------------------ 02b
            b = kit / "02b-repo-linkage"
            code, out = py(b / "build_graph.py", "candidates")
            cand = json.loads((b / "work/candidates/orders-service.json").read_text())
            targets = set((x["target_repo"], x["identifier"]) for x in cand["outgoing_mentions"])
            check("02b: candidate search finds the package import and the workflow reference",
                  targets == {("billing-lib", "billing_lib"), ("billing-lib", "billing-lib")}, targets)
            cross = [(h["path"], h["line"]) for h in cand["trigger_hits"] if h["cross_repo"]]
            check("02b: cross-repository trigger lines found", (".github/workflows/deploy.yml", 3) in cross and (".github/workflows/deploy.yml", 8) in cross, cand["trigger_hits"])
            check("02b: producer matched for the consumed package", cand["consumes"][0]["producers"] == [{"repo": "billing-lib", "kind": "package"}], cand["consumes"])
            links_a = {"repo": "orders-service",
                       "consumes": [{"kind": "package", "id": "billing_lib", "resolution": "internal", "to_repo": "billing-lib",
                                     "evidence_from": "src/app.py:1", "evidence_to": "billing-lib:setup.py:3", "note": ""},
                                    {"kind": "package", "id": "pytest", "resolution": "external", "evidence_from": ".github/workflows/ci.yml:9",
                                     "note": "pytest is a public test framework from PyPI"}],
                       "edges": [{"to_repo": "billing-lib", "kind": "uses_workflow", "identifier": "release.yml",
                                  "evidence_from": ".github/workflows/deploy.yml:8", "evidence_to": "billing-lib:.github/workflows/release.yml:3", "confidence": "high"}],
                       "mentions_reviewed": [{"target_repo": "billing-lib", "identifier": "billing_lib", "is_edge": True, "reason": "imports the package"},
                                             {"target_repo": "billing-lib", "identifier": "billing-lib", "is_edge": True, "reason": "calls its reusable workflow"}],
                       "pipelines": [{"name": "ci", "triggers": [{"type": "push", "detail": "main", "source_repo": "orders-service", "evidence": ".github/workflows/ci.yml:3"}]},
                                     {"name": "deploy", "triggers": [{"type": "upstream", "detail": "runs after ci completes", "source_repo": "orders-service", "evidence": ".github/workflows/deploy.yml:3"}],
                                      "downstream": [{"repo": "billing-lib", "pipeline": "release", "evidence": ".github/workflows/deploy.yml:8"}]}],
                       "trigger_hits_dismissed": []}
            links_b = {"repo": "billing-lib", "consumes": [], "edges": [], "mentions_reviewed": [],
                       "pipelines": [{"name": "release", "triggers": [{"type": "upstream", "detail": "called by the deploy workflow of orders-service",
                                                                        "source_repo": "orders-service", "evidence": "orders-service:.github/workflows/deploy.yml:8"}]}],
                       "trigger_hits_dismissed": [{"path": ".github/workflows/release.yml", "line": 3, "reason": "declares the workflow as callable; the caller is recorded as the trigger"}]}
            incomplete = json.loads(json.dumps(links_a))
            incomplete["consumes"].pop()
            incomplete["mentions_reviewed"].pop()
            incomplete["pipelines"][1]["triggers"][0]["evidence"] = ".github/workflows/deploy.yml:1"
            dump(b / "links/orders-service.json", incomplete)
            dump(b / "links/billing-lib.json", links_b)
            code, out = py(b / "verify.py", "--repo", "orders-service", "--no-update")
            check("02b: unresolved consume, unreviewed mention and unused trigger line are rejected",
                  "FAIL  L2" in out and "FAIL  L3" in out and "FAIL  L5" in out, out)
            dump(b / "links/orders-service.json", links_a)
            py(kit / "tools/manifest.py", "set", b / "manifest.csv", "orders-service,billing-lib", "status=done")
            code, out = py(b / "verify.py", "--status", "done")
            r = rows(b / "manifest.csv", "repo")
            check("02b: complete links files are verified", all(x["status"] == "verified" for x in r.values()), out)
            code, out = py(b / "build_graph.py", "final")
            edges = (b / "graph/edges.csv").read_text()
            pipes = (b / "graph/pipelines.csv").read_text()
            check("02b: graph has the package edge and the workflow edge", "consumes:package,billing_lib" in edges and "uses_workflow,release.yml" in edges, edges)
            check("02b: pipeline table records the cross-repository trigger", "billing-lib,release,github_actions" in pipes and "orders-service" in pipes.split("billing-lib,release")[1], pipes)
            code, out = py(b / "verify.py", "--final")
            check("02b: final is NOT ACCEPTED until overview.md is written", code != 0 and "overview.md" in (b / "outputs/verification-report.md").read_text(), out)
            write(b / "graph/overview.md", "# Overview\n")
            code, out = py(b / "verify.py", "--final")
            check("02b: final report ACCEPTED", code == 0, out)

            # ------------------------------------------------------------------ 03
            k = kit / "03-repo-business-knowledge"
            code, out = py(kit / "tools/bk.py", "seed", "--kind", "repo", "--loop", k.name)
            check("03: manifest seeded from verified repositories", "added=2" in out, out)
            entry = {"type": "rule", "name": "Manual approval threshold",
                     "statement": "Orders with a total above 10000 are sent to manual review instead of being charged automatically.",
                     "evidence": [{"where": "src/app.py:6", "quote": "if order.total > MAX_ORDER_TOTAL:"}],
                     "basis": "stated", "confidence": "high", "related": ["orders"], "jira_keys": ["PAY-12"]}
            invented = dict(entry, evidence=[{"where": "src/app.py:6", "quote": "orders over fifty thousand are rejected"}])
            dump(k / "business/orders-service.json", {"source": "orders-service", "verdict": "extracted", "reason": "", "entries": [invented]})
            dump(k / "business/billing-lib.json", {"source": "billing-lib", "verdict": "no_business_content",
                                                    "reason": "Only packaging metadata and a charge stub without any rules.", "entries": []})
            time.sleep(0.05)
            dump(k / "checks/orders-service.json", {"sampled": [{"name": "Manual approval threshold", "result": "PASS", "reason": "line 6 compares the total"}]})
            dump(k / "checks/billing-lib.json", {"agrees": True, "reason": "the repository holds only packaging and a stub"})
            py(kit / "tools/manifest.py", "set", k / "manifest.csv", "orders-service,billing-lib", "status=done")
            code, out = py(kit / "tools/bk.py", "verify", "--kind", "repo", "--loop", k.name, "--ids", "orders-service", "--no-update")
            check("03: a quote that is not in the code is rejected", "FAIL  B4" in out, out)
            dump(k / "business/orders-service.json", {"source": "orders-service", "verdict": "extracted", "reason": "", "entries": [entry]})
            time.sleep(0.05)
            os.utime(k / "checks/orders-service.json", None)
            code, out = py(kit / "tools/bk.py", "verify", "--kind", "repo", "--loop", k.name, "--status", "done")
            r = rows(k / "manifest.csv", "repo")
            check("03: grounded entries and a confirmed empty verdict are verified",
                  r["orders-service"]["status"] == "verified" and r["billing-lib"]["verdict"] == "no_business_content" and r["billing-lib"]["status"] == "verified", out)
            code, out = py(kit / "tools/bk.py", "render", "--kind", "repo", "--loop", k.name)
            check("03: catalog rendered", "Manual approval threshold" in (k / "catalog/rules-catalog.md").read_text()
                  and "billing-lib" in (k / "catalog/no-business-content.md").read_text(), out)
            write(k / "catalog/conflicts.md", "# Conflicts\n\nNone.\n")
            code, out = py(kit / "tools/bk.py", "verify", "--kind", "repo", "--loop", k.name, "--final")
            check("03: final report ACCEPTED", code == 0, out)

        # ------------------------------------------------------------------ 04
        c = kit / "01-confluence-download"
        write(c / "pages/2001-refund-policy.md",
              "---\ntitle: \"Refund policy\"\npage_id: \"2001\"\n---\n\n# Refund policy\n\n## Refund window\n\n"
              "Customers may request a **refund within 30 days** of purchase. See PAY-12.\n\n"
              "Refund data is loaded into Snowflake every night by the Refunds team for the Finance reporting group.\n")
        write(c / "pages/2002-team-lunch.md", "---\ntitle: \"Team lunch\"\npage_id: \"2002\"\n---\n\n# Team lunch\n\nPizza on Friday.\n")
        with open(c / "manifest.csv", "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["page_id", "title", "last_modified", "md_path", "status", "attempts", "notes"])
            w.writerow(["2001", "Refund policy", "2025-03-01", "pages/2001-refund-policy.md", "verified", "0", ""])
            w.writerow(["2002", "Team lunch", "2021-01-01", "pages/2002-team-lunch.md", "verified", "0", ""])
            w.writerow(["2003", "Not downloaded", "", "", "needs_human", "3", ""])
        g = kit / "04-confluence-business-knowledge"
        code, out = py(kit / "tools/bk.py", "seed", "--kind", "page", "--loop", g.name)
        check("04: only verified pages are seeded", "added=2" in out and "excluded_because_source_not_verified=1" in out, out)
        page_entry = {"type": "policy", "name": "Refund window", "statement": "Customers can ask for a refund up to 30 days after purchase.",
                      "evidence": [{"where": "Refund window", "quote": "refund within 30 days of purchase"}],
                      "basis": "stated", "confidence": "high", "related": [], "jira_keys": ["PAY-12"]}
        wrong_heading = dict(page_entry, evidence=[{"where": "Chargebacks", "quote": "refund within 30 days of purchase"}])
        dump(g / "business/2001.json", {"source": "2001", "verdict": "extracted", "reason": "", "entries": [wrong_heading]})
        dump(g / "business/2002.json", {"source": "2002", "verdict": "no_business_content", "reason": "A social announcement about a team lunch on Friday.", "entries": []})
        py(kit / "tools/manifest.py", "set", g / "manifest.csv", "2001,2002", "status=done")
        code, out = py(kit / "tools/bk.py", "verify", "--kind", "page", "--loop", g.name, "--status", "done", "--no-update")
        check("04: a heading that is not on the page is rejected", "is not in the page" in out, out)
        check("04: an empty verdict without an independent check is rejected", "FAIL  B7" in out, out)
        dump(g / "business/2001.json", {"source": "2001", "verdict": "extracted", "reason": "", "entries": [page_entry]})
        time.sleep(0.05)
        dump(g / "checks/2002.json", {"agrees": True, "reason": "the page only announces a lunch"})
        code, out = py(kit / "tools/bk.py", "verify", "--kind", "page", "--loop", g.name, "--status", "done")
        r = rows(g / "manifest.csv", "page_id")
        check("04: quote across markdown formatting is found and pages are verified", all(x["status"] == "verified" for x in r.values()), out)
        py(kit / "tools/bk.py", "render", "--kind", "page", "--loop", g.name)
        check("04: catalog shows the page title and date", "last modified 2025-03-01" in (g / "catalog/rules-catalog.md").read_text())

        # ------------------------------------------------------------------ 06
        h = kit / "06-business-handbook"
        hb = h / "handbook.py"
        code, out = py(hb, "tree", "--platforms", "Snowflake,Databricks")
        check("06: page tree and platform index written", "[2001] Refund policy" in (h / "work/tree.md").read_text()
              and "## Snowflake (1 pages)" in (h / "work/platform-mentions.md").read_text(), out)
        outline = {"organisation": "Payments Intelligence", "platforms": ["Snowflake", "Databricks"],
                   "areas": [{"id": "refunds", "title": "Refunds", "team": "Refunds", "kind": "team", "pages": ["2001"]},
                             {"id": "overview", "title": "Payments Intelligence — overview", "team": "", "kind": "overview", "pages": []}]}
        dump(h / "outline.json", outline)
        code, out = py(hb, "verify-outline")
        check("06: outline that leaves a page unassigned is rejected", code != 0 and "FAIL  O4" in out and "2002" in out, out)
        outline["areas"][0]["pages"] = ["2001", "2002"]
        dump(h / "outline.json", outline)
        code, out = py(hb, "verify-outline", "--write-manifest")
        r = rows(h / "manifest.csv", "area")
        check("06: complete outline accepted, overview queued last", code == 0 and list(r) == ["refunds", "overview"], out)

        nd = "Not documented in the pages for this area."
        def team_chapter(why, process, platforms, not_used="None."):
            return ("# Refunds\n\nArea: refunds\n\n## 1. Why this team exists\n%s\n\n## 2. People, roles and ownership\n%s\n\n"
                    "## 3. What the team delivers\n%s\n\n## 4. Consumers and stakeholders\n"
                    "The Finance reporting group receives the refund data. [p:2001]\n\n## 5. Processes followed\n%s\n\n"
                    "## 6. Platforms and tools\n%s\n\n## 7. Data and reporting\n%s\n\n## 8. Rules, policies and service levels\n%s\n\n"
                    "## 9. History and decisions\n%s\n\n## 10. Gaps, contradictions and stale content\n%s\n\n## Pages not used\n%s\n"
                    % (why, nd, nd, process, platforms, nd, nd, nd, nd, not_used))
        good_platforms = "### Snowflake\nRefund data is loaded every night by the Refunds team. [p:2001]\n\n### Databricks\n" + nd
        bad = team_chapter("The team was founded to cut refund fraud across the EMEA region.",
                           "- Customers may request a refund within 45 days of purchase. [p:2001]",
                           "### Snowflake\nSnowflake is a cloud data warehouse.")
        write(h / "chapters/refunds.md", bad)
        py(kit / "tools/manifest.py", "set", h / "manifest.csv", "refunds", "status=done")
        code, out = py(hb, "verify", "--area", "refunds", "--no-update")
        check("06: paragraph without a source is rejected", "FAIL  H2" in out, out)
        check("06: number that is not on the cited page is rejected", "FAIL  H4" in out and "45" in out, out)
        check("06: platform described from general knowledge, or left out, is rejected", "FAIL  H6" in out and "Databricks" in out and "Snowflake" in out, out)
        check("06: chapter without an independent check is rejected", "FAIL  H9" in out, out)
        empty = team_chapter(nd, nd, "### Snowflake\n" + nd + "\n\n### Databricks\n" + nd, "- [p:2001] nothing relevant on this page")
        write(h / "chapters/refunds.md", empty.replace("The Finance reporting group receives the refund data. [p:2001]", nd))
        code, out = py(hb, "verify", "--area", "refunds", "--no-update")
        check("06: a page with catalogued business knowledge cannot be set aside as not used",
              "FAIL  H5" in out and "loop 04 found business knowledge" in out, out)
        check("06: a platform the pages mention cannot be marked not documented", "FAIL  H6" in out and "Snowflake: 1 page(s) mention it" in out, out)
        write(h / "chapters/refunds.md", team_chapter("The Refunds team handles refund requests from customers. [p:2001]",
                                                      "### Refund request\n- Customers may request a refund within 30 days of purchase. [p:2001]",
                                                      good_platforms))
        time.sleep(0.05)
        dump(h / "checks/refunds.json", {"sampled": [
            {"block": "The Refunds team handles refund requests from customers. [p:2001]", "pages": ["2001"], "result": "PASS", "reason": "stated"},
            {"block": "The Finance reporting group receives the refund data. [p:2001]", "pages": ["2001"], "result": "PASS", "reason": "stated"},
            {"block": "- Customers may request a refund within 30 days of purchase. [p:2001]", "pages": ["2001"], "result": "PASS", "reason": "stated"},
            {"block": "Refund data is loaded every night by the Refunds team. [p:2001]", "pages": ["2001"], "result": "PASS", "reason": "stated"}], "left_out": []})
        overview = ("# Payments Intelligence — overview\n\nArea: overview\n\n## 1. Why it exists\n" + nd + "\n\n## 2. Teams and what each owns\n"
                    "### Refunds\nThe Refunds team loads refund data every night. [p:2001]\n\n## 3. Consumers\n"
                    "The Finance reporting group consumes refund data. [p:2001]\n\n## 4. Processes followed\n"
                    "- Refund request (Refunds): customers may request a refund within 30 days of purchase. [p:2001]\n\n"
                    "## 5. Platforms and tools\n### Snowflake\nThe Refunds team loads refund data into it every night. [p:2001]\n\n"
                    "### Databricks\n" + nd + "\n\n## 6. How work and data flow across teams\n" + nd +
                    "\n\n## 7. Gaps, contradictions and stale content\n" + nd + "\n\n## Pages not used\nNone.\n")
        write(h / "chapters/overview.md", overview)
        time.sleep(0.05)
        dump(h / "checks/overview.json", {"sampled": [
            {"block": "The Refunds team loads refund data every night. [p:2001]", "result": "PASS"},
            {"block": "The Finance reporting group consumes refund data. [p:2001]", "result": "PASS"},
            {"block": "- Refund request (Refunds): customers may request a refund within 30 days of purchase. [p:2001]", "result": "PASS"},
            {"block": "The Refunds team loads refund data into it every night. [p:2001]", "result": "PASS"}]})
        py(kit / "tools/manifest.py", "set", h / "manifest.csv", "overview", "status=done")
        code, out = py(hb, "verify", "--area", "overview")
        check("06: overview is not checked while a team chapter is still open", "SKIPPED  overview" in out, out)
        code, out = py(hb, "verify", "--area", "refunds")
        check("06: grounded, cited team chapter is verified", rows(h / "manifest.csv", "area")["refunds"]["status"] == "verified", out)
        code, out = py(hb, "verify", "--area", "overview")
        check("06: overview chapter is verified", rows(h / "manifest.csv", "area")["overview"]["status"] == "verified", out)
        code, out = py(hb, "verify", "--final")
        check("06: final is NOT ACCEPTED before the handbook is assembled", code != 0, out)
        code, out = py(hb, "assemble")
        book = (h / "HANDBOOK.md").read_text()
        check("06: handbook assembled with overview first and linked sources",
              book.index("Why it exists") < book.index("Why this team exists")
              and "[p:2001](../01-confluence-download/pages/2001-refund-policy.md)" in book and "## Source index" in book, book)
        check("06: catalogued facts from loop 04 are attached to the chapter", "**Refund window** (policy)" in book, book)
        code, out = py(hb, "verify", "--final")
        check("06: final report ACCEPTED", code == 0, out)

        if have_git:
            # ------------------------------------------------------------------ 05
            j = kit / "05-jira-enrichment"
            write(j / "project-keys.txt", "PAY\n")
            code, out = py(j / "jira_tools.py", "keys")
            r = rows(j / "manifest.csv", "key")
            refs = (j / "references.csv").read_text()
            check("05: keys found in a page, in code and in a commit message", set(r) == {"PAY-7", "PAY-12"}, out)
            check("05: references record where each key was seen", "PAY-12,page,2001" in refs and "PAY-12,repo,orders-service,src/app.py:3" in refs and "commit" in refs, refs)
            ticket = {"key": "PAY-12", "summary": "Manual review for large orders", "type": "Story", "status": "Done", "resolution": "Done",
                      "created": "2024-01-10", "updated": "2024-02-01", "parent": "", "epic": "", "links": [{"type": "relates to", "key": "PAY-99"}],
                      "description": "Finance requires that any order above 10000 is reviewed by a person before the customer is charged.",
                      "acceptance_criteria": "Orders above the limit are not charged automatically.", "comments": [],
                      "why": "Finance wanted a human check on large orders to reduce fraud losses, so orders above the limit go to manual review.",
                      "entries": [{"type": "rule", "name": "Large order review", "statement": "Orders above 10000 must be reviewed by a person before charging.",
                                   "evidence": [{"where": "description", "quote": "any order above 10000 is reviewed by a person"}],
                                   "basis": "stated", "confidence": "high", "related": [], "jira_keys": []}]}
            dump(j / "tickets/PAY-12.json", ticket)
            py(kit / "tools/manifest.py", "set", j / "manifest.csv", "PAY-12", "status=done")
            code, out = py(j / "jira_tools.py", "verify", "--ids", "PAY-12", "--no-update")
            check("05: ticket with an unqueued linked ticket is rejected", "FAIL  J5" in out, out)
            code, out = py(j / "jira_tools.py", "linked")
            r = rows(j / "manifest.csv", "key")
            check("05: linked ticket added one hop out", r.get("PAY-99", {}).get("depth") == "1", out)
            code, out = py(j / "jira_tools.py", "verify", "--ids", "PAY-12")
            check("05: grounded ticket is verified", rows(j / "manifest.csv", "key")["PAY-12"]["status"] == "verified", out)
            dump(j / "tickets/PAY-99.json", dict(ticket, key="PAY-99", links=[{"type": "relates to", "key": "PAY-500"}], entries=[]))
            py(kit / "tools/manifest.py", "set", j / "manifest.csv", "PAY-99", "status=done")
            code, out = py(j / "jira_tools.py", "verify", "--ids", "PAY-99")
            py(j / "jira_tools.py", "linked")
            r = rows(j / "manifest.csv", "key")
            check("05: links of a linked ticket are not followed", r["PAY-99"]["status"] == "verified" and "PAY-500" not in r, out)
            py(kit / "tools/manifest.py", "set", j / "manifest.csv", "PAY-7", "status=not_found", "notes=Jira returned issue does not exist")
            py(j / "jira_tools.py", "render")
            by_page = (j / "enrichment/by-page.md").read_text()
            check("05: enrichment links the page to the ticket and its reason", "2001 — Refund policy" in by_page and "Finance wanted a human check" in by_page, by_page)
            check("05: enrichment by repository", "orders-service" in (j / "enrichment/by-repo.md").read_text())
            code, out = py(j / "jira_tools.py", "verify", "--final")
            check("05: final report ACCEPTED", code == 0, out)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print()
    if FAILED:
        print("%d TEST(S) FAILED" % len(FAILED))
        sys.exit(1)
    print("ALL TESTS PASSED" if have_git else "ALL TESTS PASSED (git-dependent tests skipped: install git before running loops 02a, 02b, 03 and 05)")


if __name__ == "__main__":
    main()
