# Jira VOC Nexus handoff — 2026-09-10

## Current state

- The OSS/VOC reuse research gate is satisfied and recorded in
  [docs/OSS_RESEARCH.md](docs/OSS_RESEARCH.md) and
  [docs/TOOLING_DECISION.md](docs/TOOLING_DECISION.md).
- The baseline is Python 3.9+ stdlib/SQLite, the existing OpenCode native CLI,
  and the four shared local skills (`orca-cli`, `orchestration`, `voc-slice`,
  `voc-workflow`).
- Jira connector, Promptfoo, Pydantic AI/LangGraph, and n8n/Activepieces
  runtime are not installed. `atlassian-python-api==5.0.4` remains a future
  candidate for after real ACL/auth/server flavor exists; Promptfoo is an
  optional future eval for stored results.
- The CLI is a file-input local proposal scaffold. It provides no production
  ingress, Jira ACL/adapter, webhook, RAG, or write reconciliation. It runs one
  OpenCode process per event with evidence and skips the provider process when
  there is no evidence.
- **Format contract v1 landed** (this session): `render_comment` now emits
  header / recommendations / sorted Evidence / sorted Labels / final
  `voc-nexus-comment|v1|<event_id>` marker, and the new `render_issue` renders
  the escalation issue template (`[VOC] ` summary ≤ 80 chars, structured
  description, `voc-nexus-issue|v1|<event_id>` marker) exposed as the additive
  `issue` key in the public result. Exact templates, real examples, event/corpus
  input contracts, and the label taxonomy live in
  [docs/TEMPLATES.md](docs/TEMPLATES.md). The markers are the dedupe lookup
  keys required by [docs/INTEGRATION.md](docs/INTEGRATION.md) completion
  condition 2; renderers fail closed on `event_id` values containing `|` or
  newlines so markers stay single-line and unambiguous.
- Repo docs and agent rules are now English (AGENTS.md, README.md, all of
  docs/). `CLAUDE.md` remains a relative symlink to AGENTS.md.
- **Issue #1 applied as design reference** (this session): the production
  Knowledge Retrieval Platform research (Haystack + OpenSearch hybrid/RRF +
  BGE-M3/reranker + PostgreSQL knowledge registry, canonical NormalizedIssue
  contract, Problem→Issue→Resolution retrieval rule, Wiki metadata contract,
  evaluation gate) is now recorded in [docs/RAG_DESIGN.md](docs/RAG_DESIGN.md)
  with an acceptance-criteria mapping. It is explicitly proposed-not-adopted;
  [docs/TOOLING_DECISION.md](docs/TOOLING_DECISION.md) carries the boundary
  and the current runtime is unchanged.

## RAG toolkit slice (2026-09-10, later session)

- The local POC toolkit from the issue #1 design now exists under `rag/`:
  strict contracts (`NormalizedIssue`, `WikiPage`, entity/relation,
  `IndexDocument`), ACL-before-scoring retrieval (BM25 + hashing-embedding
  vectors + RRF + boosts + lexical reranker; trust tiebreak), SQLite
  knowledge registry with BFS relation expansion (+ real lazy psycopg PG
  adapter), trust-ordered context builder, golden-set evaluation harness
  (recall@5/10, MRR@10, nDCG@10, latency p50/p95), and a local-only CLI
  (`python3 -m rag index|query|eval`). Optional extras (`rag-platform`,
  `rag-pg`, `rag-reranker`) carry the OpenSearch/BGE/PG adapters; default
  imports stay stdlib-only.
- Company deployment guides live in `guides/` (deployment/swap, Jira
  ingestion with verbatim LLM comment-classification prompt contract, wiki
  ingestion, registry seeding with LLM-assisted extraction + validation,
  ACL, evaluation). They are written to be consumed by an LLM without repo
  context.
- Verification: **136/136 tests** (20 nexus + 116 rag; 3 PG tests skip
  without `NEXUS_RAG_PG_TEST_DATASOURCE`); `python3 -m rag eval` on the
  10-query synthetic golden set: recall@5 = 1.000 for all five variants
  (rerank variants ndcg@10 = 0.989 — honest synthetic signal, real verdict
  needs the company golden corpus); `python3 -m rag query` works with the
  registry sidecar deleted (state is one JSON); nexus/ byte-identical.
- Review provenance: Grok R1 gate review (1 high: ACL-after-scoring + 8
  more) applied and re-verified; Grok R2 final review (1 high: OpenSearch
  swap corpus + 9 more) applied and re-verified. A Codex GPT-6 Astra
  final-judgment pass was dispatched at the 05:29 quota reset but the 5h
  window was still exhausted; task `task_f667be08f1ff` is blocked with that
  reason — retry it when the window refills if a design-level second
  opinion is still wanted.
- Boundary: this is the POC toolkit, not an adoption. The nexus/ runtime is
  unchanged; adoption still requires the evaluation gate (real-but-sanitized
  golden corpus, metric comparison, ACL leakage = 0) per
  [docs/RAG_DESIGN.md](docs/RAG_DESIGN.md) and
  [docs/TOOLING_DECISION.md](docs/TOOLING_DECISION.md).
- Review follow-up in the current shared WIP: evaluation now validates empty/
  duplicate golden IDs, empty sets, duplicate variant names/cutoffs,
  unknown/type-excluded IDs, and duplicate returned IDs, while requesting the
  actual evaluation depth from the retrieval seam. Context assembly keeps a
  hard character budget including omission notices, selected problem-to-
  resolution linkage, deduplication, and canonical-before-supporting order.
  Index staging treats embedded JSON as authoritative and the registry sidecar
  as disposable; query/eval close only owned temporary registry connections,
  never shared indexes.
- The retrieval adapter's `retrieve(query, *, top_k=None)` seam has since
  landed (raises lexical/vector/registry/fuse/final candidate limits to at
  least `top_k`, serving default unchanged at 5), along with a bounded
  ACL-visible registry-linked RRF channel and a fail-closed trusted-entity
  scope for relation expansion. The coordinator's final battery (after applying the
  last Grok delta review: Lucene HNSW method on the knn mapping, walk-all-
  hits ACL validation before top_k truncation, search-body/leak/competing-
  edge tests, operations-guide signal reframe, index/cross-ref fixes)
  reports **177/177 passing** (3 PG registry tests skip without
  `NEXUS_RAG_PG_TEST_DATASOURCE`). Orchestration history for this
  reinforcement pass: two design reviews plus three Codex implementation
  workers were dispatched by a root Astra orchestrator, which then hit the
  account 5h quota mid-run; the coordinator took over, and Claude Sonnet
  successors finished the three work packages before the final Grok delta
  review. The earlier 136/136 result above is superseded historical
  baseline evidence and must not be reused as the final count for this WIP.
  The synthetic golden set is now 11 queries (recall@5 = 1.000 across all
  five variants on the coordinator's run).
- Replay caveat: an event first processed before format v1 keeps its
  originally stored comment/result when replayed (replay identity is
  `event_id` + payload fingerprint and does not include the renderer version).
  A fresh state file or a new event ID renders the new format. A future
  re-render policy is an open integration question, not a local bug.

## Gap analysis: auto-recommendation, auto-labeling, dual-audience action items (2026-09-10, later session)

- User asked for a gap analysis of auto issue-recommendation, auto-labeling, and
  recommended-action generation (user-side + developer-side), explicitly requiring Orca
  CLI orchestration end-to-end (no other spawn mechanism), OMP/Grok as the review agents,
  and OMP restricted to the direct Z.AI path (`zai/glm-5.3-flash`), never OpenRouter.
- Ran 4 parallel read-only research tasks under Run `run_2cf16fa35e46` (OMP,
  `zai/glm-5.3-flash`, thinking `high`) over disjoint areas — core runtime (`nexus/`), RAG
  evidence layer (`rag/`), integration/action-routing contract, and product
  scope/taxonomy — then synthesized all four into **[docs/GAP_ANALYSIS.md](docs/GAP_ANALYSIS.md)**
  (35 ranked gaps + open design questions), then had Grok 4.6 (`high`, native `grok` CLI)
  adjudicate it. Grok's review is appended to that file: it confirmed the core
  dual-audience/two-label/fail-closed-schema diagnosis, downgraded 4 items (Jira-adapter
  absence, publish-path absence, ungated RAG top-5, unmet RAG adoption gate) from High to
  Medium as expected-for-a-pre-production-scaffold, **upgraded "dual-audience output is
  absent from stated scope" to High** as the actual decision gate for the others, corrected
  3 overstated claims, and found 2 new Medium gaps (`nexus/` never calls into `rag/`; the
  OpenCode prompt carries no audience/label/duplication policy).
- Raw per-area research reports are at `.local/gap-research/{A,B,C,D}-*.md` (local-only,
  not for external distribution, git-ignored).
- Filed the Grok-recalibrated High-severity gaps plus the 2 new findings as GitHub issues
  **#2–#11** on `hjung3113/jira-voc-nexus`, cross-linked so #9 (dual-audience scope
  decision) is marked as gating #2, #5, #8. Committed as `539b9dd` and pushed to
  `origin/main`.
- Orchestration lesson learned (repeat pattern from a prior session's Grok stall, now also
  hit with OMP): `orca orchestration dispatch --task <id> --to <handle> --inject` pastes
  the full task+preamble text into `omp`, which raises its own paste-confirmation dialog
  ("Attach as a wrapped block" / "Attach as local file" / "Paste inline") for large pastes.
  Orca's dispatch-liveness monitor does not wait past ~30s for that dialog and marks the
  dispatch `failed` (`agent_prompt_stalled`, capability revoked) even though the terminal
  is still live and will run the task correctly once an Enter is sent to accept the default
  option. All 4 GLM workers this session hit this and had their `worker_done`/heartbeats
  rejected after-the-fact (`dispatch_capability_invalid`); the coordinator verified
  completion by reading the on-disk report files directly and closed each task with a
  manual `task-update --status completed` plus a note, rather than trusting the lifecycle
  channel. **Fix for next time**: after `dispatch --inject` into an `omp` terminal, send an
  immediate confirming `terminal send --text "" --enter` within a few seconds (before the
  ~30s stall timeout) rather than inspecting the dialog first — this worked cleanly for the
  Grok dispatch in the same session (`grok --model grok-4.6 --reasoning-effort high`, no
  paste dialog, no capability revocation, full `worker_done` lifecycle). Also:
  `worker-start --model`/`--effort` is not supported for the `omp` or `grok` agent adapters
  ("Agent X does not support launch-time model selection") — the low-level
  `terminal create --command "<agent> --model ... --thinking/--reasoning-effort ..."` +
  `dispatch --inject` path is required for per-invocation model/effort control on these two
  agents.

## Verification (2026-09-10, by coordinator)

- `python3 -m unittest discover -s tests -v`: **20/20 passing** — includes the
  format-contract suite (marker-last, section order, sorted Evidence/Labels,
  79/80/81 summary boundary, URL-gate omission in both renderers, marker-safe
  `event_id` rejection, frozen public key set) plus the pre-existing
  fail-closed, replay-conflict, concurrency, and cross-project regressions.
- Fixture CLI smoke on a fresh state file: exit 0, `dry_run: true`,
  `published: false`, labels `["possible-duplicate"]`, comment and issue
  description both end with their `v1` markers.
- `python3 scripts/doctor.py`: all environment checks true (read-only by
  design; provider auth deliberately not checked).
- `git diff --check` clean; every relative link in AGENTS.md/README.md/docs/
  resolves; no Korean prose remains outside this-file-history.
- Review provenance: Grok 4.6 read-only review (1 high + 4 medium + 4 low
  findings) adjudicated and applied by the coordinator — the high finding
  (issue URL-gate test could not catch a leak) and all medium findings are
  fixed; the low doc findings (optional-Evidence skeletons, taxonomy wording)
  are fixed too.

## Orchestration record

- Run `run_d3f2ef5e6141`: impl task `task_8ad9817155f7` (Claude Sonnet 5
  medium; Codex was quota-blocked until 05:29 and the OMP injection path
  stalled on OMP's paste dialog), translation task `task_42a9c1038f8e` (same
  terminal, reused), review task `task_fb8db1150610` (Grok 4.6; prompt had to
  be submitted manually because its telemetry overlay blocked the injected
  Enter). All dispatches settled and terminals released.

## Next steps

- **Start here next session**: [GitHub issue #9](https://github.com/hjung3113/jira-voc-nexus/issues/9)
  needs a human product decision — is a user-ready response/workaround text in MVP scope
  at all, or does the MVP stop at internal triage pointers? This gates #2 (audience-split
  content), #5 (input contract fields), and #8 (routing), and shapes #3/#4/#6/#7. Answer
  this before starting schema/contract work on any of the other gap issues.
- Once #9 is answered, pick one of `docs/GAP_ANALYSIS.md`'s "Suggested next-slice
  candidates" (audience-split output contract, taxonomy dimensions, or a nexus↔rag wiring
  slice per issue #10) as the next `voc-workflow`/`voc-slice` task — do not start more than
  one in parallel given the shared `nexus/proposals.py` and `docs/TEMPLATES.md` surface.
- Real Jira/provider connection is a separate slice after the ACL/auth/server
  contracts in [docs/INTEGRATION.md](docs/INTEGRATION.md) are met (tracked loosely by
  issues #9/#10 above but not blocked on them). The write lifecycle will consume the
  TEMPLATES.md formats and marker contract.
- Coordinator commits/pushes this state; no runnable Jira adapter and no new
  required dependency are in this commit.
