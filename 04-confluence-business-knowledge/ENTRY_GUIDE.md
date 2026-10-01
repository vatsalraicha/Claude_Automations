# Entry guide — business knowledge from a Confluence page

## What counts as business knowledge

| Type | What it is | Typical page content |
|---|---|---|
| `process` | a sequence of business steps, who does them, what starts and ends them | runbooks, "how we onboard a customer", workflows |
| `rule` | a condition the business imposes | eligibility, approval rules, "must", "never", "only if" |
| `policy` | a stated organisational decision that people must follow | retention, access, pricing, SLA policy |
| `decision` | what was decided, when, and why | decision logs, ADRs, meeting outcomes |
| `calculation` | how a business number is derived | formulas, pricing tables, KPI definitions |
| `constraint` | a limit or invariant | maximums, deadlines, cut-off times, regulatory limits |
| `state` | statuses and what moves an item between them | lifecycle diagrams, status tables |
| `term` | a business word and its meaning | glossaries, definitions, acronyms |
| `role` | who is responsible or allowed | RACI tables, ownership lists, escalation paths |
| `integration` | a relationship with another system, team or outside party | interface descriptions, vendor pages |
| `metric` | a measure and its definition | KPI pages, reporting definitions |

Not business knowledge: meeting logistics, holiday lists, social announcements, empty templates, pure
navigation pages, personal to-do lists. Technical how-to pages count only for the business facts in them
(for example the cut-off time in a deployment runbook).

## How to read a page

Read the whole Markdown file, including tables. Tables often hold the densest knowledge: one entry per
meaningful row is normal. A placeholder such as `[Confluence macro: jira …]` means content that was not
captured; do not guess what it showed.

## The entries file: `business/<page_id>.json`

```json
{
  "source": "<page_id>",
  "verdict": "extracted",
  "reason": "",
  "entries": [
    {
      "type": "policy",
      "name": "Refund window",
      "statement": "Customers can ask for a refund up to 30 days after purchase.",
      "evidence": [{"where": "Refund window", "quote": "refund within 30 days of purchase"}],
      "basis": "stated",
      "confidence": "high",
      "related": ["refunds"],
      "jira_keys": ["PAY-12"]
    }
  ]
}
```

Rules for each field:

- `name`: 1 to 12 words. Unique within the file for its type.
- `statement`: 5 to 90 words, plain language, one idea, with the actual numbers, dates, owners and conditions.
- `evidence`: at least one item. `where` is the **exact text of the heading** the quote sits under, or
  `(top)` if it comes before the first heading. `quote` is 3 to 40 words **copied verbatim** from the page.
  The checker searches the page for it. Do not paraphrase inside `quote`.
- `basis`: `stated` when the page says it directly; `inferred` when you concluded it from several statements.
- `confidence`: `high`, `medium` or `low`. Lower it when the page is a draft, contradicts itself, or is
  marked as outdated.
- `related`: other entry names, systems, teams, tables. May be empty.
- `jira_keys`: ticket keys that appear on the page near the evidence. May be empty.

## Verdicts

- `extracted`: at least one entry.
- `no_business_content`: no entries, and `reason` says in at least 8 words what the page is (for example
  "Agenda and dial-in details for a weekly meeting; no decisions recorded"). An independent checker must
  agree before it can be verified.
- `needs_human`: you cannot tell, for example the page is almost entirely macro placeholders or images.
  `reason` says why.

## Things to avoid

- Stating more than the page says, or tidying up an ambiguous sentence into a firm rule. Keep the ambiguity
  and lower the confidence.
- Treating a proposal or an open question as a decision. If the page says "proposed" or "TBD", say so.
- Personal data: do not quote phone numbers, private addresses or anything about individuals beyond their
  role in a process.
