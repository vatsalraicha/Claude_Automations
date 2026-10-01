# Chapter template — business handbook

A chapter is written for a reader who is new to the organisation and wants to understand how it actually
works: why a team exists, who relies on it, what it does day to day, and which platforms it does it on.
Write connected prose, not a list of facts. Explain how things fit together, in the order a newcomer would
need them.

## Rules that apply to every chapter

1. **Only what the pages say.** Use the Markdown pages assigned to the area and nothing else. Do not add
   general knowledge. In particular, do not explain what AWS, Snowflake, Databricks or any other product is
   or can do. Describe **how the pages say this team uses it**: which service, for what, by whom, with which
   data, on what schedule. If the pages only name a platform without saying how it is used, say exactly that.
2. **Cite every block.** Every paragraph, every list item and every table row ends with one or more source
   markers of the form `[p:PAGE_ID]`, naming the page or pages it came from. A nested bullet may rely on the
   citation of its parent item.
3. **Use the pages' own words for specifics.** Numbers, dates, acronyms, system names, table names, job names
   and anything in quotation marks must appear exactly as they do in a page that the same block cites. The
   checker looks for each one. Do not count things yourself ("the team runs 12 pipelines") unless a page
   states the count.
4. **Say when something is not documented.** If the pages are silent on a section, write the single line
   `Not documented in the pages for this area.` Do not fill the gap with likely-sounding text. For a single
   missing item inside a section, write for example `Not documented in the pages for this area: Databricks.`
5. **Keep contradictions.** If two pages disagree, state both versions with their citations and the
   last-modified date of each page. Do not choose.
6. **Mark age and status.** If a page is a draft, a proposal, marked deprecated, or old, say so next to what
   you take from it.
7. **People.** Refer to roles and team names. Name an individual only where a page lists them as an owner or
   contact for something.
8. **Depth.** Cover every process, consumer, rule and platform use the pages describe. A chapter that reduces
   thirty pages to five paragraphs fails the depth check.

---

## Team chapter (kind `team` or `cross-team`): `chapters/<area id>.md`

Use exactly these headings, in this order.

```markdown
# <area title>

Area: <area id>

## 1. Why this team exists
The problem it solves and for whom. Its mission and scope as the pages state them. What would not happen
if the team did not exist. What is explicitly out of scope.

## 2. People, roles and ownership
The roles in the team and what each is responsible for. Who owns which system, dataset, process or
decision. Escalation paths and on-call arrangements.

## 3. What the team delivers
Products, services, datasets, models, reports, dashboards, APIs and tools the team builds or runs. For
each: what it is, what it is for, and its current status.

## 4. Consumers and stakeholders
Who uses what the team delivers: other teams, business functions, external parties, regulators, systems.
For each consumer: what they consume, how they receive it (dashboard, table, file, API, report), how often,
and what they use it for. Then the teams and systems this team depends on.

## 5. Processes followed
One subsection (### heading) per process. For each: what starts it, the steps in order, who performs each
step, which systems and tools are used at each step, what it produces, how long it takes or when it runs,
the approvals and controls in it, and what happens when it fails. Include recurring ceremonies and
operational routines (intake, prioritisation, release, incident handling, access requests, data fixes)
as well as the data and analytical processes.

## 6. Platforms and tools
One subsection (### heading) per platform or tool. Cover every platform listed in `outline.json` and any
other the pages rely on. For each: what this team uses it for; which accounts, environments, workspaces,
databases, schemas, clusters, jobs or services are named; what data lives there or moves through it; how
access is obtained; conventions and constraints the pages state; costs or limits if mentioned.
A platform the pages do not mention gets the line `Not documented in the pages for this area: <name>.`

## 7. Data and reporting
The data that comes in (sources, feeds, frequency), how it is transformed, where it is stored, and what
goes out. Key tables, datasets, models, metrics and their definitions. Data quality rules and known issues.

## 8. Rules, policies and service levels
Business rules, thresholds, eligibility conditions, approval rules, retention and access policies,
regulatory requirements, service levels and deadlines. State each with its actual numbers and conditions.

## 9. History and decisions
Why things are the way they are: decisions recorded, alternatives rejected, migrations, incidents that
changed how the team works.

## 10. Gaps, contradictions and stale content
What a newcomer would need that the pages do not say. Where pages contradict each other. Pages that look
out of date, with their last-modified date.

## Pages not used
One line per assigned page that is not cited above: `- [p:PAGE_ID] reason`, for example "duplicate of
[p:123]", "empty template", "meeting logistics only". Write `None.` if every page is cited.
```

---

## Overview chapter (kind `overview`): written last

It is written from the verified team chapters, but it cites **pages**, not chapters. Use exactly these headings.

```markdown
# <organisation> — overview

Area: <area id>

## 1. Why it exists
Why the organisation exists: the business problem, who it serves, its mission and scope, and what it is
accountable for. How it fits into the wider company.

## 2. Teams and what each owns
One short subsection per team: what it is responsible for, what it delivers, and how it relates to the
other teams.

## 3. Consumers
Everyone who consumes what the organisation produces, across all teams: who they are, what they consume,
through which channel, and what they use it for. Group by type of consumer.

## 4. Processes followed
The processes that span the organisation or are common to all teams, and an index of the team-specific
processes: one line per process naming the team and what the process is for.

## 5. Platforms and tools
One subsection per platform: across the whole organisation, which teams use it, for what, and how the
platforms connect to each other (what moves from where to where). Cover every platform in `outline.json`.

## 6. How work and data flow across teams
The end-to-end picture: where work and data enter, which team does what in which order, and where the
results go.

## 7. Gaps, contradictions and stale content
The organisation-level picture of what is missing, contradictory or out of date.

## Pages not used
As above. `None.` if the overview area has no assigned pages.
```
