#!/usr/bin/env python3
"""Clone every repository in the manifest into repos/. Standard library only. Read-only towards the remote.

Usage:
  python clone_all.py --manifest manifest.csv [--only repoA,repoB] [--limit 20]

For each row whose clone_status is not `cloned` or `empty`:
  git clone --filter=blob:none <clone_url> repos/<repo>     (full history, file contents fetched on demand)
  falls back to a plain clone if the server refuses the filter.
Fills clone_status (cloned | empty | failed), commit_sha and default_branch. Never changes `status`.
"""
import argparse
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
from manifest import read_manifest, write_manifest, add_note  # noqa: E402


def repo_dirname(repo):
    return repo.replace("/", "__")


def git(args, cwd=None):
    try:
        p = subprocess.run(["git"] + args, cwd=cwd, capture_output=True, text=True)
    except OSError as e:
        return 1, "", str(e)
    return p.returncode, p.stdout.strip(), p.stderr.strip()


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--manifest", required=True)
    p.add_argument("--only")
    p.add_argument("--limit", type=int)
    a = p.parse_args()

    manifest = Path(a.manifest).resolve()
    base = manifest.parent
    fields, rows = read_manifest(str(manifest))
    only = set(x.strip() for x in a.only.split(",")) if a.only else None
    (base / "repos").mkdir(exist_ok=True)
    done = 0
    summary = {"cloned": 0, "empty": 0, "failed": 0, "skipped": 0}
    for row in rows:
        if only and row["repo"] not in only:
            continue
        if row.get("clone_status") in ("cloned", "empty"):
            summary["skipped"] += 1
            continue
        if a.limit and done >= a.limit:
            break
        done += 1
        dest = base / "repos" / repo_dirname(row["repo"])
        if not (dest / ".git").exists():
            url = row.get("clone_url", "")
            if not url:
                row["clone_status"] = "failed"
                add_note(row, "clone_url is empty")
                summary["failed"] += 1
                continue
            code, _, err = git(["clone", "--quiet", "--filter=blob:none", url, str(dest)])
            if code != 0:
                shutil.rmtree(dest, ignore_errors=True)
                code, _, err = git(["clone", "--quiet", url, str(dest)])
            if code != 0:
                shutil.rmtree(dest, ignore_errors=True)
                row["clone_status"] = "failed"
                add_note(row, "clone failed: %s" % err[-200:])
                summary["failed"] += 1
                print("FAILED  %s  %s" % (row["repo"], err[-200:]))
                continue
        code, sha, _ = git(["rev-parse", "HEAD"], cwd=str(dest))
        if code != 0:
            row["clone_status"], row["commit_sha"] = "empty", ""
            summary["empty"] += 1
            print("EMPTY   %s" % row["repo"])
        else:
            row["clone_status"], row["commit_sha"] = "cloned", sha
            code, branch, _ = git(["rev-parse", "--abbrev-ref", "HEAD"], cwd=str(dest))
            if code == 0 and not row.get("default_branch"):
                row["default_branch"] = branch
            summary["cloned"] += 1
            print("CLONED  %s  %s" % (row["repo"], sha[:12]))
        write_manifest(str(manifest), fields, rows)
    write_manifest(str(manifest), fields, rows)
    print(summary)
    sys.exit(1 if summary["failed"] else 0)


if __name__ == "__main__":
    main()
