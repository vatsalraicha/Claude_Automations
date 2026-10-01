# First prompt — business knowledge from the repositories

Run this after the repository documentation loop (`02a-repo-docs/`) has finished.
Open Claude in the kit root folder and paste the whole block.

```
/loop Run the repository business-knowledge loop in 03-repo-business-knowledge/.

Read 03-repo-business-knowledge/LOOP_INSTRUCTIONS.md and follow it exactly. PROGRESS.md in that folder says which phase to run. Do one iteration, update PROGRESS.md and the audit log, then run the next iteration. Every statement needs a quote copied verbatim from the code. Stop looping only when PROGRESS.md says Phase: COMPLETE, Phase: PILOT_REVIEW or Phase: BLOCKED, and tell me why you stopped.
```

## If `/loop` is not available

Paste the same text without `/loop`. If Claude stops before `Phase: COMPLETE`, type `continue`.

## What you will be asked to do

1. **Review the pilot.** After three repositories Claude shows three entries files. This is the moment to say
   what you want more or less of ("ignore infrastructure limits", "capture every status transition"). Your
   instructions are written into `ENTRY_GUIDE.md` and applied to every later repository. To skip, add
   `Skip the pilot review.` to the first prompt.
2. **Read the result**: `03-repo-business-knowledge/catalog/rules-catalog.md` and `glossary.md`.
3. **Give two lists to someone who knows the domain**: `catalog/inferred-for-review.md` and
   `catalog/no-business-content.md`.
