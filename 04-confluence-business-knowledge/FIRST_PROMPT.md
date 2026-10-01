# First prompt — business knowledge from the Confluence pages

Run this after the Confluence download loop (`01-confluence-download/`) has finished.
Open Claude in the kit root folder and paste the whole block.

```
/loop Run the Confluence business-knowledge loop in 04-confluence-business-knowledge/.

Read 04-confluence-business-knowledge/LOOP_INSTRUCTIONS.md and follow it exactly. PROGRESS.md in that folder says which phase to run. Do one iteration, update PROGRESS.md and the audit log, then run the next iteration. Work only from the local Markdown pages in 01-confluence-download/pages/. Every statement needs a quote copied verbatim from the page. Stop looping only when PROGRESS.md says Phase: COMPLETE, Phase: PILOT_REVIEW or Phase: BLOCKED, and tell me why you stopped.
```

## If `/loop` is not available

Paste the same text without `/loop`. If Claude stops before `Phase: COMPLETE`, type `continue`.

## What you will be asked to do

1. **Review the pilot.** After 10 pages Claude shows three entries files next to their pages. Say what you
   want more or less of; your instructions are written into `ENTRY_GUIDE.md` and applied to every later page.
   To skip, add `Skip the pilot review.` to the first prompt.
2. **Read the result**: `04-confluence-business-knowledge/catalog/rules-catalog.md` and `glossary.md`, then
   `conflicts.md` and, if the repository loop has run, `confluence-vs-code.md`.
3. **Give two lists to someone who knows the domain**: `catalog/inferred-for-review.md` and
   `catalog/no-business-content.md`.
