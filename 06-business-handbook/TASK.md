# Task — the business handbook

## Goal

Write one readable handbook that explains the organisation's business knowledge as the Confluence pages
describe it, organised by team: why the organisation and each team exist, who consumes their work, the
processes they follow, how they use their platforms and tools, their data, rules and history. A person new
to the organisation should be able to read it start to finish and understand how things work.

Every paragraph cites the page it came from, and every downloaded page is accounted for.

## Input

- Organisation: `(not set yet — taken from the first prompt and written here during SETUP)`
- Teams named by the user: `(optional — otherwise found from the page tree and confirmed at the outline review)`
- Platforms and tools to cover: `(from the first prompt; default AWS, Snowflake, Databricks, Exchange, Devnav; add others the pages rely on)`
- Source: the finished Confluence download, `01-confluence-download/` (manifest and `pages/*.md`). Only pages
  that are `verified` there are used. This loop never contacts Confluence.
- Optional: `04-confluence-business-knowledge/`. If it has run, its verdicts and catalogued facts are used.
- Outline review: `required`   <!-- change to `skip` only if the user said so in the first prompt -->
- Pilot review: `required`     <!-- change to `skip` only if the user said so in the first prompt -->
- Chapters per iteration: `1`

## What the finished work looks like

```
06-business-handbook/
├── HANDBOOK.md             THE DELIVERABLE: the whole handbook in one document, with contents and source index
├── chapters/<area>.md      one chapter per team or topic, and one overview chapter
├── outline.json            the teams, the chapters, which pages belong to which chapter, the platforms to cover
├── work/tree.md            the page tree with sizes (input to the outline)
├── work/platform-mentions.md   which pages mention each platform
├── checks/<area>.json      result of the independent check of each chapter
├── manifest.csv            one row per chapter with its status
└── outputs/verification-report.md
```

`HANDBOOK.md` starts with the overview (why the organisation exists, its teams, its consumers, its
processes, its platforms, how work flows), then has one chapter per team with the same ten sections.

## Allowed and not allowed

Allowed: read anything under `01-confluence-download/` and `04-confluence-business-knowledge/`; create and
change files inside `06-business-handbook/`.

Not allowed:
- Contacting Confluence, or changing anything under `01-confluence-download/` or `04-confluence-business-knowledge/`.
- Writing anything that is not in the pages, including general knowledge about a platform or product.
- Editing `HANDBOOK.md` by hand. It is produced only by `handbook.py assemble` from the chapters.
- Copying secret values or personal data.
- Setting a chapter to `verified` by any means other than `handbook.py verify`.

## Done means

`python3 06-business-handbook/handbook.py verify --final` prints `RESULT: ACCEPTED` and PROGRESS.md says
`Phase: COMPLETE`.

Honest limit: ACCEPTED proves every page was assigned to a chapter and either cited or set aside with a
reason; every paragraph cites its pages; every number, acronym, system name and quotation appears in a
cited page; and a sampled independent reading passed. It does not prove that every sentence is a perfect
reading of its source, and it cannot make the handbook more correct or more current than the pages are.
The handbook describes what Confluence says.
