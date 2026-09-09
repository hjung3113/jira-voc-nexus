"""RAG core: contracts, ACL, knowledge registry, retrieval, context building,
and the evaluation harness.

Importable with the stdlib alone. ``opensearch`` and ``psycopg`` adapters
lazy-import their dependency and only fail when actually used.
"""

from .context import BuiltContext, ContextBuilder, ContextConfig, ContextSection
from .errors import RagInputError
from .eval import (
    GoldenEntry,
    PipelineVariant,
    default_local_variants,
    load_golden_set,
    mrr_at_k,
    ndcg_at_k,
    recall_at_k,
    render_markdown_table,
    run_evaluation,
)

__all__ = [
    "RagInputError",
    "ContextBuilder",
    "ContextConfig",
    "ContextSection",
    "BuiltContext",
    "GoldenEntry",
    "PipelineVariant",
    "load_golden_set",
    "recall_at_k",
    "mrr_at_k",
    "ndcg_at_k",
    "run_evaluation",
    "render_markdown_table",
    "default_local_variants",
]
