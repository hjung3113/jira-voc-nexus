# Jira VOC Nexus

> Execution design is in [architecture](ARCHITECTURE.md), findings and resolutions
> are in [review](REVIEW.md), progress status is in [HANDOFF](../HANDOFF.md), and
> the full document set is in the [index](INDEX.md).

## Product direction and future MVP

`Jira VOC Nexus` aims to be a bot that connects VOC received in in-house Jira
with existing issues, project wikis, and related project code knowledge to
support triage and action recommendation. The list below is the direction of
the future product MVP — it does not mean the current local scaffold already
provides it.

1. A trusted Jira adapter receives new VOC and normalizes title, body,
   comments, and metadata.
2. A permission filter is applied first, then similar issues are selected from
   past-issue RAG.
3. Applicable recommendations are built from the actual remediation and
   outcome recorded on resolved issues.
4. Each recommendation is shown to a human for review along with its source
   issue and remediation evidence.
5. Within an approved boundary, Jira comments and labels are applied together
   with retry/dedupe rules.
6. Human edit/approval/dismissal feedback is re-indexed to improve quality.

The future knowledge sources to connect are Jira issue RAG, a project-wide
knowledge wiki, and a related-project code-graph RAG. The first operational
connection is limited to past Jira issues with a real permission/provenance
contract in place; the wiki and code graph are added afterward.

## Current local scaffold

The current implementation uses a file-based CLI and a synthetic fixture
corpus. It strictly validates input schema, first compares
`project == event.project` in the corpus, then picks up to five deterministic
lexical evidence items. This project comparison is a **synthetic
trusted-fixture boundary** that verifies ordering and leak prevention — it is
not production authorization or a Jira ACL check. The CLI is not internet
ingress and does not verify webhook signatures, principal, or issue security.

The corpus's `text` field must hold the actual remediation and outcome
obtained from the source — for example, what was changed and what result was
observed. The `resolved` boolean is only a status hint used for search
priority and the fixture heuristic; it does not by itself prove the factual
accuracy of the remediation or outcome. All issue body text and search
results are treated as untrusted data.

The default fixture engine is a deterministic demo that never calls a model.
The `opencode` engine calls OpenCode exactly once, using an approved in-house
provider configuration, when evidence exists; semantic rerank is out of scope
for now. Model output must pass a fixed schema, an allowlist, size limits, and
evidence linkage. When there is no evidence, the provider is not called and a
`needs-triage` proposal is produced instead.

Each local event is stored once in SQLite under its `event_id`. The canonical
SHA-256 fingerprint of the originally submitted event JSON is stored as well.
The same ID with the same payload reuses the existing result and does not
re-run the engine; the same ID with a different payload fails with
`StateConflictError`. The fingerprint does not include the corpus, so
reprocessing that reflects a corpus or logic change requires a new event
ID/version policy.

## Currently out of scope

Automatic issue closure, unreviewed deployment, automatic code modification,
permission bypass, real Jira writes, real-time webhook/queue, and an
operational RAG with feedback indexing are not included in the current
scaffold.
