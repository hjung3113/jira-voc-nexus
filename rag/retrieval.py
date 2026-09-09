"""Local stand-ins for the hybrid retrieval pipeline (BM25 + vector + RRF +
rerank + relation expansion + boosts), all deterministic and stdlib-only.

``LexicalIndex``/``HashingEmbedding`` are local substitutes for
OpenSearch/BGE-M3 so the pipeline shape and scoring contract can be
developed and tested without a network dependency. ``OpenSearchBackend`` and
``BgeRerankerAdapter`` are the real adapters; both lazy-import their
dependency and are integration-unverified in this environment.

ACL is a pre-retrieval boundary: :meth:`RetrievalPipeline.retrieve` computes
the ACL-visible (and document-type-allowed) doc id set from the full corpus
once, up front, and passes it into both searches as ``allowed_doc_ids`` so
hidden documents never consume a ``top_k`` slot, never receive a boost, and
never reach the reranker.
"""

from __future__ import annotations

import copy
import hashlib
import math
import re
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

try:
    from typing import Protocol
except ImportError:  # pragma: no cover
    Protocol = object  # type: ignore[assignment,misc]

from nexus.models import normalize_text

from .acl import AllowAllAcl, PreRetrievalAcl, apply_acl
from .contracts import IndexDocument, TRUST_LEVELS, parse_index_document
from .errors import RagInputError
from .registry import KnowledgeRegistry, RegistryExpansion

_CJK_RANGES = (
    (0x4E00, 0x9FFF),   # CJK Unified Ideographs
    (0x3040, 0x309F),   # Hiragana
    (0x30A0, 0x30FF),   # Katakana
    (0xAC00, 0xD7A3),   # Hangul syllables
)


def _is_cjk(ch: str) -> bool:
    cp = ord(ch)
    return any(lo <= cp <= hi for lo, hi in _CJK_RANGES)


def tokenize(text: str) -> List[str]:
    """Deterministic tokenization: unicode word tokens (len>=2), lowercased,
    plus per-character bigrams for CJK runs.

    Normalization reuses :func:`nexus.models.normalize_text` (NFKC +
    whitespace collapse) so retrieval scoring and contract parsing share one
    normalization convention.

    A single leftover CJK character (a run of length 1) is kept as a
    unigram rather than dropped: without it, a one-character CJK query term
    would tokenize to nothing and could never match, even though CJK
    "words" are often exactly one character.
    """

    normalized = normalize_text(text).lower()
    tokens: List[str] = []
    word_buf: List[str] = []
    cjk_buf: List[str] = []

    def flush_word() -> None:
        if len(word_buf) >= 2:
            tokens.append("".join(word_buf))
        word_buf.clear()

    def flush_cjk() -> None:
        if len(cjk_buf) == 1:
            tokens.append(cjk_buf[0])
        elif len(cjk_buf) > 1:
            for i in range(len(cjk_buf) - 1):
                tokens.append(cjk_buf[i] + cjk_buf[i + 1])
        cjk_buf.clear()

    for ch in normalized:
        if _is_cjk(ch):
            flush_word()
            cjk_buf.append(ch)
        elif ch.isalnum():
            flush_cjk()
            word_buf.append(ch)
        else:
            flush_word()
            flush_cjk()
    flush_word()
    flush_cjk()
    return tokens


@dataclass(frozen=True)
class ScoredDoc:
    doc_id: str
    score: float
    doc: IndexDocument
    reasons: Tuple[str, ...] = ()


# --------------------------------------------------------------------------
# Lexical (BM25) index
# --------------------------------------------------------------------------

_BM25_K1 = 1.2
_BM25_B = 0.75


class LexicalIndex:
    """Local BM25 stand-in over title (weighted x2) + text.

    Two deliberate simplifications relative to textbook Okapi BM25:

    - IDF uses the Lucene/Elasticsearch ``BM25Similarity`` "+1" guard,
      ``log((N-df+0.5)/(df+0.5) + 1)``, which stays positive for every
      ``df``. Textbook Robertson IDF, ``log((N-df+0.5)/(df+0.5))``, goes
      negative once a term appears in more than half the corpus; the +1
      guard is the standard fix used by real search engines and is kept
      here intentionally rather than "corrected".
    - Query terms are deduplicated (``sorted(set(tokenize(query)))``), so
      query-term frequency does not scale the score. This is a common,
      intentional simplification, not a bug.
    """

    def __init__(self, documents: Sequence[IndexDocument]) -> None:
        self._documents = list(documents)
        self._doc_tokens: List[List[str]] = []
        self._term_freq: List[Dict[str, int]] = []
        self._doc_len: List[int] = []
        self._df: Dict[str, int] = {}

        for doc in self._documents:
            title_tokens = tokenize(doc.title)
            text_tokens = tokenize(doc.text)
            combined = title_tokens + title_tokens + text_tokens
            self._doc_tokens.append(combined)
            self._doc_len.append(len(combined))
            tf: Dict[str, int] = {}
            for token in combined:
                tf[token] = tf.get(token, 0) + 1
            self._term_freq.append(tf)
            for token in tf:
                self._df[token] = self._df.get(token, 0) + 1

        self._n = len(self._documents)
        self._avgdl = (sum(self._doc_len) / self._n) if self._n else 0.0

    @property
    def documents(self) -> Tuple[IndexDocument, ...]:
        return tuple(self._documents)

    def _idf(self, term: str) -> float:
        df = self._df.get(term, 0)
        return math.log(((self._n - df + 0.5) / (df + 0.5)) + 1.0)

    def search(
        self, query: str, top_k: int, allowed_doc_ids: Optional[Set[str]] = None
    ) -> List[ScoredDoc]:
        query_terms = sorted(set(tokenize(query)))
        if not query_terms or self._n == 0:
            return []
        scored: List[Tuple[float, str, int]] = []
        for idx, doc in enumerate(self._documents):
            if allowed_doc_ids is not None and doc.doc_id not in allowed_doc_ids:
                continue
            tf_map = self._term_freq[idx]
            dl = self._doc_len[idx]
            score = 0.0
            for term in query_terms:
                tf = tf_map.get(term, 0)
                if tf == 0:
                    continue
                idf = self._idf(term)
                denom = tf + _BM25_K1 * (1 - _BM25_B + _BM25_B * (dl / self._avgdl if self._avgdl else 0.0))
                score += idf * (tf * (_BM25_K1 + 1)) / denom
            if score > 0:
                scored.append((score, doc.doc_id, idx))
        scored.sort(key=lambda item: (-item[0], item[1]))
        top = scored[: max(0, top_k)]
        return [
            ScoredDoc(doc_id=doc_id, score=score, doc=self._documents[idx], reasons=("bm25",))
            for score, doc_id, idx in top
        ]


# --------------------------------------------------------------------------
# Vector (hashing embedding) index
# --------------------------------------------------------------------------


class EmbeddingFunction(Protocol):
    def embed(self, texts: Sequence[str]) -> List[List[float]]: ...


class HashingEmbedding:
    """Deterministic feature-hashing embedding: local stand-in for BGE-M3.

    Unigrams and adjacent-token bigrams from :func:`tokenize` are hashed
    into a fixed-size vector (sign + bucket derived from SHA-256), then
    L2-normalized.
    """

    DIM = 256

    def embed(self, texts: Sequence[str]) -> List[List[float]]:
        return [self._embed_one(text) for text in texts]

    def _embed_one(self, text: str) -> List[float]:
        vector = [0.0] * self.DIM
        tokens = tokenize(text)
        features = list(tokens)
        features.extend(tokens[i] + "\x1f" + tokens[i + 1] for i in range(len(tokens) - 1))
        for feature in features:
            digest = hashlib.sha256(feature.encode("utf-8")).digest()
            index = int.from_bytes(digest[:4], "big") % self.DIM
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            vector[index] += sign
        norm = math.sqrt(sum(v * v for v in vector))
        if norm > 0:
            vector = [v / norm for v in vector]
        return vector


def _cosine(a: Sequence[float], b: Sequence[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


class VectorIndex:
    def __init__(self, documents: Sequence[IndexDocument], embedder: EmbeddingFunction) -> None:
        self._documents = list(documents)
        self._embedder = embedder
        texts = [f"{doc.title} {doc.text}" for doc in self._documents]
        self._vectors = embedder.embed(texts) if texts else []

    @property
    def documents(self) -> Tuple[IndexDocument, ...]:
        return tuple(self._documents)

    def search(
        self, query: str, top_k: int, allowed_doc_ids: Optional[Set[str]] = None
    ) -> List[ScoredDoc]:
        if not self._documents:
            return []
        query_vector = self._embedder.embed([query])[0]
        scored = []
        for idx, doc in enumerate(self._documents):
            if allowed_doc_ids is not None and doc.doc_id not in allowed_doc_ids:
                continue
            score = _cosine(query_vector, self._vectors[idx])
            scored.append((score, doc.doc_id, idx))
        scored.sort(key=lambda item: (-item[0], item[1]))
        top = scored[: max(0, top_k)]
        return [
            ScoredDoc(doc_id=doc_id, score=score, doc=self._documents[idx], reasons=("vector",))
            for score, doc_id, idx in top
        ]


# --------------------------------------------------------------------------
# Reciprocal Rank Fusion
# --------------------------------------------------------------------------


def rrf_fuse(result_lists: Sequence[Sequence[ScoredDoc]], k: int = 60, top_n: int = 30) -> List[ScoredDoc]:
    scores: Dict[str, float] = {}
    docs: Dict[str, IndexDocument] = {}
    reasons: Dict[str, List[str]] = {}

    for result_list in result_lists:
        for rank, scored in enumerate(result_list, start=1):
            scores[scored.doc_id] = scores.get(scored.doc_id, 0.0) + 1.0 / (k + rank)
            docs[scored.doc_id] = scored.doc
            existing = reasons.setdefault(scored.doc_id, [])
            for reason in scored.reasons:
                if reason not in existing:
                    existing.append(reason)

    ordered = sorted(scores.items(), key=lambda item: (-item[1], item[0]))
    top = ordered[: max(0, top_n)]
    return [
        ScoredDoc(doc_id=doc_id, score=score, doc=docs[doc_id], reasons=tuple(reasons[doc_id]))
        for doc_id, score in top
    ]


# --------------------------------------------------------------------------
# Reranking
# --------------------------------------------------------------------------


class Reranker(Protocol):
    def rerank(self, query: str, docs: Sequence[ScoredDoc], top_k: int) -> List[ScoredDoc]: ...


_TRUST_RANK = {level: idx for idx, level in enumerate(TRUST_LEVELS)}


class LexicalOverlapReranker:
    """Local rerank stand-in: query/doc token overlap, trust-level tiebreak."""

    def rerank(self, query: str, docs: Sequence[ScoredDoc], top_k: int) -> List[ScoredDoc]:
        query_tokens = set(tokenize(query))
        scored = []
        for scored_doc in docs:
            doc_tokens = set(tokenize(scored_doc.doc.title)) | set(tokenize(scored_doc.doc.text))
            overlap = len(query_tokens & doc_tokens)
            trust_rank = _TRUST_RANK.get(scored_doc.doc.trust_level, len(TRUST_LEVELS))
            reasons = scored_doc.reasons + ("rerank:lexical-overlap",)
            scored.append((overlap, -trust_rank, scored_doc.doc_id, ScoredDoc(
                doc_id=scored_doc.doc_id, score=float(overlap), doc=scored_doc.doc, reasons=reasons,
            )))
        scored.sort(key=lambda item: (-item[0], -item[1], item[2]))
        top = scored[: max(0, top_k)]
        return [item[3] for item in top]


class BgeRerankerAdapter:
    """Real BGE-Reranker-v2-m3 adapter (HF transformers). Integration-unverified here."""

    def __init__(self, model_name: str = "BAAI/bge-reranker-v2-m3") -> None:
        self._model_name = model_name
        self._model = None
        self._tokenizer = None

    def _load(self) -> None:
        if self._model is not None:
            return
        try:
            import torch  # type: ignore
            from transformers import AutoModelForSequenceClassification, AutoTokenizer  # type: ignore
        except ImportError as exc:  # pragma: no cover - exercised only without the extra
            raise RagInputError(
                "torch/transformers are required for BgeRerankerAdapter; "
                "install them with: pip install 'jira-voc-nexus[rag-reranker]'"
            ) from exc
        self._torch = torch
        self._tokenizer = AutoTokenizer.from_pretrained(self._model_name)
        self._model = AutoModelForSequenceClassification.from_pretrained(self._model_name)
        self._model.eval()

    def rerank(self, query: str, docs: Sequence[ScoredDoc], top_k: int) -> List[ScoredDoc]:
        self._load()
        pairs = [[query, f"{d.doc.title} {d.doc.text}"] for d in docs]
        with self._torch.no_grad():
            inputs = self._tokenizer(pairs, padding=True, truncation=True, return_tensors="pt")
            logits = self._model(**inputs).logits.view(-1).float()
        scored = list(zip(logits.tolist(), docs))
        scored.sort(key=lambda item: (-item[0], item[1].doc_id))
        top = scored[: max(0, top_k)]
        return [
            ScoredDoc(doc_id=d.doc_id, score=float(s), doc=d.doc, reasons=d.reasons + ("rerank:bge",))
            for s, d in top
        ]


# --------------------------------------------------------------------------
# OpenSearch backend (real adapter, integration-unverified here)
# --------------------------------------------------------------------------

INDEX_SETTINGS = {
    "settings": {
        "index": {"knn": True},
        "analysis": {
            "analyzer": {
                "nori_analyzer": {"type": "custom", "tokenizer": "nori_tokenizer", "filter": ["nori_readingform", "lowercase"]}
            }
        },
    },
    "mappings": {
        "properties": {
            "doc_id": {"type": "keyword"},
            "source_type": {"type": "keyword"},
            "document_type": {"type": "keyword"},
            "system": {"type": "keyword"},
            "component": {"type": "keyword"},
            "entity_ids": {"type": "keyword"},
            "trust_level": {"type": "keyword"},
            "source_id": {"type": "keyword"},
            "updated_at": {"type": "date"},
            "title": {"type": "text", "analyzer": "nori_analyzer"},
            "text": {"type": "text", "analyzer": "nori_analyzer"},
            "embedding": {"type": "knn_vector", "dimension": HashingEmbedding.DIM},
        }
    },
}

_OPENSEARCH_ACL_OVERSAMPLE_FACTOR = 5


def _build_index_settings(embedding_dimension: int) -> Dict[str, Any]:
    """A deep copy of :data:`INDEX_SETTINGS` with ``embedding.dimension`` set
    to ``embedding_dimension`` -- never mix vectors from two different
    embedders (e.g. the local ``HashingEmbedding`` and a company BGE-M3
    endpoint) inside one OpenSearch index; their dimensions and semantics
    differ, so an index must be built for exactly one embedder."""

    settings = copy.deepcopy(INDEX_SETTINGS)
    settings["mappings"]["properties"]["embedding"]["dimension"] = embedding_dimension
    return settings


class OpenSearchBackend:
    """Real hybrid (BM25/Nori + knn) OpenSearch adapter. Integration-unverified here.

    ACL note: unlike :class:`LexicalIndex`/:class:`VectorIndex`, this
    backend cannot filter the candidate set *inside* OpenSearch's own
    scoring without per-principal filtered aliases or document-level
    security configured on the cluster. When ``allowed_doc_ids`` is passed
    to :meth:`search`, this adapter fetches an oversized page
    (``top_k * _OPENSEARCH_ACL_OVERSAMPLE_FACTOR``) and post-filters down to
    the allowed set, then truncates to ``top_k``. That still lets enough
    hidden documents occupy result slots to under-fill ``top_k`` in the
    worst case. Production deployments serving multiple principals should
    configure OpenSearch-side filtered aliases / document-level security
    scoped to the caller's ACL instead of relying on this workaround.

    ``documents`` is the local corpus mirror :class:`RetrievalPipeline`
    reads at construction time (``self.documents = self._lexical.documents``)
    to compute the ACL-visible id set before any search -- pass the same
    document set you indexed into OpenSearch so pre-scoring ACL filtering
    works the same way it does for the local indexes.
    """

    def __init__(
        self,
        hosts: Sequence[str],
        index_name: str,
        embedder: EmbeddingFunction,
        documents: Sequence[IndexDocument] = (),
        embedding_dimension: Optional[int] = None,
    ) -> None:
        self._hosts = list(hosts)
        self._index_name = index_name
        self._embedder = embedder
        self._client = None
        self._documents = tuple(documents)
        self._embedding_dimension = embedding_dimension if embedding_dimension is not None else HashingEmbedding.DIM

    @property
    def documents(self) -> Tuple[IndexDocument, ...]:
        return self._documents

    def _connect(self):
        if self._client is not None:
            return self._client
        try:
            from opensearchpy import OpenSearch  # type: ignore
        except ImportError as exc:  # pragma: no cover - exercised only without the extra
            raise RagInputError(
                "opensearch-py is required for OpenSearchBackend; "
                "install it with: pip install 'jira-voc-nexus[rag-platform]'"
            ) from exc
        self._client = OpenSearch(hosts=self._hosts)
        return self._client

    def ensure_index(self) -> None:
        client = self._connect()
        if not client.indices.exists(index=self._index_name):
            client.indices.create(index=self._index_name, body=_build_index_settings(self._embedding_dimension))

    def search(
        self, query: str, top_k: int, allowed_doc_ids: Optional[Set[str]] = None
    ) -> List[ScoredDoc]:
        client = self._connect()
        vector = self._embedder.embed([query])[0]
        fetch_size = top_k * _OPENSEARCH_ACL_OVERSAMPLE_FACTOR if allowed_doc_ids is not None else top_k
        body = {
            "size": max(0, fetch_size),
            "query": {
                "bool": {
                    "should": [
                        {"multi_match": {"query": query, "fields": ["title^2", "text"]}},
                        {"knn": {"embedding": {"vector": vector, "k": max(0, fetch_size)}}},
                    ]
                }
            },
        }
        response = client.search(index=self._index_name, body=body)
        results: List[ScoredDoc] = []
        for hit in response.get("hits", {}).get("hits", []):
            source = hit["_source"]
            payload = {
                "doc_id": source.get("doc_id", ""),
                "source_type": source.get("source_type", ""),
                "document_type": source.get("document_type", ""),
                "system": source.get("system", ""),
                "component": source.get("component", ""),
                "entity_ids": list(source.get("entity_ids", [])),
                "trust_level": source.get("trust_level", ""),
                "source_id": source.get("source_id", ""),
                "updated_at": source.get("updated_at", ""),
                "title": source.get("title", ""),
                "text": source.get("text", ""),
            }
            doc = parse_index_document(payload)
            if allowed_doc_ids is not None and doc.doc_id not in allowed_doc_ids:
                continue
            results.append(ScoredDoc(doc_id=doc.doc_id, score=float(hit["_score"]), doc=doc, reasons=("opensearch",)))
            if len(results) >= top_k:
                break
        return results


# --------------------------------------------------------------------------
# Pipeline
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class BoostConfig:
    error_code: float = 3.0
    component: float = 1.5
    version_family: float = 1.0
    verified_outcome: float = 1.0
    same_project: float = 0.5


@dataclass(frozen=True)
class RetrievalQuery:
    text: str
    project: str = ""
    component: str = ""
    error_codes: Tuple[str, ...] = ()
    entities: Tuple[str, ...] = ()
    document_types: Tuple[str, ...] = ("jira_problem",)


@dataclass(frozen=True)
class RetrievalResult:
    """``fused`` is the pre-boost, ACL-visible RRF output (``rrf_fuse``'s
    return value, truncated to ``fuse_top_n``); it does not reflect boosts.
    ``final`` is the post-boost, post-rerank, ACL-rechecked output."""

    fused: Tuple[ScoredDoc, ...]
    final: Tuple[ScoredDoc, ...]
    expansion: Optional[RegistryExpansion]
    acl_filtered_count: int


@dataclass(frozen=True)
class RetrievalConfig:
    top_k_lexical: int = 50
    top_k_vector: int = 50
    fuse_top_n: int = 30
    final_top_k: int = 5
    boosts: BoostConfig = field(default_factory=BoostConfig)


_VERSION_FAMILY_RE = re.compile(r"\d+(?:\.\d+)+")


def _version_prefix(value: str) -> str:
    """Extract a version-like token (e.g. ``3.2`` from ``3.2.1``), never a
    bare integer -- a bare number such as an error code must not trigger the
    version-family boost."""

    match = _VERSION_FAMILY_RE.search(value)
    return match.group(0) if match else ""


def _token_boundary_contains(haystack: str, needle: str) -> bool:
    """True iff ``needle`` appears in ``haystack`` delimited by non-alphanumeric
    boundaries (or start/end of string) -- so error code "41" does not match
    inside "4107"."""

    if not needle:
        return False
    pattern = re.compile(r"(?<![0-9A-Za-z])" + re.escape(needle) + r"(?![0-9A-Za-z])", re.IGNORECASE)
    return bool(pattern.search(haystack))


class RetrievalPipeline:
    def __init__(
        self,
        lexical: LexicalIndex,
        vector: VectorIndex,
        reranker: Reranker,
        registry: Optional[KnowledgeRegistry] = None,
        acl: PreRetrievalAcl = AllowAllAcl(),
        config: RetrievalConfig = RetrievalConfig(),
    ) -> None:
        self._lexical = lexical
        self._vector = vector
        self._reranker = reranker
        self._registry = registry
        self._acl = acl
        self._config = config
        # The corpus ACL is applied to; lexical and vector indexes must be
        # built over the same document set (the lexical index is treated as
        # the source of truth for that set).
        self.documents: Tuple[IndexDocument, ...] = self._lexical.documents

    def _apply_boosts(self, query: RetrievalQuery, scored_docs: Sequence[ScoredDoc]) -> List[ScoredDoc]:
        boosts = self._config.boosts
        version_prefix = _version_prefix(query.text)
        result = []
        for scored in scored_docs:
            score = scored.score
            reasons = list(scored.reasons)
            doc = scored.doc
            if query.error_codes and any(
                code and _token_boundary_contains(doc.text, code) for code in query.error_codes
            ):
                score += boosts.error_code
                reasons.append("boost:error-code")
            if query.component and query.component == doc.component:
                score += boosts.component
                reasons.append("boost:component")
            if version_prefix and version_prefix in doc.text:
                score += boosts.version_family
                reasons.append("boost:version-family")
            if doc.trust_level == "verified-resolution":
                score += boosts.verified_outcome
                reasons.append("boost:verified-outcome")
            if query.project and doc.system == query.project:
                score += boosts.same_project
                reasons.append("boost:same-project")
            result.append(ScoredDoc(doc_id=scored.doc_id, score=score, doc=doc, reasons=tuple(reasons)))
        return result

    def retrieve(self, query: RetrievalQuery) -> RetrievalResult:
        expansion = None
        if self._registry is not None and query.entities:
            expansion = self._registry.expand(query.entities)

        visible_docs, filtered_count = apply_acl(self.documents, self._acl)
        if query.document_types:
            allowed_types = set(query.document_types)
            allowed_doc_ids = {doc.doc_id for doc in visible_docs if doc.document_type in allowed_types}
        else:
            allowed_doc_ids = {doc.doc_id for doc in visible_docs}

        lexical_results = self._lexical.search(query.text, self._config.top_k_lexical, allowed_doc_ids=allowed_doc_ids)
        vector_results = self._vector.search(query.text, self._config.top_k_vector, allowed_doc_ids=allowed_doc_ids)

        fused = rrf_fuse([lexical_results, vector_results], top_n=self._config.fuse_top_n)
        boosted = self._apply_boosts(query, fused)
        boosted.sort(key=lambda item: (-item.score, item.doc_id))

        reranked = self._reranker.rerank(query.text, boosted, self._config.final_top_k)
        final_docs, _ = apply_acl([sd.doc for sd in reranked], self._acl)
        final_ids = {doc.doc_id for doc in final_docs}
        final = tuple(sd for sd in reranked if sd.doc_id in final_ids)

        return RetrievalResult(
            fused=tuple(fused),
            final=final,
            expansion=expansion,
            acl_filtered_count=filtered_count,
        )


def fetch_resolution_context(
    issue_keys: Iterable[str],
    resolution_corpus: Sequence[IndexDocument],
    acl: PreRetrievalAcl,
) -> List[IndexDocument]:
    by_key = {doc.source_id: doc for doc in resolution_corpus if doc.document_type == "jira_resolution"}
    candidates = [by_key[key] for key in issue_keys if key in by_key]
    visible, _ = apply_acl(candidates, acl)
    return visible
