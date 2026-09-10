# Gap analysis: auto-recommendation, auto-labeling, and dual-audience action items

Status: draft research synthesis, not adopted. This document does not change runtime
behavior; it compiles four parallel research passes into one ranked gap list to inform
future slice prioritization. See [ARCHITECTURE.md](ARCHITECTURE.md), [RAG_DESIGN.md](RAG_DESIGN.md),
[INTEGRATION.md](INTEGRATION.md), and [PROJECT_OVERVIEW.md](PROJECT_OVERVIEW.md) for the
current adopted contracts this analysis is checked against.

## Method

Four read-only research passes were run in parallel (OMP, `zai/glm-5.3-flash`, thinking
`high`) over disjoint areas of the repository, each required to cite `file:line` or a doc
section for every claim:

- **A — Core runtime** (`nexus/`): the local proposal engine, renderers, and taxonomy.
- **B — RAG evidence layer** (`rag/`): the proposed-not-adopted retrieval/evidence toolkit.
- **C — Integration/action-routing contract**: what stands between a rendered proposal and
  a real Jira write reaching the right person.
- **D — Product scope and label taxonomy**: whether the stated MVP scope and taxonomy
  support two distinct audiences at all.

Raw per-area reports are preserved at `.local/gap-research/{A,B,C,D}-*.md` (local-only,
not for external distribution). This document merges and ranks their findings; it does not
edit any of the four originals.

## Cross-cutting finding

All four areas converge on the same root cause, described from different layers:

**The system has exactly one generic recommendation list and a 2-label taxonomy
(`needs-triage`, `possible-duplicate`), and every component — retrieval, engine contract,
templates, and the input/output data model — treats "the recommendation" as singular and
audience-agnostic.** There is no field, anywhere in the pipeline, that distinguishes
content a support/end-user reply needs (acknowledgment, workaround, status) from content a
developer/engineering ticket needs (suspected root cause, affected component, remediation
steps). This is a scope gap (nothing in `PROJECT_OVERVIEW.md`'s non-goals forbids it — see
D6) and a data-contract gap (the strict input/output schemas have no place to put it — see
A-gap-1, B-gap-5, D-gap-3), not a bug in existing code.

## Ranked gaps

Severity and provenance are carried from the source reports. Each item names the owning
area report for full evidence.

### High severity

1. **No differentiated user-facing vs developer-facing action content.** `render_comment`
   and `render_issue` both consume the same `proposal["recommendations"]` list; the engine
   contract has only generic `recommendations` + `labels` fields.
   (A-1: `nexus/proposals.py:120-123,154-158`; D-1: `docs/TEMPLATES.md` §1-2)
2. **No severity/impact/priority scoring anywhere in the runtime.** `Event` carries no
   severity/impact fields; retrieval scores are discarded before reaching output.
   (A-2: `nexus/models.py:59-76`, `nexus/retrieval.py:71-84`, `nexus/service.py:50-62`)
3. **Label taxonomy has no severity/component/root-cause/fix-type dimension**, and
   `possible-duplicate` is emitted on any evidence match with no duplication judgment.
   (A-3: `nexus/proposals.py:13,199`; D-2: `docs/TEMPLATES.md` §5)
4. **Input contracts carry no component/severity/root-cause data**, so audience-specific
   output cannot be composed even if templates were extended without a breaking schema
   change (event/corpus are exact-field-set, fail-closed).
   (D-3: `docs/TEMPLATES.md` §3-4)
5. **No relevance/confidence threshold gates what becomes a "recommendation."** RAG's
   top-5 is returned unconditionally; scores are uncalibrated across RRF/rerank stages.
   (B-1: `rag/retrieval.py:1064-1071,903`)
6. **Retrieval quality is unproven and unevaluated at the decision level.** The project's
   own adoption gate (≥100 real queries, ACL leakage = 0) is unmet; no metric exists for
   "was the recommended issue actually a duplicate" or "was the label right."
   (B-2: `docs/RAG_DESIGN.md:430-438`, `guides/RAG_EVALUATION.md:80-84`)
7. **No evidence-to-label linkage.** Source labels never reach `IndexDocument`; label
   choice is ungrounded model opinion the validator cannot check against evidence.
   (B-3: `rag/contracts.py:306-333,365-419`)
8. **Project is absent from `IndexDocument`**, so project-level ACL is impossible without
   an out-of-band side table; cross-project evidence leakage is possible today.
   (B-4: `rag/contracts.py:365-419`, `guides/RAG_ACL.md:91-101`)
9. **No real Jira adapter** — no connector, service principal, ACL/auth, or decided server
   flavor. Nothing the scaffold produces can reach Jira.
   (C-1: `docs/INTEGRATION.md:8-14,27-31`)
10. **No publish/write execution path.** Dedupe-lookup, lost-publish handling, retry, and
    atomic worker ownership exist only as future-slice completion conditions.
    (C-2: `docs/INTEGRATION.md:76-98`)
11. **No routing logic deciding the recipient.** No user-support vs dev-team split, no
    component/team ownership registry, no assignee/queue field. Every output dead-ends in
    one undifferentiated triage label.
    (C-3: `docs/INTEGRATION.md:39-45`, `HANDOFF.md:21-29`)

### Medium severity

12. **No confidence/uncertainty signaling** in nexus output — reviewers see recommendations
    with no strength indication. (A-4)
13. **The only implemented engine is a declared non-production demo** (fixture heuristic
    picks the alphabetically-first token); OpenCode-path semantic quality is unmeasured.
    (A-5: `nexus/proposals.py:175-176,185-188`)
14. **No human-in-the-loop override/feedback capture** — no approve/reject/edit path;
    dedupe store replays stale proposals forever. (A-6: `nexus/storage.py:49-54`)
15. **"Related" and "duplicate" are not distinguished** — a single label covers both.
    (A-7)
16. **No user-reply vs dev-fix distinction in RAG evidence** — resolution structure is
    flattened at index time; ingestion's 5-class comment taxonomy is discarded after
    mapping. (B-5: `rag/contracts.py:395-417`, `guides/RAG_JIRA_INGESTION.md:87-100`)
17. **Documented ranking signals (verified-resolution trust, error-code boost) are dead or
    dominant depending on reranker regime** — uncalibrated, regime-dependent behavior.
    (B-6: `rag/retrieval.py:1064-1068`)
18. **No feedback loop from wrong/rejected recommendations back into the evidence layer**
    (RAG side) — golden set can't grow from operations. (B-7)
19. **Resolution evidence is reachable only through its own problem doc** — the documented
    "correct remediation lives on a different related issue" case is structurally
    unreachable. (B-8: `rag/retrieval.py:1032-1036`)
20. **No escalation/priority mechanism tied to labels** — no condition triggers escalation
    issue creation or maps to a Jira priority. (C-4: `docs/INTEGRATION.md:43`)
21. **No feedback/outcome tracking loop** (integration side) — recommendation correctness
    is unmeasurable; routing/threshold rules can never be tuned from evidence. (C-5)
22. **Rate-limit/write-budget policy is specified but not implemented.** (C-6:
    `docs/INTEGRATION.md:89-91`)
23. **No SLA/ownership handoff contract for dev-facing tickets** — no ack/claim semantics,
    no clock start definition; tickets can rot unowned. (C-7)
24. **Ambiguous-classification handling is undefined** — `needs-triage` and
    `possible-duplicate` can co-occur with no precedence rule. (D-4: `docs/TEMPLATES.md` §5)
25. **Taxonomy stability/versioning is marker-only** — the `v1` marker versions rendering
    format only, not the label vocabulary; replayed events can show stale
    formats/labels with no compatibility policy. (D-5)
26. **Dual-audience output is absent from stated scope, not deferred by it** — this needs
    an explicit product decision, not code; no non-goal currently blocks it. (D-6)

### Low severity

27. Incoming event labels are parsed but never used by retrieval or output taxonomy. (A-8)
28. Replay identity ignores corpus/engine changes — stale proposals persist after corpus
    growth. (A-9)
29. Renderer limit inconsistencies (fixture caps at 3 of an allowed 5; 80-char summary
    truncation ignores word boundaries). (A-10)
30. Default-path "semantic" evidence is lexical coincidence (hashing embeddings, token
    overlap) — real vector/rerank adapters are integration-unverified. (B-9)
31. Context budget selects by trust order, not relevance; omitted evidence cannot be
    re-requested by the LLM. (B-10)
32. OpenSearch adapter hard-fails above 10,000 ACL-visible doc ids per principal —
    availability gap at broad-principal scale. (B-11)
33. No real-time ingress — CLI is file-based only; no webhook/queue. (C-8)
34. Re-render/versioning policy for replayed pre-format-v1 events is undecided. (C-9,
    overlaps D-5)
35. Delivery boundary means even a correct dual-audience contract has no delivery path in
    the current scaffold — contract and write adapter must be sequenced, contract first.
    (D-7)

## Open design questions requiring a human product decision

These recur across reports and are not resolvable by further code investigation:

- **Audience scope decision**: is a user-ready response/workaround in MVP scope, or does
  the MVP stop at internal triage pointers? (D) This gates nearly every other gap above.
- **Where the recommendation splits**: one proposal with `customer_reply` +
  `engineering_actions` sections, or two separately-validated proposals? (A, D)
- **Confidence/threshold ownership**: computed deterministically in code vs self-reported
  by the LLM (untrusted input under this repo's rules) vs a nexus-side policy check over
  RAG's uncalibrated scores. (A, B)
- **Severity/component source of truth**: producer-supplied (event contract must extend,
  a breaking change for producers already shipping v1) vs inferred in-runtime vs
  human-edited before approval. (A, D)
- **Project-level ACL**: is `project` actually required in `IndexDocument`, or is `system`
  the real access unit? (B)
- **Routing model**: static label→queue/component/assignee config vs a data-driven
  ownership registry, and who owns it. (C)
- **Escalation trigger semantics**: which label/evidence combination creates the `[VOC]`
  escalation issue vs a comment only, and what priority mapping applies. (C)
- **Feedback source of truth**: Jira issue transitions vs local SQLite, and how outcomes
  correlate back to `event_id` and individual recommendations (which have no stable
  per-item ID today). (B, C)
- **Taxonomy versioning policy**: bump the marker to v2 on label-vocabulary change, add a
  separate taxonomy-version field, or both — and what happens to already-replayed results.
  (D)

## Non-goal check

Per `docs/PROJECT_OVERVIEW.md`'s explicit "currently out of scope" list (auto-close,
unreviewed deployment, automatic code modification, permission bypass, real Jira writes,
real-time webhook/queue, operational RAG): **none of these forbid building dual-audience
recommendations, a richer label taxonomy, or action routing.** The gaps above are scope
omissions the current MVP simply hasn't reached, not prohibitions. The nearest adjacent
non-goal ("real Jira writes") blocks *delivery* of any of this, not the *content contract*
design — so contract work (audience split, taxonomy dimensions, severity fields) can
proceed ahead of, and independent from, the write-adapter slice.

## Suggested next-slice candidates (not decided — for coordinator prioritization)

1. Extend the engine/output contract with an explicit audience split
   (`customer_reply` / `engineering_action`, each with its own evidence grounding) —
   addresses gaps 1, 4, 16, 24.
2. Add a severity/component/root-cause dimension to the label taxonomy and event input
   contract, with an explicit compatibility/versioning plan — addresses gaps 3, 4, 25.
3. Define a nexus-side confidence/threshold policy consuming RAG's raw scores before RAG
   itself is calibrated — addresses gaps 5, 12.
4. Design the routing/ownership registry (label → team/component/assignee) as a
   contract-only slice, ahead of the real Jira write adapter — addresses gaps 9, 10, 11, 20.

These are inputs to a decision gate, not a plan; the coordinator and user should pick
which (if any) becomes the next `voc-workflow`/`voc-slice` task.

## Review record

### Grok 4.6 review

Adjudication of this draft against the current repository (read-only
spot-check of High-severity citations plus a missing-gap / severity /
internal-consistency pass). This section does not change runtime behavior
or adopt the ranked list.

### Verified claims

- Gap 1 (undifferentiated comment vs issue content): confirmed accurate against `nexus/proposals.py:119-123` (`render_comment` walks `proposal["recommendations"]`) and `nexus/proposals.py:146,154-158` (`render_issue` walks the same list). `docs/TEMPLATES.md` §1–2 specify identical Recommendations bullets in both artifacts.
- Gap 2 (no severity/impact/priority in the runtime): confirmed. `Event` is exactly `event_id/issue_key/project/summary/description/labels` (`nexus/models.py:59-76`); `retrieve()` computes a score then returns documents only (`nexus/retrieval.py:71-84`); the public result has no score/priority field (`nexus/service.py:50-62`).
- Gap 4 (strict event/corpus field sets carry no component/severity/root-cause): confirmed. `docs/TEMPLATES.md` §3–4 and `nexus/models.py:16-24,54-56,99-101` reject unknown fields; neither contract has those dimensions.
- Gap 5 (RAG top-5 with no score floor): confirmed as a retrieval fact. `RetrievalConfig.final_top_k = 5` (`rag/retrieval.py:903`); `retrieve()` fuses, boosts, reranks, re-ACLs, and returns `final` with no relevance/confidence cutoff (`rag/retrieval.py:1064-1071`). See Corrections for the “recommendation” wording.
- Gap 6 (adoption gate unmet; fixture eval is not adoption evidence): confirmed. `docs/RAG_DESIGN.md:430-438` still requires ≥100 real queries, metric comparison, and ACL leakage = 0; `guides/RAG_EVALUATION.md:80-84` states the committed set is harness smoke only. `fixtures/rag/golden_set.json` has 11 queries.
- Gap 7 (no evidence-to-label linkage): confirmed, and slightly stronger than stated. `IndexDocument` has no labels field (`rag/contracts.py:306-333`); `issue_to_documents` copies only `system`/`component`/`updated_at` (`rag/contracts.py:365-419`). Ingestion *does* map `fields.labels` → `metadata.labels` (`guides/RAG_JIRA_INGESTION.md:57`) and then drops them at projection. Downstream, `validate_proposal` allowlists labels and never grounds them in evidence (`nexus/proposals.py:47-48` vs text grounding at `:68-74`).
- Gap 9 (no real Jira adapter): confirmed. `docs/INTEGRATION.md:8-14` (no connector installed; `atlassian-python-api` is a future candidate pending ACL/auth/server flavor).
- Gap 10 (no publish/write path): confirmed. Completion conditions 1–6 are future-slice acceptance criteria; “the current CLI provides neither a publish feature nor a publish-success status” (`docs/INTEGRATION.md:76-98`).
- Gap 11 (no recipient routing): confirmed as a contract gap. Proposal allowlist is only `needs-triage` / `possible-duplicate` with no assignee/queue field (`docs/INTEGRATION.md:39-45`). See Corrections for the “one label” wording and the `HANDOFF.md:21-29` citation.
- Non-goal list vs `docs/PROJECT_OVERVIEW.md:64-69`: the enumerated out-of-scope items match (auto-close, unreviewed deployment, automatic code modification, permission bypass, real Jira writes, real-time webhook/queue, operational RAG with feedback indexing). Dual-audience / richer taxonomy / action-routing are indeed not named as prohibitions.

### Corrections

- [wording] Gap 3 states `possible-duplicate` “is emitted on any evidence match with no duplication judgment.” That is true of `fixture_proposal` (`nexus/proposals.py:178-201`) and is the documented workflow *intent* in `docs/TEMPLATES.md` §5, but it is **not** a validator invariant (`nexus/proposals.py:47-48` only checks the allowlist) and the OpenCode path is free to emit either allowlisted label. Correct state: fixture heuristic emits `possible-duplicate` whenever any evidence was retrieved; OpenCode label choice is ungrounded model output constrained only by the allowlist. Evidence: `nexus/proposals.py:13,47-48,199`; `docs/TEMPLATES.md` §5 (“It is not a validator invariant”).
- [wording] Gap 5 calls the ungated RAG top-5 “what becomes a recommendation.” RAG returns evidence documents; nexus recommendations are a later engine/validator step. The missing score floor is real; the layer mix is not. Evidence: `rag/retrieval.py:903,1064-1071` vs `nexus/proposals.py:27-78` and `nexus/service.py:34-48`.
- [overstated] Gap 8’s “cross-project evidence leakage is possible today” is true of the unadopted `rag/` toolkit under `CompanyPrincipalAcl` (system filter only; `IndexDocument` has no `project` — `rag/contracts.py:306-333,365-419`; `guides/RAG_ACL.md:91-101`). It is not true of the adopted nexus CLI, which still applies the synthetic `document.project == event.project` prefilter (`nexus/retrieval.py:63`). Correct state: project-level ACL is a `rag/` contract hole; the current scaffold’s lexical path does not leak across projects.
- [wording] Gap 11’s “every output dead-ends in one undifferentiated triage label” overstates the taxonomy: there are two labels, and they can co-occur (see gap 24). Correct state: no routing/assignee/queue field; output is a two-label, audience-agnostic triage hint. Evidence: `nexus/proposals.py:13`; `docs/INTEGRATION.md:39-45`.
- [citation] Gap 11’s `HANDOFF.md:21-29` citation describes format-contract v1 (comment/issue renderers and markers), not routing. The routing claim stands on `docs/INTEGRATION.md:39-45` alone.
- [internal consistency] Suggested next-slice candidate 4 says a **contract-only** routing/ownership registry, “ahead of the real Jira write adapter,” addresses gaps **9, 10, 11, 20**. Gaps 9 and 10 *are* the missing adapter and publish path; a contract-only slice cannot address them. Correct mapping: candidate 4 addresses 11 and 20 (and the routing/escalation open questions), not 9 or 10. This also collides with the Non-goal check’s “contract work can proceed independent of the write-adapter slice.”
- [internal consistency] Suggested next-slice candidate 1 (output audience split) claims to address gaps 4, 16, and 24. An output-contract split does not add component/severity/root-cause to the fail-closed event/corpus schemas (4), does not un-flatten RAG resolution fields (16), and does not define `needs-triage` vs `possible-duplicate` precedence (24). Correct mapping: candidate 1 addresses gap 1 (and the audience-split open question); 4 belongs with candidate 2; 16 is a RAG projection change; 24 is a taxonomy-precedence rule.
- [overstated] Non-goal check sentence “The gaps above are scope omissions the current MVP simply hasn't reached, not prohibitions” is too broad. Dual-audience / taxonomy / routing are omissions, as stated. Gaps 9, 10, and 33 sit on the explicit non-goal **real Jira writes** / **real-time webhook/queue**; gaps 18 and 21 sit on **operational RAG with feedback indexing** (`docs/PROJECT_OVERVIEW.md:64-69`). Those five are deferred by current scope, not merely unreached.

### Missing gaps

- Nexus cannot consume the RAG toolkit as recommendation evidence. `NexusService.process` calls `nexus.retrieval.retrieve` only (`nexus/service.py:34`); `nexus/` has no `rag` import. `rag/` imports `nexus.models.normalize_text` only. `docs/ARCHITECTURE.md:24-31` already records that `rag/` does not change the nexus runtime, but none of the 35 ranked items names this wiring gap. Auto-recommendation/auto-labeling work on the engine contract will still be fed by the lexical fixture retriever until an adoption/wiring slice exists. Evidence: `nexus/service.py:11,34`; `docs/ARCHITECTURE.md:24-31`. Suggested severity: **medium** (documented proposed-not-adopted boundary, but it is the actual evidence path for every recommendation today).
- The OpenCode prompt never instructs audience split, duplication judgment, or when to choose which allowlisted label. `_request_message` sends a generic `recommendations`+`labels` contract whose example labels list is only `["possible-duplicate"]`, with instructions limited to “JSON object / supplied evidence ids / no markdown” (`nexus/opencode.py:110-122`). Schema gaps 1 and 3 cover the fields; they do not cover this instruction surface, which is the only auto-labeling/auto-recommendation policy the LLM sees. Suggested severity: **medium**.

No other auto-recommendation / auto-labeling / dual-audience gap in `nexus/` or `rag/` rose to the level of a new ranked item. Recommendation items still lack a stable per-item ID (needed for feedback correlation); that is already in the open-questions list and does not need a 36th gap.

### Severity recalibration

Lens: this is a pre-production local scaffold; real Jira writes and operational RAG are explicit non-goals.

- **Gap 9 (no Jira adapter) and gap 10 (no publish path) should be Medium.** They are true and documented (`docs/INTEGRATION.md:8-14,76-98`; `docs/PROJECT_OVERVIEW.md:64-69`; `docs/TOOLING_DECISION.md:69-71`), but ranking them High contradicts this document’s own Non-goal check and next-slice sequencing (contract first, adapter later). They are the known next integration slice, not blockers for the content-contract work the analysis is for.
- **Gap 5 (no RAG score floor) should be Medium.** The adopted product is a dry-run human-review proposal; RAG is not adopted. A missing calibrated hold-vs-recommend threshold matters after adoption, not before. Keep the “no decision-level duplicate/label metric” half of gap 6 in view, but demote the ungated top-5 itself.
- **Gap 6 (adoption gate unmet) should be Medium.** ≥100 real queries / ACL leakage = 0 is the documented *adoption criterion* for a proposed-not-adopted toolkit (`docs/RAG_DESIGN.md:430-438`), not a defect of the current scaffold. The absence of a decision-level duplicate/label metric is a real auto-labeling hole and can stay as a Medium item of its own; it is not High while RAG is unwired.
- **Gap 26 (dual-audience absent from stated scope) should be High.** The open-questions section already says this decision “gates nearly every other gap above,” yet it is ranked Medium while its consequences (1, 4, 11) are High. That inversion will mislead prioritization: the first action is a product decision, not a schema patch.
- **Gap 27 (incoming event labels parsed then unused) should be Medium, not Low, under an auto-labeling lens.** Labels are accepted at the strict event boundary (`nexus/models.py:102-115`) and then ignored by retrieval (`nexus/retrieval.py:57`) and by the output taxonomy (`nexus/proposals.py:13`). That discards the only producer-supplied classification signal the v1 contract already carries.
- **No other High→Low or Low→High moves.** Gaps 1, 3, 4, 7, and 11 stay High *if* dual-audience / auto-labeling is in MVP scope after the gap-26 decision. Gap 8 stays High as an ACL-shaped hole in `rag/`, with the “not the adopted CLI” caveat in Corrections. Gap 13 (demo fixture engine) can stay Medium because `demo_only` is explicit.

### Overall verdict

The synthesis is accurate enough to drive a coordinator prioritization decision once the corrections above are applied: the dual-audience / two-label / fail-closed-schema diagnosis is right, the High-severity file:line citations I checked are not stale, and the open questions correctly identify the audience-scope decision as the real gate. It over-ranks the known Jira-adapter and RAG-adoption-gate absences for a pre-production scaffold, mis-maps next-slice candidate 4 onto gaps 9–10, and misses the nexus↛rag wiring plus the empty OpenCode labeling prompt. Do not treat this draft as adopted scope; use it as input to a decision gate that first answers whether a user-ready reply is in MVP at all, then pick a contract slice (audience split and/or taxonomy dimensions) before any write adapter.
