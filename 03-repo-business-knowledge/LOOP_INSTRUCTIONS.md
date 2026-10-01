# Loop Instructions — business knowledge from the repositories

You are running a loop. Each iteration does one step, records it, and stops. The state is on disk.

All commands are run from the kit root. Use `python3`; if it does not exist use `python`.

```
L=03-repo-business-knowledge
M=03-repo-business-knowledge/manifest.csv
```

## Every iteration starts the same way

1. Read `$L/TASK.md`, `$L/PROGRESS.md` and `$L/ENTRY_GUIDE.md`. The `Phase:` line says which section to run.
2. If `manifest.csv` exists, run `python3 tools/manifest.py counts $M`.
3. If PROGRESS.md lists a blocking item under "Needs Human Review", report it and stop the loop.

## Every iteration ends the same way

1. Update PROGRESS.md and append one entry to `outputs/audit-log.md`.
2. `Phase: COMPLETE`, `Phase: PILOT_REVIEW` or `Phase: BLOCKED` → stop the loop and tell the user why.
   Otherwise run the next iteration.

---

## Phase: SETUP

1. Run `python3 tools/selftest.py`. The last line must be exactly `ALL TESTS PASSED`. If it fails, or says
   tests were skipped because git is missing, set `Phase: BLOCKED` and report the output.
2. `python3 tools/manifest.py counts 02a-repo-docs/manifest.csv`. If rows there are still `pending`, `done` or
   `failed`, set `Phase: BLOCKED` with the note "finish 02a first".
3. `python3 tools/bk.py seed --kind repo --loop $L` — creates the manifest from the verified repositories.
4. Set `Phase: PILOT`.

## Phase: PILOT

Process three repositories of different kinds (prefer ones whose documentation describes application or
data logic) with the worker and checker steps below. Then, unless TASK.md says `Pilot review: skip`, set
`Phase: PILOT_REVIEW`, show the user the three `business/*.json` files and stop. With `skip`, set `Phase: RUN`.

## Phase: PILOT_REVIEW

If the user approved, record `Pilot approved: yes` under "Decisions Made" and set `Phase: RUN`. If they asked
for changes (more detail, different types, things to ignore), update ENTRY_GUIDE.md so every later iteration
follows them, redo the pilot repositories, and ask again. Otherwise stop and wait.

## Phase: RUN

One iteration = one repository.

### Worker steps

1. `python3 tools/manifest.py next $M --n 1 --fields repo,status,notes`
2. Extract in a **fresh context**: hand the work to a subagent with this brief, filled in:
   "Extract business knowledge from the repository at `02a-repo-docs/repos/<name>`. First read
   `03-repo-business-knowledge/ENTRY_GUIDE.md` and `02a-repo-docs/docs/<name>.md`. Then read the repository
   in the order the guide gives. Write `03-repo-business-knowledge/business/<name>.json` exactly as the
   guide specifies. Every entry needs a quote copied verbatim from the file and line you cite. Do not modify
   anything under `02a-repo-docs/`. Do not run code. Report which folders you read and which you did not."
   If subagents are not available, do the same yourself.
3. Record in the audit log which folders were read and which were not. If a top-level folder with source
   code was not read, read it before continuing.
4. `python3 tools/manifest.py set $M <repo> status=done`
   If the verdict is `needs_human`, still set `done`; the verify step moves the row to `needs_human`.

### Checker steps

1. Independent check with the `loop-checker` subagent (or yourself as a separate step, noted in the audit log):
   - verdict `extracted`: pick 8 entries at random (all if fewer). For each give the statement and the
     evidence location. Request: "Open the cited lines. PASS or FAIL: does the code there say what the
     statement says, no more and no less?" Write
     `$L/checks/<name>.json` as `{"sampled": [{"name": "<entry name>", "result": "PASS", "reason": "..."}]}`.
     If two or more FAIL: correct those entries, re-read the areas they came from, and check again with a
     new sample.
   - verdict `no_business_content`: request: "Look through the repository at `02a-repo-docs/repos/<name>`,
     including tests, SQL and configuration. PASS if it truly contains no business rules, terms or
     processes; FAIL and name what you found otherwise." Write `$L/checks/<name>.json` as
     `{"agrees": true, "reason": "..."}`. If the checker disagrees, the verdict was wrong: extract the entries.
2. `python3 tools/bk.py verify --kind repo --loop $L --ids <repo>`

### When a check fails

`bk.py` records the failure and counts the attempt; three failures make the row `needs_human`.

- B4 (quote not found): the quote was paraphrased or the line is wrong. Open the file, copy the text
  exactly, cite the right line. If the code does not say it, delete the entry.
- B3 (fields): fix the entry as the message says.
- B7 (independent check): see checker step 1. Never write a check file without running the check.

### Leaving RUN

When `manifest.py counts` shows `"still_open": 0`, set `Phase: FINAL`.

## Phase: FINAL

1. `python3 tools/bk.py render --kind repo --loop $L`
2. Read `$L/catalog/name-collisions.md`. Write `$L/catalog/conflicts.md`: for each collision group say
   whether the sources describe the same thing consistently, or disagree. For a disagreement, state both
   versions with their sources. Do not pick a winner.
3. `python3 tools/bk.py verify --kind repo --loop $L --final`
4. `RESULT: ACCEPTED` → `Phase: COMPLETE`. Failed rows → `Phase: RUN`. Only `needs_human` rows left → `Phase: BLOCKED`.
5. Tell the user: the result line, the number of entries by type, the number of real conflicts, and that
   `catalog/inferred-for-review.md` and `catalog/no-business-content.md` need a person who knows the domain.

---

## Safety rules

- Read-only towards everything under `02a-repo-docs/`. Write only inside `03-repo-business-knowledge/`.
- Never run code from the clones. Never copy secret values or personal data into entries.
- If unsure whether an action is allowed, do not do it: record it, set `Phase: BLOCKED`, stop.

## Stop conditions

Stop the loop when PROGRESS.md says `Phase: COMPLETE`, `Phase: PILOT_REVIEW` or `Phase: BLOCKED`.
