# Task — business knowledge from the downloaded Confluence pages

## Goal

Extract the business knowledge written in the Confluence pages: processes, rules, policies, decisions,
terms, roles and metrics. Every statement must be backed by a quote from the page. Every page must end with
either a set of entries or an explicit, independently confirmed verdict that it holds no business knowledge.

## Input

- The finished Confluence download: `01-confluence-download/` (manifest and `pages/*.md`). Only pages that
  are `verified` there are included. This loop never contacts Confluence.
- Pilot review: `required`   <!-- change to `skip` only if the user said so in the first prompt -->
- Pages per iteration: `10`

## What the finished work looks like

```
04-confluence-business-knowledge/
├── business/<page_id>.json         entries for one page (the checked source of truth)
├── business/<page_id>.md           the same, readable (generated)
├── checks/<page_id>.json           independent confirmation for pages judged to have no business content
├── catalog/rules-catalog.md        THE DELIVERABLE: every rule, process, policy, decision, by type
├── catalog/glossary.md             THE DELIVERABLE: business terms
├── catalog/inferred-for-review.md  entries that were inferred, for a domain expert to confirm
├── catalog/no-business-content.md  pages judged to hold no business knowledge, with reasons
├── catalog/name-collisions.md      the same name used on more than one page (generated)
├── catalog/conflicts.md            your decision on each collision: same thing, or pages that disagree
├── catalog/confluence-vs-code.md   where the pages and the code disagree (only if loop 03 has run)
├── catalog/all-entries.jsonl       machine-readable copy of every entry
├── manifest.csv
└── outputs/verification-report.md
```

## Allowed and not allowed

Allowed: read anything under `01-confluence-download/` and `03-repo-business-knowledge/catalog/`; create and
change files inside `04-confluence-business-knowledge/`.

Not allowed: changing anything under `01-confluence-download/`; contacting Confluence; copying secret values
or personal data into entries; writing a statement without a verbatim quote that supports it; setting
`verified` by any means other than `tools/bk.py verify`.

## Done means

`python3 tools/bk.py verify --kind page --loop 04-confluence-business-knowledge --final` prints
`RESULT: ACCEPTED` and PROGRESS.md says `Phase: COMPLETE`.

Honest limit: ACCEPTED proves every page was examined and every statement is backed by text that really is
on the page. It cannot prove that every piece of knowledge on every page was noticed, and it says nothing
about whether the page itself is still true. Each entry carries the page's last-modified date for that reason.
