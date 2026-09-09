"""Exception hierarchy for the RAG core (contracts, registry, retrieval)."""


class RagInputError(Exception):
    """Strict input validation failure for a RAG contract payload."""
