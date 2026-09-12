# Company-internal onboarding checklist

Copy this template into the company's access-controlled record system before
using it. Leave Git, public artifacts, external models, and ordinary logs free
of company data. The operator fills `Status / record` for each row; blank rows
are not approvals. Use `pass`, `hold`, `in-progress`, `not-started`, or `n/a`.

| Phase | Role owner | Action | Expected internal evidence | Pass / hold criterion | Status / record |
| --- | --- | --- | --- | --- | --- |
| 0 | Product + data steward | Record purpose, scope, retention, incident contact, and no-export handling rule. | Policy reference and named owners. | Pass only if internal handling is approved; otherwise hold. | |
| 0 | Operator | Prepare only synthetic fixtures for external/pre-onboarding work. | Fixture revision and run date; no company payload. | Pass if no company data, identity, URL, config, log, embedding, judgment, or evidence leaves approved systems. | |
| 0 | Operator | Capture environment manifest: repo revision, Python, package versions, optional extras present/absent. | Version output and digest record. | Pass if observed values are recorded; hold if an unverified dependency is assumed. | |
| 0 | Platform + security | Review proxy, CA trust, egress allowlist, secret injection, and log retention. | Internal control references, CA/config digests, retention period. | Pass only for approved internal paths; never record secret values. | |
| 0 | Operations | Define the CPU/RAM/disk/cache/GPU, indexing/query latency, concurrency, and recovery benchmark plan. | Dated plan, target workload, and rollback hypothesis. | Pass when the plan and owner exist; run actual measurements after fixture and internal controls. | |
| 1 | Operator | Run isolated `nexus` fixture dry-run in a fresh `mktemp` state path. | JSON result, non-empty SQLite state, command/date/revision. | `dry_run=true`, `published=false`; no Jira write. | |
| 1 | Retrieval owner | Run local `rag index`, JSON `query`, and five-variant `eval` in fresh state. | State path, query output, eval table, stdout/stderr retention decision. | 21-doc fixture index, OPS-201 problem+resolution context, five variants; fixture-only. | |
| 1 | Operator | Confirm local smoke is not integration evidence. | Record explicitly says no live Jira/provider/OpenSearch/PG/BGE/ACL proof. | Any production claim is a hold. | |
| 2 | Jira/platform | Decide and record Jira flavor/version, read-only auth, principal resolution, issue/comment visibility, URL/CA, and rate policy. | Internal decision record and principal/visibility matrix. | Unknown mapping is an explicit hold; do not guess API/version instructions. | |
| 2 | Jira/platform + security | Implement or assign the missing read-only adapter slice; fetch issue/comments with trusted principal before search/model. | Internal adapter test evidence, auth audit trail, no-write proof. | Pass only after adapter and principal path are real; repository has no runnable Jira adapter. | |
| 2 | Data steward | Normalize and sanitize an approved internal sample; verify deterministic re-run and source provenance. | Raw/sanitized/normalized hashes or internal locators, date range, mapping report. | Parser passes; no credential/PII/topology leak; no invented resolution. | |
| 2 | Ingestion owner | Exercise update, comment edit, issue deletion, and deterministic document IDs. | Before/after docs, deletion/revocation watermark, replay report. | All comments reprocessed; deleted issue removes both docs; otherwise hold. | |
| 3 | LLM/provider owner | Validate one approved in-house provider/model with synthetic input, separately from retrieval/Jira. | Provider/model identity, config digest, proxy/CA/egress/secret path, latency/resource log. | One approved provider only; no public fallback or unbounded retry; malformed/truncated output holds. | |
| 3 | Data/security + operations | Verify prompt/result, credentials, embeddings, and logs stay in approved internal systems. | Retention and access review, redacted log sample, secret-injection evidence. | Any uncontrolled destination is a hold; may run in parallel with Phase 2 after Phase 1 controls. | |
| 4 | Evaluation owner | Set recall/MRR/nDCG/latency/throughput/resource thresholds before measurement. | Dated threshold decision and reviewer names. | Only internal owners set quality cutoffs; do not import guesses. | |
| 4 | Evaluation owner | Build representative golden set with at least 100 queries and dated provenance. | Corpus scope/date range, strata, judgments, misses/rationale. | >=100 is required for adoption; smaller set is a hold for that decision. | |
| 4 | Retrieval owner | Run all five variants and report aggregate plus error-code, cross-project, language, project/system, status, component subsets. | Full metric table, p50/p95, throughput, re-index cost, config/model/index digests. | Meet predeclared thresholds; every unexplained miss is a hold/review item. | |
| 4 | ACL owner | Run real-principal leakage set across every access-scope class. | Triples, forbidden IDs, fused/final/context results, `acl_filtered_count`. | Leakage must be exactly zero for adoption; any forbidden ID is a hard hold. | |
| 4 | ACL + ingestion owner | Revoke access and delete source/entity after indexing, then query and reindex/rollback. | Revocation/deletion results, watermarks, stale-state check, rollback evidence. | Denied/deleted data never appears; stale visibility is a hold. | |
| 4 | Operations | Drill retrieval timeout/adapter error, ACL error, resource benchmark, restore, reindex, and rollback. | Failure classes, bounded logs, recovery timing, bundle/state manifest. | Fail closed without `AllowAllAcl`, fallback, or best-effort answer; otherwise hold. | |
| 5 | Architecture owner | Review future Nexus↔RAG request-scoped wiring and adoption bundle. | Principal→ACL→search/model flow, failure/rollback plan, code/config digests. | No shared local CLI/`AllowAllAcl`; no automatic adoption. | |
| 5 | Product + Jira/platform | Open a separate human-reviewed write-gate decision. | Internal approval reference, operation key/markers, unknown-write and label-retry drill. | No writes until read-only, eval, ACL, provider, wiring, and dedupe gates pass. | |
| 5 | Architecture owner | Defer wiki/codegraph and remote marker reconciliation until required gates pass. | Explicit later-scope record and dependency list. | Optional future work must not be represented as onboarded. | |

## Record fields and references

For every row retain: record ID, status, owner, run date, code revision,
package/optional-dependency/offline-artifact manifest, configuration/policy
digests, sample provenance/date range, subset metrics, misses, ACL
revocation/deletion result, failure drills, resource measurements, rollback
result, internal evidence locator, retention, and decision notes. Do not invent
an approval field or export raw evidence. A minimal aggregate pass/hold result
may leave the company only if a separate company policy explicitly permits it.

Use the long guides for procedure rather than copying them here: [deployment
and local smoke](RAG_DEPLOYMENT.md#local-first-run-verify-before-touching-any-adapter),
[Jira mapping and sanitization](RAG_JIRA_INGESTION.md#field-mapping-table),
[ACL verification](RAG_ACL.md#verification-checklist), [evaluation recording](RAG_EVALUATION.md#recording-results),
and [operations verification/fail-closed rules](RAG_OPERATIONS.md#verification-checklist).

The current local replay record is not remote reconciliation: SQLite reuses a
same-payload `event_id` and rejects a changed payload, while a future Jira
adapter must reconcile both marker versions, unknown publish responses, and
label-only retries without reposting comments. See
[integration completion conditions](../docs/INTEGRATION.md#jira-commentlabel-adapter-completion-conditions).
