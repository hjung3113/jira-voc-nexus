# RAG operations runbook

## What this covers

Day-2 operations for the `rag/` toolkit once any part of it is wired into a
real workflow: what actually needs backing up (and what does not), how to
reindex and roll back safely, what to monitor and alert on, and the
fail-closed rules an operator must not weaken under incident pressure. It
also states plainly what deployment boundary exists today versus what a
production rollout would still have to build. Self-contained: restates the
contracts it uses rather than assuming `rag/` is open. See
[guides/RAG_DEPLOYMENT.md](RAG_DEPLOYMENT.md) for adapter wiring,
[guides/RAG_ACL.md](RAG_ACL.md) for the ACL contract this runbook's
monitoring section watches, and
[guides/RAG_EVALUATION.md](RAG_EVALUATION.md) for the metrics this
runbook's regression checks compare against.

## Prerequisites

- The local toolkit already verified per
  [guides/RAG_DEPLOYMENT.md](RAG_DEPLOYMENT.md#local-first-run) (index /
  query / eval all pass on fixtures) before any of this applies to a real
  deployment.
- Whatever real adapters you have wired in (`OpenSearchBackend`,
  `PostgresKnowledgeRegistry`, a real embedding endpoint, `BgeRerankerAdapter`)
  per [guides/RAG_DEPLOYMENT.md](RAG_DEPLOYMENT.md)'s swap sections, and
  your company's existing backup/monitoring infrastructure for the
  databases those adapters point at -- this runbook does not replace your
  company's PostgreSQL/OpenSearch operational tooling, it says what from
  this toolkit specifically needs to plug into it.

## Current deployment boundary (read this before promising an SLA)

Be exact about what exists today:

- `rag/` is a Python library plus a local-only CLI
  (`python3 -m rag index|query|eval`, see
  [guides/RAG_DEPLOYMENT.md](RAG_DEPLOYMENT.md)). It is **not** an HTTP
  service, has no webhook listener, and ships no Jira read/write adapter --
  matching the same boundary [docs/ARCHITECTURE.md](../docs/ARCHITECTURE.md)
  states for `nexus/` ("not an HTTP/webhook server or internet ingress").
- `docs/RAG_DESIGN.md` lists FastAPI as the *proposed* "retrieval service
  boundary when a production API is introduced" -- that API does not exist
  in this repository. Do not describe this toolkit as production-ready or
  as having a service boundary; it has a callable library boundary only.
- **The callable integration path that does exist today**: a caller can
  `import rag` and call `RetrievalPipeline.retrieve` followed by
  `ContextBuilder.build` in-process, in the same Python process that has
  already resolved the trusted principal and built the `PreRetrievalAcl`
  described in [guides/RAG_ACL.md](RAG_ACL.md). This is the only current
  path suitable for request-scoped authorization. The local CLI
  (`python3 -m rag query --state <path> --text <text> --json`) is a bounded
  fixture/local-corpus tool: `_build_pipeline` uses `AllowAllAcl` and rebuilds
  its registry from the state file, so it is safe only when the state file is
  a pre-authorized corpus for one already-authorized principal. Do not expose
  that CLI as a shared service, accept multiple principals through it, or use
  the client query fields to make authorization decisions. A production
  caller must build a request-scoped ACL in-process (and use server-side
  OpenSearch ACL filtering when applicable) before search or context fetch.
- **What a real rollout still has to build, and this toolkit does not
  provide**: request authentication/authorization resolution (this
  toolkit only *consumes* a trusted principal via `PreRetrievalAcl` -- it
  does not resolve one from a session/token), an external HTTP retrieval
  service/ingress boundary, a Jira read/ingest or comment/label write
  adapter (out of scope for `rag/` entirely -- see
  [guides/RAG_JIRA_INGESTION.md](RAG_JIRA_INGESTION.md)), a supervising
  process/service around the library call (retry policy, queueing,
  concurrency limits), and the backup/monitoring wiring this runbook
  describes below. None of this exists in the repository today; do not
  report it as built. In particular, the local CLI is not a substitute for
  the missing authenticated HTTP service or Jira ingress.

## Backup and restore

### Local mode (`.local/rag/state.json` + sidecar registry)

- `state.json` (path given via `--state`) is the single source of truth
  for a local index: it embeds both the full `IndexDocument` corpus and
  the registry's `entities`/`relations` payload (see
  `_cmd_index`/`_load_state` in `rag/__main__.py`). Back up **this file
  only** -- back it up the same way you back up any other repo-adjacent
  state file your deployment produces (your existing file backup/snapshot
  policy; this toolkit does not ship one).
- The `<stem>.registry.db` sidecar SQLite file next to `state.json` is a
  **derived cache**, not a second source of truth: `python3 -m rag query`
  always rebuilds a fresh registry database from `state.json`'s embedded
  `registry` payload into a temporary directory (see `_build_pipeline`),
  never from the sidecar. Losing the sidecar is a non-event; regenerate it
  by re-running `python3 -m rag index` from the same fixtures, or just
  ignore it if only `query`/`eval` are needed.
- **Restore**: copy `state.json` back into place and re-run
  `python3 -m rag query --state <path> --text "<smoke query>"` -- if it
  returns a context, the restore is complete. There is no separate restore
  step for the sidecar (see above). A restored state is never evidence of
  authorization correctness: before serving a principal, revalidate the
  restored corpus's document ACL metadata and registry/entity ACL snapshot
  against the current policy, including deletions and revocations made after
  the snapshot. Do not use a restored local state for shared multi-principal
  serving because the CLI's `AllowAllAcl` is intentionally local-only.
- `.local/` is excluded from log collection per
  [AGENTS.md](../AGENTS.md) but a backup destination for `state.json` must
  still be treated per your data-handling policy -- it contains the same
  Jira/wiki-derived text that was indexed, sanitized per
  [guides/RAG_JIRA_INGESTION.md](RAG_JIRA_INGESTION.md#sanitization-rules-before-indexing)
  and [guides/RAG_WIKI_INGESTION.md](RAG_WIKI_INGESTION.md), but never a
  credential (see the secrets policy in
  [guides/RAG_DEPLOYMENT.md](RAG_DEPLOYMENT.md#secrets-policy)).

### Production adapters (PostgreSQL registry, OpenSearch index)

- **PostgreSQL (`PostgresKnowledgeRegistry`)**: back it up with your
  company's standard PostgreSQL backup mechanism (e.g. `pg_dump` /
  continuous WAL archiving / your managed-Postgres provider's snapshot
  feature) pointed at whatever database `NEXUS_RAG_PG_DATASOURCE` names.
  This toolkit does not add a bespoke backup path -- `knowledge_entity`
  and `knowledge_relation` (the DDL in
  [guides/RAG_REGISTRY.md](RAG_REGISTRY.md#postgresql-ddl-and-adapter-usage))
  are ordinary tables in whatever database you already operate.
- **OpenSearch (`OpenSearchBackend`)**: treat the index as a **rebuildable
  derived artifact**, not a primary source of truth to back up directly.
  The authoritative content is Jira and the company wiki (per
  [docs/RAG_DESIGN.md](../docs/RAG_DESIGN.md#knowledge-source-roles)'s
  trust ordering) plus the knowledge registry above -- disaster recovery
  for the search index is "re-run ingestion" (per
  [guides/RAG_JIRA_INGESTION.md](RAG_JIRA_INGESTION.md) and
  [guides/RAG_WIKI_INGESTION.md](RAG_WIKI_INGESTION.md)) into a freshly
  created index, not "restore a search-index snapshot". If your ingestion
  volume makes a full re-run too slow to be an acceptable recovery time,
  use OpenSearch's own snapshot API as a faster-restore optimization on
  top of, not instead of, keeping ingestion re-runnable from source.
- Keep the exact ACL metadata/policy version, registry snapshot identity,
  source deletion/revocation watermark, embedding model/dimension, and index
  mapping/analysis identity with the source snapshot. An index snapshot or a
  `state.json` copy without those identities is not a safe multi-principal
  restore candidate.
- Never treat a `state.json` file, an OpenSearch index, or the registry
  database as something you hand-edit to "fix" bad data in place -- fix
  the mapping/extraction step
  ([guides/RAG_JIRA_INGESTION.md](RAG_JIRA_INGESTION.md),
  [guides/RAG_WIKI_INGESTION.md](RAG_WIKI_INGESTION.md),
  [guides/RAG_REGISTRY.md](RAG_REGISTRY.md)) and re-index, so the fix
  survives the next full rebuild.

## Reindex and rollback

### Reindexing without downtime

1. Build the new index/state under a **new name**, never in place:
   - Local: a new `--state` path (e.g. `.local/rag/state.<version>.json`).
   - `OpenSearchBackend`: a new `index_name` (per
     [guides/RAG_DEPLOYMENT.md](RAG_DEPLOYMENT.md#swap-2-lexicalindexvectorindex---opensearchbackend)'s
     warning to never reuse an `index_name` across an embedder swap --
     the same rule applies to any reindex, embedder swap or not, so a bad
     reindex never corrupts the index callers are currently reading).
   - `PostgresKnowledgeRegistry`: a registry reindex is normally an
     incremental upsert (per
     [guides/RAG_REGISTRY.md](RAG_REGISTRY.md#seeding-workflow)'s dry-run
     diff), not a full rebuild -- but if you are rebuilding from scratch
     (e.g. after a bad batch), build into a new database/schema and
     verify before pointing production traffic at it, for the same reason
     as above.
2. Run the full smoke checklist from
   [guides/RAG_DEPLOYMENT.md](RAG_DEPLOYMENT.md#smoke-checklist-after-any-adapter-swap)
   plus the ACL poison-document recipe
   ([guides/RAG_ACL.md](RAG_ACL.md#poison-document-test-recipe)) against
   the *new* index/state before any caller is switched to it.
3. Run the golden-set comparison
   ([guides/RAG_EVALUATION.md](RAG_EVALUATION.md#running-the-5-variants))
   against the new index/state and compare to the last recorded baseline
   (see "Monitoring" below) -- a reindex that regresses recall/nDCG
   without an explained cause (e.g. an intentional mapping change) is a
   signal to hold the swap, not push it.
4. Only then prepare a cutover **bundle**, not just an index. The bundle must
   identify the exact local corpus mirror/state (when used), OpenSearch
   index/alias, PostgreSQL registry snapshot, embedding endpoint/model and
   dimension, analyzer/mapping version, and ACL policy/version plus deletion
   watermark. Verify all members were built from the same source snapshot and
   that the current ACL policy still denies revoked documents/entities.
5. Publish one immutable bundle manifest through the caller's configuration
   coordinator, then switch callers to that manifest. For local mode, update
   the state path atomically; for OpenSearch, move the alias only as part of
   this coordinated publication. An alias-only switch is unsafe: a stale
   local mirror or registry can apply the wrong ACL or entity expansion to
   documents returned by the new index. If the deployment cannot coordinate
   these pointers atomically, stop traffic during the short cutover rather
   than serving a mixed bundle.

### Rollback

- **Local mode**: point `--state` back at the previous `state.json`. This
  has zero external dependency and is always available -- it is the same
  fallback [guides/RAG_DEPLOYMENT.md](RAG_DEPLOYMENT.md#rollback)
  describes for a failed/misbehaving adapter, and it applies equally to a
  bad reindex.
- **OpenSearch**: restore the previous complete bundle manifest, including
  the previous local corpus mirror and registry identity; moving only the
  alias back is not sufficient. Revalidate current document/entity ACLs and
  deletion/revocation watermarks before re-enabling callers, because an old
  snapshot may contain content that is no longer authorized.
- **PostgreSQL registry**: if a bad seeding batch was already written
  (skipped its dry-run review, or the review missed something), there is
  no built-in versioning in `rag.registry`/`rag.registry_pg` -- recovery
  is either (a) restore from the most recent database backup (above) if
  the batch is recent and a short data-loss window is acceptable, or (b)
  construct a reverse batch from the dry-run diff artifact your seeding
  process should have kept
  ([guides/RAG_REGISTRY.md](RAG_REGISTRY.md#seeding-workflow) step 3) and
  apply it (delete the added relations/entities, restore any
  `upsert_entity` field changes to their prior values). This is exactly
  why the dry-run diff artifact must be retained after a write, not
  discarded once the human reviewer approves it.
- After any rollback, re-run the smoke checklist and the ACL
  poison-document recipe against whatever you rolled back *to* -- a
  rollback target that has not been re-verified recently can itself be
  stale or wrong. Treat a revoked document or entity discovered during this
  check as a failed rollback, not as a reason to relax the ACL.

## Monitoring

This toolkit is stdlib-only and ships no metrics/logging integration by
design (per [guides/RAG_DEPLOYMENT.md](RAG_DEPLOYMENT.md)'s package
layout). Wire the following into your own structured logging
(Python's stdlib `logging` module needs no new dependency) or metrics
system around every real call site. `acl_filtered_count` is the only
per-request retrieval signal exposed as a `retrieve()` return value; the
other rows below describe instrumentation you add at the call site (or in a
custom pipeline), not toolkit return values:

| Signal | Where it comes from | Why it matters |
| --- | --- | --- |
| `RetrievalResult.acl_filtered_count` | Return value of `RetrievalPipeline.retrieve` | Per [guides/RAG_ACL.md](RAG_ACL.md), a persistent `0` on queries that should have hidden documents is itself a misconfiguration signal, not a clean result. Log it on every request. |
| Separate lexical and dense channel counts/latencies plus RRF depth | Wrap the channel calls yourself: time each `search_lexical`/`search_dense` (or your custom pipeline's two channel calls) around `pipeline.retrieve()` -- `RetrievalResult` does not expose per-channel fields | A single mixed query can hide channel failure and defeats the intended server-ACL-before-RRF contract; alert when either channel is absent, under-fills unexpectedly, or returns an invalid response shape. |
| Any adapter/ACL/registry exception (including `RagInputError`, HTTP client errors, OpenSearch client errors, and psycopg driver errors) | Catch at the service boundary and classify into a bounded failure class | Per "Fail-closed operational rules" below, this must hold that request, not be swallowed or opened up. Alert on a rate increase, not just log it; never assume `RagInputError` is the only exception type. |
| Bundle manifest and ACL/source watermarks | Cutover/restore coordinator and ingestion registry | Detect an alias, local mirror, registry, model identity, or ACL policy that no longer refers to the same source snapshot. A mismatch blocks cutover. |
| Reindex throughput, fresh/warm query latency, and ACL filter cost | Scheduled evaluation/reindex measurement, split by lexical, dense, RRF, rerank, and context fetch | A green relevance score can still violate an operational budget or hide a slow ACL implementation; record p50/p95 and resource usage for the corpus size being adopted. |
| Golden-set metric drift | Re-run [guides/RAG_EVALUATION.md](RAG_EVALUATION.md)'s 5-variant comparison on a schedule (e.g. weekly, or after every reindex per above) against the same golden set, and diff against the last recorded table | Silent retrieval-quality regression (a bad reindex, an ingestion mapping change, an embedder drift after a model version bump) has no other signal -- nothing else in this toolkit fails loudly when relevance quietly gets worse. |
| ACL leakage golden-set result | Re-run [guides/RAG_ACL.md](RAG_ACL.md#the-acl-leakage--0-evaluation-method) on the same cadence as the golden-set re-run above, and after every ACL or ingestion-mapping change | Per that guide, leakage is a hard pass/fail gate, not a metric to average -- treat any non-zero result as a page-worthy incident, not a backlog item. |

A minimal per-request log line (illustrative -- adapt field names to your
company's logging schema):

```python
import logging
import time

logger = logging.getLogger("rag.retrieval")

def logged_retrieve(pipeline, query):
    started = time.perf_counter()
    try:
        result = pipeline.retrieve(query)
    except Exception:
        # Fixed event and bounded classification only. Do not pass the
        # exception, traceback, URL, authorization header, query, or source
        # payload to the logger: adapter errors can contain all of them.
        logger.error(
            "rag_retrieve_hold",
            extra={
                "failure_class": "adapter_or_acl_error",
                "query_text_len": len(query.text) if isinstance(query.text, str) else None,
            },
        )
        raise
    logger.info(
        "rag_retrieve_ok",
        extra={
            "latency_ms": (time.perf_counter() - started) * 1000.0,
            "acl_filtered_count": result.acl_filtered_count,
            "final_count": len(result.final),
        },
    )
    return result
```

Note what this example deliberately omits: it never logs `query.text` or
document `title`/`text` content verbatim (only a length) -- per
[AGENTS.md](../AGENTS.md)'s "never send production VOC data ... to Git,
external models used for development, or public artifacts" rule, treat
your log sink the same way if it is not a company-internal, access-
controlled system, and never log raw Jira/wiki text to a third-party
logging vendor without the same review you would give any other
production-data destination.

## Fail-closed operational rules

These mirror [docs/ARCHITECTURE.md](../docs/ARCHITECTURE.md)'s "Model
errors, timeouts, truncated streams, and insufficient evidence are treated
as hold/fail" rule and [AGENTS.md](../AGENTS.md)'s "no public model
fallback, unbounded retries, or automatic escalation" rule, applied to
this toolkit's own failure surfaces. An operator under incident pressure
must not weaken any of these to "get retrieval working again" faster:

1. **Any adapter, transport, registry, parsing, or ACL exception is a
   hold/fail signal for that request, never a trigger to silently retry
   against a different backend, degrade to `AllowAllAcl`, or return an
   empty/best-effort context and mark it as if it were a normal empty
   result.** The service boundary must catch `Exception` broadly enough to
   include urllib/OpenSearch/psycopg errors, log only a fixed bounded event,
   and convert it to the caller's explicit hold/no-recommendation outcome.
   A narrowly caught `RagInputError` is not sufficient. Bounded retries, if
   a company supervisor has explicitly approved them, must preserve the same
   principal, ACL filters, bundle identity, and failure classification; no
   retry may broaden access or switch to an unreviewed provider.
2. **If the ACL predicate implementation itself throws, that is not a
   reason to fall back to `AllowAllAcl`.** `AllowAllAcl` is documented in
   [guides/RAG_ACL.md](RAG_ACL.md) as "the development/local default --
   it must never be the ACL used to serve a real multi-principal
   deployment"; an ACL-resolution failure must fail the request, exactly
   like any other ACL denial-adjacent error, not open access as a
   fallback.
3. **A missing optional extra (`RagInputError: ... install it with: pip
   install ...`) is a configuration error to fix before serving traffic,
   never a signal to fall back to a public/hosted model or a different,
   unreviewed provider** -- this is the same "no public model fallback"
   rule [AGENTS.md](../AGENTS.md) states for the in-house LLM, applied
   here to the embedding/reranker/registry adapters.
4. **A reindex or rollback that has not passed the smoke checklist and
   ACL poison-document recipe (above) must not be pointed at by any live
   caller**, even under time pressure to restore service after an
   incident -- restoring service with unverified ACL enforcement is a
   worse outcome than staying on a known-good (even if stale) index.
5. **Never treat `acl_filtered_count == 0` as evidence the ACL is
   correctly wired** during an incident -- per
   [guides/RAG_ACL.md](RAG_ACL.md)'s failure-modes table, it is equally
   explained by "the ACL predicate always returns `True`". Confirm with
   the poison-document recipe before treating a `0` reading as good news.

6. **A no-answer or empty result is not interchangeable with an adapter
   failure.** Record whether the pipeline completed with zero visible
   candidates versus held before retrieval; neither state authorizes a model
   recommendation. The caller must preserve that distinction for evaluation
   and incident triage.

## Verification checklist

- [ ] `state.json` (or the production PostgreSQL/OpenSearch equivalents)
      has a documented, tested restore path that someone other than the
      person who wrote it has actually exercised once.
- [ ] Every reindex builds under a new name/path and is smoke-tested +
      ACL-poison-tested + golden-set-compared before any caller switches
      to it (never reindex in place).
- [ ] A rollback path exists and has been exercised (not just described)
      for local mode, the OpenSearch alias, and the PostgreSQL registry.
- [ ] `acl_filtered_count`, per-request latency, and every adapter/ACL
      failure are captured from real call sites, not just available as unused
      return values; exception text and traces are not sent to logs.
- [ ] Lexical and dense server-side ACL filters are tested independently,
      RRF is applied only to their filtered result sets, and a denied
      document/entity cannot be reached through registry expansion or a
      resolution/context fetch.
- [ ] Reindex/restore records throughput, p50/p95 latency, resource use,
      ACL-filter cost, and the complete bundle manifest (including model and
      policy identities).
- [ ] The golden-set evaluation and the ACL leakage evaluation both run on
      a recurring cadence, not only once at initial adoption.
- [ ] A green evaluation is recorded for human review only; no job
      automatically adopts a model, mapping, alias, registry snapshot, or
      deployment configuration.
- [ ] Nobody on the operating team believes this toolkit currently
      exposes an HTTP service or a Jira write adapter -- if the "Current
      deployment boundary" section above is news to someone operating
      this, fix that gap before the next incident, not during it.

## Failure modes

| Symptom | Likely cause | Where to look |
| --- | --- | --- |
| Restore from `state.json` succeeds but `query` returns nothing | Restored the sidecar `.registry.db` but not `state.json` itself, or restored an older `state.json` than intended | "Backup and restore" above -- `state.json` is the only file that matters for local mode |
| Reindex "succeeded" but callers still see old results | Cutover step (path/alias switch) was skipped or only partially applied | "Reindexing without downtime" step 4 above |
| New OpenSearch results are paired with wrong context or ACL behavior | Alias moved without the matching local corpus mirror, registry snapshot, embedding identity, or ACL policy version | Restore the complete bundle manifest; never fix this by switching to `AllowAllAcl` |
| Golden-set metrics regressed after a reindex with no ACL/mapping change intended | Source data actually changed (Jira/wiki content drift), or an unrelated dependency/model version drifted | Compare the exact `IndexDocument.text` for a sample of docs before/after, per [guides/RAG_JIRA_INGESTION.md](RAG_JIRA_INGESTION.md)'s failure-modes table |
| Restore passes smoke tests but exposes a revoked document/entity | The old snapshot predates an ACL revocation/deletion watermark | Revalidate the current ACL and source tombstones before serving; remove/hold the bundle if any revoked item remains |
| An incident response reindexes or rolls back without running the ACL poison-document recipe first | Time pressure led to skipping "Fail-closed operational rules" rule 4 | Treat the skipped verification as still owed immediately after service is restored, not waived |
| Nobody notices a real adapter has been silently returning `RagInputError` for hours | No alerting wired on the `RagInputError` log signal, only a log line nobody watches | "Monitoring" table above -- alert on the rate, do not rely on someone reading logs |
