# Task — Jira context for pages and code

## Goal

For every Jira ticket referenced by a downloaded Confluence page or by a repository (code, commit messages,
branch names), fetch the ticket read-only and record why the work was done and any business rules it
states. Attach that context back to the page or repository that referenced it.

Jira is not downloaded wholesale. Only referenced tickets are fetched, plus their parent, epic and directly
linked tickets (one hop).

## Input

- `01-confluence-download/pages/` and/or `02a-repo-docs/repos/`. At least one must exist.
- The Jira connector available in this Claude installation.
- Jira project keys in scope: written to `05-jira-enrichment/project-keys.txt` during SETUP (one per line).
- Pilot review: `required`   <!-- change to `skip` only if the user said so in the first prompt -->
- Tickets per iteration: `10`

## What the finished work looks like

```
05-jira-enrichment/
├── project-keys.txt            the Jira project keys that count as ticket prefixes
├── references.csv              every place a ticket key was seen: page, file and line, commit, branch
├── tickets/<KEY>.json          one file per ticket: verbatim fields, the "why", and cited entries
├── enrichment/by-page.md       THE DELIVERABLE: for each Confluence page, its tickets and why they existed
├── enrichment/by-repo.md       THE DELIVERABLE: the same for each repository
├── enrichment/tickets.md       all tickets with summary, status and why
├── enrichment/all-entries.jsonl machine-readable business entries taken from tickets
├── manifest.csv                one row per ticket key
└── outputs/verification-report.md
```

## Allowed and not allowed

Allowed: read tickets through the Jira connector; read anything under `01-confluence-download/` and
`02a-repo-docs/`; create and change files inside `05-jira-enrichment/`.

Not allowed:
- Any write to Jira: no create, edit, transition, comment, assign, link, watch, vote or label.
- Following links beyond one hop from a referenced ticket.
- Recording people's names from tickets. Describe roles ("the reporter", "finance") instead.
- Copying secret values or customer personal data.
- Setting `verified` by any means other than `jira_tools.py verify`.

## Done means

`python3 05-jira-enrichment/jira_tools.py verify --final` prints `RESULT: ACCEPTED` and PROGRESS.md says
`Phase: COMPLETE`. Every key is then `verified`, `not_found` or `no_access`, each with a note.

Honest limit: only tickets whose key is written somewhere in the pages or repositories are found. Work
that was never referenced by key is invisible to this loop.
