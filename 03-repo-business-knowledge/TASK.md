# Task — business knowledge from the repositories

## Goal

Extract what the code says about the business: rules, calculations, thresholds, statuses, terms, processes
and constraints. Every statement must be backed by a quote from the code or its documentation. Every
repository must end with either a set of entries or an explicit, independently confirmed verdict that it
contains no business logic.

## Input

- The finished documentation loop: `02a-repo-docs/` (manifest, `docs/`, `repos/`). Only repositories that are
  `verified` there are included.
- Pilot review: `required`   <!-- change to `skip` only if the user said so in the first prompt -->
- Repositories per iteration: `1`

## What the finished work looks like

```
03-repo-business-knowledge/
├── business/<repo>.json            entries for one repository (the checked source of truth)
├── business/<repo>.md              the same, readable (generated)
├── checks/<repo>.json              result of the independent check
├── catalog/rules-catalog.md        THE DELIVERABLE: every rule, calculation, process, constraint, by type
├── catalog/glossary.md             THE DELIVERABLE: business terms
├── catalog/inferred-for-review.md  entries inferred from behaviour, for a domain expert to confirm
├── catalog/no-business-content.md  repositories judged to hold no business logic, with reasons
├── catalog/name-collisions.md      the same name used in more than one repository (generated)
├── catalog/conflicts.md            your decision on each collision: same thing, or a real conflict
├── catalog/all-entries.jsonl       machine-readable copy of every entry
├── manifest.csv
└── outputs/verification-report.md
```

## Allowed and not allowed

Allowed: read anything under `02a-repo-docs/`; create and change files inside `03-repo-business-knowledge/`.

Not allowed: changing anything under `02a-repo-docs/`; running code from the clones; copying secret values or
customer personal data into entries; writing a statement without a verbatim quote that supports it; setting
`verified` by any means other than `tools/bk.py verify`.

## Done means

`python3 tools/bk.py verify --kind repo --loop 03-repo-business-knowledge --final` prints `RESULT: ACCEPTED`
and PROGRESS.md says `Phase: COMPLETE`.

Honest limit: ACCEPTED proves that every repository was examined and that every statement is backed by text
that really is in the code. It cannot prove that every rule in the code was noticed. The lists
`inferred-for-review.md` and `no-business-content.md` are where a person who knows the domain should look.
