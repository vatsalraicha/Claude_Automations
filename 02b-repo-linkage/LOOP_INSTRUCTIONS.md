# Loop Instructions — repository linkage

You are running a loop. Each iteration does one step, records it, and stops. The state is on disk.

All commands are run from the kit root. Use `python3`; if it does not exist use `python`.

```
M=02b-repo-linkage/manifest.csv
```

## Every iteration starts the same way

1. Read `02b-repo-linkage/TASK.md` and `PROGRESS.md`. The `Phase:` line says which section to run.
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
2. Check the documentation loop: `python3 tools/manifest.py counts 02a-repo-docs/manifest.csv`. If it has
   rows that are still `pending`, `done` or `failed`, set `Phase: BLOCKED` with the note "finish 02a first".
   Rows that are `needs_human` there are simply left out here and listed in the final report.
3. Run the deterministic search across all clones:
   `python3 02b-repo-linkage/build_graph.py candidates`
   It writes `work/candidates/<repo>.json` for every repository and creates the manifest.
4. Read `work/skipped-identifiers.json`. These repository names and identifiers were too short or too
   generic to search for automatically. For each one, search the clones yourself with a more specific
   pattern (the full `org/name`, an import statement, a URL) and write what you find, with `path:LINE`, to
   `work/manual-mentions.md`. Later iterations must read that file.
5. Set `Phase: PILOT`.

## Phase: PILOT

Process three repositories that have many candidate mentions (`n_mentions` in the manifest), using the
worker and checker steps below. Then, unless TASK.md says `Pilot review: skip`, set `Phase: PILOT_REVIEW`,
show the user the three `links/` files and stop. With `skip`, set `Phase: RUN`.

## Phase: PILOT_REVIEW

If the user approved, record `Pilot approved: yes` under "Decisions Made" and set `Phase: RUN`. Otherwise
apply the requested changes, re-verify the pilot rows, and ask again, or stop and wait.

## Phase: RUN

### Worker steps

1. `python3 tools/manifest.py next $M --n 1 --fields repo,n_consumes,n_mentions,n_cross_trigger_hits,status,notes`
2. Read, for that repository: `work/candidates/<name>.json`, `02a-repo-docs/facts/<name>.json`,
   `02a-repo-docs/docs/<name>.md`, `work/manual-mentions.md`, and `LINKS_TEMPLATE.md`.
3. Resolve every `consumes` item:
   - If the candidates file lists a producer, open both sides and confirm it is the same thing → `internal`.
   - If not, search the other clones for the identifier and variations of it. Found → `internal`.
   - Clearly third-party (a public package, a cloud service, a vendor API) → `external`, with a note.
   - Otherwise → `unresolved`, with a note saying exactly what you searched for.
4. Review every `outgoing_mentions` item: open the sample lines. Decide whether it is a real relationship
   (import, API call, shared workflow, image, data read or write, trigger) or not (comment, example,
   coincidence of names). Record each in `mentions_reviewed`, and each real one in `edges`.
5. For every pipeline in the facts file, find what starts it:
   - triggers written in its own definition file;
   - triggers defined elsewhere: search **all** clones for the pipeline name, the workflow file name, the
     job name, the DAG id, the repository name. Look especially in infrastructure repositories (event rules,
     schedules, bucket notifications, queue subscriptions) and in other pipelines that call this one;
   - if nothing is found anywhere: `no_trigger_found: true` and say what you searched for.
   Also record what each pipeline starts in other repositories under `downstream`.
6. Account for every `trigger_hits` line with `cross_repo: true`: use it as evidence or dismiss it with a reason.
7. Write `02b-repo-linkage/links/<name>.json`. Then `python3 tools/manifest.py set $M <repo> status=done`.

### Checker steps

1. `python3 02b-repo-linkage/verify.py --repo <repo>`
2. For three random `edges` with confidence `high` or `medium`, ask the `loop-checker` subagent: "Open both
   evidence locations. PASS or FAIL: do they show that the first repository uses something the second
   repository provides?" For any FAIL: correct the links file and run step 1 again; if it cannot be
   corrected, `python3 tools/manifest.py fail $M <repo> --note "<edge and reason>"`.

### When a check fails

Fix the cause: resolve the consume that was skipped, review the mention that was skipped, open the file and
cite the real line. Do not delete items from the candidates file, and do not weaken `verify.py`.

### Leaving RUN

When `manifest.py counts` shows `"still_open": 0`, set `Phase: FINAL`.

## Phase: FINAL

1. `python3 02b-repo-linkage/build_graph.py final`
2. Write `02b-repo-linkage/graph/overview.md` from the graph files: the main clusters of repositories and
   what each cluster does; the repositories most depended on; the pipeline chains that cross repositories
   (A triggers B triggers C) with their triggers; the counts of unresolved references, pipelines with no
   trigger found, and isolated repositories. Every statement must be traceable to a row in `edges.csv` or
   `pipelines.csv`.
3. `python3 02b-repo-linkage/verify.py --final`
4. `RESULT: ACCEPTED` → `Phase: COMPLETE`. Failed rows → `Phase: RUN`. Otherwise `Phase: BLOCKED`.
5. Tell the user: the result line, the number of edges and pipelines, and the three lists that need people:
   `graph/unresolved.md`, pipelines with no trigger found, and `graph/isolated.md`.

---

## Safety rules

- Read-only towards GitHub and towards everything under `02a-repo-docs/`.
- Write only inside `02b-repo-linkage/`.
- Never run code from the clones. Never copy secret values.
- If unsure whether an action is allowed, do not do it: record it, set `Phase: BLOCKED`, stop.

## Stop conditions

Stop the loop when PROGRESS.md says `Phase: COMPLETE`, `Phase: PILOT_REVIEW` or `Phase: BLOCKED`.
