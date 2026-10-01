# First prompt — repository linkage

Run this after the repository documentation loop (`02a-repo-docs/`) has finished.
Open Claude in the kit root folder and paste the whole block.

```
/loop Run the repository linkage loop in 02b-repo-linkage/.

Read 02b-repo-linkage/LOOP_INSTRUCTIONS.md and follow it exactly. PROGRESS.md in that folder says which phase to run. Do one iteration, update PROGRESS.md and the audit log, then run the next iteration. Everything under 02a-repo-docs/ is read-only. Stop looping only when PROGRESS.md says Phase: COMPLETE, Phase: PILOT_REVIEW or Phase: BLOCKED, and tell me why you stopped.
```

## If `/loop` is not available

Paste the same text without `/loop`. If Claude stops before `Phase: COMPLETE`, type `continue`.

## What you will be asked to do

1. **Review the pilot.** After three repositories Claude shows three `links/` files. Reply `continue`, or
   say what to change. To skip, add `Skip the pilot review.` to the first prompt.
2. **Read the result**: `02b-repo-linkage/graph/overview.md` first, then `edges.csv` and `pipelines.csv`.
3. **Take three lists to people who know**: `graph/unresolved.md`, the rows in `pipelines.csv` with
   trigger type `none_found`, and `graph/isolated.md`.
