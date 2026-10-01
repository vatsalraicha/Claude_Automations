# Task — deep-dive documentation for every repository

## Goal

Produce, for every repository in scope, a deep-dive document and a structured facts file, and prove that
no repository, no top-level folder and no pipeline definition was skipped.

## Input

- GitHub organisation(s) or repository list: `(not set yet — taken from the first prompt and written here during SETUP)`
- Include archived repositories: `yes`
- Include forks: `yes` (flag them in the document)
- Pilot review: `required`   <!-- change to `skip` only if the user said so in the first prompt -->
- Repositories per iteration: `1` (up to `3` when all are `small`)

## What the finished work looks like

```
02a-repo-docs/
├── repos/<repo>/            local clone (read-only use)
├── scans/<repo>.json        deterministic inventory of the clone: the checklist for the document
├── docs/<repo>.md           THE DELIVERABLE: deep-dive document, ten fixed sections, every claim cited
├── docs/INDEX.md            one line per repository
├── facts/<repo>.json        the same facts in structured form (used by the linkage loop)
├── checks/<repo>.json       result of the independent citation check
├── manifest.csv             one row per repository with its status
└── outputs/verification-report.md
```

## Allowed and not allowed

Allowed:
- Read from GitHub (list repositories, clone).
- Create and change files inside `02a-repo-docs/`.

Not allowed:
- Any write to GitHub: no push, commit to a remote, branch, tag, pull request, issue, comment or setting change.
- Changing any file inside `repos/`. The clones are evidence. Do not run the code in them, do not install
  their dependencies, do not execute their scripts.
- Copying secrets, tokens, passwords or `.env` values into any output. Name the variable, never the value.
- Setting a row to `verified` by any means other than `verify.py`.

## Done means

`python3 02a-repo-docs/verify.py --manifest 02a-repo-docs/manifest.csv --final` prints `RESULT: ACCEPTED`
and PROGRESS.md says `Phase: COMPLETE`.

Honest limit: ACCEPTED proves every repository was documented, every top-level folder and pipeline file
is covered, and every citation points to a real line. A sampled check confirms the cited lines support the
claims. It does not prove that every detail of every file was noticed.
