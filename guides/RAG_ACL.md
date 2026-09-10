# RAG ACL guide

## What this covers

The pre-retrieval ACL boundary contract, how to implement
`PreRetrievalAcl` for your company's principal/SSO system, a
poison-document test recipe you can run against any pipeline wiring to
prove enforcement, and the "ACL leakage = 0" evaluation method required
before adoption. Self-contained: restates the contract rather than
assuming `rag/acl.py`/`rag/retrieval.py` are open. See
[docs/RAG_DESIGN.md](../docs/RAG_DESIGN.md#jira-retrieval-rule) ("Production
authorization/ACL filtering is a separate mandatory pre-retrieval boundary
-- it never replaces relevance ranking, and relevance ranking never
replaces it") and [docs/ARCHITECTURE.md](../docs/ARCHITECTURE.md)
("Permission filtering is applied **before** search/LLM calls ... The
client-supplied `project` field is never a basis for authorization").

## Prerequisites

- Your company's trusted principal source (SSO session, service-to-service
  auth claim, or equivalent) -- something the *server*, not the client
  request, establishes.
- A per-document authorization predicate your company can evaluate given a
  principal and a document's metadata (project, system, component, or a
  dedicated ACL field you attach to `IndexDocument`/its source record).

## The pre-retrieval boundary contract

```python
class PreRetrievalAcl(Protocol):
    def visible_document(self, doc: IndexDocument) -> bool: ...

def apply_acl(documents: Sequence[IndexDocument], acl: PreRetrievalAcl) -> Tuple[List[IndexDocument], int]:
    ...  # (visible_documents, filtered_count)
```

Non-negotiable rules, already enforced by `rag.retrieval.RetrievalPipeline`
and re-stated here because a deployment must not accidentally bypass them
when wiring a custom pipeline or a real backend:

1. **ACL runs before scoring, on the full candidate corpus.**
   `RetrievalPipeline.retrieve` computes the ACL-visible (and
   document-type-allowed) doc id set once, from `self.documents` (the
   full corpus), before calling `LexicalIndex.search`/`VectorIndex.search`.
   A hidden document must never consume a `top_k` slot, never receive a
   relevance boost, and never reach the reranker. If you write a custom
   pipeline (e.g. wiring `OpenSearchBackend` directly), reproduce this
   ordering -- do not filter results *after* they come back from search.
2. **ACL is re-applied to anything fetched by id afterwards.**
   `rag.retrieval.fetch_resolution_context` re-checks ACL on the
   resolution documents it fetches by issue key, and
   `RetrievalPipeline.retrieve` re-checks ACL on the final reranked docs.
   Any new code path that looks up a document by id (not via the scored
   search path) must call `apply_acl` on the result before returning it.
3. **The client-supplied `project` field is never an authorization basis.**
   `RetrievalQuery.project` only ever feeds the `same_project` *relevance
   boost* (`+0.5` by default) in `RetrievalPipeline._apply_boosts` -- it is
   soft ranking signal, not a filter, and a client can set it to anything.
   Authorization comes only from the trusted principal your server
   resolves and passes into the `PreRetrievalAcl` implementation.
4. **`acl_filtered_count` is corpus-level.** `RetrievalResult.acl_filtered_count`
   counts documents the ACL denied out of the *full* corpus for this
   query, not just ones that happened to survive fusion/reranking far
   enough to be checked again. Use it as your leakage-monitoring signal
   (see "ACL leakage = 0" below) -- a value of 0 on a query you know should
   have hidden documents is itself a signal something is misconfigured.

## Implementing `PreRetrievalAcl` for company principal/SSO

```python
from dataclasses import dataclass
from typing import FrozenSet
from rag.acl import PreRetrievalAcl
from rag.contracts import IndexDocument

@dataclass(frozen=True)
class Principal:
    user_id: str
    allowed_projects: FrozenSet[str]     # resolved server-side from SSO/IAM group membership
    allowed_systems: FrozenSet[str]

class CompanyPrincipalAcl:
    """PreRetrievalAcl for one resolved, trusted principal."""

    def __init__(self, principal: Principal) -> None:
        self._principal = principal

    def visible_document(self, doc: IndexDocument) -> bool:
        # doc.system is populated for both Jira- and wiki-derived documents
        # (see rag.contracts.issue_to_documents / wiki_to_document).
        if doc.system and doc.system not in self._principal.allowed_systems:
            return False
        # issue_to_documents copies NormalizedIssue.project into
        # IndexDocument.project. WikiPage has no project concept, so wiki
        # documents leave this field empty and are not project-filtered here.
        if doc.project and doc.project not in self._principal.allowed_projects:
            return False
        return True
```

Build one `CompanyPrincipalAcl` (or equivalent) per request, from the
principal your server already trusts (the session/service auth, resolved
*before* this code runs) -- never from anything in the request body a
client could set. Pass it as `RetrievalPipeline(..., acl=your_acl)`.

`AllowAllAcl` (in `rag.acl`) is the development/local default -- it must
never be the ACL used to serve a real multi-principal deployment.

## Poison-document test recipe

Run this against *any* pipeline wiring (local components or real
adapters) before trusting its ACL enforcement. It proves both
"invisible" and "acl_filtered_count > 0", and it proves the ACL holds even
when the poison document would otherwise win on relevance:

```python
from rag.acl import PreRetrievalAcl
from rag.contracts import IndexDocument
from rag.retrieval import RetrievalConfig, RetrievalPipeline, RetrievalQuery

class DenyByComponentAcl(PreRetrievalAcl):
    def __init__(self, denied_component: str) -> None:
        self._denied_component = denied_component

    def visible_document(self, doc: IndexDocument) -> bool:
        return doc.component != self._denied_component

def make_poison_doc(doc_id: str, denied_component: str, exact_error_code: str) -> IndexDocument:
    # BM25-dominant text that also carries the exact boosted error code, so
    # neither lexical/vector ranking nor the error-code boost can promote
    # it around the ACL.
    text = f"error code {exact_error_code} " * 5 + "grant access override"
    return IndexDocument(
        doc_id=doc_id, source_type="jira", document_type="jira_problem",
        project="", system="", component=denied_component, entity_ids=(), trust_level="supporting",
        source_id=doc_id, updated_at="", title=f"error {exact_error_code}", text=text,
    )

# 1. Build your real corpus + poison_doc, your real pipeline (local or wired
#    to real adapters), with acl=DenyByComponentAcl("<the poison doc's component>").
# 2. Use a *small* top_k / final_top_k in RetrievalConfig -- small enough
#    that if the poison doc consumed a slot before ACL filtering, a real
#    visible document would be evicted. This is what proves "before
#    scoring", not just "not in the final list by coincidence of a large
#    top_k".
# 3. result = pipeline.retrieve(RetrievalQuery(text=..., error_codes=[exact_error_code]))
# 4. Assert:
assert poison_doc.doc_id not in [sd.doc_id for sd in result.fused]
assert poison_doc.doc_id not in [sd.doc_id for sd in result.final]
assert result.acl_filtered_count > 0
```

`tests/test_rag_retrieval.py::RetrieveAclEnforcementTests::test_retrieve_denying_acl_hides_poison_everywhere`
in this repository is exactly this recipe against the local pipeline --
reuse its shape (small `top_k_lexical=top_k_vector=fuse_top_n=final_top_k=1`,
a BM25-dominant poison doc carrying the exact boosted error code) when
writing the same test against a real adapter wiring (OpenSearch/PG) after
a swap, per [guides/RAG_DEPLOYMENT.md](RAG_DEPLOYMENT.md)'s smoke
checklist. For `OpenSearchBackend` specifically, also re-read its ACL
caveat in that guide (Swap 2) -- the filter is applied server-side inside
the query (a `terms` filter on the lexical channel, the same filter inside
the k-NN clause on the dense channel) and the response parser fails closed
if a hit falls outside it, but this recipe is still the only way to prove
your *wiring* actually threads `allowed_doc_ids` from your `PreRetrievalAcl`
into that query -- the library-level mechanism existing is not the same as
your deployment code calling it correctly.

## The "ACL leakage = 0" evaluation method

This is the specific metric [docs/RAG_DESIGN.md](../docs/RAG_DESIGN.md#evaluation-gate-before-adoption)
lists alongside Recall/MRR/nDCG/latency as required evaluation-gate
evidence before adopting any given pipeline configuration for production.

1. Construct a **leakage golden set**: for a representative sample of
   principals (at minimum, one per distinct access-scope class your
   company has -- e.g. "sees only project X", "sees only system Y", "sees
   everything"), pair each principal with a query and the specific set of
   `doc_id`s that principal must **never** see, drawn from your real
   corpus (not synthetic poison docs -- exercise the real ACL predicate
   against real documents it should deny).
2. For each `(principal, query, forbidden_doc_ids)` triple: build the
   pipeline with that principal's real `PreRetrievalAcl`, call
   `pipeline.retrieve(query)`, and assert
   `forbidden_doc_ids.isdisjoint({sd.doc_id for sd in result.fused} | {sd.doc_id for sd in result.final})`.
3. **Leakage = 0** means: zero forbidden doc ids appeared in `fused` or
   `final`, across every triple in the leakage golden set, for every
   variant under evaluation (see
   [guides/RAG_EVALUATION.md](RAG_EVALUATION.md) for the 5-variant
   comparison this runs alongside). This is a hard pass/fail gate, not a
   metric to average or improve over time -- any leakage blocks adoption
   of that pipeline configuration until fixed, independent of how good its
   Recall/MRR/nDCG numbers are.
4. Record the leakage golden set size, the triples exercised, and the
   pass/fail result alongside the metric table when recording adoption-gate
   evidence (see [guides/RAG_EVALUATION.md](RAG_EVALUATION.md#recording-results)).
5. Re-run this whenever the ACL implementation changes, whenever a new
   access-scope class is introduced, and on some regular cadence
   thereafter (e.g. alongside the golden-set evaluation cadence) -- ACL
   correctness is not a one-time proof. See
   [guides/RAG_OPERATIONS.md](RAG_OPERATIONS.md#monitoring) for how to
   wire this cadence and `acl_filtered_count` into ongoing monitoring, and
   that guide's "Fail-closed operational rules" for what an operator must
   never do to route around an ACL failure during an incident.

## Verification checklist

- [ ] `PreRetrievalAcl.visible_document` is built from a server-resolved
      trusted principal, never from a client-supplied field in the query.
- [ ] The poison-document recipe above passes against every pipeline
      wiring you deploy (local and each real adapter swap).
- [ ] `result.acl_filtered_count` is nonzero on at least one test query
      per deployment (proves the ACL is actually wired in, not silently
      defaulted to `AllowAllAcl`).
- [ ] The leakage golden set covers every distinct access-scope class in
      your company's principal model, not just one.
- [ ] Leakage = 0 recorded before adoption, and the leakage golden set is
      re-run after any ACL or ingestion-mapping change.

## Failure modes

| Symptom | Likely cause | Fix |
| --- | --- | --- |
| Poison doc appears in `result.fused` or `result.final` | ACL wired after scoring instead of before, or `acl=AllowAllAcl()` left as the default in a real deployment | Re-read the pre-retrieval boundary contract above; confirm the `acl=` argument passed to `RetrievalPipeline` |
| `acl_filtered_count == 0` on a query that should have hidden documents | ACL predicate always returns `True` (misconfigured principal, or an ACL bug), or the corpus genuinely has nothing to hide for this query | Check with a poison-document test first -- if that also shows leakage, the ACL predicate itself is broken |
| `OpenSearchBackend`-backed pipeline raises `RagInputError: ... response violated the document ACL` | The OpenSearch server ignored or mis-applied the `terms`/k-NN `filter` clause built from `allowed_doc_ids` | This is the adapter failing closed as designed -- investigate the OpenSearch-side filter/mapping, do not catch and suppress this error (see [guides/RAG_DEPLOYMENT.md](RAG_DEPLOYMENT.md) Swap 2) |
| `OpenSearchBackend`-backed pipeline raises `RagInputError: allowed_doc_ids is too large` | This principal's ACL-visible corpus exceeds the 10,000-id cap (`_OPENSEARCH_MAX_ALLOWED_DOC_IDS`) | Narrow the access-scope class, or move to OpenSearch-side filtered aliases/document-level security (see [guides/RAG_DEPLOYMENT.md](RAG_DEPLOYMENT.md) Swap 2) |
| Leakage golden set passes but a real user reports seeing something they shouldn't | Leakage golden set does not cover that user's access-scope class | Add the missing class to the leakage golden set; this is a golden-set coverage gap, not necessarily an ACL bug |
