# First prompt — Jira enrichment

Run this after the Confluence download (`01-confluence-download/`) and/or the repository documentation
(`02a-repo-docs/`) have finished. It uses whichever of the two exists.
Open Claude in the kit root folder and paste the whole block.

```
/loop Run the Jira enrichment loop in 05-jira-enrichment/.

Read 05-jira-enrichment/LOOP_INSTRUCTIONS.md and follow it exactly. PROGRESS.md in that folder says which phase to run. Do one iteration, update PROGRESS.md and the audit log, then run the next iteration. Use the Jira connector read-only: never create, edit, transition or comment on a ticket. Stop looping only when PROGRESS.md says Phase: COMPLETE, Phase: PILOT_REVIEW or Phase: BLOCKED, and tell me why you stopped.
```

To limit the run to certain Jira projects, add a line such as: `Only these Jira projects: PAY, BILL, OPS.`

## If `/loop` is not available

Paste the same text without `/loop`. If Claude stops before `Phase: COMPLETE`, type `continue`.

## What you will be asked to do

1. **Approve tool use** for the Jira connector's read calls. Decline any write call if one is ever requested.
2. **Review the pilot.** After 5 tickets Claude shows two ticket files. Reply `continue`, or say what to
   change. To skip, add `Skip the pilot review.` to the first prompt.
3. **Read the result**: `05-jira-enrichment/enrichment/by-page.md` and `by-repo.md`.

If you run this before both earlier loops have finished, run it again afterwards: it picks up the new
ticket keys and leaves finished tickets alone. To do that, set `Phase: SETUP` in
`05-jira-enrichment/PROGRESS.md` and paste the prompt again.
