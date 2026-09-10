"""Golden-set evaluation harness for the retrieval pipeline.

Implements the metrics and baseline comparison from RAG_DESIGN.md's
"Evaluation gate before adoption" section: Recall@k, MRR@10, nDCG@10, and
p50/p95 latency, compared across five local-only pipeline variants
(bm25-only, vector-only, hybrid, hybrid+rerank, hybrid+rerank+expansion).
This harness measures the local stand-in components; it does not itself
constitute the adoption decision (see guides/RAG_EVALUATION.md).
"""

from __future__ import annotations

import json
import math
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from .contracts import IndexDocument
from .errors import RagInputError
from .registry import SqliteKnowledgeRegistry
from .retrieval import (
    HashingEmbedding,
    LexicalIndex,
    LexicalOverlapReranker,
    RetrievalPipeline,
    RetrievalQuery,
    ScoredDoc,
    VectorIndex,
)

_QUERY_FIELDS = {"text", "project", "component", "error_codes", "entities", "document_types"}
_ENTRY_FIELDS = {"query", "relevant_doc_ids"}


def _require_object(value: Any, field: str) -> Dict[str, Any]:
    if not isinstance(value, dict):
        raise RagInputError(f"{field} must be a JSON object")
    return value


def _require_string(value: Any, field: str, *, allow_empty: bool = True) -> str:
    if not isinstance(value, str):
        raise RagInputError(f"{field} must be a string")
    if not allow_empty and not value.strip():
        raise RagInputError(f"{field} must not be empty")
    return value


def _require_string_list(value: Any, field: str) -> Tuple[str, ...]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise RagInputError(f"{field} must be a list of strings")
    return tuple(value)


def _parse_query(payload: Any, field: str) -> RetrievalQuery:
    data = _require_object(payload, field)
    if set(data) != _QUERY_FIELDS:
        raise RagInputError(f"{field} has missing or unknown fields")
    return RetrievalQuery(
        text=_require_string(data["text"], f"{field}.text", allow_empty=False),
        project=_require_string(data["project"], f"{field}.project"),
        component=_require_string(data["component"], f"{field}.component"),
        error_codes=_require_string_list(data["error_codes"], f"{field}.error_codes"),
        entities=_require_string_list(data["entities"], f"{field}.entities"),
        document_types=_require_string_list(data["document_types"], f"{field}.document_types"),
    )


@dataclass(frozen=True)
class GoldenEntry:
    query: RetrievalQuery
    relevant_doc_ids: Tuple[str, ...]


def load_golden_set(path: str) -> List[GoldenEntry]:
    """Strict JSON loader: a list of ``{"query": {...}, "relevant_doc_ids": [...]}``
    entries. ``query`` must carry exactly the six ``RetrievalQuery`` fields
    (empty string/list for unused ones); ``relevant_doc_ids`` must be a
    non-empty list of strings referencing real index doc ids."""

    with open(path, encoding="utf-8") as stream:
        payload = json.load(stream)
    if not isinstance(payload, list) or not payload:
        raise RagInputError("golden set must be a non-empty JSON list")
    entries: List[GoldenEntry] = []
    for index, item in enumerate(payload):
        field = f"golden_set[{index}]"
        data = _require_object(item, field)
        if set(data) != _ENTRY_FIELDS:
            raise RagInputError(f"{field} has missing or unknown fields")
        query = _parse_query(data["query"], f"{field}.query")
        relevant = _require_string_list(data["relevant_doc_ids"], f"{field}.relevant_doc_ids")
        _validate_relevant_ids(relevant, field)
        entries.append(GoldenEntry(query=query, relevant_doc_ids=relevant))
    return entries


def _validate_relevant_ids(relevant: Sequence[str], field: str) -> None:
    if (not relevant or any(not isinstance(item, str) or not item.strip() for item in relevant)
            or len(set(relevant)) != len(relevant)):
        raise RagInputError(f"{field}.relevant_doc_ids must contain unique non-blank IDs")


# --------------------------------------------------------------------------
# Metrics
# --------------------------------------------------------------------------


def recall_at_k(results: Sequence[str], relevant: Sequence[str], k: int) -> float:
    """``|top-k results ∩ relevant| / |relevant|``. 0.0 if ``relevant`` is empty."""

    relevant_set = set(relevant)
    if not relevant_set:
        return 0.0
    hits = len(set(results[:k]) & relevant_set)
    return hits / len(relevant_set)


def mrr_at_k(results: Sequence[str], relevant: Sequence[str], k: int = 10) -> float:
    """``1 / rank`` of the first relevant doc within the top ``k``; 0.0 if none."""

    relevant_set = set(relevant)
    for rank, doc_id in enumerate(results[:k], start=1):
        if doc_id in relevant_set:
            return 1.0 / rank
    return 0.0


def ndcg_at_k(results: Sequence[str], relevant: Sequence[str], k: int = 10) -> float:
    """Binary-gain nDCG: ``DCG = sum(1/log2(rank+1))`` over relevant hits in the
    top ``k``, ``IDCG`` is the same sum for the ideal ordering (all relevant
    docs, up to ``min(|relevant|, k)``, ranked first). 0.0 if ``IDCG`` is 0."""

    relevant_set = set(relevant)
    dcg = 0.0
    seen = set()
    for rank, doc_id in enumerate(results[:k], start=1):
        if doc_id in relevant_set and doc_id not in seen:
            dcg += 1.0 / math.log2(rank + 1)
        seen.add(doc_id)
    ideal_hits = min(len(relevant_set), k)
    idcg = sum(1.0 / math.log2(rank + 1) for rank in range(1, ideal_hits + 1))
    if idcg == 0.0:
        return 0.0
    return dcg / idcg


def _percentile(sorted_values: Sequence[float], pct: float) -> float:
    if not sorted_values:
        return 0.0
    index = max(0, min(len(sorted_values) - 1, int(round(pct * (len(sorted_values) - 1)))))
    return sorted_values[index]


# --------------------------------------------------------------------------
# Variant comparison
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class PipelineVariant:
    name: str
    build: Callable[[], RetrievalPipeline]
    # A variant may own disposable resources (for example, the SQLite
    # registry opened by the expansion variant).  Keep cleanup explicit so
    # run_evaluation never guesses at ownership and accidentally closes
    # indexes or registries borrowed by a caller.
    cleanup: Optional[Callable[[Any], None]] = None


def run_evaluation(
    variants: Sequence[PipelineVariant], golden: Sequence[GoldenEntry], ks: Tuple[int, ...] = (5, 10)
) -> Dict[str, Any]:
    """Run every variant over the full golden set once; report per-variant
    ``recall@k`` for each ``k`` in ``ks``, plus ``mrr@10``/``ndcg@10`` (always
    at k=10, independent of ``ks``), plus p50/p95 latency in milliseconds
    over ``time.perf_counter()`` timings of each ``pipeline.retrieve()`` call
    (percentile = sorted_latencies[round(pct * (n-1))])."""

    if not golden or not variants:
        raise RagInputError("evaluation requires non-empty golden entries and variants")
    if not ks or any(type(k) is not int or k <= 0 for k in ks) or len(set(ks)) != len(ks):
        raise RagInputError("evaluation cutoffs must be unique positive integers")
    names = [variant.name for variant in variants]
    if any(not isinstance(name, str) or not name.strip() for name in names) or len(set(names)) != len(names):
        raise RagInputError("evaluation variant names must be unique and non-blank")
    depth = max(10, *ks)
    report: Dict[str, Any] = {}
    for variant in variants:
        pipeline = variant.build()
        try:
            corpus = {doc.doc_id: doc for doc in pipeline.documents}
            if len(corpus) != len(pipeline.documents):
                raise RagInputError("evaluation corpus contains duplicate document IDs")
            for entry in golden:
                _validate_relevant_ids(entry.relevant_doc_ids, "golden entry")
                if not isinstance(entry.query.text, str) or not entry.query.text.strip():
                    raise RagInputError("golden query text must not be blank")
                for doc_id in entry.relevant_doc_ids:
                    if doc_id not in corpus:
                        raise RagInputError("golden relevance ID is absent from the evaluation corpus")
                    if entry.query.document_types and corpus[doc_id].document_type not in entry.query.document_types:
                        raise RagInputError("golden relevance ID is excluded by query document_types")
            n = len(golden)
            recall_sums = {k: 0.0 for k in ks}
            mrr_sum = 0.0
            ndcg_sum = 0.0
            latencies_ms: List[float] = []

            for entry in golden:
                start = time.perf_counter()
                result = pipeline.retrieve(entry.query, top_k=depth)
                latencies_ms.append((time.perf_counter() - start) * 1000.0)
                ranked_ids = [sd.doc_id for sd in result.final]
                if len(set(ranked_ids)) != len(ranked_ids):
                    raise RagInputError("evaluation pipeline returned duplicate document IDs")
                if any(doc_id not in corpus for doc_id in ranked_ids):
                    raise RagInputError("evaluation pipeline returned an unknown document ID")
                for k in ks:
                    recall_sums[k] += recall_at_k(ranked_ids, entry.relevant_doc_ids, k)
                mrr_sum += mrr_at_k(ranked_ids, entry.relevant_doc_ids, k=10)
                ndcg_sum += ndcg_at_k(ranked_ids, entry.relevant_doc_ids, k=10)

            sorted_latencies = sorted(latencies_ms)
            metrics: Dict[str, float] = {}
            for k in ks:
                metrics[f"recall@{k}"] = recall_sums[k] / n if n else 0.0
            metrics["mrr@10"] = mrr_sum / n if n else 0.0
            metrics["ndcg@10"] = ndcg_sum / n if n else 0.0
            metrics["latency_ms_p50"] = _percentile(sorted_latencies, 0.5)
            metrics["latency_ms_p95"] = _percentile(sorted_latencies, 0.95)
            report[variant.name] = metrics
        finally:
            if variant.cleanup is not None:
                variant.cleanup(pipeline)

    return report


def _column_sort_key(column: str) -> Tuple[int, int]:
    if column.startswith("recall@"):
        return (0, int(column.split("@", 1)[1]))
    if column.startswith("mrr@"):
        return (1, int(column.split("@", 1)[1]))
    if column.startswith("ndcg@"):
        return (2, int(column.split("@", 1)[1]))
    if column == "latency_ms_p50":
        return (3, 0)
    if column == "latency_ms_p95":
        return (3, 1)
    return (4, 0)


def render_markdown_table(report: Dict[str, Any]) -> str:
    if not report:
        return ""
    variant_names = list(report.keys())
    columns: List[str] = []
    seen = set()
    for name in variant_names:
        for key in report[name]:
            if key not in seen:
                seen.add(key)
                columns.append(key)
    columns.sort(key=_column_sort_key)

    header = "| variant | " + " | ".join(columns) + " |"
    separator = "| --- | " + " | ".join("---" for _ in columns) + " |"
    rows = [header, separator]
    for name in variant_names:
        cells = []
        for column in columns:
            value = report[name].get(column)
            if value is None:
                cells.append("")
            elif column.startswith("latency"):
                cells.append(f"{value:.2f}")
            else:
                cells.append(f"{value:.3f}")
        rows.append("| " + name + " | " + " | ".join(cells) + " |")
    return "\n".join(rows)


# --------------------------------------------------------------------------
# Local-only baseline variants
# --------------------------------------------------------------------------


class _NullSearchIndex:
    """Search stand-in that always returns no results but still reports the
    real document corpus, so disabling one retrieval channel (for the
    bm25-only / vector-only variants) does not shrink the ACL/document-type
    candidate set the other channel searches over."""

    def __init__(self, documents: Sequence[IndexDocument]) -> None:
        self._documents = tuple(documents)

    @property
    def documents(self) -> Tuple[IndexDocument, ...]:
        return self._documents

    def search(self, query: str, top_k: int, allowed_doc_ids: Optional[Any] = None) -> List[ScoredDoc]:
        return []


class _PassthroughReranker:
    """No-op reranker: preserves the fused/boosted order and scores as-is,
    for variants that do not include a rerank stage."""

    def rerank(self, query: str, docs: Sequence[ScoredDoc], top_k: int) -> List[ScoredDoc]:
        return list(docs[: max(0, top_k)])


def default_local_variants(documents: Sequence[IndexDocument], registry_path: str) -> List[PipelineVariant]:
    """Build the 5 RAG_DESIGN evaluation-gate variants from local-only
    components: :class:`LexicalIndex` (BM25), :class:`HashingEmbedding` +
    :class:`VectorIndex`, :class:`LexicalOverlapReranker`, and
    :class:`SqliteKnowledgeRegistry`.

    ``registry_path`` must be an existing, already-populated SQLite registry
    database (e.g. built by ``python3 -m rag index``) for the
    ``hybrid+rerank+expansion`` variant to use relation expansion; pass an
    empty string to run that variant without a registry (identical to
    ``hybrid+rerank`` in that case).
    """

    documents = list(documents)
    lexical_index = LexicalIndex(documents)
    vector_index = VectorIndex(documents, HashingEmbedding())
    null_index = _NullSearchIndex(documents)
    reranker = LexicalOverlapReranker()
    passthrough = _PassthroughReranker()

    def build_registry() -> Optional[SqliteKnowledgeRegistry]:
        return SqliteKnowledgeRegistry(registry_path) if registry_path else None

    def close_owned_registry(pipeline: Any) -> None:
        # Only the expansion variant opts into this callback.  Its registry
        # is created by build_registry; the shared lexical/vector indexes
        # remain borrowed and are intentionally never closed here.
        registry = getattr(pipeline, "_registry", None)
        close = getattr(registry, "close", None)
        if callable(close):
            close()

    return [
        PipelineVariant(
            "bm25-only",
            lambda: RetrievalPipeline(lexical=lexical_index, vector=null_index, reranker=passthrough),
        ),
        PipelineVariant(
            "vector-only",
            lambda: RetrievalPipeline(lexical=null_index, vector=vector_index, reranker=passthrough),
        ),
        PipelineVariant(
            "hybrid",
            lambda: RetrievalPipeline(lexical=lexical_index, vector=vector_index, reranker=passthrough),
        ),
        PipelineVariant(
            "hybrid+rerank",
            lambda: RetrievalPipeline(lexical=lexical_index, vector=vector_index, reranker=reranker),
        ),
        PipelineVariant(
            "hybrid+rerank+expansion",
            lambda: RetrievalPipeline(
                lexical=lexical_index, vector=vector_index, reranker=reranker, registry=build_registry()
            ),
            cleanup=close_owned_registry,
        ),
    ]
