# Knowledge loops kit

This folder contains seven loops. Each loop lives in its own folder and is driven by three files in that folder:

- `TASK.md` — the goal, the scope, what may and may not be written
- `LOOP_INSTRUCTIONS.md` — the procedure for one iteration, phase by phase
- `PROGRESS.md` — the current state; the `Phase:` line says what to do next

| Folder | What it does | Needs first |
|---|---|---|
| `01-confluence-download/` | Downloads Confluence pages and stores each one as a Markdown file | — |
| `02a-repo-docs/` | Writes a deep-dive document and a facts file for every repository | — |
| `02b-repo-linkage/` | Maps how repositories connect, where pipelines live and what triggers them | 02a |
| `03-repo-business-knowledge/` | Extracts cited business rules and terms from the repositories | 02a |
| `04-confluence-business-knowledge/` | Extracts cited business knowledge from the downloaded pages | 01 |
| `05-jira-enrichment/` | Fetches the Jira tickets referenced by pages and code to explain why | 01 and/or 02a |
| `06-business-handbook/` | Writes one readable handbook, organised by team, from the downloaded pages | 01 (04 optional) |

## Rules that apply to every loop

1. **Follow the loop's `LOOP_INSTRUCTIONS.md` exactly.** Read `TASK.md` and `PROGRESS.md` at the start of
   every iteration. Update `PROGRESS.md` and `outputs/audit-log.md` at the end of every iteration.
2. **State lives on disk.** Each loop has a `manifest.csv` with one row per item. Use `tools/manifest.py`
   to read and change it. Do not track progress from memory of the conversation.
3. **Only verify scripts set `verified`.** Never mark an item verified by hand, never skip or weaken a
   check, never lower a threshold to make a check pass.
4. **External systems are read-only.** Confluence, GitHub and Jira: read only. No edits, comments, ticket
   updates, labels, pushes, pull requests or merges.
5. **Write only inside the folder of the loop you are running.** The one exception is a bug fix in
   `tools/`, which must come with a test and an audit-log entry.
6. **No secrets in outputs.** Never read, print or copy credentials, tokens, keys or `.env` values. Refer to
   them by name only. If a secret appears in a source, write `[REDACTED]` and note where it was.
7. **Copy, do not paraphrase,** wherever a loop stores source content. Where a loop extracts knowledge,
   every statement needs evidence that points to the source.
8. **When unsure whether something is allowed, do not do it.** Record the question under "Needs Human
   Review" in `PROGRESS.md`, set `Phase: BLOCKED`, and stop.

## Commands

Run every command from this folder (the kit root). Use `python3`, or `python` if `python3` does not exist.

```
python3 tools/manifest.py counts <loop>/manifest.csv      # where the loop stands
python3 tools/selftest.py                                 # confirms the kit's scripts work on this machine
python3 01-confluence-download/tests/run_tests.py         # confirms the Confluence converter and checker work
```
