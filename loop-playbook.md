# Loop playbook: Confluence download, repo documentation, business knowledge

> This is the design explanation. The ready-to-run kit built from it is in the numbered folders next to this
> file; start with `START-HERE.md`. Where folder names or details differ, the kit is the current version.

Adapted from "How to Create Loops with Claude Code" (Youssef Hosni) for five jobs:

| # | Loop | Reads | Writes |
|---|------|-------|--------|
| 1 | Confluence download | Confluence (read-only) | local pages + attachments |
| 2a | Repo deep-dive docs | local clones of each repo | one doc + one facts file per repo |
| 2b | Repo linkage and pipelines | the facts files from 2a | cross-repo graph, pipeline/trigger table |
| 3 | Business knowledge from repos | local clones + 2a docs | cited business rules and glossary |
| 4 | Business knowledge from Confluence | the local download from 1 | cited processes, rules, glossary |
| 5 | Jira enrichment | Jira (read-only) | the "why" behind pages and code |

---

## 1. What the article says, and what changes for these jobs

The article's loop has six parts: **trigger → context → action → verification → state update → decision**.
Its worked example is a small daily review that runs once a day forever.

Your jobs are a different shape: each one is a large queue of items (pages, repos, tickets) that must be
worked through until the queue is empty. The six parts still apply, with three adaptations.

**1. State is a manifest, not only PROGRESS.md.**
The article says markdown state stops being enough when the loop needs structured querying. That is your case.
Keep one row per item (page, repo, ticket) in `manifest.csv` with a status column. PROGRESS.md stays short
and holds only counts, blockers, decisions and "do not repeat" notes.

**2. The inventory comes first and is built separately from the work.**
"Nothing is missing" only means something if there is a list to be missing from. Each loop starts by asking the
source system for the full list of items, and verifying that list, before any item is processed.

**3. The stop condition is "queue empty and verified", not a time interval.**
The article distinguishes `/loop` (repeat because time passed) from `/goal` (continue until a condition holds).
These jobs are the second kind.

The rest carries over unchanged: run manually on a small slice first, keep the worker and checker separate,
give the checker a pass/fail standard, cap retries, record failures, stay read-only on external systems.

---

## 2. The shared skeleton

```
knowledge-loops/
├── 01-confluence-download/
│   ├── TASK.md                 goal, scope, what may be written
│   ├── LOOP_INSTRUCTIONS.md    procedure for one iteration
│   ├── PROGRESS.md             control panel: counts, blockers, decisions
│   ├── manifest.csv            one row per item, with status
│   ├── convert.py              raw page → markdown (Claude writes this once)
│   ├── verify.py               deterministic checks (Claude writes this once)
│   ├── raw/                    page bodies exactly as Confluence returned them
│   ├── pages/                  one markdown file per page (the deliverable)
│   ├── attachments/            images and files, one folder per page
│   └── outputs/
│       ├── audit-log.md
│       └── verification-report.md
├── 02a-repo-docs/
├── 02b-repo-linkage/
├── 03-repo-business-knowledge/
├── 04-confluence-business-knowledge/
└── 05-jira-enrichment/
```

**Item statuses** (same in every loop):

```
pending → done → verified
              ↘ failed (attempts + 1) → pending   (max 3 attempts)
                                      → needs_human
```

**One iteration** (same in every loop):

1. Read TASK.md, PROGRESS.md, LOOP_INSTRUCTIONS.md.
2. Take the next N rows with status `pending` from the manifest (start with N = 10 pages or 1 repo).
3. Do the work for those rows only.
4. Run the checker on those rows. Mark each `verified` or `failed`.
5. Update the manifest, PROGRESS.md and the audit log.
6. Stop. The next iteration picks up from the manifest.

**Stop condition** (same in every loop): zero rows `pending` or `failed`, every row is `verified` or
`needs_human`, and the final reconciliation (re-inventory and diff) is clean.

**Why small batches:** a long session gets its context summarised. If progress lives only in the conversation,
items get silently skipped. With the manifest on disk, any iteration, in any session, knows exactly what is left.

**Permissions for all five loops:** read-only on Confluence, GitHub and Jira. Writes only inside
`knowledge-loops/`. No ticket updates, no page edits, no pushes. Never copy secrets, tokens or customer
personal data into outputs; write `[REDACTED]` and note the location.

---

## 3. Loop 1 — Confluence download

### Step 0: probe the connector (do this before anything else)

Ask Claude at the office:

> Read the confluence-connector skill. Without downloading anything, tell me: can it (a) list every page in a
> space with pagination, (b) return page ID, parent ID, version number and last-modified date, (c) return the
> raw page body, (d) list and download attachments, (e) fetch comments, (f) run a CQL count query?
> What rate limits or page-size limits apply? Does it write content to disk itself, or does the content pass
> through you? In what format does it return the page body: storage format (XHTML), rendered HTML, or
> already-converted markdown? If markdown, can it also return the original format?

The answers decide the design. Two of them matter most.

*Does content pass through the model?* If page bodies pass through the model and the model then writes the
file, long pages can be truncated or subtly reworded. Prefer a path where content goes from the API straight
to disk (a script inside the skill, or a small script Claude writes that calls the Confluence REST API). Use
the model to orchestrate and check, and a script to copy bytes.

*What format comes back?* The deliverable is markdown, but the markdown has to be checked against something.
If the connector can return the original format, save that as the raw file and convert it yourself. If it
only returns markdown, you have no original to compare against, so the conversion checks in Phase C cannot
run; in that case fetch the original through the Confluence REST API for at least a sample of pages and
compare, so you know how much the connector's own conversion drops.

### Phase A: inventory

Build `manifest.csv` with one row per page:

```
page_id, title, parent_id, type, version, last_modified, body_chars, attachment_count,
status, attempts, raw_path, md_path, macros_placeholder, verified_at, notes
```

Inventory checks, all must pass before Phase B:

- Row count equals the count Confluence reports from an independent query (for example a CQL count for the space).
- No duplicate page IDs.
- Every `parent_id` is in the manifest or is the space root, so the page tree is closed.
- Pagination reached the end (the last response had no "next" cursor).
- Content types beyond normal pages are listed explicitly as in or out of scope: blog posts, archived pages,
  drafts, comments, whiteboards, databases, folders.

### Phase B: download (worker)

The deliverable is **one markdown file per Confluence page**. Each page goes through two steps, and they are
kept separate so that each can be checked on its own:

1. **Fetch** the raw body (Confluence storage format, which is XHTML) to `raw/<page_id>.html`.
2. **Convert** the raw file to markdown at `pages/<page_id>-<slug>.md`.

Rules for the markdown files:

- File name includes the page ID, for example `pages/123456-onboarding-guide.md`. Titles alone collide and
  contain characters that break paths. If you want folders that mirror the page tree, build them from
  `parent_id`, and still keep the ID in the file name.
- Each file starts with front matter: `page_id`, `title`, `parent_id`, `version`, `last_modified`, `source_url`.
- Convert with a deterministic tool (pandoc, or a small script using a library such as markdownify), not by
  having the model rewrite the page. A converter gives the same result every time and does not shorten or
  paraphrase. Claude writes the conversion script once; the loop runs it.
- Links to other Confluence pages are rewritten to the local markdown file of the target page (looked up by
  page ID in the manifest). Links to pages outside the download stay as the original URL.
- Images and attachments go to `attachments/<page_id>/`, and the markdown references them by relative path.
- Tables become markdown tables. Tables that markdown cannot express (merged cells, nested tables) are kept
  as an inline HTML block rather than flattened, so no cells are lost.
- Code blocks keep their language tag. Info, warning and note panels become block quotes with a label.
- Macros that have no stored content (Jira issue lists, include/excerpt, page-properties reports, table of
  contents) are written as a visible placeholder naming the macro and its parameters, for example
  `> [Confluence macro: jira — jql="project = ABC"]`, and the page is noted in the manifest. They are never
  silently dropped.

Keep the `raw/` files after conversion. They are what the markdown is verified against, and they let you fix
the converter and re-convert everything without downloading again.

### Phase C: verify (checker, read-only, a script wherever possible)

For every manifest row, PASS or FAIL with no partial credit:

*Download checks (raw file against Confluence):*

1. `raw/<page_id>.html` exists and is not empty.
2. Raw body length matches `body_chars` recorded at inventory time.
3. Number of attachment files equals `attachment_count`, and each file size matches what Confluence reported.

*Conversion checks (markdown file against raw file):*

4. `pages/<page_id>-<slug>.md` exists, is not empty, and its front matter `page_id` and `version` match the manifest.
5. No two rows share a `md_path`.
6. Element counts match between raw and markdown: headings, tables, table rows, code blocks, images, links.
   A page with 4 tables in the raw file must have 4 tables (or HTML table blocks) in the markdown.
7. Visible text length of the markdown is within a small tolerance of the visible text length of the raw
   file (start with 5%). A larger gap means content was dropped.
8. Every image and attachment reference in the markdown points to a file that exists on disk.
9. Every internal page link points to a markdown file that exists, or is an original URL for a page outside the download.
10. Every macro in the raw file appears in the markdown as converted content or as a placeholder.
11. No leftover Confluence markup (`<ac:`, `<ri:` tags) in the markdown outside deliberate HTML table blocks.

*Spot checks each run:*

- Pick 20 random `verified` pages, re-fetch them live, compare version and body length.
- Pick 5 random pages and have a separate checker (fresh context, read-only) read the raw and markdown side
  by side and return PASS or FAIL on whether the markdown is a faithful, readable rendering. This catches
  what counts cannot, such as a table whose columns are scrambled.

Run check 9 again over all pages once the queue is empty, because a link target may not have been downloaded
yet when its source page was first checked.

### Phase D: reconcile

When the queue is empty, run the inventory again from scratch into `manifest-recheck.csv` and diff:
new pages, changed versions, deleted pages. New or changed rows go back to `pending`.

### What usually goes missing

Attachments; pages restricted to other people (the connector cannot see them, so they are absent from the
inventory, not failed); archived pages; blog posts; comments; images and draw.io diagrams embedded in pages;
content produced by macros (Jira issue lists, include/excerpt macros, page-properties reports), which appears
in the browser but not in the stored body; page history.

Losses specific to the markdown conversion: tables with merged or nested cells; content inside expand
sections, tabs and multi-column layouts; panels; task lists; mentions and dates (stored as special tags, not
text); emoji and status lozenges; internal links left pointing at Confluence instead of the local file.
The element-count and text-length checks in Phase C exist to catch these.

### Starter LOOP_INSTRUCTIONS.md

```markdown
# Loop Instructions — Confluence download

## Before you start
1. Read TASK.md and PROGRESS.md.
2. Read manifest.csv. Count rows by status.
3. If PROGRESS.md lists anything under "Needs Human Review" that blocks downloading, stop.

## What to do in one iteration
1. Select the next 10 rows with status `pending` (lowest page_id first).
2. For each: download the raw body to `raw/<page_id>.html` and all attachments to `attachments/<page_id>/`.
3. For each: run `python convert.py --page <page_id>` to produce `pages/<page_id>-<slug>.md`.
   Do not write or edit the markdown by hand. If the converter output is wrong, record it and fix convert.py.
4. Set status `done` and fill `raw_path` and `md_path`.

## Checker phase (separate from the worker phase)
1. Run `python verify.py --rows <the 10 page_ids>`.
2. For each row, set `verified` on PASS. On FAIL set `failed`, increment `attempts`, record the failed check in `notes`.
3. A row with attempts = 3 becomes `needs_human`. Do not retry it again.
4. Run `python verify.py --spot-check 20`.

## State update (mandatory before stopping)
- Update the counts in PROGRESS.md: pending / done / verified / failed / needs_human.
- Append one entry to outputs/audit-log.md: rows attempted, rows verified, rows failed and why.

## Safety rules
- Confluence is read-only. Never create, edit, move, delete or comment.
- Write only inside this folder.
- Do not summarise, shorten or reword page content. The markdown must carry the same content as the page.
- If a tool call fails with an auth or rate-limit error, stop and record it. Do not mark rows as done.
- If convert.py is changed, every row already `verified` goes back to `done` and is re-converted and
  re-checked from the existing raw files. No re-download is needed.

## Stop condition
The loop is complete only when: zero rows are `pending`, `done` or `failed`; `python verify.py --all`
reports ACCEPTED; and the reconciliation diff is empty. Otherwise run another iteration.
```

---

## 4. Loop 2a — deep-dive documentation per repo

**Inventory.** List every repo from the org (`gh repo list <org> --limit 1000 --json name,isArchived,pushedAt,primaryLanguage`),
including archived ones. Check the row count against the org's repo count. Clone each repo locally (shallow
clone is fine); local clones are far faster to search than reading through an API, and Loop 2b needs to grep
across all of them.

Manifest columns: `repo, archived, default_branch, commit_sha, size, status, attempts, doc_path, facts_path, notes`.
Recording `commit_sha` lets a later run detect that a repo changed and re-queue it.

**One repo per iteration, in a fresh context** (a sub-agent per repo, or a new session). Otherwise details
from repo A leak into the write-up of repo B. Very large repos get several manifest rows, one per major area.

**Fixed doc template** (`docs/<repo>.md`). Every section is mandatory; "none found" is a valid answer but an
empty section is a FAIL:

1. Purpose and owners
2. Languages, frameworks, layout of top-level directories
3. Entry points and how to build, test and run
4. Configuration and environment variables (names only, never values)
5. Data stores read and written (tables, buckets, topics, queues)
6. APIs and interfaces exposed
7. APIs, packages and services consumed (internal and third-party)
8. Pipelines: every CI/CD, scheduler and orchestration definition, with its triggers and what it deploys or runs
9. Deployment targets and infrastructure
10. Unknowns and open questions

Every factual claim cites `path:line`.

**Facts file** (`facts/<repo>.json`) — the same information in a structured form, so Loop 2b never has to
re-read the repos:

```json
{
  "repo": "", "commit": "",
  "produces": [{"kind": "api|package|image|topic|table|bucket|artifact", "id": "", "evidence": "path:line"}],
  "consumes": [{"kind": "", "id": "", "evidence": "path:line"}],
  "pipelines": [{
    "name": "", "system": "github_actions|jenkins|airflow|other", "definition": "path",
    "triggers": [{"type": "push|pull_request|cron|manual|upstream|webhook|event", "detail": "", "evidence": "path:line"}],
    "runs": "", "deploys_to": "", "calls_out_to": []
  }],
  "unknowns": []
}
```

**Verification** (this is how "I don't miss anything" becomes checkable):

- *Coverage:* a script lists every top-level directory and every pipeline-like file
  (`.github/workflows/*`, `Jenkinsfile*`, `.gitlab-ci.yml`, `azure-pipelines.yml`, `dags/**`, `Dockerfile*`,
  `*.tf`, Helm charts, `Makefile`, cron definitions). Each one must be mentioned in the doc. Any path not
  mentioned is a FAIL.
- *Structure:* all ten sections present, facts file is valid JSON and matches the schema.
- *Accuracy:* a separate checker (fresh context, read-only) picks 10 cited claims at random, opens the cited
  lines and returns PASS or FAIL for each. Two or more FAILs sends the repo back to `pending`.
- *Consistency:* every pipeline in the doc is in the facts file and the reverse.

---

## 5. Loop 2b — linkage: how repos connect, where pipelines live, what triggers them

Runs only after 2a is fully verified. Input is the facts files plus org-wide search across the local clones.

**Outputs:**

- `graph/edges.csv`: `from_repo, to_repo, kind, identifier, evidence_from, evidence_to, confidence`
- `graph/pipelines.csv`: `pipeline, repo, system, trigger_type, trigger_detail, upstream, downstream, evidence`
- `graph/unresolved.md`: references that could not be matched to any repo
- `graph/overview.md`: a readable summary and diagram

**Method.**

1. Match every `consumes` id against every `produces` id. A match is an edge.
2. Search all clones for each repo's name, package names, image names and hostnames. Hits in other repos are edges.
3. Hunt triggers specifically, because the trigger for a pipeline often lives in a different repo than the
   pipeline itself (commonly the infrastructure repo): GitHub Actions `workflow_run`, `repository_dispatch`,
   `workflow_call` and `uses: org/repo/.github/workflows/...`; Jenkins `build job:` and upstream triggers;
   Airflow `TriggerDagRunOperator` and external task sensors; cron and scheduler definitions; cloud event
   rules, bucket notifications and queue subscriptions declared in Terraform or CloudFormation; webhooks.
4. Unmatched references become their own queue. Each one is investigated once with a targeted search, then
   classified as internal (edge found), external third-party, or unresolved.

**Verification.**

- Every `consumes` entry is matched, marked external, or listed in `unresolved.md`. None are dropped.
- Every pipeline has at least one trigger with evidence, or the explicit statement "no trigger found in any repo".
- Every repo in the manifest is a node in the graph. Repos with no edges are listed for human review, since
  an isolated repo is more often a missed link than a true island.
- Each edge has evidence on at least one side; edges with evidence on only one side are flagged low confidence.

---

## 6. Loop 3 — business knowledge from repos

A separate pass with a different lens: not "how does it work" but "what does the business do and require".

**Where to look:** READMEs and `docs/`; test names and test cases (tests state business rules plainly);
validation logic, thresholds, eligibility checks and calculations; status enums and state transitions;
database schemas, migrations and SQL/dbt models; configuration constants and feature flags; error messages;
code comments that explain why.

**Output per repo** (`business/<repo>.md`), each entry in a fixed shape:

```
Rule / term / process:
Statement:                  (one or two plain sentences)
Evidence:                   path:line
Stated or inferred:         stated in code/docs | inferred from behaviour
Confidence:                 high | medium | low
Related entities:
```

Plus one consolidated `business/glossary.md` and `business/rules-catalog.md` built in a final merge pass.

**Verification.**

- Every repo has a business file, or an explicit verdict "no business logic (infrastructure/tooling)" with a reason.
- Every entry has a citation. The checker opens a random sample of citations and returns PASS or FAIL on
  whether the cited code supports the statement.
- Entries marked "inferred" are listed separately for review by someone who knows the domain.
- The same term defined differently in two repos is recorded as a conflict, not silently merged.

---

## 7. Loop 4 — business knowledge from the downloaded Confluence pages

Runs on the local copy from Loop 1, never on live Confluence. Reuse Loop 1's manifest with extra columns:
`bk_status, bk_path, bk_notes`.

**Per page**, extract into the same entry shape as Loop 3, with the citation being `page_id` + heading, and
add `last_modified`. Age matters: a process page untouched for four years is weaker evidence than one edited
last month.

**Page verdicts** (every page gets exactly one): `extracted`, `no_business_content` (with a reason: meeting
logistics, empty template, index page), or `needs_human`.

**Consolidation pass.** Merge into the shared glossary and rules catalog, de-duplicate, and record conflicts:
between two Confluence pages, and between Confluence and code. When they disagree, the code describes what
actually runs and the page describes what was intended; keep both and flag the difference.

**Verification.** Every page has a verdict. A sample of `no_business_content` pages is re-read by the checker
to confirm they were not dismissed wrongly (this is where knowledge is most often lost). A sample of entries
is checked against the cited heading.

---

## 8. Loop 5 — Jira enrichment

Jira is not downloaded wholesale. It is used to answer "why" for things already found.

**Inventory.** Scan the Confluence download and the repos (commit messages, branch names, PR titles, code
comments, page text) for ticket keys (pattern `[A-Z][A-Z0-9]+-\d+`). Build `jira-manifest.csv`:
`key, referenced_from, status, attempts, notes`.

**Per ticket (read-only):** summary, description, acceptance criteria, type, status, resolution, parent/epic,
linked issues, and comments that record a decision. Write `jira/<KEY>.md` and attach a one-paragraph "why" back
to the page or repo entry that referenced it.

**Bounded crawl.** Follow parent/epic and linked issues one hop only. New keys found go into the manifest as
`pending`, tagged with depth; depth above 1 is not followed. Without a depth limit the queue never empties.

**Verification.** Every key is `verified`, `not_found` or `no_access`. Every enriched entry cites the ticket
key. No Jira write operations appear in the audit log.

---

## 9. Running the loops

**Order:** 1 → 2a → 2b → 3 → 4 → 5 → final consolidation. Loops 1 and 2a are independent and can run side by side.

**Roll-out for each loop** (the article's maturity path):

1. Manual run on a tiny slice: one small Confluence space, or three repos of different kinds.
2. Separate read-only verification pass. Inspect the output yourself.
3. Repeat three to five times, tightening LOOP_INSTRUCTIONS.md each time something is missed.
4. Only then attach the trigger and scale to the full manifest.

**Trigger options:**

- Self-paced: `/loop Run one iteration of the loop in this folder. Follow LOOP_INSTRUCTIONS.md exactly. Stop looping when the stop condition in LOOP_INSTRUCTIONS.md is met.`
- Interval: `/loop 15m <same prompt>`, useful when rate limits force pauses.
- Condition-driven, as the article describes: `/goal manifest.csv has no rows that are pending, done or failed, and outputs/verification-report.md says ACCEPTED.`
  Confirm `/goal` exists in the Claude version at your office before relying on it.

`/loop` runs only while the session is open. The manifest makes that harmless: reopen and it resumes.

**Final check for every loop**, run in a fresh session so it is not influenced by the worker:

> Run a verification pass for this loop. Do not modify any files. Run verify.py over every row. Re-run the
> inventory from the source and diff it against manifest.csv. Report PASS or FAIL per check, the list of rows
> that are not verified, and ACCEPTED or NOT ACCEPTED overall.

---

## 10. What can and cannot be proven

| Claim | Provable? | How |
|-------|-----------|-----|
| Every page the account can see was downloaded intact | Yes | inventory count, per-row checks, reconciliation diff |
| Pages the account cannot see were downloaded | No | compare the inventory count with the total a space admin sees |
| Every repo was documented and every pipeline file was covered | Yes | manifest + coverage script |
| Every stated fact is correct | Mostly | citations + sampled checker; raise the sample size for more assurance |
| Every piece of business knowledge was noticed | No | coverage and citations reduce the risk; a domain expert reviewing the "inferred", "no_business_content" and "unresolved" lists closes most of the rest |

Extraction loops can prove that everything was looked at and that what was written is supported. They cannot
prove nothing was overlooked. Plan a human review of the three lists above rather than treating ACCEPTED as
the end.

One practical note: confirm that bulk-exporting Confluence, Jira and source code to a local machine is allowed
by your company's data policy, and keep `knowledge-loops/` in an approved location.
