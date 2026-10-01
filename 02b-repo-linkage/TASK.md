# Task — how the repositories connect

## Goal

Map how the repositories depend on each other, which pipelines live in which repository, and what triggers
each pipeline, including triggers defined in a different repository. Prove that every dependency, every
cross-repository mention and every pipeline was looked at.

## Input

- The finished documentation loop: `02a-repo-docs/` (manifest, `facts/`, `repos/`). Only repositories that are
  `verified` there are included.
- Pilot review: `required`   <!-- change to `skip` only if the user said so in the first prompt -->
- Repositories per iteration: `1` (up to `3` when each has fewer than 10 candidate mentions)

## What the finished work looks like

```
02b-repo-linkage/
├── work/candidates/<repo>.json   deterministic search results: what this repo consumes, which other repos it
│                                 mentions, and which lines look like triggers
├── links/<repo>.json             the reviewed result for one repository (see LINKS_TEMPLATE.md)
├── graph/edges.csv               THE DELIVERABLE: from_repo, to_repo, kind, identifier, evidence on both sides
├── graph/pipelines.csv           THE DELIVERABLE: every pipeline, its repo, its triggers and where each trigger is defined
├── graph/nodes.csv               every repository with its number of links
├── graph/unresolved.md           references that could not be matched to any repository
├── graph/isolated.md             repositories with no links at all (to be confirmed by a person)
├── graph/graph.mmd               Mermaid diagram of the dependency graph
├── graph/overview.md             readable summary written at the end
├── manifest.csv
└── outputs/verification-report.md
```

## Allowed and not allowed

Allowed: read anything under `02a-repo-docs/`; create and change files inside `02b-repo-linkage/`.

Not allowed: changing anything under `02a-repo-docs/`; any GitHub write; running code from the clones;
copying secret values; setting `verified` by any means other than `verify.py`.

## Done means

`python3 02b-repo-linkage/verify.py --final` prints `RESULT: ACCEPTED` and PROGRESS.md says `Phase: COMPLETE`.

Honest limit: links that leave no trace in any repository (a job configured only in a web console, a
manually run script, a consumer outside these repositories) cannot be found here. They show up as pipelines
with "no trigger found", as unresolved references, or as isolated repositories. Those three lists are the
places to ask people.
