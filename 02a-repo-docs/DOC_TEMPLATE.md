# Templates for one repository

Two files are written per repository. `<name>` is the repository name with `/` replaced by `__`.

---

## 1. The document: `docs/<name>.md`

Use exactly these headings, in this order. Every section must have content. If there is nothing to report,
write "None found" and say where you looked.

**Citations.** Every factual claim ends with a citation in this exact form: `(src: path/to/file.ext:LINE)`
or `(src: path/to/file.ext:LINE-LINE)`. The path is relative to the repository root. `verify.py` opens each
one. A claim you cannot cite belongs in section 10.

**Coverage.** Every path listed under `must_mention` in `scans/<name>.json` must appear in the document,
written exactly as in the scan (for example `src/` or `.github/workflows/deploy.yml`).

```markdown
# <repository name>

Repo: <repository name exactly as in the manifest>
Commit: <full commit sha from the manifest>

## 1. Purpose and owners
What this repository is for, in plain words. Who owns it (CODEOWNERS, README, package metadata).
Whether it is archived or a fork.

## 2. Languages, frameworks and layout
Languages and main frameworks. Then one line for every top-level folder and file: what it contains.

## 3. Entry points, build, test and run
Where execution starts. The commands to build, test and run, as the repository defines them.

## 4. Configuration and environment variables
Every configuration file and every environment variable the code reads: name, purpose, where it is read.
Names only, never values.

## 5. Data stores
Every database, table, bucket, topic, queue, cache and file location read or written, with direction.

## 6. Interfaces exposed
APIs, endpoints, published packages, container images, events emitted, CLI commands, reusable workflows.

## 7. Dependencies consumed
Internal packages, other internal services and APIs called, shared workflows used, base images. Then the
notable third-party dependencies. Say for each whether it is internal or third-party.

## 8. Pipelines and triggers
One subsection per CI/CD, scheduler and orchestration definition found by the scan. For each: the file,
what triggers it (push, pull request, cron expression, manual, another pipeline, an event), what it runs
step by step, what it deploys or produces, and what it calls outside this repository.

## 9. Deployment and infrastructure
Where and how this is deployed: environments, infrastructure-as-code, containers, cloud resources.

## 10. Unknowns and open questions
Everything you could not determine from the repository, and what would answer it.
```

---

## 2. The facts file: `facts/<name>.json`

The same information in a fixed structure. `evidence` is always `"path:LINE"` relative to the repository root.

```json
{
  "repo": "<repository name exactly as in the manifest>",
  "commit": "<full commit sha from the manifest>",
  "kind": "service | library | pipeline | infrastructure | data | frontend | tooling | docs | config | other",
  "purpose": "One or two sentences.",
  "owners": ["team or person names found in the repository"],
  "languages": ["python"],
  "produces": [
    {"kind": "api | package | image | topic | queue | table | database | bucket | file | artifact | service | repo | workflow | secret | other",
     "id": "the exact identifier others would use to refer to it", "evidence": "path:LINE"}
  ],
  "consumes": [
    {"kind": "(same list)", "id": "the exact identifier as written in this repository",
     "evidence": "path:LINE", "external": "yes | no | unknown"}
  ],
  "pipelines": [
    {"name": "short name", "system": "github_actions | jenkins | airflow | gitlab_ci | azure_pipelines | argo | cron | other",
     "definition": "path/to/the/definition/file",
     "runs": "what it does, in one or two sentences",
     "triggers": [{"type": "push | pull_request | tag | release | cron | manual | upstream | webhook | event | api | other",
                   "detail": "branch, cron expression, upstream pipeline name, event name", "evidence": "path:LINE"}],
     "no_trigger_found": false,
     "deploys_to": "environment or target, or empty",
     "calls_out_to": ["other repositories, pipelines or services it invokes"]}
  ],
  "not_pipelines": [{"path": "file the scan flagged that is not a pipeline", "reason": "why it is not one"}],
  "unknowns": ["things that could not be determined"]
}
```

Rules:

- Every file in `ci_cd_files` and `orchestration_files` of the scan must appear either as the `definition`
  of a pipeline or under `not_pipelines` with a reason.
- A pipeline with no trigger in this repository gets `"triggers": []` and `"no_trigger_found": true`. The
  linkage loop looks for its trigger in other repositories.
- `id` values matter: the linkage loop matches `consumes` in one repository against `produces` in another.
  Use the identifier exactly as it appears in code (package name as imported, image name without tag,
  topic name, table name with schema, API base path).
- `external` is `yes` for third-party things, `no` for things your organisation owns, `unknown` if unclear.
- For an empty repository: the document says "This is an empty repository." and the facts file has empty lists.
