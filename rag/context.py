"""Build the final LLM context from selected retrieval evidence.

Mirrors the RAG_DESIGN.md "Context construction" shape: canonical domain
knowledge first, then system/implementation knowledge, then relationship
(registry) evidence, then historical Jira issues (problem, then resolution,
grouped per issue) -- the trust order documented in RAG_DESIGN.md. The LLM
consumes only the returned text; it never retrieves on its own.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

from .contracts import IndexDocument, TRUST_LEVELS
from .errors import RagInputError
from .registry import RegistryExpansion
from .retrieval import RetrievalQuery, RetrievalResult

_DOMAIN_DOCUMENT_TYPES = ("domain_knowledge",)
_SYSTEM_DOCUMENT_TYPES = ("system_knowledge", "code_knowledge", "db_knowledge")


@dataclass(frozen=True)
class ContextSection:
    heading: str
    lines: Tuple[str, ...]
    source: str  # doc_id, or "registry" for relationship-expansion evidence


@dataclass(frozen=True)
class ContextConfig:
    max_chars: int = 8_000

    def __post_init__(self) -> None:
        if type(self.max_chars) is not int or self.max_chars < 0:
            raise RagInputError("max_chars must be a non-negative integer")


@dataclass(frozen=True)
class BuiltContext:
    text: str
    sections: Tuple[ContextSection, ...]
    omitted_sections: Tuple[str, ...]


def _collect_jira_sections(
    final_docs: Sequence[IndexDocument], resolution_docs: Sequence[IndexDocument]
) -> List[ContextSection]:
    order: List[str] = []
    per_issue: Dict[str, Dict[str, IndexDocument]] = {}

    def add(doc: IndexDocument, kind: str) -> None:
        key = doc.source_id
        if key not in per_issue:
            per_issue[key] = {}
            order.append(key)
        per_issue[key].setdefault(kind, doc)

    # Problem docs first, then resolution docs (from the final results and
    # from any resolution corpus the caller fetched separately) -- matches
    # the Problem -> Issue -> Resolution retrieval rule in RAG_DESIGN.md.
    for doc in final_docs:
        if doc.document_type == "jira_problem":
            add(doc, "problem")
    for doc in final_docs:
        if doc.document_type == "jira_resolution" and doc.source_id in per_issue:
            add(doc, "resolution")
    for doc in resolution_docs:
        if doc.document_type == "jira_resolution" and doc.source_id in per_issue:
            add(doc, "resolution")

    sections = []
    for key in order:
        entry = per_issue[key]
        lines: List[str] = []
        problem = entry.get("problem")
        resolution = entry.get("resolution")
        if problem is not None:
            lines.append(f"Problem: {problem.title}")
            lines.append(problem.text)
        if resolution is not None:
            lines.append(f"Resolution: {resolution.title}")
            lines.append(resolution.text)
        source_doc = problem if problem is not None else resolution
        assert source_doc is not None
        sections.append(
            ContextSection(heading=f"Historical Jira {key}", lines=tuple(lines), source=source_doc.doc_id)
        )
    return sections


class ContextBuilder:
    def __init__(self, config: ContextConfig = ContextConfig()) -> None:
        self._config = config

    def build(
        self,
        query: RetrievalQuery,
        result: RetrievalResult,
        resolution_docs: Sequence[IndexDocument] = (),
        registry_expansion: Optional[RegistryExpansion] = None,
    ) -> BuiltContext:
        # Repeated hits must not consume the evidence budget twice.
        final_docs = list({sd.doc_id: sd.doc for sd in result.final}.values())
        final_docs.sort(key=lambda doc: TRUST_LEVELS.index(doc.trust_level))
        sections: List[ContextSection] = []

        for doc in final_docs:
            if doc.document_type in _DOMAIN_DOCUMENT_TYPES and doc.trust_level == "canonical":
                sections.append(ContextSection(heading="Canonical Domain", lines=(doc.title, doc.text), source=doc.doc_id))
        for doc in final_docs:
            if doc.document_type in _SYSTEM_DOCUMENT_TYPES and doc.trust_level != "supporting":
                sections.append(ContextSection(heading="System", lines=(doc.title, doc.text), source=doc.doc_id))

        expansion = registry_expansion if registry_expansion is not None else result.expansion
        if expansion is not None:
            path_lines = tuple(" -> ".join(path) for path in expansion.paths if len(path) > 1)
            if path_lines:
                sections.append(ContextSection(heading="Relationship Evidence", lines=path_lines, source="registry"))

        sections.extend(_collect_jira_sections(final_docs, resolution_docs))

        for doc in final_docs:
            if ((doc.document_type in _DOMAIN_DOCUMENT_TYPES and doc.trust_level != "canonical")
                    or (doc.document_type in _SYSTEM_DOCUMENT_TYPES and doc.trust_level == "supporting")):
                sections.append(ContextSection(heading="Supporting Knowledge", lines=(doc.title, doc.text), source=doc.doc_id))

        return self._apply_budget(sections)

    def _apply_budget(self, sections: Sequence[ContextSection]) -> BuiltContext:
        included: List[ContextSection] = []
        blocks: List[str] = []
        used = 0
        cutoff = len(sections)

        for index, section in enumerate(sections):
            block = "\n".join([section.heading, *section.lines])
            addition = ("\n" if blocks else "") + block
            if used + len(addition) > self._config.max_chars:
                cutoff = index
                break
            blocks.append(block)
            included.append(section)
            used += len(addition)

        omitted = tuple(section.heading for section in sections[cutoff:])
        text = "\n".join(blocks)
        if omitted:
            omitted_line = "Omitted: " + ", ".join(omitted)
            addition = f"\n{omitted_line}" if text else omitted_line
            if len(text) + len(addition) <= self._config.max_chars:
                text += addition

        return BuiltContext(text=text, sections=tuple(included), omitted_sections=omitted)
