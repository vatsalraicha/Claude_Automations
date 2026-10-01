# Template — `links/<name>.json`

One file per repository. `<name>` is the repository name with `/` replaced by `__`.

Evidence format: `"path:LINE"` for a file in this repository, `"other-repo:path:LINE"` for a file in another
repository's clone. Every evidence value is opened by `verify.py`.

```json
{
  "repo": "<repository name exactly as in the manifest>",

  "consumes": [
    {"kind": "package", "id": "billing_lib",
     "resolution": "internal | external | unresolved",
     "to_repo": "the repository that provides it (required when internal)",
     "evidence_from": "path:LINE where this repository uses it",
     "evidence_to": "other-repo:path:LINE where the other repository defines it (when internal)",
     "note": "for external: what it is. for unresolved: what you searched for and where"}
  ],

  "edges": [
    {"to_repo": "other repository",
     "kind": "imports | calls_api | triggers | triggered_by | reads_data | writes_data | uses_image | uses_workflow | deploys | config | submodule | publishes_to | subscribes_to | other",
     "identifier": "the name that links them",
     "evidence_from": "path:LINE",
     "evidence_to": "other-repo:path:LINE, or empty if only one side shows it",
     "confidence": "high | medium | low"}
  ],

  "mentions_reviewed": [
    {"target_repo": "other repository", "identifier": "the text that was found",
     "is_edge": true, "reason": "what the mention is: an import, a comment, a coincidence of names"}
  ],

  "pipelines": [
    {"name": "pipeline name exactly as in the facts file",
     "triggers": [
       {"type": "push | pull_request | tag | release | cron | manual | upstream | webhook | event | api | other",
        "detail": "branch, cron expression, upstream pipeline, event",
        "source_repo": "repository where the trigger is defined (may be another repository)",
        "evidence": "path:LINE or other-repo:path:LINE"}
     ],
     "no_trigger_found": false,
     "searched": "when no trigger was found: what you searched for across all repositories",
     "downstream": [{"repo": "repository", "pipeline": "pipeline it starts", "evidence": "path:LINE"}]}
  ],

  "trigger_hits_dismissed": [
    {"path": "file", "line": 12, "reason": "why this line is not a trigger relationship"}
  ]
}
```

What `verify.py` requires:

- **consumes**: one entry for every `consumes` item in `02a-repo-docs/facts/<name>.json` (same `kind` and `id`).
- **mentions_reviewed**: one entry for every item in `outgoing_mentions` of `work/candidates/<name>.json`
  (same `target_repo` and `identifier`). Every mention with `is_edge: true` needs a matching entry in
  `edges` or an internal `consumes` to the same repository.
- **pipelines**: one entry for every pipeline in the facts file. Each has at least one trigger with
  evidence, or `no_trigger_found: true` with `searched` filled in.
- **trigger hits**: every line in `trigger_hits` of the candidates file with `cross_repo: true` must either be
  used as evidence somewhere in this file or be listed in `trigger_hits_dismissed`.
- **confidence**: `high` when both sides have evidence, `medium` when one side has clear evidence, `low` when
  the link is inferred from naming.
