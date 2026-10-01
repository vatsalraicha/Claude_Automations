# Loop Instructions — Confluence download to Markdown

You are running a loop. Each iteration does one step, records it, and stops. The state is on disk, not in
the conversation. Never rely on memory of earlier iterations.

All commands are run from the kit root (the folder that contains `tools/` and `01-confluence-download/`).
Use `python3`; if it does not exist on this machine use `python`. Short names used below:

```
M=01-confluence-download/manifest.csv
```

## Every iteration starts the same way

1. Read `01-confluence-download/TASK.md`.
2. Read `01-confluence-download/PROGRESS.md`. The line `Phase:` tells you which section below to run.
3. Read `01-confluence-download/CONNECTOR_NOTES.md` (once it has content).
4. If `manifest.csv` exists, run `python3 tools/manifest.py counts $M`.
5. If PROGRESS.md lists a blocking item under "Needs Human Review", do nothing else: report it and stop the loop.

## Every iteration ends the same way

1. Update PROGRESS.md: phase, counts, last run, blockers, what the next iteration should do.
2. Append one entry to `outputs/audit-log.md` (date, phase, page ids touched, checks passed and failed,
   any script change and why).
3. Decide:
   - `Phase: COMPLETE`, `Phase: PILOT_REVIEW` (waiting for the user) or `Phase: BLOCKED` → stop the loop and tell the user why.
   - Otherwise → run the next iteration. Under `/loop`, schedule it with the shortest delay allowed; nothing
     external needs waiting for unless a rate limit was hit.

---

## Phase: SETUP

1. Run `python3 01-confluence-download/tests/run_tests.py`. It must end with `ALL TESTS PASSED`.
   If it does not, set `Phase: BLOCKED` and report the output. Do not continue with broken scripts.
2. Write the Confluence link from the first prompt into TASK.md. If no link was given, set `Phase: BLOCKED`.
3. Read the confluence-connector skill. Without downloading page content yet, find out and write into
   `CONNECTOR_NOTES.md`:
   - how to list every page under a root page or in a space, including pagination to the last page;
   - which fields the listing returns (page id, title, parent id, version, last modified, URL);
   - how to get an independent count of pages in the scope (a second method, for example a CQL count);
   - how to fetch one page body, and in which formats (storage format, rendered HTML, ADF JSON, Markdown);
   - how to list and download attachments, and whether sizes are reported;
   - rate limits and page-size limits;
   - whether the connector can write a response straight to a file, or whether content passes through you.
4. Resolve the link: space key, root page id and title. Write "Resolved scope" into TASK.md.
5. Choose the body format in this order of preference and record it in CONNECTOR_NOTES.md:
   1. **Storage format (XHTML)** → save as `raw/<page_id>.html`. `convert.py` handles this.
   2. **Rendered ("view" / "export") HTML** → save as `raw/<page_id>.html`. `convert.py` handles this.
   3. **ADF JSON only** → `convert.py` does not handle it. Add ADF support to `convert.py`, add an ADF test
      case to `tests/run_tests.py`, run the tests, and only then continue.
   4. **Markdown only** → save as `raw/<page_id>.md`. `convert.py` passes it through and adds front matter.
      The conversion cannot be checked against an original in this case. Record this under
      "Needs Human Review" as non-blocking and say so in the final summary.
6. Choose how bytes reach the disk and record the exact recipe (commands or tool calls) in CONNECTOR_NOTES.md:
   - Preferred: a command that writes the API response directly to the file (a script in the skill with
     output redirected, or a small script that calls the Confluence REST API using credentials the skill
     already has configured). Never ask the user to paste a token into the chat, and never print one.
   - Fallback: the content arrives in your context and you write it with the file tool. Then you must write
     it **verbatim and complete**, set the batch size to 5 in TASK.md, and record under "Needs Human Review"
     (non-blocking): "page content passes through the model; a direct-to-disk fetch would be safer".
7. Test the recipe on one page: fetch it, look at the first and last 20 lines of the raw file, confirm it is
   the whole body in the chosen format. Then delete that test file.
8. Set `Phase: INVENTORY`.

## Phase: INVENTORY

1. List every page in scope using the recipe. Follow pagination until there is no next page.
2. Write one JSON object per page to `01-confluence-download/inventory.jsonl` with these keys (strings):
   `page_id, title, space_key, parent_id, type, version, last_modified, source_url, attachment_count`.
   Leave `attachment_count` empty if the listing does not report it; it is filled when the page is fetched.
3. Create and fill the manifest:
   ```
   python3 tools/manifest.py init $M --columns page_id,title,space_key,parent_id,type,version,last_modified,source_url,attachment_count,empty_body,status,attempts,raw_path,md_path,placeholders,verified_at,notes
   python3 tools/manifest.py add $M --jsonl 01-confluence-download/inventory.jsonl
   ```
4. Get the independent count with the second method. Identify the root ids (pages whose parent is outside
   the scope: normally just the root page, or the top-level pages of a space).
5. Check the inventory:
   ```
   python3 01-confluence-download/verify.py --manifest $M --inventory --expected-count <N> --roots <id,id>
   ```
6. If it prints `INVENTORY: NOT ACCEPTED`, find the cause (missed pagination, a content type counted by one
   method and not the other, duplicate rows) and repeat. After three failed attempts set `Phase: BLOCKED`.
   If no second counting method exists, run the listing twice at different times, compare, and record
   under "Needs Human Review" (non-blocking): "no independent page count available".
7. Record in PROGRESS.md: total pages, expected count, root ids, and any content types present in the scope
   that are not being downloaded.
8. Set `Phase: PILOT`.

## Phase: PILOT

1. Pick 10 pages: the root page, the 4 with the highest `attachment_count`, and the next 5 in manifest order.
2. Run the "Worker steps" and "Checker steps" below for these 10 pages.
3. Run `python3 01-confluence-download/convert.py --manifest $M --index`.
4. Open three of the converted Markdown files yourself and compare each with its raw file, reading both
   fully. Fix converter problems now (see "When a check fails").
5. If TASK.md says `Pilot review: skip`, set `Phase: RUN`.
   Otherwise set `Phase: PILOT_REVIEW`, and tell the user: the three file paths to open, the check results,
   which macros became placeholders, and that replying "continue" starts the full download. Stop the loop.

## Phase: PILOT_REVIEW

- If the user has approved (they replied "continue" or similar), write `Pilot approved: yes` with the date
  under "Decisions Made" in PROGRESS.md, set `Phase: RUN`, and continue.
- If the user asked for changes, make them, re-run the pilot pages through convert and verify, and ask again.
- Otherwise stop the loop and wait.

## Phase: RUN

One iteration = one batch.

### Worker steps

1. Select the batch (failed rows are served first, then pending):
   ```
   python3 tools/manifest.py next $M --n <batch size> --fields page_id,title,status,notes
   ```
   For a `failed` row, read its `notes` first: they say which check failed.
2. For each page, using the recipe in CONNECTOR_NOTES.md:
   - fetch the body to `raw/<page_id>.html` (or `.md` in the Markdown-only case);
   - fetch every attachment to `attachments/<page_id>/<original filename>`;
   - write `attachments/<page_id>/_attachments.json` as a list of `{"filename": ..., "size": ...}` taken
     from what Confluence reports (omit `size` if it is not reported). Skip the folder if there are none.
3. Record what was fetched, one command per page:
   ```
   python3 tools/manifest.py set $M <page_id> raw_path=raw/<page_id>.html attachment_count=<n> empty_body=<yes|no>
   ```
   `empty_body=yes` only when Confluence itself returned an empty body for that page.
4. Convert:
   ```
   python3 01-confluence-download/convert.py --manifest $M --ids <id,id,...>
   ```
   Read the `warnings` in its output. A warning about an unhandled tag means content was kept as plain text;
   look at that page.
5. Mark the batch as done:
   ```
   python3 tools/manifest.py set $M <id,id,...> status=done
   ```
6. If a fetch fails with an authentication, permission or rate-limit error: do not mark anything done.
   For rate limits, wait and retry once. Otherwise record it and set `Phase: BLOCKED`.

### Checker steps (separate from the worker steps; no fixing while checking)

1. Run the deterministic checks. This is the only thing that can set `verified`:
   ```
   python3 01-confluence-download/verify.py --manifest $M --ids <id,id,...>
   ```
2. Independent reading check: give the `loop-checker` subagent three random pages from the batch (raw path
   and Markdown path for each) with this request: "Read the raw file and the Markdown file fully. For each
   page answer PASS or FAIL: is every piece of visible content in the raw page present in the Markdown, in
   the same order, with tables, lists and code intact? Quote the first difference you find. Do not modify
   files." If subagents are not available, do this reading yourself as a separate step and note in the
   audit log that it was not independent. For any FAIL: `python3 tools/manifest.py fail $M <id> --note "<what differs>"`.
3. Every fifth batch, spot-check against live Confluence:
   ```
   python3 01-confluence-download/verify.py --manifest $M --spot-pick 10
   ```
   Re-fetch those pages to `spotcheck/<page_id>.<ext>` with the same recipe, then:
   ```
   python3 01-confluence-download/verify.py --manifest $M --spot-compare
   ```
   For each `DIFF`: fetch the live version number. If it is newer than the manifest, the page was edited:
   update `version` and set the row to `status=pending`. If the version is the same, the earlier fetch was
   wrong: run `manifest.py fail` for the row and re-examine the fetch recipe before the next batch.
   Empty the `spotcheck/` folder afterwards.

### When a check fails

`verify.py` has already recorded the failure and counted the attempt. A row that fails three times becomes
`needs_human` and is never retried. For each failure, find the cause before the next batch:

- **Fetch problem** (D1, D2, D3): the raw file or attachments are incomplete. The row is retried next batch.
  If several pages fail the same way, the recipe is wrong: fix the recipe in CONNECTOR_NOTES.md first.
- **Converter problem** (C6, C7, C10, C11, or a reading-check FAIL): `convert.py` lost or mangled something.
  Fix `convert.py`, add a test case for it to `tests/run_tests.py`, and run the tests until they pass. Then
  re-convert and re-check every page from the raw files already on disk (no re-download):
  ```
  python3 tools/manifest.py bulk $M --where status=verified --set status=done
  python3 01-confluence-download/convert.py --manifest $M --status done
  python3 01-confluence-download/verify.py --manifest $M --status done
  ```
- **Checker false alarm**: only if you have read the raw and the Markdown and they are truly equivalent.
  Fix `verify.py`, add a test case, run the tests, and write the page id and the evidence in the audit log.

Never do any of these: lower `--min-coverage`, delete or skip a check, edit a Markdown page by hand, edit a
raw file, or mark a row done without fetching it.

### Leaving RUN

When `manifest.py counts` shows `"still_open": 0`, set `Phase: RECONCILE`.

## Phase: RECONCILE

Pages change while a long download runs. Compare with the source one more time.

1. Run the inventory listing again into `inventory-recheck.jsonl`, then:
   ```
   python3 tools/manifest.py init 01-confluence-download/manifest-recheck.csv --columns page_id,title,space_key,parent_id,type,version,last_modified,source_url,attachment_count
   python3 tools/manifest.py add 01-confluence-download/manifest-recheck.csv --jsonl 01-confluence-download/inventory-recheck.jsonl
   python3 tools/manifest.py diff $M 01-confluence-download/manifest-recheck.csv --fields version,title,parent_id
   ```
2. Act on the diff:
   - `only_in_second` (new pages): add them to the manifest with `manifest.py add` (they start as pending).
   - `changed`: write the new metadata plus `"status": "pending"` for those ids to a JSONL file and apply it
     with `manifest.py add $M --jsonl <file> --update`.
   - `only_in_first` (deleted or moved out of scope): `manifest.py set $M <id> status=removed_at_source`.
     Keep the local files.
3. Delete `manifest-recheck.csv` and `inventory-recheck.jsonl`. Update the expected count in PROGRESS.md.
4. If anything was re-queued and this was reconcile round 1 or 2, set `Phase: RUN`.
   After round 2, or when the diff is empty, set `Phase: FINAL` and record any remaining differences.

## Phase: FINAL

1. `python3 01-confluence-download/convert.py --manifest $M --index`
2. `python3 01-confluence-download/verify.py --manifest $M --final --expected-count <N> --roots <id,id>`
   This re-checks every page, checks that every page link resolves to a file on disk, and writes
   `outputs/verification-report.md`.
3. If it prints `RESULT: ACCEPTED`: set `Phase: COMPLETE`.
   If not: rows that are `failed` go back through RUN (set `Phase: RUN`). If the only thing left is
   `needs_human` rows or an inventory mismatch that cannot be fixed, set `Phase: BLOCKED`.
4. Tell the user, in plain words: how many pages were downloaded as Markdown, the result line, how many rows
   need a person and why, which macros are placeholders (content that exists only when Confluence renders
   the page), how many links point outside the download, what was out of scope, and every non-blocking
   item recorded under "Needs Human Review".

---

## Safety rules

- Confluence is read-only. Never create, edit, move, delete, comment, label, like or watch anything.
- Write only inside `01-confluence-download/`. A bug fix in `tools/` is the single exception.
- Do not read, print or store credentials, tokens or cookies. If one appears in tool output, do not repeat it.
- Do not summarise, shorten or reword page content at any step.
- If you are unsure whether an action is allowed, do not do it: record the question under
  "Needs Human Review", set `Phase: BLOCKED`, and stop.

## Stop conditions

Stop the loop when PROGRESS.md says `Phase: COMPLETE`, `Phase: PILOT_REVIEW` or `Phase: BLOCKED`.
In every other phase, keep iterating.
