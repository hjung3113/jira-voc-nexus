"""Pre-retrieval ACL boundary.

ACL filtering happens before any scoring, on the full candidate corpus, and
is re-applied to any document fetched by id afterwards (e.g. resolution
context lookups). The client-supplied ``project`` field is never itself an
authorization basis; a real adapter must supply the trusted principal/ACL.
"""

from __future__ import annotations

from typing import List, Sequence, Tuple

try:
    from typing import Protocol
except ImportError:  # pragma: no cover - py<3.8 fallback, unused at py3.9+
    Protocol = object  # type: ignore[assignment,misc]

from .contracts import IndexDocument


class PreRetrievalAcl(Protocol):
    def visible_document(self, doc: IndexDocument) -> bool: ...


class AllowAllAcl:
    """Development/testing default: every document is visible."""

    def visible_document(self, doc: IndexDocument) -> bool:
        return True


def apply_acl(documents: Sequence[IndexDocument], acl: PreRetrievalAcl) -> Tuple[List[IndexDocument], int]:
    visible: List[IndexDocument] = []
    filtered = 0
    for doc in documents:
        if acl.visible_document(doc):
            visible.append(doc)
        else:
            filtered += 1
    return visible, filtered
