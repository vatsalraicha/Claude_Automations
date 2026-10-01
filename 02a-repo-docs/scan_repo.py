#!/usr/bin/env python3
"""Deterministic inventory of one cloned repository. Standard library only.

Usage:
  python scan_repo.py --manifest manifest.csv --repo NAME      -> writes scans/NAME.json
  python scan_repo.py --manifest manifest.csv --all-cloned

The scan is the checklist for the documentation worker and the yardstick for verify.py:
every path in `must_mention` has to appear in the repository document.
"""
import argparse
import fnmatch
import json
import os
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
from manifest import read_manifest, write_manifest  # noqa: E402

SKIP_DIRS = {".git", "node_modules", "vendor", "dist", "build", "target", ".venv", "venv", "__pycache__",
             ".terraform", ".idea", ".vscode", ".gradle", ".mvn", "bower_components", ".next", ".nuxt",
             "coverage", ".pytest_cache", ".mypy_cache", ".tox", "site-packages"}
MAX_CONTENT_BYTES = 500000

CI_CD = ["*/.github/workflows/*.yml", "*/.github/workflows/*.yaml", ".github/workflows/*.yml", ".github/workflows/*.yaml",
         "Jenkinsfile*", "*/Jenkinsfile*", "*.jenkinsfile", ".gitlab-ci.yml", "*/.gitlab-ci.yml",
         "azure-pipelines*.yml", "*/azure-pipelines*.yml", "azure-pipelines*.yaml", ".circleci/config.yml",
         "bitbucket-pipelines.yml", ".travis.yml", "buildspec*.yml", "*/buildspec*.yml", "buildspec*.yaml",
         "cloudbuild*.yaml", "cloudbuild*.yml", "*/cloudbuild*.yaml", ".drone.yml", ".buildkite/*.yml",
         "appveyor.yml", "codefresh.yml", ".teamcity/*", "skaffold.yaml", "Tiltfile", ".harness/*.yaml",
         ".tekton/*.yaml", "*/.tekton/*.yaml"]
BUILD = ["Dockerfile*", "*/Dockerfile*", "docker-compose*.yml", "*/docker-compose*.yml", "docker-compose*.yaml",
         "Makefile", "*/Makefile", "Procfile", "serverless.yml", "serverless.yaml", "*/serverless.yml",
         "template.yaml", "template.yml", "cdk.json", "Pulumi.yaml", "Chart.yaml", "*/Chart.yaml",
         "kustomization.yaml", "*/kustomization.yaml", "Taskfile.yml", "justfile", "tox.ini", "noxfile.py"]
DEPENDENCY = ["package.json", "*/package.json", "requirements*.txt", "*/requirements*.txt", "pyproject.toml",
              "*/pyproject.toml", "Pipfile", "setup.py", "setup.cfg", "pom.xml", "*/pom.xml", "build.gradle",
              "*/build.gradle", "build.gradle.kts", "*/build.gradle.kts", "go.mod", "*/go.mod", "Cargo.toml",
              "Gemfile", "composer.json", "*.csproj", "*/*.csproj", "*.sln", "environment.yml", "build.sbt",
              "packages.yml", "dbt_project.yml", "*/dbt_project.yml"]
DOCS = ["README*", "*/README*", "CHANGELOG*", "CONTRIBUTING*", "CODEOWNERS", ".github/CODEOWNERS", "docs/CODEOWNERS",
        "OWNERS", "ARCHITECTURE*", "docs/*.md", "docs/*/*.md", "doc/*.md", "adr/*.md", "docs/adr/*.md"]
CONFIG = [".env.example", ".env.sample", ".env.template", "*/.env.example", "application*.yml", "*/application*.yml",
          "application*.yaml", "application*.properties", "*/application*.properties", "config/*.yml",
          "config/*.yaml", "config/*.json", "config/*.toml", "settings*.py", "*/settings*.py", "appsettings*.json",
          "*/appsettings*.json", "values*.yaml", "*/values*.yaml"]

# (label, regex) checked against file content to find orchestration and scheduling definitions
CONTENT_RULES = [
    ("airflow_dag", ("py",), re.compile(r"^\s*(from\s+airflow|import\s+airflow)\b", re.M)),
    ("prefect_flow", ("py",), re.compile(r"^\s*(from\s+prefect|import\s+prefect)\b", re.M)),
    ("dagster_job", ("py",), re.compile(r"^\s*(from\s+dagster|import\s+dagster)\b", re.M)),
    ("k8s_cronjob", ("yml", "yaml"), re.compile(r"^\s*kind:\s*CronJob\b", re.M)),
    ("argo_workflow", ("yml", "yaml"), re.compile(r"^\s*kind:\s*(Workflow|CronWorkflow|WorkflowTemplate|Sensor|EventSource)\b", re.M)),
    ("tekton", ("yml", "yaml"), re.compile(r"^\s*kind:\s*(Pipeline|PipelineRun|Task|TriggerTemplate|EventListener)\b", re.M)),
    ("step_function", ("json",), re.compile(r'"StartAt"\s*:\s*"[^"]+".{0,2000}"States"\s*:', re.S)),
    ("data_factory_pipeline", ("json",), re.compile(r'"activities"\s*:\s*\[.{0,4000}"type"\s*:\s*"[A-Za-z]+"', re.S)),
    ("databricks_job", ("json", "yml", "yaml"), re.compile(r"(notebook_task|spark_python_task|job_clusters)\b")),
    ("scheduled_event_rule", ("tf", "yml", "yaml", "json"), re.compile(r"(schedule_expression|ScheduleExpression|aws_scheduler_schedule|google_cloud_scheduler_job)")),
    ("crontab", ("", "cron", "txt"), re.compile(r"^\s*(\*|[0-9,/-]+)\s+(\*|[0-9,/-]+)\s+(\*|[0-9,/-]+)\s+(\*|[0-9A-Za-z,/-]+)\s+(\*|[0-9A-Za-z,/-]+)\s+\S+", re.M)),
]


def matches(rel, patterns):
    return any(fnmatch.fnmatch(rel, pat) for pat in patterns)


def scan(repo_dir):
    repo_dir = Path(repo_dir)
    top_level = sorted(e.name + ("/" if e.is_dir() else "") for e in repo_dir.iterdir() if e.name != ".git")
    ext = Counter()
    files = total_bytes = 0
    found = {"ci_cd": [], "orchestration": [], "build": [], "dependency": [], "docs": [], "config": []}
    tf_dirs, sql_dirs, migration_dirs = set(), Counter(), set()
    for root, dirs, names in os.walk(repo_dir):
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS)
        for name in sorted(names):
            path = Path(root) / name
            rel = path.relative_to(repo_dir).as_posix()
            files += 1
            try:
                size = path.stat().st_size
            except OSError:
                continue
            total_bytes += size
            suffix = path.suffix.lower().lstrip(".")
            ext[suffix or "(none)"] += 1
            rel_dir = os.path.dirname(rel) or "."
            if suffix == "tf":
                tf_dirs.add(rel_dir)
            if suffix == "sql":
                sql_dirs[rel_dir] += 1
            if re.search(r"(^|/)(migrations?|alembic|flyway|liquibase|changelog)(/|$)", rel_dir, re.I):
                migration_dirs.add(rel_dir)
            if matches(rel, CI_CD):
                found["ci_cd"].append(rel)
                continue
            if matches(rel, BUILD):
                found["build"].append(rel)
            if matches(rel, DEPENDENCY):
                found["dependency"].append(rel)
            if matches(rel, DOCS):
                found["docs"].append(rel)
            if matches(rel, CONFIG):
                found["config"].append(rel)
            if size <= MAX_CONTENT_BYTES and (suffix in ("py", "yml", "yaml", "json", "tf", "cron", "txt", "") or name == "crontab"):
                if suffix in ("txt", "") and "cron" not in name.lower():
                    continue
                try:
                    text = path.read_text(encoding="utf-8", errors="ignore")
                except OSError:
                    continue
                for label, exts, rx in CONTENT_RULES:
                    if suffix in exts and rx.search(text):
                        found["orchestration"].append({"path": rel, "kind": label})
                        break
    size_class = "small" if files < 200 else ("medium" if files < 2000 else "large")

    must = [t for t in top_level if t not in (".gitignore", ".gitattributes", "LICENSE", "LICENSE.md", ".editorconfig")]
    orch_paths = [o["path"] for o in found["orchestration"]]
    for group in (found["ci_cd"], orch_paths):
        if len(group) > 40:  # very many definitions: require each containing folder instead of each file
            must.extend(sorted(set((os.path.dirname(g) or ".") + "/" for g in group)))
        else:
            must.extend(group)
    must.extend(found["build"] if len(found["build"]) <= 40 else sorted(set((os.path.dirname(g) or ".") + "/" for g in found["build"])))
    must.extend(sorted(d + "/" for d in tf_dirs if d != "."))
    seen, must_mention = set(), []
    for m in must:
        if m not in seen and m not in ("./",):
            seen.add(m)
            must_mention.append(m)

    return {
        "file_count": files, "total_bytes": total_bytes, "size_class": size_class,
        "top_level": top_level,
        "extensions": dict(ext.most_common(20)),
        "ci_cd_files": found["ci_cd"],
        "orchestration_files": found["orchestration"],
        "build_files": found["build"],
        "dependency_files": found["dependency"][:100],
        "doc_files": found["docs"][:100],
        "config_files": found["config"][:100],
        "terraform_dirs": sorted(tf_dirs),
        "sql_dirs": dict(sql_dirs.most_common(30)),
        "migration_dirs": sorted(migration_dirs)[:30],
        "must_mention": must_mention,
    }


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--manifest", required=True)
    p.add_argument("--repo")
    p.add_argument("--all-cloned", action="store_true")
    a = p.parse_args()
    manifest = Path(a.manifest).resolve()
    base = manifest.parent
    fields, rows = read_manifest(str(manifest))
    if a.repo:
        targets = [r for r in rows if r["repo"] == a.repo]
        if not targets:
            sys.exit("Not in manifest: %s" % a.repo)
    elif a.all_cloned:
        targets = [r for r in rows if r.get("clone_status") == "cloned"]
    else:
        sys.exit("Give --repo NAME or --all-cloned")
    (base / "scans").mkdir(exist_ok=True)
    for row in targets:
        name = row["repo"].replace("/", "__")
        repo_dir = base / "repos" / name
        if not repo_dir.is_dir():
            print("SKIP  %s  (no clone at repos/%s)" % (row["repo"], name))
            continue
        result = scan(repo_dir)
        result["repo"] = row["repo"]
        result["commit"] = row.get("commit_sha", "")
        (base / "scans" / (name + ".json")).write_text(json.dumps(result, indent=2), encoding="utf-8")
        if "size_class" in row:
            row["size_class"] = result["size_class"]
        print("SCANNED  %s  files=%d size=%s pipelines=%d must_mention=%d" % (
            row["repo"], result["file_count"], result["size_class"],
            len(result["ci_cd_files"]) + len(result["orchestration_files"]), len(result["must_mention"])))
    write_manifest(str(manifest), fields, rows)


if __name__ == "__main__":
    main()
