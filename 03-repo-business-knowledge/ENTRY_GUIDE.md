# Entry guide — business knowledge from a repository

## What counts as business knowledge

Something a business person would recognise and care about, as opposed to how the software is built.

| Type | What it is | Typical place in code |
|---|---|---|
| `rule` | a condition the business imposes | validation, `if` checks on amounts, dates, roles, eligibility |
| `calculation` | how a business number is derived | pricing, fees, tax, interest, scoring, aggregation queries |
| `constraint` | a limit or invariant | maximums, minimums, uniqueness, required fields, retention periods |
| `state` | statuses and allowed transitions | enums, state machines, status columns, workflow steps |
| `process` | a sequence of business steps | orchestration code, pipelines, job chains, sagas |
| `term` | a business word and its meaning | entity and table names, glossary comments, README |
| `policy` | a stated organisational decision | README, ADRs, comments beginning "per finance", "legal requires" |
| `decision` | why something is the way it is | ADRs, commit-style comments, design notes |
| `role` | who may do what | permission checks, role enums, approval steps |
| `integration` | a business relationship with another system or party | clients for payment providers, partners, regulators |
| `metric` | a business measure and its definition | reporting queries, KPI definitions, dashboards as code |

Not business knowledge: framework configuration, logging, retries, build tooling, generic CRUD, test scaffolding.

## Where to look, in this order

1. `02a-repo-docs/docs/<name>.md` — to know what the repository is and where its main modules are.
2. README, `docs/`, ADRs.
3. **Test names and test cases.** Tests state business rules plainly ("rejects_refund_after_30_days").
4. Validation, eligibility, pricing, calculation and status-transition code.
5. Database schemas, migrations, SQL and dbt models: table and column meanings, constraints, derived fields.
6. Enums, constants and configuration values that carry business meaning (limits, rates, cut-off times).
7. Feature flags and their descriptions.
8. Error messages shown to users: they often state the rule being enforced.
9. Comments that explain why.

## The entries file: `business/<name>.json`

`<name>` is the repository name with `/` replaced by `__`.

```json
{
  "source": "<repository name exactly as in the manifest>",
  "verdict": "extracted",
  "reason": "",
  "entries": [
    {
      "type": "rule",
      "name": "Manual approval threshold",
      "statement": "Orders with a total above 10000 are sent to manual review instead of being charged automatically.",
      "evidence": [{"where": "src/app.py:6", "quote": "if order.total > MAX_ORDER_TOTAL:"}],
      "basis": "stated",
      "confidence": "high",
      "related": ["orders", "MAX_ORDER_TOTAL"],
      "jira_keys": ["PAY-12"]
    }
  ]
}
```

Rules for each field:

- `name`: 1 to 12 words. Unique within the file for its type.
- `statement`: 5 to 90 words, plain language, one idea. Include the actual numbers, units and conditions.
- `evidence`: at least one item. `where` is `path:LINE` relative to the repository root. `quote` is 3 to 40
  words **copied verbatim** from that file within about 20 lines of `LINE`. The checker searches for it. Do
  not paraphrase inside `quote`.
- `basis`: `stated` when the code or its documentation says it directly. `inferred` when you concluded it
  from behaviour (for example a status flow read off several functions).
- `confidence`: `high`, `medium` or `low`.
- `related`: other entry names, tables, systems. May be empty.
- `jira_keys`: ticket keys seen next to the evidence (comments, test names). May be empty.

## Verdicts

- `extracted`: at least one entry.
- `no_business_content`: no entries, and `reason` says in at least 8 words what the repository contains
  instead (for example "Terraform modules for networking only; no application or data logic"). An
  independent checker must agree before it can be verified.
- `needs_human`: you cannot tell (generated code, binary assets, a language you cannot read). `reason` says why.

## Things to avoid

- Stating a rule more broadly than the code does. If the check is `> 10000`, say "above 10000", not "large orders".
- Merging two rules into one entry.
- Entries about how the code is organised.
- Any secret value or personal data in a quote. Pick different lines.
