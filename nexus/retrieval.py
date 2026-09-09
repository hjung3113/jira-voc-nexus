"""Deterministic lexical retrieval behind the synthetic fixture filter."""

from __future__ import annotations

import re
import unicodedata
from typing import Iterable, List, Set

from .models import Document, Event


MAX_EVIDENCE = 5
_TOKEN_RE = re.compile(r"[^\W_]+", re.UNICODE)
_STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "for",
    "from",
    "in",
    "is",
    "it",
    "of",
    "on",
    "or",
    "that",
    "the",
    "to",
    "was",
    "with",
}


def lexical_tokens(value: str) -> Set[str]:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return {
        token
        for token in _TOKEN_RE.findall(normalized)
        if len(token) > 1 and token not in _STOPWORDS
    }


def retrieve(event: Event, documents: Iterable[Document], limit: int = MAX_EVIDENCE) -> List[Document]:
    """Apply the synthetic fixture project filter before lexical scoring.

    This comparison is not a production authorization check: an integration
    adapter must obtain and enforce the trusted Jira principal/ACL before
    calling retrieval.
    """

    bounded_limit = max(0, min(limit, MAX_EVIDENCE))
    query_tokens = lexical_tokens(event.summary + " " + event.description)
    ranked = []

    # This synthetic-fixture comparison is intentionally before
    # tokenization/scoring: documents from other projects must not influence
    # retrieval or model context.
    allowed_documents = [document for document in documents if document.project == event.project]
    for document in allowed_documents:
        title_tokens = lexical_tokens(document.title)
        text_tokens = lexical_tokens(document.text)
        title_hits = query_tokens & title_tokens
        text_hits = query_tokens & text_tokens
        if not title_hits and not text_hits:
            continue
        score = len(title_hits) * 3 + len(text_hits) + int(document.resolved)
        ranked.append(
            (
                -score,
                -len(title_hits),
                -len(text_hits),
                -int(document.resolved),
                document.id,
                document,
            )
        )

    ranked.sort(key=lambda item: item[:-1])
    return [item[-1] for item in ranked[:bounded_limit]]
