# Production Knowledge Retrieval Platform — proposed design (issue #1)

Status: **proposed design, not an adoption decision.** This document applies
the research recorded in [GitHub issue #1](https://github.com/hjung3113/jira-voc-nexus/issues/1)
as the repo's design reference for the production retrieval layer. Nothing in
it changes the currently adopted runtime: the deterministic stdlib/SQLite
scaffold described in [ARCHITECTURE.md](ARCHITECTURE.md) and
[TOOLING_DECISION.md](TOOLING_DECISION.md) stays in place until the evaluation
gate below passes. Tool adoption happens only through an evaluation slice and
operational constraints, not by this document alone.

## Goal

Design the production retrieval layer as a **customizable, high-performance
Knowledge Retrieval Platform**, not as a Jira-only vector RAG.

The platform must support Jira VOC recommendation while also resolving
questions across tightly coupled internal systems such as applications, UI/menu
flows, schedulers/jobs, DB tables/SPs, logs/specs, source code, and domain
knowledge.

## Proposed architecture

```text
                    Query / Jira VOC
                          |
                          v
                  Haystack Pipeline
                          |
                Query / Entity Analyzer
                          |
        +-----------------+------------------+
        |                 |                  |
        v                 v                  v
   BM25 / Nori       Vector Search      Relation Expansion
    OpenSearch          BGE-M3          Knowledge Registry
        |                 |               PostgreSQL
        +-----------------+------------------+
                          |
                          v
                    Candidate Fusion
                         RRF
                          |
                          v
                 BGE-Reranker-v2-m3
                          |
                          v
                 Context Reconstruction
                          |
                          v
                     Internal LLM
```

### Proposed stack

| Component | Role |
| --- | --- |
| Haystack | Retrieval/index/evaluation orchestration and custom pipeline components |
| OpenSearch | BM25 + Nori + vector + metadata filtering + hybrid retrieval/RRF |
| BGE-M3 | Multilingual semantic embedding baseline |
| BGE-Reranker-v2-m3 | Final relevance reranking |
| PostgreSQL Knowledge Registry | Exact entity/relation model for system dependencies |
| Confluence/internal Wiki | Canonical domain/system knowledge source |
| FastAPI | Retrieval service boundary when a production API is introduced |
| Internal LLM | Grounded recommendation/explanation generation only after evidence selection |

## Knowledge source roles

Do not collapse all knowledge into vector documents.

| Source | Role |
| --- | --- |
| Domain/System Wiki | Canonical definition: what a term/system/component means and how it is supposed to work |
| Code / DB schema / Config | Actual implementation evidence |
| Knowledge Registry | Exact relationships between programs/UI/API/jobs/SP/tables/components |
| Jira historical issues | What actually failed in the past |
| Jira resolution evidence | Root cause, action taken, verification/outcome |

Authority is question-dependent. Default trust ordering:

1. Canonical Wiki / Spec for definitions and intended behavior
2. Code / DB schema / Config for actual implementation
3. Resolved Jira + verified outcome for historical remediation
4. Jira investigation/comments for supporting evidence only

## Canonical Jira normalization contract (NormalizedIssue)

Do **not** index each Jira issue as one long document and do **not** treat
every comment as an independent generic chunk. Normalize each issue into a
canonical representation:

```text
NormalizedIssue
├─ Metadata
├─ Problem
├─ Investigation
└─ Resolution
   ├─ RootCause
   ├─ Action
   └─ Verification
```

```json
{
  "issue_key": "ABC-123",
  "metadata": {
    "project": "ABC",
    "issue_type": "Bug",
    "component": "Parser",
    "status": "Resolved",
    "resolution": "Fixed",
    "labels": ["parser", "reconnect"],
    "affected_version": "3.2.1",
    "fix_version": "3.2.2",
    "error_codes": ["4107"],
    "exceptions": ["NullReferenceException"],
    "system": "LogWarehouse",
    "equipment": "TYPE_A"
  },
  "problem": {
    "summary": "...",
    "symptom": "...",
    "environment": "...",
    "error": "..."
  },
  "investigation": ["..."],
  "resolution": {
    "root_cause": "...",
    "action": "...",
    "verification": "..."
  }
}
```

### Comment handling

Comments are classified/filtered, not blindly chunked. Candidate classes:

- irrelevant/coordination
- investigation
- cause-candidate
- resolution/action
- verification/outcome

Comments such as "확인하겠습니다", "로그 전달했습니다" must normally not become
retrieval evidence.

## Jira retrieval rule

Primary retrieval must be **Problem → historical Problem → Issue →
Resolution**, not "new problem → search all resolutions/comments directly".

```text
New Jira Problem
      |
      v
Historical Problem Retrieval
      |
      v
Top Issue IDs
      |
      v
Fetch RootCause / Action / Verification
      |
      v
Grounded recommendation context
```

Initial retrieval baseline:

```text
BM25/Nori Top 50
      +
BGE-M3 Top 50
      |
      v
     RRF
      |
   Top 30
      |
      v
BGE Reranker
      |
    Top 5
```

Potential ranking signals after baseline measurement:

- exact error code: strong boost
- same component/module: boost
- same version family: boost
- resolved + verified outcome: boost
- same project: small boost, **not a hard filter by default**

Project-only filtering can hide valid cross-project failures/remediations.
Production authorization/ACL filtering is a separate mandatory pre-retrieval
boundary — it never replaces relevance ranking, and relevance ranking never
replaces it.

## Domain/System Wiki design

Use the Wiki as a **canonical source**, not as a separate isolated
chatbot/RAG.

```text
Domain
├─ business terms
├─ Context / Carryover / Lot / Wafer definitions
├─ standard log specification
└─ business rules

Systems
├─ system overview
├─ architecture
├─ data flow
├─ components
└─ interfaces

Data
├─ Raw Data definitions
├─ tables/contracts
└─ generation/validation rules
```

Wiki page metadata contract (machine-readable front matter):

```yaml
page_type: domain
system: LogWarehouse
component: Parser
status: canonical
owner: DataPlatform
related_entities:
  - component:parser
  - table:rawdata
```

Wiki remains the source of truth; OpenSearch stores only the retrieval
representation.

## Knowledge Registry (entity/relation contract)

System dependencies must not rely on embeddings alone. Start with PostgreSQL;
do not introduce a graph DB immediately.

```text
knowledge_entity
- id
- type            (component | ui | api | service | job | stored_procedure | table | ...)
- name
- system
- description

knowledge_relation
- source_id       -> knowledge_entity.id
- relation_type   (CALLS | EXECUTES | READS | WRITES | USES | ...)
- target_id       -> knowledge_entity.id
```

Example relations:

```text
RawData UI      CALLS    -> RawData API
RawData API     CALLS    -> RawDataService
RawDataService  EXECUTES -> SP_GET_RAW
SP_GET_RAW      READS    -> RAW_DATA
ParserJob       EXECUTES -> SP_INSERT_RAW
SP_INSERT_RAW   WRITES   -> RAW_DATA
```

Haystack provides a custom relationship-expansion component that expands query
entities before OpenSearch retrieval. Consider Neo4j/GraphRAG later only if
measured use cases frequently require complex multi-hop traversal that
PostgreSQL relation queries cannot serve cleanly.

## OpenSearch logical document types and metadata

Prefer explicit document/source types instead of mixing everything without
metadata.

```text
domain_knowledge
system_knowledge
code_knowledge
db_knowledge
jira_problem
jira_resolution
```

Every indexed document carries at least:

```text
source_type
document_type
project
system
component
entity_ids
trust_level
source_id
updated_at
labels
```

**Stale-list fix (2026-09-12)**: `project` (added for [GitHub issue
#7](https://github.com/hjung3113/jira-voc-nexus/issues/7), the same-project
retrieval boost's actual comparison field) and `labels` (added for [GitHub
issue #6](https://github.com/hjung3113/jira-voc-nexus/issues/6) — see
`docs/ARCHITECTURE.md`'s "Evidence-to-label linkage" section) were missing
from this list even though `project` has been a real `IndexDocument` field
since #7 landed. `doc_id`/`title`/`text` stay implicit
(every document needs an id and content) and are not re-listed here.

## Context construction

The final LLM context is reconstructed across sources:

```text
Canonical Domain
- Context definition

System
- Parser responsibility

Relationship Evidence
- ParserJob -> sp_InsertRaw -> RawData

Historical Jira ABC-123
- Problem
- Root Cause
- Action
- Verification

Historical Jira ABC-456
- ...
```

The LLM explains/recommends from selected evidence only. It does not perform
unrestricted retrieval and never owns Jira write permissions — same boundary as
[ARCHITECTURE.md](ARCHITECTURE.md).

## Performance and customization requirements

The design must keep these concerns independently tunable:

- dense embedding model
- BM25 analyzer/field weighting
- metadata filtering
- relation expansion
- fusion algorithm
- reranker
- context budget
- source trust/priority
- source-specific normalization

Avoid framework decisions that hide these controls behind a fixed agent
abstraction.

## Evaluation gate before adoption

Create a representative internal golden set before declaring the stack
adopted.

Minimum retrieval metrics:

- Recall@5, Recall@10, MRR@10, nDCG@10

Compare at least:

1. BM25 only
2. Dense only
3. BM25 + Dense hybrid
4. Hybrid + reranker
5. Hybrid + reranker + relation expansion

Also measure:

- retrieval latency p50/p95
- indexing throughput
- re-index cost
- Korean + English mixed issue quality
- exact error/code identifier recall
- cross-project false positives
- ACL leakage = 0

Adoption updates [TOOLING_DECISION.md](TOOLING_DECISION.md) only after this
evidence exists.

## Implementation slices

Each slice is independently creatable as a follow-up issue:

1. **Document/Entity contracts** — canonical Jira normalization, Wiki metadata
   contract, entity/relation schema
2. **Offline golden corpus** — real-but-sanitized historical issue set where
   allowed; expected related issues and remediation evidence
3. **OpenSearch retrieval POC** — Nori BM25, BGE-M3 dense retrieval, RRF
4. **Reranker POC** — BGE-Reranker-v2-m3; measure quality/latency improvement
5. **Relationship expansion** — PostgreSQL entity/relation registry, Haystack
   custom component
6. **Unified context builder** — Wiki + implementation + Jira evidence;
   trust/source rules
7. **Evaluation and adoption decision** — benchmark against the current
   deterministic lexical baseline; update TOOLING_DECISION only after evidence

## Non-goals

- automatic Jira write/comment rollout
- automatic code modification
- Neo4j/GraphRAG adoption from day one
- unrestricted LLM tool access
- treating OpenSearch as the canonical source of domain knowledge
- replacing the current deterministic fixture runtime before the
  POC/evaluation gate passes

## Acceptance criteria mapping

| Issue #1 criterion | Where satisfied |
| --- | --- |
| `RAG_DESIGN.md` defines source roles and proposed architecture | This document (sections above) |
| Canonical `NormalizedIssue` contract documented | Canonical Jira normalization contract |
| Problem → Issue → Resolution retrieval rule documented | Jira retrieval rule |
| Wiki canonical metadata contract defined | Domain/System Wiki design |
| Knowledge entity/relation contract defined | Knowledge Registry |
| OpenSearch document metadata/index strategy defined | OpenSearch logical document types |
| Haystack component boundaries defined | Proposed architecture + Performance/customization |
| Golden-set evaluation plan and metrics defined | Evaluation gate |
| Proposed stack clearly separated from adopted runtime | Status header + TOOLING_DECISION.md |
| Follow-up implementation issues creatable independently | Implementation slices |

## Implementation status

A local proof-of-concept toolkit implementing slices 1, 3-6, and 7's
harness now exists under `rag/` (contracts, ACL, SQLite registry, retrieval
pipeline, context builder, evaluation harness, `python3 -m rag` CLI) with
deployment/ingestion/registry/ACL/evaluation guides under `guides/` (see
[the guides index entry](INDEX.md)). The default path uses only local
stand-in components -- BM25 (`LexicalIndex`), a deterministic hashing
embedding (`HashingEmbedding`), a lexical-overlap reranker
(`LexicalOverlapReranker`), and `SqliteKnowledgeRegistry` -- so it runs with
no network and no optional dependencies. The optional adapters
(`OpenSearchBackend`, `BgeRerankerAdapter`, `PostgresKnowledgeRegistry`) are
real, lazy-imported code reviewed against their documented contracts but not
yet exercised against a live OpenSearch/HF/PostgreSQL deployment in this
environment. None of this changes the adopted runtime described above or in
[TOOLING_DECISION.md](TOOLING_DECISION.md): adoption still requires the
evaluation-gate evidence (golden set >= 100 queries, the metric comparisons,
ACL leakage = 0) described above, gathered per
[guides/RAG_EVALUATION.md](../guides/RAG_EVALUATION.md).

The local harness also enforces its own evaluation and context boundaries:
`run_evaluation` rejects empty or duplicate golden IDs, empty sets, duplicate
variant names/cutoffs, unknown or document-type-excluded relevance IDs, and
duplicate/unknown returned IDs; it calls the retrieval seam with at least
`max(10, *cutoffs)` so the fixed MRR@10 and nDCG@10 metrics are true top-10
measurements. `ContextBuilder` keeps canonical evidence ahead of supporting
knowledge, links resolutions to selected problem issue keys, deduplicates
repeated hits, and treats the omission notice as part of the hard character
budget. The file-based CLI stages state atomically with authoritative JSON and
an optional disposable registry sidecar, then rebuilds and closes only its
owned temporary SQLite registry. These are POC-local correctness decisions,
not production adoption or proof of real ACL/provider behavior.
