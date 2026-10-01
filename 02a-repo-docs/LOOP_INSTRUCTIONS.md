# Loop Instructions — repository documentation

You are running a loop. Each iteration does one step, records it, and stops. The state is on disk, not in
the conversation. Never rely on memory of earlier iterations.

All commands are run from the kit root. Use `python3`; if it does not exist use `python`.

```
M=02a-repo-docs/manifest.csv
```

## Every iteration starts the same way

1. Read `02a-repo-docs/TASK.md`, `PROGRESS.md` and `ACCESS_NOTES.md` in that folder.
2. The line `Phase:` in PROGRESS.md tells you which section below to run.
3. If `manifest.csv` exists, run `python3 tools/manifest.py counts $M`.
4. If PROGRESS.md lists a blocking item under "Needs Human Review", report it and stop the loop.

## Every iteration ends the same way

1. Update PROGRESS.md: phase, counts, last run, blockers, what the next iteration should do.
2. Append one entry to `outputs/audit-log.md` (date, phase, repositories touched, checks passed and failed).
3. `Phase: COMPLETE`, `Phase: PILOT_REVIEW` or `Phase: BLOCKED` → stop the loop and tell the user why.
   Otherwise run the next iteration (under `/loop`, with the shortest delay allowed).

---

## Phase: SETUP

1. Run `python3 tools/selftest.py`. The last line must be exactly `ALL TESTS PASSED`. If it fails, or says
   tests were skipped because git is missing, set `Phase: BLOCKED` and report the output.
2. Write the organisation(s) or repository list from the first prompt into TASK.md. If none was given, set
   `Phase: BLOCKED`.
3. Find out how GitHub can be reached on this machine and write it into ACCESS_NOTES.md: `gh auth status`,
   `git --version`, or the GitHub connector. Record the exact commands for (a) listing every repository of
   the organisation including archived ones, (b) an independent count of repositories, (c) cloning.
   Never print or store a token.
4. Check free disk space and record it. If the organisation is large, record the expected clone size.
5. Set `Phase: INVENTORY`.

## Phase: INVENTORY

1. List every repository in scope. Follow pagination to the end.
2. Write one JSON object per repository to `02a-repo-docs/inventory.jsonl` with keys
   `repo, clone_url, archived, default_branch, primary_language, pushed_at`. `repo` is the repository name;
   if more than one organisation is in scope use `org/name`.
3. Create and fill the manifest:
   ```
   python3 tools/manifest.py init $M --columns repo,clone_url,archived,default_branch,primary_language,pushed_at,clone_status,commit_sha,size_class,status,attempts,doc_path,facts_path,verified_at,notes
   python3 tools/manifest.py add $M --jsonl 02a-repo-docs/inventory.jsonl
   ```
4. Get the independent count, then: `python3 02a-repo-docs/verify.py --manifest $M --inventory --expected-count <N>`
5. If `INVENTORY: NOT ACCEPTED`, find the cause and repeat (three attempts, then `Phase: BLOCKED`). If no
   second counting method exists, list twice and record a non-blocking item under "Needs Human Review".
6. Set `Phase: CLONE`.

## Phase: CLONE

1. `python3 02a-repo-docs/clone_all.py --manifest $M --limit 50` (repeat in later iterations until every row
   has a `clone_status`).
2. For each `clone_status=failed`: read the note, retry once with `--only <repo>`. If it still fails:
   `python3 tools/manifest.py set $M <repo> status=needs_human notes="clone failed: <reason>"`.
3. `python3 02a-repo-docs/scan_repo.py --manifest $M --all-cloned`
4. When every row is `cloned`, `empty` or `needs_human`, set `Phase: PILOT`.

## Phase: PILOT

1. Pick three cloned repositories of different kinds (for example an application, a pipeline or data
   repository, and an infrastructure repository), preferably `small` or `medium`.
2. Run the "Worker steps" and "Checker steps" below for each.
3. If TASK.md says `Pilot review: skip`, set `Phase: RUN`. Otherwise set `Phase: PILOT_REVIEW`, tell the user
   the three document paths and the check results, and stop the loop.

## Phase: PILOT_REVIEW

If the user approved, write `Pilot approved: yes` with the date under "Decisions Made", set `Phase: RUN`.
If the user asked for changes, apply them to the pilot documents (and to DOC_TEMPLATE.md if the change is
general), re-run the checker steps, and ask again. Otherwise stop and wait.

## Phase: RUN

One iteration = one repository (up to three when all are `small`).

### Worker steps

1. `python3 tools/manifest.py next $M --n 1 --fields repo,clone_status,commit_sha,size_class,status,notes`
   For a `failed` row, the notes say which check failed: fix that, do not start over.
2. Read `scans/<name>.json`. Its `must_mention` list and its pipeline lists are your checklist.
3. Document the repository in a **fresh context**: hand the work to a subagent with this brief, filled in:
   "Document the repository at `02a-repo-docs/repos/<name>` at commit `<sha>`. Read
   `02a-repo-docs/DOC_TEMPLATE.md` and `02a-repo-docs/scans/<name>.json` first. Read the repository in this
   order: README and docs; dependency files; entry points; **every** CI/CD and orchestration file in full;
   build and infrastructure files; configuration; then the source folders, at least the main modules of each
   top-level folder; then test names. Write `02a-repo-docs/docs/<name>.md` and
   `02a-repo-docs/facts/<name>.json` exactly as the template says. Every claim needs a citation
   `(src: path:LINE)` that you have opened. Do not modify anything under `repos/`. Do not run code. Never
   copy a secret value." If subagents are not available, do the same yourself.
   For a `large` repository, use one subagent per top-level folder to return cited notes, then write the
   document from the notes.
4. For an `empty` clone, write the two files yourself as the template describes for empty repositories.
5. `python3 tools/manifest.py set $M <repo> status=done`

### Checker steps (separate from the worker steps)

1. Independent citation check. Pick 10 citations from the document at random (all of them if there are
   fewer). Give the `loop-checker` subagent the repository path and, for each citation, the sentence that
   carries it, with the request: "For each item open the cited lines and answer PASS or FAIL: do the cited
   lines support the sentence?" If subagents are not available, do it yourself as a separate step and say
   so in the audit log.
2. Write the result to `02a-repo-docs/checks/<name>.json`:
   `{"sampled": [{"citation": "path:LINE", "claim": "the sentence", "result": "PASS", "reason": "..."}]}`
3. If two or more are FAIL: the document is not reliable. Correct those claims, re-read the sections they
   came from, and run the check again with a new sample. Do not edit the check file to make it pass.
4. Deterministic checks (the only thing that can set `verified`):
   `python3 02a-repo-docs/verify.py --manifest $M --repo <repo>`

### When a check fails

`verify.py` records the failure and counts the attempt; three failures make the row `needs_human`.
Fix the cause, not the symptom:

- R4 (coverage): something in the repository was not described. Read it and describe it. Adding the bare
  path to the document without describing what is there is not a fix.
- R6 (pipelines): a pipeline file was not analysed. Read it in full and add it.
- R7 (citations): a cited line does not exist. Open the file and cite the real line, or remove the claim.
- R9 (independent check): see checker step 3.

Never weaken `verify.py`, the scan patterns or the template to make a repository pass. If a check is truly
wrong, fix the script, add a test to `tools/selftest.py`, run it, and record the reason in the audit log.

### Leaving RUN

When `manifest.py counts` shows `"still_open": 0`, set `Phase: FINAL`.

## Phase: FINAL

1. `python3 02a-repo-docs/verify.py --manifest $M --final` — re-checks everything, writes
   `outputs/verification-report.md` and `docs/INDEX.md`.
2. `RESULT: ACCEPTED` → `Phase: COMPLETE`. Failed rows → `Phase: RUN`. Only `needs_human` rows left →
   `Phase: BLOCKED` and list them.
3. Tell the user: how many repositories were documented, the result line, which need a person and why,
   and the most common entries in the "Unknowns" sections.

---

## Safety rules

- GitHub is read-only: clone and list only. No push, pull request, issue, comment or setting change.
- Never modify, build, install or execute anything inside `repos/`.
- Write only inside `02a-repo-docs/`.
- Never copy secret values. If a repository contains one, write `[REDACTED]`, cite the location, and list
  it under "Needs Human Review" as non-blocking so someone can rotate it.
- If unsure whether an action is allowed, do not do it: record it, set `Phase: BLOCKED`, stop.

## Stop conditions

Stop the loop when PROGRESS.md says `Phase: COMPLETE`, `Phase: PILOT_REVIEW` or `Phase: BLOCKED`.
