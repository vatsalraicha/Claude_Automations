# First prompt — repository documentation

Open Claude in the kit root folder. Replace the organisation, then paste the whole block.

```
/loop Run the repository documentation loop in 02a-repo-docs/.

GitHub organisation (or list of repositories) to document: <PASTE THE ORG NAME OR REPO LIST HERE>

Read 02a-repo-docs/LOOP_INSTRUCTIONS.md and follow it exactly. PROGRESS.md in that folder says which phase to run. Do one iteration, update PROGRESS.md and the audit log, then run the next iteration. GitHub is read-only: list and clone only. Stop looping only when PROGRESS.md says Phase: COMPLETE, Phase: PILOT_REVIEW or Phase: BLOCKED, and tell me why you stopped.
```

## If `/loop` is not available

Paste the same text without `/loop`. If Claude stops before `Phase: COMPLETE`, type `continue`.

## What you will be asked to do

1. **Approve tool use** for `git clone`, `gh` and the kit's scripts. Choose "always allow".
2. **Review the pilot.** After three repositories Claude stops and names three documents. Read them, say what
   to change, or reply `continue`. To skip this stop, add `Skip the pilot review.` to the first prompt.
3. **Read the result** in `02a-repo-docs/outputs/verification-report.md` and browse `02a-repo-docs/docs/INDEX.md`.

Hundreds of repositories take many hours. You can close the session at any time: the manifest records what
is done, and pasting the same prompt again resumes from there.
