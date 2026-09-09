# RAG deployment guide

## What this covers

How to install, run, and verify the local `rag/` toolkit on fixtures, and
how to swap each local stand-in component for a real company-hosted
adapter (OpenSearch, a company BGE-M3 embedding endpoint, the BGE
reranker, PostgreSQL) without changing the retrieval contract. Read this
before touching any adapter wiring in a deployment environment. This guide
is self-contained: it restates the contracts it uses rather than assuming
you have read the code first, but for full design rationale also see
[docs/RAG_DESIGN.md](../docs/RAG_DESIGN.md) (architecture, trust ordering,
evaluation gate) and [docs/ARCHITECTURE.md](../docs/ARCHITECTURE.md)
(execution boundary this toolkit must not cross).

## Prerequisites

- Python >= 3.9, this repository checked out.
- No network access is required for local-mode use (index/query/eval on
  fixtures). Network access and the relevant extra are required only when
  you wire in a real adapter, per component below.
- You are not required to have OpenSearch, PostgreSQL, or a BGE-M3 endpoint
  running to complete the "Local-first run" section.

## Package layout

```
rag/
  errors.py       RagInputError -- the one exception type this package raises
  contracts.py    NormalizedIssue, WikiPage, KnowledgeEntity/Relation, IndexDocument,
                  strict parsers, issue_to_documents(), wiki_to_document()
  acl.py          PreRetrievalAcl protocol, AllowAllAcl, apply_acl()
  registry.py     KnowledgeRegistry protocol, SqliteKnowledgeRegistry (local default)
  registry_pg.py  PostgresKnowledgeRegistry (real adapter, lazy psycopg import)
  retrieval.py    tokenize(), LexicalIndex (BM25), HashingEmbedding, VectorIndex,
                  rrf_fuse(), LexicalOverlapReranker, BgeRerankerAdapter,
                  OpenSearchBackend, RetrievalPipeline, fetch_resolution_context()
  context.py      ContextBuilder -- assembles the final LLM context text
  eval.py         golden-set metrics, run_evaluation(), default_local_variants()
  __main__.py     `python3 -m rag` CLI (index / query / eval; local-only, no network flags)
fixtures/rag/      normalized_issues.json, wiki_pages.json, registry.json, golden_set.json
guides/            this directory
```

Everything above imports with the Python stdlib alone. `opensearch-py`,
`psycopg`, `torch`/`transformers` are imported lazily, only inside the real
adapter classes/functions that need them, and only when you actually call
into that adapter.

## Install

```sh
pip install -e ".[rag-platform,rag-pg,rag-reranker]"
```

Install only the extras you need for the adapters you are wiring in:

| Extra | Package | Needed for |
| --- | --- | --- |
| `rag-platform` | `opensearch-py>=2.4` | `rag.retrieval.OpenSearchBackend` |
| `rag-pg` | `psycopg[binary]>=3.1` | `rag.registry_pg.PostgresKnowledgeRegistry` |
| `rag-reranker` | `torch>=2.2`, `transformers>=4.44` | `rag.retrieval.BgeRerankerAdapter` |

Local-mode (fixtures/CLI below) needs none of them.

## Local-first run (verify before touching any adapter)

Always get this working first -- it is the fallback described in
"Rollback" below, and it is what CI / a first-time reader should run to
confirm the toolkit itself is sound before any company infrastructure is
involved.

```sh
python3 -m rag index --fixtures-dir fixtures/rag --state .local/rag/state.json
```

Expected output (document count may differ if fixtures change):

```
indexed 21 documents -> .local/rag/state.json
registry -> .local/rag/state.registry.db
```

```sh
python3 -m rag query --state .local/rag/state.json --text "4107 오류" --error-code 4107
```

Expected: a context beginning with any matching `Canonical Domain`/`System`
sections, followed by a `Historical Jira OPS-201` section containing both a
`Problem:` line (mentioning `4107`) and a `Resolution:` line.

```sh
python3 -m rag eval --fixtures-dir fixtures/rag --golden fixtures/rag/golden_set.json
```

Expected: a 5-row Markdown table (`bm25-only`, `vector-only`, `hybrid`,
`hybrid+rerank`, `hybrid+rerank+expansion`) with `recall@5`, `recall@10`,
`mrr@10`, `ndcg@10`, `latency_ms_p50`, `latency_ms_p95` columns. On the
committed `fixtures/rag/golden_set.json`, `hybrid+rerank` scores
`recall@5 >= 0.5` (verified figures: see
[guides/RAG_EVALUATION.md](RAG_EVALUATION.md)).

If any of the three commands above fails or the state file is missing, stop
-- do not proceed to adapter wiring on top of a broken local baseline.

## Secrets policy

Every adapter below is configured through **environment variable names**
given here. This guide, the code, `fixtures/`, and any `.local/rag/state.json`
file **never** contain a secret value -- only the name of the environment
variable the deployment environment must set. `.local/` is excluded from
log collection per [AGENTS.md](../AGENTS.md) but must still never hold a
raw credential; if a value must be cached locally for a session, put it
outside the repository entirely (e.g. your shell's exported environment,
not a file under this checkout).

## Swap 1: `HashingEmbedding` -> company BGE-M3 HTTP endpoint

`rag.retrieval.EmbeddingFunction` is the whole contract:

```python
class EmbeddingFunction(Protocol):
    def embed(self, texts: Sequence[str]) -> List[List[float]]: ...
```

`HashingEmbedding` (the local stand-in) returns 256-dim L2-normalized
vectors. A real BGE-M3 endpoint returns 1024-dim vectors; `VectorIndex`
and `rrf_fuse` do not care about dimension, but you must not mix vectors
from two different embedders inside one `VectorIndex` (rebuild the whole
index after swapping).

**`HttpEmbeddingFunction` contract** (implement this class in your
deployment code, not in `rag/` -- it is a real adapter with a real network
call and belongs next to your other company-specific adapters):

- **Request**: `POST {NEXUS_RAG_EMBED_URL}` with JSON body
  `{"texts": ["<text 1>", "<text 2>", ...]}` and header
  `Authorization: Bearer <value of NEXUS_RAG_EMBED_API_KEY>`.
- **Response**: `200 OK` with JSON body
  `{"embeddings": [[<float>, ...], [<float>, ...], ...]}`, one vector per
  input text, in the same order. Any other status or a body that fails to
  parse must raise, not return a zero vector -- silently degrading to
  "no signal" only masks failures downstream.
- **Timeout**: read from `NEXUS_RAG_EMBED_TIMEOUT_S` (seconds, float);
  treat a timeout as a raised error, not an empty result.
- **Dimension check**: after receiving a response, assert
  `len(vector) == EXPECTED_DIM` for every vector (`EXPECTED_DIM` is a
  constant you set to match the deployed model, e.g. `1024` for BGE-M3) and
  raise `RagInputError` (from `rag.errors`) if it does not match -- a
  silent dimension mismatch corrupts every cosine score in `VectorIndex`.

```python
import os
import urllib.request
import json
from rag.errors import RagInputError

class HttpEmbeddingFunction:
    def __init__(self, dim: int = 1024):
        self._url = os.environ["NEXUS_RAG_EMBED_URL"]
        self._api_key = os.environ["NEXUS_RAG_EMBED_API_KEY"]
        self._timeout_s = float(os.environ.get("NEXUS_RAG_EMBED_TIMEOUT_S", "10"))
        self._dim = dim

    def embed(self, texts):
        body = json.dumps({"texts": list(texts)}).encode("utf-8")
        request = urllib.request.Request(
            self._url, data=body, method="POST",
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self._api_key}",
            },
        )
        with urllib.request.urlopen(request, timeout=self._timeout_s) as response:
            payload = json.loads(response.read())
        vectors = payload["embeddings"]
        for vector in vectors:
            if len(vector) != self._dim:
                raise RagInputError(f"embedding dimension mismatch: expected {self._dim}, got {len(vector)}")
        return vectors
```

Wire it in: `VectorIndex(documents, HttpEmbeddingFunction())` in place of
`VectorIndex(documents, HashingEmbedding())`.

## Swap 2: `LexicalIndex`/`VectorIndex` -> `OpenSearchBackend`

`rag.retrieval.OpenSearchBackend` is a real adapter already in the repo
(lazy-imports `opensearchpy`). It exposes the same
`search(query, top_k, allowed_doc_ids=None) -> List[ScoredDoc]` shape as
`LexicalIndex`/`VectorIndex`, so `RetrievalPipeline` can take either the
pair of local indexes or a single `OpenSearchBackend` in a custom pipeline
wiring (`RetrievalPipeline` currently expects a `lexical` and `vector`
argument separately; if you route both through one hybrid OpenSearch
query, pass the same `OpenSearchBackend` instance as both `lexical` and
`vector`, and rely on `rrf_fuse` naturally deduplicating identical
`doc_id`s across the two "channels" -- or fork `RetrievalPipeline.retrieve`
in your deployment code if you want a single-call hybrid path instead of
two).

`RetrievalPipeline.__init__` reads `self._lexical.documents` at
construction time to compute the ACL-visible corpus before any search --
so `OpenSearchBackend` must be constructed with the same `documents` you
indexed into OpenSearch, via its `documents=` constructor argument, or
`RetrievalPipeline` will see an empty corpus and every query will return
nothing.

The Nori-analyzer BM25 + knn mapping is the module constant
`rag.retrieval.INDEX_SETTINGS`; its knn vector dimension defaults to
`HashingEmbedding.DIM` (256) and must be set to match whatever embedder
you actually pass in -- `OpenSearchBackend`'s `embedding_dimension=`
constructor argument controls this (`ensure_index` builds the index body
from a copy of `INDEX_SETTINGS` with that dimension substituted in, so the
module constant itself is never mutated):

```python
from rag.retrieval import OpenSearchBackend

backend = OpenSearchBackend(
    hosts=os.environ["NEXUS_RAG_OS_URL"].split(","),
    index_name=os.environ.get("NEXUS_RAG_OS_INDEX", "nexus-rag"),
    embedder=HttpEmbeddingFunction(),  # or HashingEmbedding() to test wiring only
    documents=documents,               # the same IndexDocument corpus you are indexing
    embedding_dimension=1024,          # match HttpEmbeddingFunction's dimension; HashingEmbedding is 256
)
backend.ensure_index()  # creates the index (INDEX_SETTINGS + the dimension above) if missing
```

Never mix vectors from `HashingEmbedding` and a real BGE-M3 endpoint (or
any two different embedders) inside one OpenSearch index -- their
dimensions and semantics differ; rebuild the index under a new
`index_name` after any embedder swap rather than reusing one populated by
a different embedder.

`INDEX_SETTINGS` requires the `nori_tokenizer`/`nori_readingform` plugin
installed on the OpenSearch cluster (the Korean analyzer used throughout
the fixtures and golden set) and knn enabled (`index.knn: true`, already
set in `INDEX_SETTINGS`).

**ACL caveat** (read [guides/RAG_ACL.md](RAG_ACL.md) fully before using
this in a multi-principal deployment): `OpenSearchBackend.search` cannot
filter *inside* OpenSearch's own scoring the way the local indexes do. It
oversamples (`top_k * 5`) and post-filters by `allowed_doc_ids`, which can
still under-fill `top_k` in the worst case. Configure OpenSearch-side
filtered aliases or document-level security scoped to the caller's ACL for
a real multi-principal deployment; do not rely on the oversample-and-filter
workaround alone.

## Swap 3: `LexicalOverlapReranker` -> `BgeRerankerAdapter`

```python
from rag.retrieval import BgeRerankerAdapter

reranker = BgeRerankerAdapter(model_name="BAAI/bge-reranker-v2-m3")
```

`BgeRerankerAdapter._load()` calls `AutoTokenizer.from_pretrained` /
`AutoModelForSequenceClassification.from_pretrained` on first use -- this
downloads from Hugging Face (or reads a local cache set via the standard
`HF_HOME`/`TRANSFORMERS_CACHE` environment variables) the first time it
runs, which is a network call outside this toolkit's default no-network
path. Pin the model to a local cache/mirror for a network-isolated
deployment; set `HF_HUB_OFFLINE=1` once the cache is warm to guarantee no
further network calls.

## Swap 4: `SqliteKnowledgeRegistry` -> `PostgresKnowledgeRegistry`

`rag.registry_pg.PostgresKnowledgeRegistry` implements the same
`KnowledgeRegistry` protocol (`expand`, `neighbors`, `upsert_entity`,
`add_relation`, `dump_payload`) as `SqliteKnowledgeRegistry`. DDL (module
constant `rag.registry_pg.DDL`):

```sql
CREATE TABLE IF NOT EXISTS knowledge_entity (
    id TEXT PRIMARY KEY, type TEXT NOT NULL, name TEXT NOT NULL,
    system TEXT NOT NULL, description TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS knowledge_relation (
    source_id TEXT NOT NULL REFERENCES knowledge_entity(id),
    relation_type TEXT NOT NULL,
    target_id TEXT NOT NULL REFERENCES knowledge_entity(id),
    PRIMARY KEY (source_id, relation_type, target_id)
);
CREATE INDEX IF NOT EXISTS knowledge_relation_type_idx ON knowledge_relation (relation_type);
```

```python
import os
from rag.registry_pg import PostgresKnowledgeRegistry

registry = PostgresKnowledgeRegistry(datasource=os.environ["NEXUS_RAG_PG_DATASOURCE"])
```

`NEXUS_RAG_PG_DATASOURCE` is a standard PostgreSQL connection string (e.g.
`postgresql://user@host:5432/dbname`) -- credentials embedded in it come
from the deployment secret store, never from a file in this repository.
See [guides/RAG_REGISTRY.md](RAG_REGISTRY.md) for the seeding workflow and
sync cadence. `add_relation` rejects an exact-duplicate relation with
`RagInputError` on both backends (a `UNIQUE`/`PRIMARY KEY` violation is
translated, not swallowed).

## Smoke checklist (after any adapter swap)

1. `python3 -m rag eval --fixtures-dir fixtures/rag --golden fixtures/rag/golden_set.json`
   still exits 0 and every variant row still has `acl_filtered_count`-style
   ACL enforcement intact (see [guides/RAG_ACL.md](RAG_ACL.md)'s
   poison-document recipe -- run it against the swapped adapter, not just
   the local one).
2. Confirm no secret value appears in `.local/rag/state.json`, CLI stdout,
   or any log line -- only environment variable *names* should ever appear.
3. Confirm `python3 -m unittest discover -s tests -v` is still green (the
   real adapters are not exercised by these tests without the corresponding
   env var / extra, by design -- see `tests/test_rag_registry_pg.py` for
   the skip-gate pattern to follow for any new adapter test).
4. Re-run the "Local-first run" commands above with the *local* components
   still available (do not delete `HashingEmbedding`/`LexicalIndex`/
   `SqliteKnowledgeRegistry` usage from your deployment code) to confirm
   rollback still works.

## Rollback

Local mode has no external dependency and is always available: construct
`RetrievalPipeline` with `LexicalIndex`, `VectorIndex(documents,
HashingEmbedding())`, and `LexicalOverlapReranker()` (optionally
`SqliteKnowledgeRegistry`), exactly as `rag.__main__` and
`rag.eval.default_local_variants` already do. If any real adapter is
unreachable or misbehaving, fall back to this local wiring rather than
degrading the ACL or evidence contract to keep a broken adapter "working".

## Failure modes

| Symptom | Likely cause | Where to look |
| --- | --- | --- |
| `RagInputError: ... is required for ...; install it with: pip install ...` | Optional extra not installed | Install section above |
| `RagInputError: embedding dimension mismatch` | `HttpEmbeddingFunction` model changed dimension, or wrong endpoint | Swap 1 |
| Search results include documents the caller should not see | ACL applied after scoring, or `OpenSearchBackend` oversample too small | [guides/RAG_ACL.md](RAG_ACL.md), Swap 2 caveat |
| `RagInputError: duplicate relation: ...` | Re-seeding without checking existing rows first | [guides/RAG_REGISTRY.md](RAG_REGISTRY.md) |
| Golden-set `recall@5` regresses after a swap | Real adapter's ranking differs from the local stand-in it was tuned against | [guides/RAG_EVALUATION.md](RAG_EVALUATION.md) |
