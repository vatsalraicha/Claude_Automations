# First prompt — the business handbook

Run this after the Confluence download loop (`01-confluence-download/`) has finished. It does not need loop 04,
but if loop 04 has finished, its catalogued facts are added to each chapter.
Open Claude in the kit root folder. Adjust the organisation, teams and platforms, then paste the whole block.

```
/loop Run the business handbook loop in 06-business-handbook/.

Organisation: Payments Intelligence. It contains several teams. Find the teams from the page tree and confirm the list with me before writing anything.
Platforms and tools to cover: AWS, Snowflake, Databricks, Exchange, Devnav, and any others the pages rely on.
The handbook must explain why Payments Intelligence exists, who consumes its work, the processes followed within it, and how each team uses those platforms.

Read 06-business-handbook/LOOP_INSTRUCTIONS.md and follow it exactly. PROGRESS.md in that folder says which phase to run. Do one iteration, update PROGRESS.md and the audit log, then run the next iteration. Work only from the local Markdown pages in 01-confluence-download/pages/. Write only what the pages say, and end every paragraph with the page it came from. Stop looping only when PROGRESS.md says Phase: COMPLETE, Phase: OUTLINE_REVIEW, Phase: PILOT_REVIEW or Phase: BLOCKED, and tell me why you stopped.
```

If you already know the team names, add a line such as: `The teams are: <name>, <name>, <name>.`

## If `/loop` is not available

Paste the same text without `/loop`. If Claude stops before `Phase: COMPLETE`, type `continue`.

## What you will be asked to do

1. **Confirm the outline.** Claude reads the page tree and shows you the teams it found, the chapters it plans
   and the platforms it will cover. You know the organisation; correct anything that is wrong ("those two are
   one team", "that branch is archived, leave it out as its own chapter", "add Airflow"). Reply `continue` when
   it is right.
2. **Review the first chapter.** Claude writes one team chapter and stops. Read it. Say what you want more or
   less of; general instructions are written into `CHAPTER_TEMPLATE.md` and applied to every later chapter.
3. **Read the result**: `06-business-handbook/HANDBOOK.md`.

To remove either stop, add `Skip the outline review.` or `Skip the pilot review.` to the first prompt. The
outline review is the one worth keeping: a wrong team list makes the whole handbook wrong.

## The document you get

`HANDBOOK.md` contains, in order:

- **Overview**: why the organisation exists; its teams and what each owns; its consumers; the processes
  followed; how each platform is used across teams; how work and data flow between teams; gaps.
- **One chapter per team** (large teams are split along their page tree), each with: why the team exists;
  people, roles and ownership; what it delivers; consumers and stakeholders; processes followed; platforms
  and tools; data and reporting; rules, policies and service levels; history and decisions; gaps,
  contradictions and stale content.
- **Source index**: every page cited, with its title and last-modified date.

Every paragraph ends with `[p:PAGE_ID]` links to the Markdown copy of the page it came from.
