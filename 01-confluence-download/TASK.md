# Task — Confluence download to Markdown

## Goal

Download every Confluence page under the link below and store **each page as one Markdown file** on this
machine, with its attachments, and prove that nothing visible to this account is missing or altered.

## Input

- Confluence link: `(not set yet — taken from the first prompt and written here during SETUP)`
- Resolved scope: `(filled during SETUP: space key, root page id and title, or "whole space")`
- Pilot review: `required`   <!-- change to `skip` only if the user said so in the first prompt -->
- Batch size: `25` pages per iteration (`10` in the pilot; `5` if page content has to pass through the model)

The scope is the page the link points to **and every page below it, at any depth**. If the link points to a
space, the scope is every page in that space.

## What the finished download looks like

```
01-confluence-download/
├── pages/<page_id>-<slug>.md      THE DELIVERABLE: one Markdown file per Confluence page
├── pages/INDEX.md                 the page tree, linking to every file
├── attachments/<page_id>/...      images and files attached to each page
├── raw/<page_id>.html             the page body exactly as Confluence returned it (kept as proof)
├── manifest.csv                   one row per page with its status
└── outputs/verification-report.md final result: ACCEPTED or NOT ACCEPTED
```

Each Markdown file starts with front matter (`title`, `page_id`, `space_key`, `parent_id`, `version`,
`last_modified`, `source_url`) followed by the page title and the converted body. Links between pages point
to the local Markdown files. Images point to the local attachment files.

## In scope

- Pages (current version), their body, their attachments.
- Blog posts, if the link is a whole space and the connector can list them.

## Out of scope unless the user says otherwise

- Page history (old versions), drafts, comments, whiteboards, databases, restricted pages this account cannot see.
- Record every content type that exists in the scope but was not downloaded in PROGRESS.md.

## Allowed and not allowed

Allowed:
- Read from Confluence through the confluence-connector skill.
- Create and change files inside `01-confluence-download/`.
- Fix `convert.py` or `verify.py` when a real bug is found, following the rules in LOOP_INSTRUCTIONS.md.

Not allowed:
- Any write to Confluence: no create, edit, move, delete, comment, label, like or watch.
- Writing files outside `01-confluence-download/` (the only exception is a bug fix in `tools/`).
- Writing or editing a Markdown page by hand. Pages are produced only by `convert.py`.
- Summarising, shortening or rewording page content.
- Setting a row to `verified` by any means other than `verify.py`.

## Done means

`python 01-confluence-download/verify.py --manifest 01-confluence-download/manifest.csv --final ...` prints
`RESULT: ACCEPTED`, and PROGRESS.md says `Phase: COMPLETE`.
