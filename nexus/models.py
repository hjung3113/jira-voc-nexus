"""Normalized input models and conservative JSON boundary validation."""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from dataclasses import dataclass
from typing import Any, Dict, List, Mapping

from .errors import InputError


_WHITESPACE_RE = re.compile(r"\s+")
_EVENT_FIELDS = {
    "event_id",
    "issue_key",
    "project",
    "summary",
    "description",
    "labels",
}
_CORPUS_FIELDS = {"id", "project", "title", "text", "resolved", "url"}


def normalize_text(value: str) -> str:
    """Apply deterministic Unicode and whitespace normalization."""

    value = unicodedata.normalize("NFKC", value)
    value = _WHITESPACE_RE.sub(" ", value).strip()
    return value


def _string(value: Any, field: str, *, allow_empty: bool = False, limit: int = 20_000) -> str:
    if not isinstance(value, str):
        raise InputError("input field must be a string")
    if any(ord(char) < 32 and char not in "\t\n\r" for char in value):
        raise InputError("input contains an unsupported control character")
    result = normalize_text(value)
    if not allow_empty and not result:
        raise InputError("input field must not be empty")
    if len(result) > limit:
        raise InputError("input field is too large")
    return result


def _object(value: Any, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise InputError("input must contain JSON objects")
    return value


def _strict_fields(value: Mapping[str, Any], expected: set[str]) -> None:
    if set(value) != expected:
        raise InputError("input has missing or unknown fields")


@dataclass(frozen=True)
class Event:
    event_id: str
    issue_key: str
    project: str
    summary: str
    description: str
    labels: List[str]

    def as_dict(self) -> Dict[str, Any]:
        return {
            "event_id": self.event_id,
            "issue_key": self.issue_key,
            "project": self.project,
            "summary": self.summary,
            "description": self.description,
            "labels": list(self.labels),
        }


@dataclass(frozen=True)
class Document:
    id: str
    project: str
    title: str
    text: str
    resolved: bool
    url: str

    def as_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "project": self.project,
            "title": self.title,
            "text": self.text,
            "resolved": self.resolved,
            "url": self.url,
        }


def parse_event(value: Any) -> Event:
    data = _object(value, "event")
    _strict_fields(data, _EVENT_FIELDS)
    labels = data["labels"]
    if not isinstance(labels, list) or any(not isinstance(label, str) for label in labels):
        raise InputError("event labels must be a list of strings")
    normalized_labels = [_string(label, "label", limit=200) for label in labels]
    if len(normalized_labels) > 100:
        raise InputError("event has too many labels")
    return Event(
        event_id=_string(data["event_id"], "event_id", limit=500),
        issue_key=_string(data["issue_key"], "issue_key", limit=500),
        project=_string(data["project"], "project", limit=200),
        summary=_string(data["summary"], "summary", limit=10_000),
        description=_string(data["description"], "description", allow_empty=True, limit=50_000),
        labels=normalized_labels,
    )


def parse_corpus(value: Any) -> List[Document]:
    if not isinstance(value, list):
        raise InputError("corpus must be a JSON list")
    if len(value) > 10_000:
        raise InputError("corpus is too large")
    documents: List[Document] = []
    seen_ids = set()
    for item in value:
        data = _object(item, "corpus document")
        _strict_fields(data, _CORPUS_FIELDS)
        document = Document(
            id=_string(data["id"], "document id", limit=500),
            project=_string(data["project"], "document project", limit=200),
            title=_string(data["title"], "document title", limit=10_000),
            text=_string(data["text"], "document text", allow_empty=True, limit=100_000),
            resolved=data["resolved"] if isinstance(data["resolved"], bool) else None,  # type: ignore[arg-type]
            url=_string(data["url"], "document URL", allow_empty=True, limit=4_000),
        )
        if document.resolved is None:
            raise InputError("document resolved must be a boolean")
        if document.id in seen_ids:
            raise InputError("corpus document ids must be unique")
        seen_ids.add(document.id)
        documents.append(document)
    return documents


def canonical_json(value: Any) -> str:
    """Canonical representation used for the event payload fingerprint."""

    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    except (TypeError, ValueError) as exc:
        raise InputError("input is not canonical JSON") from exc


def payload_fingerprint(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()
