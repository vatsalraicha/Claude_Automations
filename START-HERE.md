# Start here

This folder is a ready-to-run kit of six loops for Claude. Each loop has its own folder. You paste one prompt
per loop; Claude then works through it step by step, keeps its state on disk, checks its own work with
scripts it cannot override, and stops only when it is finished, needs your review, or is blocked.

## 1. What to copy, and where

Copy **this whole folder** to your office machine, keeping the structure exactly as it is:

```
<any location>/Calude_Automations/        ← open Claude here (this is the "kit root")
├── CLAUDE.md                              rules Claude loads automatically in this folder
├── .claude/
│   ├── settings.json                      permissions: what Claude may run without asking, what is blocked
│   └── agents/loop-checker.md             the independent, read-only checker used by every loop
├── tools/                                 shared scripts (manifest, evidence checks, self-test)
├── 01-confluence-download/
├── 02a-repo-docs/
├── 02b-repo-linkage/
├── 03-repo-business-knowledge/
├── 04-confluence-business-knowledge/
└── 05-jira-enrichment/
```

- `.claude/` is already in the right place. **Nothing goes into your home `~/.claude` folder.** The settings
  and the checker agent apply only when Claude is opened in this folder.
- `.claude` is a hidden folder. When copying, make sure hidden files are included (zip the whole folder).
- The loop folders must stay next to each other: later loops read the output of earlier ones.
- The PDF and `loop-playbook.md` are background reading. They are not needed to run anything.
- Your `confluence-connector` skill and the Jira connector stay where they already are in your office
  Claude setup. The kit calls them; it does not contain them.

## 2. What must be on the office machine

| Needed | For | Check |
|---|---|---|
| Python 3.8 or newer | every loop | `python3 --version` |
| git | loops 02a, 02b, 03, 05 | `git --version` |
| GitHub access (`gh` CLI logged in, or git credentials, or a GitHub connector) | loop 02a | `gh auth status` |
| `confluence-connector` skill | loop 01 | ask Claude: "which skills do you have?" |
| Jira connector | loop 05 | same |

No Python packages need to be installed. The scripts use only the standard library.

## 3. Test the kit once, before the first loop

In a terminal in the kit root:

```bash
python3 tools/selftest.py
```

```bash
python3 01-confluence-download/tests/run_tests.py
```

Both must end with `ALL TESTS PASSED`. (Each loop also runs these itself during its SETUP phase.)

## 4. Run the loops, in this order

Open Claude **in the kit root**, then paste the prompt from the loop's `FIRST_PROMPT.md`.

| Order | Folder | Paste the prompt from | You supply |
|---|---|---|---|
| 1 | `01-confluence-download/` | `01-confluence-download/FIRST_PROMPT.md` | the Confluence link |
| 2 | `02a-repo-docs/` | `02a-repo-docs/FIRST_PROMPT.md` | the GitHub organisation or repo list |
| 3 | `02b-repo-linkage/` | `02b-repo-linkage/FIRST_PROMPT.md` | nothing |
| 4 | `03-repo-business-knowledge/` | `03-repo-business-knowledge/FIRST_PROMPT.md` | nothing |
| 5 | `04-confluence-business-knowledge/` | `04-confluence-business-knowledge/FIRST_PROMPT.md` | nothing |
| 6 | `05-jira-enrichment/` | `05-jira-enrichment/FIRST_PROMPT.md` | optionally, the Jira projects to limit to |

`01` and `02a` are independent and can run in two separate Claude sessions at the same time.
`02b` and `03` need `02a` to be finished. `04` needs `01` to be finished. `05` uses whichever of `01` and
`02a` is finished. Run one loop per Claude session.

The first prompt, for the Confluence download, is:

```
/loop Run the Confluence download loop in 01-confluence-download/.

Confluence link (download this page or space and everything under it): <PASTE THE CONFLUENCE LINK HERE>

Read 01-confluence-download/LOOP_INSTRUCTIONS.md and follow it exactly. PROGRESS.md in that folder says which phase to run. Do one iteration, update PROGRESS.md and the audit log, then run the next iteration. Every page must end up as one Markdown file in 01-confluence-download/pages/. Use the confluence-connector skill for all Confluence access, read-only. Stop looping only when PROGRESS.md says Phase: COMPLETE, Phase: PILOT_REVIEW or Phase: BLOCKED, and tell me why you stopped.
```

Where the Markdown ends up: `01-confluence-download/pages/<page_id>-<title>.md`, one file per Confluence page,
with `pages/INDEX.md` showing the page tree. Images and attachments are in `attachments/<page_id>/`.

## 5. What Claude does, and the three times it stops

Every loop moves through phases recorded in its `PROGRESS.md`:

`SETUP → INVENTORY → PILOT → PILOT_REVIEW → RUN → (RECONCILE) → FINAL → COMPLETE`

Claude stops in exactly three situations:

1. **`PILOT_REVIEW`** — after a small first batch (10 pages, 3 repositories, 5 tickets). It names the files to
   open. Look at them and reply `continue`, or say what to change. This is the cheap moment to catch a
   systematic problem before it is repeated a thousand times. To remove this stop, add the sentence
   `Skip the pilot review.` to the first prompt.
2. **`BLOCKED`** — it needs something only you can give: access, a decision, a missing prerequisite. The reason
   is under "Needs Human Review" in `PROGRESS.md`. Fix it, set the phase back as Claude suggests, and paste
   the prompt again.
3. **`COMPLETE`** — the final report says `RESULT: ACCEPTED`.

You can close the session at any point. Pasting the same first prompt again resumes from the manifest.

Claude will ask permission the first time it uses a connector or a command that is not pre-approved. Choose
"always allow" for read operations. **Decline any request to write to Confluence, Jira or GitHub**; the
loops never need one.

## 6. How to see where a loop stands

```bash
python3 tools/manifest.py counts 01-confluence-download/manifest.csv
```

`still_open` is the number of items not yet finished. Also readable at any time:
`<loop>/PROGRESS.md` (current state), `<loop>/outputs/audit-log.md` (what each iteration did),
`<loop>/outputs/verification-report.md` (final result).

## 7. How the kit makes sure nothing is missed

- **The list comes first.** Each loop asks the source for the complete list of items and checks the count
  against a second, independent count before any work starts.
- **One row per item.** `manifest.csv` records the status of every page, repository and ticket. An item is
  never "probably done": it is `pending`, `done`, `verified`, `failed` or `needs_human`.
- **Only a script can say "verified".** Claude does the work; `verify.py` decides. Claude cannot mark an item
  verified by hand, and its instructions forbid weakening a check.
- **Three failures go to a person.** An item that fails its checks three times becomes `needs_human` and is
  listed in the final report instead of being retried forever or quietly dropped.
- **A second look.** A separate read-only checker agent compares samples against the source.
- **A final recount.** The Confluence loop lists the pages again at the end and re-downloads anything that
  changed or appeared in the meantime.

What the checks for the Confluence download cover, per page: the raw page was saved and is not truncated;
attachments match in number and size; the Markdown file exists with the right page id and version; it has
at least as many headings, tables, code blocks, images and links as the original; at least 99% of the words
of the original are present; every local image and page link points to a real file; every macro with no
stored content is shown as a visible placeholder; no Confluence markup is left over.

## 8. What the kit cannot promise

- **It has not been run against your systems.** The scripts pass their self-tests on synthetic data. The
  first real run of each loop is the real test, which is why the pilot review exists.
- **The `confluence-connector` skill is unknown to the kit.** Loop 01's SETUP phase reads the skill and works
  out how to list and fetch pages. If the skill can only return Markdown, or only ADF JSON, the
  instructions cover both cases, with weaker checks in the Markdown-only case; Claude will tell you.
- **Pages your account cannot see are not in the inventory**, so nothing will flag them. Compare the page
  count in `PROGRESS.md` with what a space administrator sees.
- **Content that only exists when Confluence renders the page** (Jira issue lists, included pages, page-tree
  macros) appears in the Markdown as a placeholder such as `[Confluence macro: jira — …]`. The final report
  counts them by type.
- **Knowledge extraction (loops 03, 04, 05) is complete in coverage, not in insight.** The checks prove every
  source was examined and every statement is backed by a real quote. They cannot prove every rule was
  noticed. Give `inferred-for-review.md` and `no-business-content.md` to someone who knows the domain.
- **The permission file is a guard, not a guarantee.** It blocks the obvious write commands. The firm
  boundary is the access your connectors and credentials have; read-only credentials are best.
- **Cost and time.** Hundreds of repositories and thousands of pages mean many hours and a large number of
  tokens. Run each pilot first and look at how long ten items took before committing to the full run.

## 9. Before you start

Confirm that exporting Confluence, Jira and source code to a local folder is allowed by your company's data
policy, and keep this folder in an approved location. The outputs will contain internal business content.
