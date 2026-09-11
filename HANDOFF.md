# Jira VOC Nexus handoff — 2026-09-11

## Issue #4 implemented: label taxonomy dimensions (2026-09-11, later session)

- Implemented the design recorded in the "Label taxonomy dimensions design for issue #4"
  entry below, per `voc-slice` (single-worker orchestration; a contract/validation/render
  change, no ACL/replay surface touched).
- Orchestration record: Run `run_9288b20bb2e2`, Task `task_8b4d6d77eb48`, `worker-start
  --agent codex --model gpt-5.6-luna --effort max` in the current worktree. Completed
  cleanly with `worker_done`, released.
- Change (`nexus/proposals.py`, `nexus/service.py`, `nexus/opencode.py`,
  `tests/test_nexus.py`, `docs/ARCHITECTURE.md`, `docs/TEMPLATES.md`): `ALLOWED_LABELS`
  split into `TRIAGE_LABELS` (`needs-triage`/`possible-duplicate`, unchanged semantics) and
  `SEVERITY_LABELS` (`severity:low|medium|high|critical`, model-emittable, at most one
  enforced in `validate_proposal`). New `audience_coverage(proposal) -> str` (parallel to
  `recipients()`) computes `customer-only`/`engineering-only`/`both`/`neither`; the value is
  added as a prefixed `audience-coverage:<value>` entry to the rendered `Labels:` line by
  both renderers and exposed as the public result's new `audience_coverage` key. A model
  attempting to emit `audience-coverage:*` directly fails validation (unknown label, fail
  closed). `nexus/opencode.py`'s prompt gained the severity selection/omission policy
  (evidence-signalled selection, never invent) alongside the existing issue #11
  audience/duplication policy. `component`/`root-cause`/`fix-type` untouched, per the design
  doc's explicit deferral.
- Coordinator verification (before committing): `python3 -m unittest discover -s tests -v`
  — **187/187 passing** (3 PG-registry tests skip, expected); fixture CLI smoke run's
  `audience_coverage: both` / `Labels: audience-coverage:both, possible-duplicate` matched
  `docs/TEMPLATES.md`'s updated real-example blocks exactly (the worker regenerated them
  from actual fixture CLI output rather than hand-writing them); `git diff --check` clean.
  Reviewed the full diff directly (not just the worker's summary) before accepting it.
- Fixture-only verification; no real OpenCode/Jira provider exercised.
- Committed and pushed as `5a6d7b3` on `main`. Closed [GitHub issue
  #4](https://github.com/hjung3113/jira-voc-nexus/issues/4) with a summary comment
  (implementation, deferred sub-parts, verification), mirroring how #2/#8 were closed.

## Label taxonomy dimensions design for issue #4 (2026-09-11, later session)

- Ran `voc-workflow` (design only, no `nexus/*.py` touched). User picked issue #4 as the
  next slice after the cross-reference fix below.
- Issue #4 is coupled to #3/#5 via an open "producer-supplied vs. in-runtime severity"
  question recorded in `docs/GAP_ANALYSIS.md` — asked the user to decide it rather than
  guessing. **User decided: in-runtime inferred (LLM/heuristic judgment over evidence),
  not producer-supplied.** This keeps the v1/v2 event/corpus schema unchanged (no breaking
  change, no dependency on issue #5's versioning decision).
- Recorded in `docs/ARCHITECTURE.md`'s new "Label taxonomy dimensions (design, GitHub
  issue #4)" section:
  - The asymmetric-audience-grounding open question (`docs/TEMPLATES.md` §5) is resolved
    as a new **computed** `audience-coverage:*` dimension (`customer-only`/
    `engineering-only`/`both`/`neither`), a pure function of the proposal parallel to
    issue #8's `recipients()` — never judged by the model, no third `needs-triage`/
    `possible-duplicate` value or precedence rule needed.
  - A new **LLM-judged**, omittable `severity:*` dimension (`low`/`medium`/`high`/
    `critical`), selected only when evidence text signals it, following the existing
    null-not-invented doctrine; `validate_proposal` would enforce structural cardinality
    (at most one `severity:*` value) but not semantic correctness.
  - `component` and `root-cause` dimensions are explicitly **deferred**: `component` needs
    a bounded component/project registry that doesn't exist in `nexus/` or `rag/`'s
    `IndexDocument`; `root-cause` needs the evidence-to-label linkage issue #6 hasn't
    designed yet. A separate `fix-type` dimension was considered and dropped — the new
    `audience-coverage` dimension already carries that signal (`engineering-only` implies
    a fix is needed; `customer-only` implies it isn't).
  - `docs/TEMPLATES.md` §5 updated from "open question" to "resolved by design, not yet
    implemented," pointing at the ARCHITECTURE.md section for the full design.
- Verification: `python3 -m unittest discover -s tests` — 184/184 passing (3 PG-registry
  tests skip, expected, doc-only change); `git diff --check` clean.
- Not implemented — implementation follow-up (dimension-aware `ALLOWED_LABELS`,
  `audience_coverage()` function, OpenCode prompt severity policy, regression tests,
  TEMPLATES.md real-example updates) is listed in `docs/ARCHITECTURE.md`'s new section.
  Not yet committed.

## Cross-reference correction in TEMPLATES.md (2026-09-11, later session)

- Read this handoff's "Next steps"; the flagged stale cross-reference (asymmetric-audience-
  grounding open question in `docs/TEMPLATES.md` §5 pointed at issue #5, which is actually
  about the input event/corpus contract, not label taxonomy) needed confirming before any
  further design work relied on it. User confirmed **#4** ("label taxonomy has no severity/
  component/root-cause/fix-type dimension") is the correct target — it matches the actual
  question content. Fixed the cross-reference directly (doc-only, one paragraph).
- No gap issue selected yet for the next design slice — user deferred that choice.
- Verification: `python3 -m unittest discover -s tests` — 184/184 passing (3 PG-registry
  tests skip, expected); `git diff --check` clean. Not yet committed/pushed.

## Issue #8 implemented: recipient routing (2026-09-11, later session)

- User asked to read this handoff, pull out parallelizable remaining work, and run it in
  parallel per the project workflow. Re-checked open gaps (#3, #4, #5, #6, #8, #10) against
  live `gh issue view` content, not just this file: only **#8** turned out to be
  implementation-ready — #3 has an explicit open design question (producer-supplied vs.
  in-runtime severity, a breaking-contract decision), and #4/#5/#6/#10 are mutually coupled
  to that same undecided taxonomy/contract question or (for #10) gated by
  `docs/RAG_DESIGN.md`'s no-pre-eval-gate-adoption non-goal. Asked the user to confirm scope
  rather than force a second parallel track that would have collided with #8's edits to
  `docs/ARCHITECTURE.md`/`docs/TEMPLATES.md`; user picked "implement #8 only."
- Ran as an Orca-orchestrated worker per `voc-slice`/`orchestration`: Run `run_73d52cdbb2a8`,
  Task `task_463bfe0b6553`, `worker-start --agent codex --model gpt-5.6-luna --effort max` in
  the current worktree. Completed cleanly with `worker_done`, released.
- Change (`nexus/proposals.py`, `nexus/service.py`, `tests/test_nexus.py`,
  `docs/TEMPLATES.md`, `docs/ARCHITECTURE.md`): implements exactly the design already recorded
  in the "Recipient routing (design, GitHub issue #8)" section — `recipients(proposal) ->
  List[str]`, a pure function of which audience fields are grounded (`customer_reply` present
  → `user-support`, `engineering_action` present → `dev-team`), computed once and shared by
  `nexus/service.py`'s new public `recipients` key and a new `Recipients: <...>` line in both
  `render_comment`/`render_issue` (after `Labels:`, before the marker line). No engine-contract
  change: `validate_proposal`'s `{customer_reply, engineering_action, labels}` schema and the
  v2 marker format/version are untouched; not wired to any real Jira assignee/component/queue.
  Docs updated from "design, not yet implemented" to "implemented," with real-example blocks
  synced to actual renderer output.
- Coordinator verification (before opening the PR): `python3 -m unittest discover -s tests -v`
  — **183/183 passing** (3 PG-registry tests skip, expected); `git diff --check` clean; fixture
  CLI smoke run's `recipients` key and `Recipients: user-support, dev-team` line matched
  `docs/TEMPLATES.md`'s example exactly.
- Opened as PR #15. Dispatched an Astra medium review of the PR title/body + diff (Orca
  orchestration Run `run_54c8975f315c`, Task `task_ab99bdce8f7c`) — the first `worker-start`
  attempt hit the same `agent_prompt_stalled` failure documented elsewhere in this file for
  OMP paste dialogs, this time on a fresh Codex terminal in a new child worktree; `worker-abandon`
  plus a `worker-start --retry-of` onto a fresh terminal in the same worktree succeeded cleanly
  on the second attempt (no `terminal send --text "" --enter` was needed this time — the retry
  itself avoided whatever the first terminal choked on). **Fix for next time**: if a freshly
  created worktree's agent terminal fails with `agent_prompt_stalled` before any confirming
  Enter is sent, try `worker-abandon` + `worker-start --retry-of <old_dispatch>` on a new
  terminal before assuming an Enter will unstick it — that path worked here without needing the
  paste-dialog workaround.
- Astra review result: 0 high, 0 medium, **1 low** — `docs/ARCHITECTURE.md`'s "Implementation"
  section claimed all four recipient cases (`customer-only`, `engineering-only`, `both`,
  `neither`) were covered "at the public result level," but the worker's tests only asserted
  `NexusService.process`'s public `recipients` key for the both-present and both-null cases;
  the two single-audience cases were only asserted at the `recipients()` unit level and the
  rendered-text level. Verified the gap directly in `tests/test_nexus.py` before fixing.
- Fix: added `StubProposalEngine` (returns a fixed raw proposal) and
  `test_public_result_recipients_for_single_audience_proposals`, exercising
  `NexusService.process` end-to-end for both single-audience cases and asserting
  `result["recipients"]` directly — closing the actual gap the doc claimed was already closed,
  rather than weakening the doc's claim. Re-verified: **184/184 passing**, `git diff --check`
  clean. Pushed as a second commit on the same PR branch.
- Merged PR #15 (squash, branch deleted) into `main` at `ba19d0a`. Re-verified on `main`:
  184/184 passing. Issue #8 auto-closed via the PR's `Closes #8`; also left a closing comment
  summarizing the implementation and the review finding.
- Remaining open gaps unchanged by this session: #3, #4, #5, #6, #10 — all still blocked on the
  design decisions described in the "Next steps" section below (unchanged from before this
  session, since none of #3/#4/#5/#6/#10 were touched).

## Issue #2 closed as already resolved; recipient-routing design for #8 (2026-09-11, later session)

- Read this file plus `docs/INDEX.md`, then checked actual `git log`/`gh issue list`
  against the prior entries below: PR #13 (gap issue #7) is in fact merged
  (`402ae95`) despite the prior "Gap issue #7" entry below saying "Not yet merged" —
  that entry is now stale; trust `git log`/`gh issue view` over it. Both #7 and #11 are
  closed. Open gaps going in: #2, #3, #4, #5, #6, #8, #10.
- **Closed [issue #2](https://github.com/hjung3113/jira-voc-nexus/issues/2)** ("No
  differentiated user-facing vs developer-facing action content") without new code —
  it was already fully resolved by the audience-split v2 contract shipped in `6602a09`/
  `ec3615f` (`nexus/proposals.py`'s `customer_reply`/`engineering_action`, independently
  evidence-grounded). Commented with the resolving commits and closed via `gh issue
  close 2`.
- User picked **issue #8** (routing/recipient) as the next slice over #5 (input-contract
  fields) and #4 (label taxonomy dimensions) — both of those need a real versioning/
  taxonomy decision first, while #8 has a natural, low-risk signal already available
  from the v2 audience split.
- **Design-only session** (ran `voc-workflow`; no `nexus/*.py` touched): recorded in
  `docs/ARCHITECTURE.md`'s new "Recipient routing (design, GitHub issue #8)" section —
  `recipients(proposal) -> List[str]`, a pure deterministic function of which audience
  fields are non-null (`customer_reply` → `user-support`, `engineering_action` →
  `dev-team`, both/neither as the union/empty case), computed once and shared by
  `nexus/service.py`'s public result and both renderers so the three call sites cannot
  disagree. Explicitly **not** an engine-contract change (`validate_proposal`'s
  three-key schema is untouched, the model never emits or decides recipients) and
  explicitly **not** wired to any real Jira assignee/component/queue — that mapping is
  out of scope until a real Jira adapter exists (`docs/INTEGRATION.md`).
  - `docs/TEMPLATES.md`: new "6. Recipient routing (design, not yet implemented)"
    section; the existing v2 real-example blocks are intentionally left unchanged
    (they reflect actual current renderer output, which does not yet include the
    future `Recipients:` line).
  - `docs/INTEGRATION.md`: fixed a **stale, unrelated finding** discovered while
    editing the adjacent "Proposal/model contract" section — it still described the
    superseded v1 `recommendations`/single-list shape a full day after the v2 cutover
    landed. Corrected to the actual v2 shape in the same edit (directly adjacent text
    this change was already touching, not a separate refactor), and added the
    `recipients` design note there too.
  - Also flagged (not fixed) a second stale finding: `docs/TEMPLATES.md`'s label-
    taxonomy "open question" paragraph cites "GitHub issue #5" for the
    asymmetric-audience-grounding question, but the actual issue #5 as filed is about
    input-contract fields (component/severity/root-cause), not labels — this
    cross-reference looks wrong and needs the user/coordinator to confirm the correct
    issue (possibly #4) before anyone relies on it. Left a correction note in place in
    `docs/TEMPLATES.md` rather than silently repointing it.
- Verification: `python3 -m unittest discover -s tests` — **182/182 passing** (3
  PG-registry tests skip, expected); `git diff --check` clean. Doc-only change, no
  behavior affected.
- Not yet implemented or committed — this is the design record only, pending the
  implementation follow-up listed in `docs/ARCHITECTURE.md` (`nexus/proposals.py`'s
  `recipients()`, `nexus/service.py`'s public key, `tests/test_nexus.py` cases,
  `docs/TEMPLATES.md` real-example updates once the renderer actually emits the line).

## Gap issue #11: OpenCode prompt policy content (2026-09-11)

- Read the prior handoff's "Pick one at a time" file-ownership caution and analyzed every
  open gap issue (#2-#8, #10, #11) by file surface before parallelizing anything: #2/#5/#8
  share `nexus/proposals.py` + `docs/TEMPLATES.md` (already flagged do-not-parallelize);
  #3/#10 share `nexus/service.py`/`retrieval.py`, and #10 additionally conflicts with
  `docs/RAG_DESIGN.md`'s explicit non-goal ("replacing the current deterministic fixture
  runtime before the POC/evaluation gate passes") since wiring `nexus/` to consume the
  unadopted `rag/` toolkit is itself a pre-gate adoption step; #4/#6 both touch
  `nexus/proposals.py`/`rag/contracts.py` and depend on #3/#5's taxonomy decisions. Only
  **#7** and **#11** (this entry) were fully file-disjoint from each other and from every
  gated/shared-surface issue, and neither needed a design decision first. Confirmed this
  scope with the user before dispatching. See the companion "Gap issue #7" entry below for
  the other slice run in parallel.
- Ran as an Orca-orchestrated worker per `voc-slice`/`orchestration`: Run
  `run_d1e8445e5d4e`, Task `task_8a0eb5264ab9`, `worker-start --agent codex --model
  gpt-5.6-luna --effort max` in the current worktree, alongside the #7 worker in the same
  worktree (disjoint files, no conflict). Completed cleanly with `worker_done`, released.
- Change (`nexus/opencode.py`, `tests/test_nexus.py`): `OpenCodeEngine._request_message`'s
  `instructions` string now states the real allowed-label set (`needs-triage`,
  `possible-duplicate`) with one sentence per label on when to use it, the audience-split
  routing rule (customer-facing impact/status/guidance in `customer_reply`, internal
  diagnosis/remediation in `engineering_action`), and the duplication-judgment policy (only
  `possible-duplicate` when evidence describes the same underlying problem, not a merely
  related one; default to `needs-triage` otherwise). `output_contract`'s JSON shape and the
  existing null-not-invented/per-field-grounding sentences are unchanged.
- Coordinator verification: `python3 -m unittest discover -s tests -v` — **182/182 passing**
  (3 PG-registry tests skip, expected without `NEXUS_RAG_PG_TEST_DATASOURCE`); `git diff
  --check` clean; fixture CLI smoke run exit 0.
- Merged as PR #12 (squashed). Astra medium review (Orca orchestration Run
  `run_025664e31ba8`, Task `task_42a1ea06f372`) found 1 medium + 1 low before merge:
  (medium) the duplicate-judgment wording compared evidence documents to each other rather
  than anchoring to the current event and allowed a bare shared "symptom" to qualify, fixed
  by rewording to "at least one evidence document describes the same underlying problem as
  this event, not merely a similar symptom" (`nexus/opencode.py`, `tests/test_nexus.py`);
  (low) a dangling "see companion entry below" reference and a stale test count, both fixed.
  Re-verified after the fix: 181/181 passing on that branch alone, `git diff --check` clean.

## Gap issue #7: project field on IndexDocument (rag/ toolkit) (2026-09-11)

- Companion slice to the "Gap issue #11" entry above, run in parallel in the same worktree
  (disjoint files: this slice touches only `rag/`, `guides/`, and their tests; see that
  entry for the full file-surface analysis of why only these two issues were parallelized).
- Ran as an Orca-orchestrated worker per `voc-slice`/`orchestration`: Run
  `run_d1e8445e5d4e`, Task `task_ddbca538169e`, `worker-start --agent codex --model
  gpt-5.6-luna --effort max`. Completed cleanly with `worker_done`, released.
- Change (`rag/contracts.py`, `rag/retrieval.py`, `guides/RAG_ACL.md`,
  `guides/RAG_JIRA_INGESTION.md`, and the affected `tests/test_rag_*.py`): `IndexDocument`
  gained a `project: str` field (`issue_to_documents` copies `NormalizedIssue.project` onto
  both the `jira_problem` and `jira_resolution` documents; `wiki_to_document` sets
  `project=""` since `WikiPage` has no project concept). `rag/retrieval.py`'s same-project
  boost at the `_apply_boosts` step now compares `doc.project == query.project` instead of
  the prior `doc.system == query.project` workaround — it remains a soft ranking boost, not
  an enforced filter, per `rag/acl.py`'s own docstring (no ACL enforcement code was added
  there, matching the issue's scope). `guides/RAG_ACL.md`'s example
  `CompanyPrincipalAcl.visible_document` now wires the already-declared-but-unused
  `Principal.allowed_projects` field into an actual `doc.project` check, replacing a comment
  that used to say project-level ACL needed a side table. Did not touch `nexus/`,
  `rag/acl.py`'s enforcement logic, `rag/registry.py`/`registry_pg.py` (their `system`
  column is the entity registry's own field, unrelated to `IndexDocument.project`), or any
  adoption-boundary doc.
- Coordinator verification: `python3 -m unittest discover -s tests -v` — **182/182 passing**
  (3 PG-registry tests skip, expected without `NEXUS_RAG_PG_TEST_DATASOURCE`); `git diff
  --check` clean; fixture CLI smoke run exit 0.
- **Real finding from re-running `python3 -m rag eval --fixtures-dir fixtures/rag --golden
  fixtures/rag/golden_set.json`** (numbers on this branch): `bm25-only` recall@5/recall@10
  stay 1.000/1.000 but mrr@10/ndcg@10 drop 1.000→0.927/0.944; `vector-only`/`hybrid` drop
  further, recall@5 1.000→0.909, mrr@10/ndcg@10 1.000→0.924/0.941; the rerank variants are
  unaffected (1.000/1.000/1.000/0.989 unchanged). Root cause: `fixtures/rag/golden_set.json`
  query index 4 sets `query.project = "PAY"` while its one relevant doc,
  `OPS-201:problem`, actually belongs to project `OPS`. Under the old buggy comparison
  (`doc.system == query.project`, a literal string like `"PAY"` never equalling a fixture
  `system` value such as `"LogWarehouse"`/`"PayGateway"`), the boost never fired for this
  query and the effect was invisible. Under the fixed comparison it now fires for every
  same-project `PAY-*` distractor, outranking the true positive.
- **Astra medium review corrected the coordinator's first framing of this finding**
  (Orca orchestration Run `run_025664e31ba8`, Task `task_da08c2097e6a`, run in a separate
  `astra-review-pr13` child worktree checked out on this branch): the coordinator had
  called query index 4 a "golden-set fixture defect" and proposed relabeling its
  `project` field. Astra pointed out this is wrong — `docs/RAG_DESIGN.md:193-198` states
  same-project is explicitly "a small boost, **not a hard filter**" specifically because
  "project-only filtering can hide valid cross-project failures/remediations," and
  `guides/RAG_EVALUATION.md:218-221` explicitly requires a cross-project golden-set subset
  "mirrored from this repo's own `fixtures/rag/golden_set.json`" — i.e. query index 4 is
  an intentional cross-project golden case, not a data-entry error, and must not be
  relabeled. Astra also reproduced the actual rank shift: the same-project boost's fixed
  weight now dominates the ~0.016-0.033 RRF fusion score range enough to move
  `OPS-201:problem` from rank 1 to rank 5-6 for `bm25-only`/`vector-only`/`hybrid`. The
  corrected framing: this is an **acknowledged cross-project ranking regression** exposed
  (not caused in kind, only in visibility) by fixing the field-comparison bug, and the real
  follow-up is **boost-magnitude calibration** (`boosts.same_project` in
  `rag/retrieval.py`), not a golden-set edit — the golden case is preserved as-is.
  `git stash`/`git stash pop` was used only to confirm the pre-fix baseline numbers on a
  clean tree; no golden-set files were modified, and boost-magnitude tuning is left out of
  this PR's scope (it needs its own evaluation pass across more than one query, and this
  issue was specifically about the missing `project` field, not boost calibration).
- Follow-up (revised): tune `boosts.same_project` in `rag/retrieval.py` against a broader
  golden-set evaluation so the now-correctly-wired same-project boost stops overriding a
  deliberately cross-project relevant result; do **not** edit
  `fixtures/rag/golden_set.json` query index 4, which is intentional per
  `guides/RAG_EVALUATION.md`'s cross-project requirement.
- Not yet merged — opened as its own PR for Astra review before merge.

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

## Audience-split output contract design (2026-09-10, later session)

- User decided [GitHub issue #9](https://github.com/hjung3113/jira-voc-nexus/issues/9):
  dual-audience output **is** in MVP scope. Decision recorded as an issue comment and
  the issue closed (`completed`).
- Ran the `voc-workflow` skill to design next-slice candidate 1 from
  `docs/GAP_ANALYSIS.md` (audience-split output contract). This session is **design
  only** — no `nexus/*.py` code was touched, per explicit scope. Recorded:
  - `docs/ARCHITECTURE.md`: new "Proposal output contract (v2, audience-split)" section
    — engine output becomes `{"customer_reply": obj|null, "engineering_action":
    obj|null, "labels": [...]}`, each audience field independently evidence-grounded,
    max 2,000 chars, `null` (never invented) when ungrounded. Documents the rationale
    for two single nullable objects instead of two 5-item lists, and lists the exact
    implementation follow-up (`nexus/proposals.py`, `nexus/opencode.py`'s prompt/
    instructions, `nexus/service.py`'s public result key rename, and the five
    regression-test cases needed). Also updates "Public result and operational status"
    to record the `recommendations` → `customer_reply`/`engineering_action` public CLI
    key change as a breaking-but-acceptable change (nothing is published yet).
  - `docs/TEMPLATES.md`: added v2 comment/issue format sections (design target) next to
    the existing v1 sections (still the actual renderer behavior), with real-example
    renders, and an open question under the label taxonomy section (asymmetric
    grounding across the two audience fields — tracked under issue #5, not decided
    here).
  - `docs/INTEGRATION.md`: noted that a future write adapter's marker lookup must check
    both `v1` and `v2` marker prefixes once v2 ships, since replay identity is
    `event_id` + payload fingerprint, not renderer version (consistent with the
    existing replay caveat).
- Verification: `python3 -m unittest discover -s tests`: **177/177 passing** (3 PG
  skip), unaffected — doc-only change. `git diff --check` clean.
- Did **not** start any other gap issue in parallel, per this file's own prior
  instruction. Issues #2, #5, #8 (which this design unblocks) are still open and
  untouched.

## Audience-split output contract implementation (2026-09-10, later session)

- Implemented the v2 audience-split contract designed in the previous session, per
  `voc-slice` (single-worker orchestration, no separate reviewer — a validation/
  rendering contract change, not ACL/replay).
- Orchestration record: Run `run_a2c8562d393b`, Task `task_548678205e72`, dispatched via
  low-level `terminal create` + `dispatch --task ... --to ... --inject` to an OMP
  terminal running `zai/glm-5.3` at `--thinking=high` (per this project's "complex
  implementation" routing rule; note the CLI flag is `--thinking=<level>`, not
  `--reasoning-effort`). Hit the same OMP paste-confirmation-dialog stall documented in
  the previous gap-analysis session's orchestration lesson (`dispatch --inject` pastes a
  large task spec, OMP raises its own confirm dialog, Orca's ~30s liveness monitor marks
  the dispatch `agent_prompt_stalled` and revokes the capability before the dialog is
  answered). Sent an immediate confirming empty Enter (`terminal send --text "" --enter`)
  after the stall was observed; the worker then ran the task to completion and sent
  `worker_done`, which Orca rejected (`dispatch_capability_invalid` — capability already
  revoked). The coordinator verified the actual work directly (diff review + full test
  run + fixture CLI) rather than trusting the lifecycle channel, then closed the task
  with a manual `task-update --status completed` carrying a note, and `worker-release`
  (reported `retained`/`no_owned_resource` since `dispatch --inject` never created a
  supervised worker row — consistent with the orchestration guide).
- Files changed by the worker: `nexus/proposals.py` (`validate_proposal` new
  `{customer_reply, engineering_action, labels}` schema with independent per-field
  lexical grounding via a new `_audience_field` helper; `fixture_proposal` produces both
  fields; `render_comment`/`render_issue` render the v2 template with `|v2|` markers),
  `nexus/opencode.py` (`_request_message`'s `output_contract`/`instructions` describe the
  new shape and the null-not-invented / per-field-grounding rules), `nexus/service.py`
  (public result's `recommendations` key replaced by `customer_reply` +
  `engineering_action`), `tests/test_nexus.py` (existing format-contract tests updated to
  v2 shape/markers/frozen-key-set; new tests for both-null, customer-only, engineering-
  only, disjoint-evidence union, and both directions of cross-field-citation rejection),
  `docs/TEMPLATES.md` (v2 real-example blocks synced to actual fixture renderer output).
- **Coordinator review finding and fix**: the worker's `nexus/opencode.py` diff
  accidentally dropped `"model": model` from the `agent.voc-triage` block in
  `_runtime_config` — unrelated to the assigned scope and uncaught by any existing test.
  Fixed directly by the coordinator (one-line restore) before verification; re-ran the
  full suite after the fix.
- Coordinator also updated `docs/ARCHITECTURE.md` (marked the v2 contract as
  implemented, not a design record; "Implementation follow-up" section rewritten as
  "Implementation record" of what actually landed; "Public result and operational
  status" updated to describe v2 as current, v1 as historical/replay-only) and
  `docs/TEMPLATES.md`/`docs/INTEGRATION.md` (v1 sections relabeled historical/superseded,
  v2 sections relabeled implemented/current, since this was a hard cutover with no v1
  code path remaining).
- Verification (coordinator, after the fix): `python3 -m unittest discover -s tests` —
  **181/181 passing** (3 PG-registry tests skip, pre-existing and unrelated); `git diff
  --check` clean; fixture CLI (`python3 -m nexus --event fixtures/event.json --corpus
  fixtures/corpus.json --state <fresh state>`) smoke run succeeded, output matches
  `docs/TEMPLATES.md`'s v2 real-example blocks exactly (`voc-nexus-comment|v2|event-001`
  / `voc-nexus-issue|v2|event-001` markers, `customer_reply`/`engineering_action` in the
  public result).
- Fixture-only verification; no real OpenCode/Jira provider was exercised this session.
- Not yet committed/pushed — pending user confirmation before commit, per this project's
  authorization scope discipline.

## Astra medium review of the audience-split commit (2026-09-11)

- Reviewed only commit `6602a09`'s message + diff (per user request), via Orca
  orchestration `worker-start --agent codex --model gpt-6-astra --effort medium`
  (Run `run_8443944f7694`, Task `task_037b58ba9674`) — no other files read, no tests run.
  Both requested/effective launch model and effort were accepted as given.
- Two low findings, both checked against the actual repo state before acting:
  1. **Real, fixed** (`ec3615f`): `tests/test_nexus.py`'s `test_no_evidence_skips_selected_engine`
     had silently lost its `self.assertEqual(engine.calls, 0)` check during the v2
     rewrite — the test still passed but no longer verified the documented
     no-provider-call-without-evidence invariant (`nexus/service.py`'s "hard no-provider
     path" comment). Restored; 181/181 still passing.
  2. **No action needed**: the commit message's "fixed a dropped model-config regression"
     line has no visible counterpart in the diff — correct as observed, because the
     coordinator fixed that regression *before* staging in the prior session, so the
     final diff against the pre-worker state shows no net change there. Documented here
     for anyone re-reading the commit message cold.
- Worker/task/run cleaned up (`worker-release`, `task-update --status completed`).

## Next steps

- **Issues #8 and #4 are now implemented, merged, and closed** (see their "implemented"
  entries above; PR #15 `ba19d0a` for #8, commit `5a6d7b3` for #4).
  ~~**Start here next session**: issue #8's recipient-routing design is recorded in
  `docs/ARCHITECTURE.md`/`docs/TEMPLATES.md`/`docs/INTEGRATION.md`... but not implemented.~~
  ~~**Start here next session**: no gap issue is currently implementation-ready. #3, #4, #5,
  #6, #10 all need a design decision first...~~
- **Start here next session**: remaining open gap issues are #3 (severity/impact/priority
  *scoring* used by retrieval/ranking — distinct from #4's now-implemented severity
  *label*), #5 (input contract fields — needs a versioning decision, breaking v1
  event/corpus schema), #6 (evidence-to-label linkage in `rag/` — blocks #4's deferred
  `root-cause` dimension and any future `component` registry work), #10 (nexus↔rag wiring,
  gated by the RAG adoption boundary in `docs/RAG_DESIGN.md`). All four still need a design
  decision before coding; #5/#10 additionally need an explicit versioning/adoption decision,
  not just a coding slice.
- Real Jira/provider connection is a separate slice after the ACL/auth/server
  contracts in [docs/INTEGRATION.md](docs/INTEGRATION.md) are met (tracked loosely by
  issue #10 above but not blocked on it). The write lifecycle will consume the v2
  TEMPLATES.md formats and marker contract; a real write adapter must still handle
  pre-cutover v1-marker'd events on replay (see docs/INTEGRATION.md's marker note).
- Orchestration lesson reaffirmed: OMP's flag for reasoning depth is `--thinking=<level>`
  (off/minimal/low/medium/high/xhigh/max/auto), not `--reasoning-effort` — the latter
  errors out immediately (`unknown flag`). Use `omp --help` to confirm flags before
  `terminal create --command` if unsure.
