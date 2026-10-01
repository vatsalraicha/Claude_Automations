# First prompt — Confluence download

Open Claude in the kit root folder (the one that contains `CLAUDE.md`, `tools/` and `01-confluence-download/`).
Replace the link, then paste the whole block.

```
/loop Run the Confluence download loop in 01-confluence-download/.

Confluence link (download this page or space and everything under it): <PASTE THE CONFLUENCE LINK HERE>

Read 01-confluence-download/LOOP_INSTRUCTIONS.md and follow it exactly. PROGRESS.md in that folder says which phase to run. Do one iteration, update PROGRESS.md and the audit log, then run the next iteration. Every page must end up as one Markdown file in 01-confluence-download/pages/. Use the confluence-connector skill for all Confluence access, read-only. Stop looping only when PROGRESS.md says Phase: COMPLETE, Phase: PILOT_REVIEW or Phase: BLOCKED, and tell me why you stopped.
```

## If `/loop` is not available

Paste the same text without the `/loop` at the start. If Claude stops before `Phase: COMPLETE`, type `continue`.
The state is on disk, so it resumes where it left off, including in a new session.

## What you will be asked to do

1. **Approve tool use.** The first time Claude calls the Confluence connector or runs a script it may ask for
   permission. Choose the "always allow" option for the read calls and the kit's scripts.
2. **Review the pilot.** After the first 10 pages Claude stops and names three Markdown files. Open them, compare
   with the pages in Confluence, and reply `continue`. To skip this stop, add this sentence to the first prompt:
   `Skip the pilot review.`
3. **Read the result.** At the end, open `01-confluence-download/outputs/verification-report.md`. The line
   `RESULT: ACCEPTED` means every page in the manifest is on disk as Markdown and passed every check.

## To check the result yourself, in a new session

```
Run a verification pass for 01-confluence-download. Do not modify any files except outputs/verification-report.md. Run verify.py with --final and --no-update using the expected count and root ids recorded in PROGRESS.md, then list every page that is not verified and say ACCEPTED or NOT ACCEPTED.
```
