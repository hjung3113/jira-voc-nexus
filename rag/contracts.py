"""Canonical document/entity contracts for the RAG core.

Mirrors the strict-parsing style of ``nexus.models``: every payload boundary
rejects unknown/missing keys, wrong types, and oversized input instead of
silently coercing it. Text normalization reuses
``nexus.models.normalize_text`` so there is a single normalization
convention across ``nexus`` and ``rag``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Optional, Tuple

from nexus.models import normalize_text

from .errors import RagInputError

TRUST_LEVELS = ("canonical", "implementation", "verified-resolution", "supporting")
SOURCE_TYPES = ("wiki", "jira", "code", "db")
DOCUMENT_TYPES = (
    "domain_knowledge",
    "system_knowledge",
    "code_knowledge",
    "db_knowledge",
    "jira_problem",
    "jira_resolution",
)
RELATION_TYPES = ("CALLS", "EXECUTES", "READS", "WRITES", "USES", "OWNS")

_WIKI_PAGE_TYPES = ("domain", "systems", "data")
_WIKI_STATUSES = ("canonical", "draft")

_MAX_STRING = 50_000
_MAX_LIST = 200
_MAX_METADATA_KEYS = 50
_MAX_METADATA_STRING = 200


def _object(value: Any, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise RagInputError(f"{field} must be a JSON object")
    return value


def _strict_fields(value: Mapping[str, Any], expected: set, field: str) -> None:
    if set(value) != expected:
        raise RagInputError(f"{field} has missing or unknown fields")


def _string(value: Any, field: str, *, allow_empty: bool = False, limit: int = _MAX_STRING) -> str:
    if not isinstance(value, str):
        raise RagInputError(f"{field} must be a string")
    if any(ord(char) < 32 and char not in "\t\n\r" for char in value):
        raise RagInputError(f"{field} contains an unsupported control character")
    result = normalize_text(value)
    if not allow_empty and not result:
        raise RagInputError(f"{field} must not be empty")
    if len(result) > limit:
        raise RagInputError(f"{field} is too large")
    return result


def _string_tuple(value: Any, field: str, *, item_limit: int = _MAX_STRING, list_limit: int = _MAX_LIST) -> Tuple[str, ...]:
    if not isinstance(value, list):
        raise RagInputError(f"{field} must be a JSON list")
    if len(value) > list_limit:
        raise RagInputError(f"{field} has too many items")
    return tuple(_string(item, field, allow_empty=False, limit=item_limit) for item in value)


def _enum(value: Any, field: str, allowed: Tuple[str, ...]) -> str:
    result = _string(value, field, allow_empty=False, limit=200)
    if result not in allowed:
        raise RagInputError(f"{field} must be one of {allowed}")
    return result


def _metadata_scalar(value: Any, field: str) -> Any:
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value
    if isinstance(value, str):
        return _string(value, field, allow_empty=True, limit=_MAX_METADATA_STRING)
    raise RagInputError(f"{field} has an unsupported metadata value type")


def _metadata(value: Any, field: str) -> Dict[str, Any]:
    data = _object(value, field)
    if len(data) > _MAX_METADATA_KEYS:
        raise RagInputError(f"{field} has too many keys")
    result: Dict[str, Any] = {}
    for key, item in data.items():
        if not isinstance(key, str) or not key:
            raise RagInputError(f"{field} has an invalid key")
        if isinstance(item, list):
            if len(item) > _MAX_LIST:
                raise RagInputError(f"{field}.{key} has too many items")
            result[key] = [_metadata_scalar(sub, f"{field}.{key}") for sub in item]
        else:
            result[key] = _metadata_scalar(item, f"{field}.{key}")
    return result


_ISO8601_RE = re.compile(r"^\d{4}-\d{2}-\d{2}(T\d{2}:\d{2}(:\d{2})?)?Z?$")


def _iso8601(value: Any, field: str) -> str:
    result = _string(value, field, allow_empty=True, limit=64)
    if not result:
        return result
    if not _ISO8601_RE.match(result):
        raise RagInputError(f"{field} must be an ISO-8601 timestamp")
    return result


# --------------------------------------------------------------------------
# Jira normalization contract
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class ProblemBlock:
    summary: str
    symptom: str
    environment: str
    error: str


@dataclass(frozen=True)
class Resolution:
    root_cause: str
    action: str
    verification: str


_PROBLEM_FIELDS = {"summary", "symptom", "environment", "error"}
_RESOLUTION_FIELDS = {"root_cause", "action", "verification"}
_ISSUE_FIELDS = {"issue_key", "project", "metadata", "problem", "investigation", "resolution"}


def _parse_problem(value: Any) -> ProblemBlock:
    data = _object(value, "problem")
    _strict_fields(data, _PROBLEM_FIELDS, "problem")
    return ProblemBlock(
        summary=_string(data["summary"], "problem.summary", limit=10_000),
        symptom=_string(data["symptom"], "problem.symptom", allow_empty=True, limit=_MAX_STRING),
        environment=_string(data["environment"], "problem.environment", allow_empty=True, limit=_MAX_STRING),
        error=_string(data["error"], "problem.error", allow_empty=True, limit=_MAX_STRING),
    )


def _parse_resolution(value: Any) -> Resolution:
    data = _object(value, "resolution")
    _strict_fields(data, _RESOLUTION_FIELDS, "resolution")
    return Resolution(
        root_cause=_string(data["root_cause"], "resolution.root_cause", allow_empty=True, limit=_MAX_STRING),
        action=_string(data["action"], "resolution.action", allow_empty=True, limit=_MAX_STRING),
        verification=_string(data["verification"], "resolution.verification", allow_empty=True, limit=_MAX_STRING),
    )


@dataclass(frozen=True)
class NormalizedIssue:
    """Canonical Jira issue representation (metadata/problem/investigation/resolution).

    ``metadata`` is a bounded free-form dict. Documented keys used elsewhere
    in this module: ``system``, ``component``, ``updated_at``.
    """

    issue_key: str
    project: str
    metadata: Dict[str, Any]
    problem: ProblemBlock
    investigation: Tuple[str, ...]
    resolution: Optional[Resolution]

    def trust_level(self) -> str:
        if self.resolution is not None and normalize_text(self.resolution.verification):
            return "verified-resolution"
        return "supporting"


def parse_normalized_issue(payload: Any) -> NormalizedIssue:
    data = _object(payload, "normalized issue")
    _strict_fields(data, _ISSUE_FIELDS, "normalized issue")
    resolution_raw = data["resolution"]
    resolution = None if resolution_raw is None else _parse_resolution(resolution_raw)
    metadata = _metadata(data["metadata"], "metadata")
    if "updated_at" in metadata:
        updated_at = metadata["updated_at"]
        if not isinstance(updated_at, str):
            raise RagInputError("metadata.updated_at must be a string")
        metadata["updated_at"] = _iso8601(updated_at, "metadata.updated_at")
    return NormalizedIssue(
        issue_key=_string(data["issue_key"], "issue_key", limit=500),
        project=_string(data["project"], "project", limit=200),
        metadata=metadata,
        problem=_parse_problem(data["problem"]),
        investigation=_string_tuple(data["investigation"], "investigation"),
        resolution=resolution,
    )


# --------------------------------------------------------------------------
# Wiki page contract
# --------------------------------------------------------------------------

_WIKI_FIELDS = {
    "page_id",
    "title",
    "text",
    "page_type",
    "system",
    "component",
    "owner",
    "status",
    "related_entities",
}


@dataclass(frozen=True)
class WikiPage:
    page_id: str
    title: str
    text: str
    page_type: str
    system: str
    component: str
    owner: str
    status: str
    related_entities: Tuple[str, ...]

    def trust_level(self) -> str:
        return "canonical" if self.status == "canonical" else "supporting"


def parse_wiki_page(payload: Any) -> WikiPage:
    data = _object(payload, "wiki page")
    _strict_fields(data, _WIKI_FIELDS, "wiki page")
    return WikiPage(
        page_id=_string(data["page_id"], "page_id", limit=500),
        title=_string(data["title"], "title", limit=10_000),
        text=_string(data["text"], "text", allow_empty=True, limit=_MAX_STRING),
        page_type=_enum(data["page_type"], "page_type", _WIKI_PAGE_TYPES),
        system=_string(data["system"], "system", allow_empty=True, limit=500),
        component=_string(data["component"], "component", allow_empty=True, limit=500),
        owner=_string(data["owner"], "owner", allow_empty=True, limit=500),
        status=_enum(data["status"], "status", _WIKI_STATUSES),
        related_entities=_string_tuple(data["related_entities"], "related_entities", item_limit=500),
    )


# --------------------------------------------------------------------------
# Knowledge entity/relation contract (used by rag.registry)
# --------------------------------------------------------------------------

_ENTITY_FIELDS = {"id", "type", "name", "system", "description"}
_RELATION_FIELDS = {"source_id", "relation_type", "target_id"}


@dataclass(frozen=True)
class KnowledgeEntity:
    id: str
    type: str
    name: str
    system: str
    description: str


@dataclass(frozen=True)
class KnowledgeRelation:
    source_id: str
    relation_type: str
    target_id: str


def parse_knowledge_entity(payload: Any) -> KnowledgeEntity:
    data = _object(payload, "knowledge entity")
    _strict_fields(data, _ENTITY_FIELDS, "knowledge entity")
    return KnowledgeEntity(
        id=_string(data["id"], "id", limit=500),
        type=_string(data["type"], "type", limit=200),
        name=_string(data["name"], "name", limit=500),
        system=_string(data["system"], "system", allow_empty=True, limit=500),
        description=_string(data["description"], "description", allow_empty=True, limit=_MAX_STRING),
    )


def parse_knowledge_relation(payload: Any) -> KnowledgeRelation:
    data = _object(payload, "knowledge relation")
    _strict_fields(data, _RELATION_FIELDS, "knowledge relation")
    return KnowledgeRelation(
        source_id=_string(data["source_id"], "source_id", limit=500),
        relation_type=_enum(data["relation_type"], "relation_type", RELATION_TYPES),
        target_id=_string(data["target_id"], "target_id", limit=500),
    )


# --------------------------------------------------------------------------
# Index document contract
# --------------------------------------------------------------------------

_INDEX_DOCUMENT_FIELDS = {
    "doc_id",
    "source_type",
    "document_type",
    "project",
    "system",
    "component",
    "entity_ids",
    "trust_level",
    "source_id",
    "updated_at",
    "title",
    "text",
}


@dataclass(frozen=True)
class IndexDocument:
    doc_id: str
    source_type: str
    document_type: str
    project: str
    system: str
    component: str
    entity_ids: Tuple[str, ...]
    trust_level: str
    source_id: str
    updated_at: str
    title: str
    text: str


def parse_index_document(payload: Any) -> IndexDocument:
    data = _object(payload, "index document")
    _strict_fields(data, _INDEX_DOCUMENT_FIELDS, "index document")
    return IndexDocument(
        doc_id=_string(data["doc_id"], "doc_id", limit=500),
        source_type=_enum(data["source_type"], "source_type", SOURCE_TYPES),
        document_type=_enum(data["document_type"], "document_type", DOCUMENT_TYPES),
        project=_string(data["project"], "project", allow_empty=True, limit=500),
        system=_string(data["system"], "system", allow_empty=True, limit=500),
        component=_string(data["component"], "component", allow_empty=True, limit=500),
        entity_ids=_string_tuple(data["entity_ids"], "entity_ids", item_limit=500),
        trust_level=_enum(data["trust_level"], "trust_level", TRUST_LEVELS),
        source_id=_string(data["source_id"], "source_id", limit=500),
        updated_at=_iso8601(data["updated_at"], "updated_at"),
        title=_string(data["title"], "title", allow_empty=True, limit=10_000),
        text=_string(data["text"], "text", allow_empty=True, limit=_MAX_STRING),
    )


# --------------------------------------------------------------------------
# Document projection helpers
# --------------------------------------------------------------------------

_WIKI_DOCUMENT_TYPE = {
    "domain": "domain_knowledge",
    "systems": "system_knowledge",
    "data": "db_knowledge",
}


def issue_to_documents(issue: NormalizedIssue) -> List[IndexDocument]:
    """Project a NormalizedIssue into its jira_problem (+ jira_resolution) documents."""

    system = str(issue.metadata.get("system", "") or "")
    component = str(issue.metadata.get("component", "") or "")
    updated_at = str(issue.metadata.get("updated_at", "") or "")

    problem_text = normalize_text(
        " ".join(
            part
            for part in (issue.problem.summary, issue.problem.symptom, issue.problem.environment, issue.problem.error)
            if part
        )
    )
    documents = [
        IndexDocument(
            doc_id=f"{issue.issue_key}:problem",
            source_type="jira",
            document_type="jira_problem",
            project=issue.project,
            system=system,
            component=component,
            entity_ids=(),
            trust_level="supporting",
            source_id=issue.issue_key,
            updated_at=updated_at,
            title=issue.problem.summary,
            text=problem_text,
        )
    ]

    if issue.resolution is not None:
        resolution_text = normalize_text(
            " ".join(
                part
                for part in (issue.resolution.root_cause, issue.resolution.action, issue.resolution.verification)
                if part
            )
        )
        documents.append(
            IndexDocument(
                doc_id=f"{issue.issue_key}:resolution",
                source_type="jira",
                document_type="jira_resolution",
                project=issue.project,
                system=system,
                component=component,
                entity_ids=(),
                trust_level=issue.trust_level(),
                source_id=issue.issue_key,
                updated_at=updated_at,
                title=f"{issue.issue_key} resolution",
                text=resolution_text,
            )
        )

    return documents


def wiki_to_document(page: WikiPage) -> IndexDocument:
    return IndexDocument(
        doc_id=f"wiki:{page.page_id}",
        source_type="wiki",
        document_type=_WIKI_DOCUMENT_TYPE[page.page_type],
        project="",
        system=page.system,
        component=page.component,
        entity_ids=page.related_entities,
        trust_level=page.trust_level(),
        source_id=page.page_id,
        updated_at="",
        title=page.title,
        text=page.text,
    )
