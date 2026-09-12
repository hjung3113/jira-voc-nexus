# Company-internal onboarding guide

This is a preparation and decision guide for an internal operator. It does not
ask a company to export Jira data, sanitized data, identities, URLs, config,
logs, embeddings, judgments, or evidence. Keep all of those inside the
company's approved systems by default. Copy the companion
[checklist](COMPANY_ONBOARDING_CHECKLIST.md) into an internal controlled record
system; the Git copy is a template, not an approval or an execution log.

## Read this boundary first

Today the repository contains two local surfaces, not a connected service:

| Surface | Available now | Still missing or not proven |
| --- | --- | --- |
| `nexus` | File-based normalized-event/corpus dry-run, deterministic fixture engine, validation, SQLite replay, and local render | Jira ingress, trusted principal, read adapter, webhook/queue, RAG wiring, and Jira writes |
| `rag` | Stdlib local `index`, `query`, and `eval`; SQLite registry; local lexical/vector/rerank stand-ins; code-level OpenSearch/PostgreSQL/BGE adapter seams | Jira ingestion adapter, request-scoped production ACL wiring, live adapter/provider/cluster evidence, and an adopted production configuration |
| OpenCode | One approved-provider process boundary exists in `nexus` when configured | An internal provider/model, secret/CA/egress path, and quality result are not validated here |

The local `rag` CLI uses `AllowAllAcl` and is safe only for one already-
authorized fixture/state corpus. It is not a shared multi-principal service.
The `nexus` and `rag` packages are not wired together. See the exact execution
boundary in [architecture](../docs/ARCHITECTURE.md#current-boundary), the
[local RAG boundary](../docs/ARCHITECTURE.md#local-rag-proof-of-concept-boundary),
and the [integration contract](../docs/INTEGRATION.md).

No automated onboarding auditor exists. `scripts/doctor.py` checks environment,
links, and entry files; it does not prove Jira auth, visibility, ACL safety,
provider containment, data quality, or adoption. An operator must collect the
evidence and mark an internal copy of the checklist manually.

## Ordered phases

### 0. Prepare externally, using synthetic data only

Before any company connection, assign internal owners for product/scope, data
handling, Jira/platform, identity/ACL, retrieval evaluation, provider, and
operations. Write down purpose, allowed systems, retention, incident contact,
and the no-export rule. Use only `fixtures/` or newly generated synthetic
records in preparation, demos, and development.

Prepare an internal environment manifest, without pretending this repository
has artifacts it does not have:

- Record the repository revision, Python version, installed package versions,
  and the optional extras from `pyproject.toml` (`rag-platform`, `rag-pg`,
  `rag-reranker`) as present/absent. `pyproject.toml` currently gives lower
  bounds, not a lockfile; the company must resolve/pin versions and record
  hashes and license approval before controlled installation. This repository
  has no offline bundle; its absence is not a failure when an approved,
  networked internal mirror is permitted.
- Decide how proxy, CA trust, egress allowlisting, secret injection, and log
  retention will be reviewed. Store names/locations/digests, never secret
  values, in the internal record.
- Define the measurement plan for CPU, RAM, disk/cache, GPU if any, indexing
  throughput, query latency, concurrency, and failure recovery. Plan the
  benchmark now; measure after the isolated fixture and internal controls, then
  select hardware or an internal endpoint from results, not guessed model specs.
- Treat Jira flavor/version, read-only authentication, principal resolution,
  issue visibility, comment visibility, source URL, and rate limits as
  explicit internal decisions. Do not guess an API/version path from a generic
  example or require web research before the owner supplies the mapping.

The package/dependency and secret boundaries are summarized in the
[deployment prerequisites and secrets policy](RAG_DEPLOYMENT.md#prerequisites)
and [secrets policy](RAG_DEPLOYMENT.md#secrets-policy).

### 1. Run an isolated local fixture smoke

Run from the repository root with a POSIX shell, Python 3.9+, and `rg`. Use a
new temporary directory each run; never reuse `.local/` or overwrite a previous
state file. These commands make no network calls and use only the published
synthetic fixtures:

```sh
(
  set -eu
  smoke_dir="$(mktemp -d "${TMPDIR:-/tmp}/jira-voc-onboarding.XXXXXX")"
  python3 -m nexus --event fixtures/event.json --corpus fixtures/corpus.json \
    --state "$smoke_dir/nexus.sqlite3" > "$smoke_dir/nexus.json"
  python3 -m rag index --fixtures-dir fixtures/rag \
    --state "$smoke_dir/rag/state.json"
  python3 -m rag query --state "$smoke_dir/rag/state.json" \
    --text "4107 오류" --error-code 4107 --json > "$smoke_dir/query.json"
  python3 -m rag eval --fixtures-dir fixtures/rag \
    --golden fixtures/rag/golden_set.json > "$smoke_dir/eval.md"
  test -s "$smoke_dir/nexus.sqlite3" && test -s "$smoke_dir/rag/state.json"
  rg -Fq '"dry_run": true' "$smoke_dir/nexus.json"
  rg -Fq '"published": false' "$smoke_dir/nexus.json"
  rg -Fq 'Problem: Parser aborts while inserting raw data after equipment disconnect' "$smoke_dir/query.json"
  rg -Fq 'Resolution: OPS-201 resolution' "$smoke_dir/query.json"
  for variant in bm25-only vector-only hybrid hybrid+rerank hybrid+rerank+expansion; do
    rg -Fq "| $variant |" "$smoke_dir/eval.md"
  done
)
```

The expected local assertions are non-empty state, `dry_run=true` and
`published=false`, an OPS-201 problem plus resolution in query context, and all
five named evaluation rows. They prove fixture/runtime behavior only; they do
not prove Jira, provider, ACL, OpenSearch, PostgreSQL, or BGE behavior. The
[local-first run](RAG_DEPLOYMENT.md#local-first-run-verify-before-touching-any-adapter)
and [operations boundary](RAG_OPERATIONS.md#current-deployment-boundary-read-this-before-promising-an-sla)
explain the same limits.

### 2. Do an internal Jira read-only and normalization slice

This phase is a company-internal decision and adapter exercise, not a request
to send data to this repository. First record the verified Jira flavor/version,
auth mechanism, trusted service principal resolution, issue-level and
comment-level visibility semantics, URL/CA path, and approved read-only scope.
Hold if any mapping is unknown. The repository has no runnable Jira read/ingest
adapter; a future adapter must be read-only first and must resolve the trusted
principal before search/model calls.

Against a small internally approved sample, prove: issue and comment visibility
matches the principal matrix; source fields normalize to `NormalizedIssue`;
sanitization is deterministic; a changed issue reprocesses all comments; and a
deleted issue removes both deterministic document IDs. Keep raw, sanitized,
normalized, and evidence artifacts in the internal system with their retention
policy. Use the exact [normalized issue contract and field mapping](RAG_JIRA_INGESTION.md#target-contract-normalizedissue),
[sanitization rules](RAG_JIRA_INGESTION.md#sanitization-rules-before-indexing),
and [incremental indexing policy](RAG_JIRA_INGESTION.md#incremental-indexing-policy).

Do not call this phase complete from a fixture export: the adapter, principal,
visibility proof, and source provenance are still absent from this repository.

### 3. Validate one approved internal LLM provider separately

Provider validation is a separate gate from retrieval quality and Jira access.
Select exactly one internally approved `provider/model`; do not use public
fallbacks, unbounded retries, or automatic escalation. Validate proxy/CA,
egress, secret injection, timeout, model identity, config digest, request/log
retention, and that no raw prompt/result leaves approved systems. Use synthetic
inputs first, then only company-approved representative inputs.

The current boundary uses `NEXUS_OPENCODE_MODEL`,
`NEXUS_APPROVED_PROVIDER`, and `NEXUS_OPENCODE_CONFIG`; record observed values
as names/digests in the internal record, never credentials. Incomplete streams,
timeouts, schema/evidence failures, and insufficient evidence are hold/fail.
Drill malformed/truncated output, timeout, and missing optional dependency.
After Phase 1 and internal endpoint/data controls pass, provider and Jira
infrastructure tests may run in parallel; do not combine them into a deployment
or send company data until their separate gates pass. Measure provider resource
use and latency before selecting hardware or an endpoint. Provider success does
not authorize Nexus/RAG adoption.

### 4. Evaluate representative retrieval and ACL safety internally

This real-data phase needs the Phase 2 approved corpus/ACL path and only the
retrieval adapters being evaluated. It does not depend on the Phase 3 OpenCode
provider smoke; those evaluations can proceed independently. Before
collecting scores, internal owners must write the quality thresholds and
decision rule. The onboarding policy requires **>=100 queries** and **ACL
leakage = 0** for adoption; these are evidence gates, not runtime checks that
`rag.eval` hardcodes. The repository does not choose recall, MRR, nDCG,
latency, throughput, or resource cutoffs for a company. Sample and date the
corpus, stratify by project/system, language, resolved status, component,
error-code, and cross-project cases, and retain misses with reviewer rationale
internally.

Run all five variants and record Recall@5/10, MRR@10, nDCG@10, latency p50/p95,
indexing throughput, re-index cost, per-subset metrics, and misses. Separately
run the real-principal ACL leakage set across every access-scope class: no
forbidden ID may appear in `fused`, `final`, or fetched context. Exercise
revocation and deletion after indexing, not only initial visibility; a stale
document or entity is a hold. Record the exact [evaluation gate and recording
requirements](RAG_EVALUATION.md#recording-results) and [ACL leakage = 0 method](RAG_ACL.md#the-acl-leakage--0-evaluation-method).

Run retrieval/ACL adapter-error drills, resource benchmarks, restore, new-name
reindex, and rollback checks. A failure holds the phase; never open access with
`AllowAllAcl`, switch providers, or silently return best effort. Use the
[fail-closed rules](RAG_OPERATIONS.md#fail-closed-operational-rules),
[monitoring](RAG_OPERATIONS.md#monitoring), and [rollback procedure](RAG_OPERATIONS.md#rollback).

### 5. Future Nexus↔RAG adoption gate, then a separate write gate

Adoption requires the read-only Jira slice, standalone provider synthetic
validation, >=100-query evaluation, ACL leakage = 0, and a reviewed
request-scoped wiring design. The future wiring must pass the trusted principal into
`PreRetrievalAcl` before search and model calls; it must not expose the local
CLI or `AllowAllAcl` to multiple principals. Publish no configuration, alias,
model, or registry snapshot automatically. Wiki and code-graph sources are
later optional phases, after Jira provenance/ACL/retention are closed; see the
[RAG operations boundary](RAG_OPERATIONS.md#current-deployment-boundary-read-this-before-promising-an-sla).

Writing to Jira is a later, separately approved gate. It needs the full
[comment/label adapter completion contract](../docs/INTEGRATION.md#jira-commentlabel-adapter-completion-conditions):
stable operation key, v1/v2 marker lookup, unknown publish state, no repost on
label-only retry, bounded retry, concurrency protection, and human review.

### Local replay versus future remote reconciliation

Current local replay is only SQLite state: the same `event_id` and payload
fingerprint reuses the result; a changed payload with the same ID is a
conflict. It has no external effect and cannot tell whether Jira was written.
Future remote reconciliation must treat a lost publish response as `unknown`,
look up both marker versions before retrying, and retry labels without reposting
an already-confirmed comment. Never infer a remote write from local replay.

## Compact internal evidence record

Use one record per phase, stored outside Git:

```text
Record ID / phase / status (not-started | in-progress | pass | hold | n/a):
Owner / run date / code revision:
Package + optional dependency + offline-artifact manifest:
Config/provider/model/policy digests (no secrets):
Sample provenance, corpus scope, and date range:
Subset metrics, misses, reviewer rationale, ACL revocation/deletion result:
Failure drills, resource measurements, restore/rollback result:
Internal evidence locator, retention, and decision notes:
```

Do not fill in approvals that have not happened. Do not export the record;
only provide a minimal aggregate pass/hold summary if company policy separately
permits it. On day one, run Phase 0, assign owners, execute Phase 1, and open
the internal Jira decision record. Phase 2 and standalone Phase 3 may run
in parallel after Phase 1 plus endpoint/data controls; there is no combined
deployment until all required gates pass. This ordering keeps wiki/codegraph,
remote reconciliation, and Jira writes optional/later rather than hidden
prerequisites. The required sequence is: Phase 0 handling/manifest before
Phase 1; Phase 1 fixture pass plus internal endpoint/data controls before Phase
2 or standalone Phase 3; Phase 2 and the selected retrieval adapters before
Phase 4. Combine Phase 3 and Phase 4 evidence for a Nexus↔RAG+LLM integration
decision; reviewed wiring and the separate write gate are still required
before any Jira write.
