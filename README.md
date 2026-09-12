# Jira VOC Nexus

`Jira VOC Nexus`'s product direction is to connect in-house Jira VOC with past
resolution cases and prepare recommended comments and labels for human review.
That direction and the future MVP scope are laid out in the
[project overview](docs/PROJECT_OVERVIEW.md).

The current repository is that product's **local proposal-generation
scaffold**. The CLI reads normalized JSON files the caller supplies, runs a
trusted project filter plus search/validation/dedupe against a synthetic
corpus, and stores the validated proposal in local SQLite. The CLI is not an
HTTP/webhook server or internet ingress, and there is no real Jira comment/
label write and no real Jira/RAG connection.

The public OSS/VOC research and current adoption decisions are recorded in
[OSS research](docs/OSS_RESEARCH.md) and [tooling decision](docs/TOOLING_DECISION.md).
No Jira connector, Promptfoo, or separate framework is installed in the
current runtime; `atlassian-python-api==5.0.4` is a future candidate to
reconsider once real ACL/auth/server flavor is secured.

```sh
python3 scripts/doctor.py
python3 -m unittest discover -s tests -v
python3 -m nexus --event fixtures/event.json --corpus fixtures/corpus.json --state .local/demo.sqlite3
git diff --check
```

`doctor.py` is only an environment check confirming Python, tools, links, and
required entry files. unittest and the fixture CLI are separate gates that
verify runtime behavior; neither command proves provider authentication or a
successful Jira connection.

## Current execution boundary

- The default `fixture` engine is a deterministic synthetic heuristic that
  never calls a model.
- The `opencode` engine uses one OpenCode process per new event with evidence,
  when an approved provider configuration is present. Auxiliary work such as
  titling may cause multiple HTTP requests to the same approved model, so
  measure the actual count and cost in the in-house integration. Semantic
  rerank is never made a separate process.
- OpenCode configuration requires `NEXUS_OPENCODE_MODEL=provider/model` and a
  `NEXUS_APPROVED_PROVIDER` whose prefix matches it. When
  `NEXUS_OPENCODE_CONFIG` is given, the adapter copies only the selected
  provider block into a temporary runtime config.
- Equality comparison on `project` is a trusted-filter boundary for the
  synthetic fixture only, not a production ACL.
- SQLite replay identity is `event_id`. The canonical SHA-256 of the event
  JSON is stored on first processing. The same `event_id` with the same
  payload reuses the stored result; a payload change fails as a conflict.
  corpus is not part of this identity — reprocessing must be expressed with a
  new event ID/version policy.

See [architecture](docs/ARCHITECTURE.md) for the proposal schema, allowed
labels, and size limits, and [operational integration contract](docs/INTEGRATION.md)
for the conditions to meet before connecting an in-house provider/Jira.
For a company-internal preparation path that does not require exporting data,
use the [onboarding guide](guides/COMPANY_ONBOARDING.md) and copy its
[checklist](guides/COMPANY_ONBOARDING_CHECKLIST.md) into an internal record
system.

## Comment output example (comment format v1)

The actual output of `result["comment"]` from running
`fixtures/event.json` + `fixtures/corpus.json`. See
[docs/TEMPLATES.md](docs/TEMPLATES.md) for the full template, issue format v1,
and what the marker means.

```text
VOC triage recommendations (dry-run):

- Review the resolved guidance for PAY-42 concerning card.

Evidence:
- PAY-42: https://jira.example.local/browse/PAY-42

Labels: possible-duplicate

voc-nexus-comment|v1|event-001
```

```text
nexus/           input normalization, search, judgment adapters, validation, state, CLI
tests/           regression tests against synthetic input and fake processes
fixtures/        publishable synthetic events and evidence corpus
scripts/         local development tools
docs/            design, review, tooling decisions, operational integration contract
.agents/skills/  canonical shared project skills (orca-cli, orchestration, voc-slice, voc-workflow)
AGENTS.md        shared agent rules
CLAUDE.md        relative link to AGENTS.md
HANDOFF.md       current status and next verification steps
```

[docs index](docs/INDEX.md) · [goal](docs/GOAL.md) ·
[design review](docs/REVIEW.md) · [tooling decision](docs/TOOLING_DECISION.md) ·
[OSS research](docs/OSS_RESEARCH.md)
