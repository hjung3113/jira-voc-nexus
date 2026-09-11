"""Grounded proposal validation, the fixture-only heuristic, and rendering."""

from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional, Sequence
from urllib.parse import urlsplit

from .errors import ProposalValidationError
from .models import Document, Event, normalize_text
from .retrieval import lexical_tokens


ALLOWED_LABELS = frozenset({"needs-triage", "possible-duplicate"})


def _clean_audience_text(value: Any, field: str) -> str:
    if not isinstance(value, str):
        raise ProposalValidationError(field + " text must be a string")
    if any(ord(char) < 32 and char not in "\t\n\r" for char in value):
        raise ProposalValidationError(field + " text contains unsupported characters")
    text = normalize_text(value)
    if not text or len(text) > 2_000:
        raise ProposalValidationError(field + " text is empty or too large")
    return text


def _audience_field(
    value: Any, field: str, evidence_by_id: Mapping[str, Document]
) -> Optional[Dict[str, Any]]:
    """Validate one audience field, grounded only in its own cited sources."""

    if value is None:
        return None
    if not isinstance(value, Mapping) or set(value) != {"text", "evidence_ids"}:
        raise ProposalValidationError(field + " must be null or an object with text and evidence_ids")
    text = _clean_audience_text(value["text"], field)
    evidence_ids = value["evidence_ids"]
    if (
        not isinstance(evidence_ids, list)
        or not evidence_ids
        or len(evidence_ids) > 5
        or any(not isinstance(source_id, str) for source_id in evidence_ids)
        or len(evidence_ids) != len(set(evidence_ids))
    ):
        raise ProposalValidationError(field + " evidence ids are invalid")
    if any(source_id not in evidence_by_id for source_id in evidence_ids):
        raise ProposalValidationError(field + " cites an unknown source")

    field_tokens = lexical_tokens(text)
    source_tokens = set()
    for source_id in evidence_ids:
        source = evidence_by_id[source_id]
        source_tokens.update(lexical_tokens(source.title + " " + source.text))
    if not field_tokens or not field_tokens.intersection(source_tokens):
        raise ProposalValidationError(field + " is not grounded in its cited source")
    return {"text": text, "evidence_ids": list(evidence_ids)}


def validate_proposal(value: Any, evidence: Sequence[Document]) -> Dict[str, Any]:
    """Validate the intentionally small engine contract (v2, audience-split).

    Evidence ids are constrained to the already synthetic-project-filtered
    retrieval result, and each audience field must share a meaningful lexical
    token with its own cited document set; a source cited by one field never
    grounds the other.  Production ACL enforcement belongs to the integration
    adapter before retrieval.  This is a conservative grounding check, not an
    LLM truth claim.
    """

    if not isinstance(value, Mapping):
        raise ProposalValidationError("proposal must be a JSON object")
    if set(value) != {"customer_reply", "engineering_action", "labels"}:
        raise ProposalValidationError("proposal has unknown or missing fields")
    labels = value["labels"]
    if not isinstance(labels, list) or any(not isinstance(label, str) for label in labels):
        raise ProposalValidationError("labels must be a list of strings")
    if len(labels) != len(set(labels)) or any(label not in ALLOWED_LABELS for label in labels):
        raise ProposalValidationError("proposal contains an unknown or duplicate label")

    evidence_by_id = {document.id: document for document in evidence}
    return {
        "customer_reply": _audience_field(value["customer_reply"], "customer_reply", evidence_by_id),
        "engineering_action": _audience_field(
            value["engineering_action"], "engineering_action", evidence_by_id
        ),
        "labels": list(labels),
    }


def _safe_http_url(value: str) -> Optional[str]:
    if not value or len(value) > 4_000 or any(char.isspace() or ord(char) < 32 for char in value):
        return None
    try:
        parsed = urlsplit(value)
    except ValueError:
        return None
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    return value


def _evidence_gate(fields: Sequence[Mapping[str, Any]], evidence_by_id: Mapping[str, Document]) -> List[tuple]:
    seen_sources = set()
    for field in fields:
        for source_id in field["evidence_ids"]:
            source = evidence_by_id[source_id]
            url = _safe_http_url(source.url)
            if url is not None:
                seen_sources.add((source.id, url))
    return sorted(seen_sources)

def _marker_event_id(event_id: Any) -> str:
    """Reject ids that would break single-line pipe-delimited marker lookup."""
    if not isinstance(event_id, str) or any(char in event_id for char in "\n\r|"):
        raise ProposalValidationError("event_id is not marker-safe")
    return event_id


def _audience_lines(proposal: Mapping[str, Any]) -> List[str]:
    """Render the two audience sections shared by both v2 formats."""

    lines = ["Customer reply:"]
    customer_reply = proposal["customer_reply"]
    if customer_reply is not None:
        lines.append(customer_reply["text"])
    else:
        lines.append("No grounded customer-facing response found; manual reply required.")
    lines.append("")
    lines.append("Engineering action:")
    engineering_action = proposal["engineering_action"]
    if engineering_action is not None:
        lines.append(engineering_action["text"])
    else:
        lines.append("No grounded engineering action found; manual triage required.")
    return lines


def _cited_fields(proposal: Mapping[str, Any]) -> List[Mapping[str, Any]]:
    return [field for field in (proposal["customer_reply"], proposal["engineering_action"]) if field is not None]


def recipients(proposal: Mapping[str, Any]) -> List[str]:
    """Return deterministic recipient labels for the grounded audiences."""

    result = []
    if proposal["customer_reply"] is not None:
        result.append("user-support")
    if proposal["engineering_action"] is not None:
        result.append("dev-team")
    return result


def render_comment(proposal: Mapping[str, Any], evidence: Sequence[Document], event_id: str) -> str:
    """Render comment format v2: header, audience sections, evidence, labels, marker.

    The final line is the ``voc-nexus-comment|v2|<event_id>`` marker, which
    integration lookups use as the dedupe key before posting (see
    docs/INTEGRATION.md completion condition 2 and docs/TEMPLATES.md).
    """

    marker_id = _marker_event_id(event_id)
    evidence_by_id = {document.id: document for document in evidence}
    recipient_list = recipients(proposal)
    lines = ["VOC triage recommendations (dry-run):", ""]
    lines.extend(_audience_lines(proposal))
    sources = _evidence_gate(_cited_fields(proposal), evidence_by_id)
    if sources:
        lines.extend(["", "Evidence:"])
        for source_id, url in sources:
            lines.append("- " + source_id + ": " + url)
    lines.extend(["", "Labels: " + ", ".join(sorted(proposal["labels"]))])
    lines.append("Recipients: " + (", ".join(recipient_list) or "none"))
    lines.extend(["", "voc-nexus-comment|v2|" + marker_id])
    return "\n".join(lines)


def render_issue(event: Event, proposal: Mapping[str, Any], evidence: Sequence[Document]) -> Dict[str, Any]:
    """Render issue format v2: summary and a structured description.

    Not published by the current CLI; this is the template a future write
    lifecycle would create issues from (see docs/TEMPLATES.md).
    """

    evidence_by_id = {document.id: document for document in evidence}
    summary = normalize_text("[VOC] " + event.summary)[:80]
    marker_id = _marker_event_id(event.event_id)
    recipient_list = recipients(proposal)
    description_lines = [
        "Context:",
        "",
        "- event_id: " + event.event_id,
        "- issue_key: " + event.issue_key,
        "- project: " + event.project,
        "",
    ]
    description_lines.extend(_audience_lines(proposal))

    sources = _evidence_gate(_cited_fields(proposal), evidence_by_id)
    if sources:
        description_lines.extend(["", "Evidence:"])
        for source_id, url in sources:
            description_lines.append("- " + source_id + ": " + url)

    description_lines.extend(["", "Labels: " + ", ".join(sorted(proposal["labels"]))])
    description_lines.append("Recipients: " + (", ".join(recipient_list) or "none"))
    marker = "voc-nexus-issue|v2|" + marker_id
    description_lines.extend(["", marker])
    description = "\n".join(description_lines)
    return {"summary": summary, "description": description, "marker": marker}


def fixture_proposal(event: Event, evidence: Sequence[Document]) -> Dict[str, Any]:
    """Deterministic demo heuristic; this is not a production recommendation engine."""

    if not evidence:
        return {"customer_reply": None, "engineering_action": None, "labels": ["needs-triage"]}

    resolved_sources = []
    for source in evidence:
        if not source.resolved:
            continue
        source_tokens = sorted(lexical_tokens(source.title + " " + source.text))
        if not source_tokens:
            continue
        resolved_sources.append((source, source_tokens[0]))
        if len(resolved_sources) == 2:
            break
    if not resolved_sources:
        return {
            "customer_reply": None,
            "engineering_action": None,
            "labels": ["possible-duplicate", "needs-triage"],
        }

    customer_source, customer_keyword = resolved_sources[0]
    action_source, action_keyword = resolved_sources[-1]
    return {
        "customer_reply": {
            "text": "Fixture demo only: the {0} issue has prior resolved guidance in {1} that may answer the customer.".format(
                customer_keyword, customer_source.id
            ),
            "evidence_ids": [customer_source.id],
        },
        "engineering_action": {
            "text": "Fixture demo only: review the resolved guidance for {0} concerning {1}.".format(
                action_source.id, action_keyword
            ),
            "evidence_ids": [action_source.id],
        },
        "labels": ["possible-duplicate"],
    }
