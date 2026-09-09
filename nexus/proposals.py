"""Grounded proposal validation, the fixture-only heuristic, and rendering."""

from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional, Sequence
from urllib.parse import urlsplit

from .errors import ProposalValidationError
from .models import Document, Event, normalize_text
from .retrieval import lexical_tokens


ALLOWED_LABELS = frozenset({"needs-triage", "possible-duplicate"})


def _clean_recommendation_text(value: Any) -> str:
    if not isinstance(value, str):
        raise ProposalValidationError("recommendation text must be a string")
    if any(ord(char) < 32 and char not in "\t\n\r" for char in value):
        raise ProposalValidationError("recommendation text contains unsupported characters")
    text = normalize_text(value)
    if not text or len(text) > 2_000:
        raise ProposalValidationError("recommendation text is empty or too large")
    return text


def validate_proposal(value: Any, evidence: Sequence[Document]) -> Dict[str, Any]:
    """Validate the intentionally small engine contract.

    Evidence ids are constrained to the already synthetic-project-filtered
    retrieval result, and every recommendation must share a meaningful lexical
    token with each cited document set.  Production ACL enforcement belongs to
    the integration adapter before retrieval.  This is a conservative
    grounding check, not an LLM truth claim.
    """

    if not isinstance(value, Mapping):
        raise ProposalValidationError("proposal must be a JSON object")
    if set(value) != {"recommendations", "labels"}:
        raise ProposalValidationError("proposal has unknown or missing fields")
    recommendations = value["recommendations"]
    labels = value["labels"]
    if not isinstance(recommendations, list) or len(recommendations) > 5:
        raise ProposalValidationError("recommendations must be a bounded list")
    if not isinstance(labels, list) or any(not isinstance(label, str) for label in labels):
        raise ProposalValidationError("labels must be a list of strings")
    if len(labels) != len(set(labels)) or any(label not in ALLOWED_LABELS for label in labels):
        raise ProposalValidationError("proposal contains an unknown or duplicate label")

    evidence_by_id = {document.id: document for document in evidence}
    normalized_recommendations: List[Dict[str, Any]] = []
    for recommendation in recommendations:
        if not isinstance(recommendation, Mapping) or set(recommendation) != {"text", "evidence_ids"}:
            raise ProposalValidationError("recommendation has unknown or missing fields")
        text = _clean_recommendation_text(recommendation["text"])
        evidence_ids = recommendation["evidence_ids"]
        if (
            not isinstance(evidence_ids, list)
            or not evidence_ids
            or len(evidence_ids) > 5
            or any(not isinstance(source_id, str) for source_id in evidence_ids)
            or len(evidence_ids) != len(set(evidence_ids))
        ):
            raise ProposalValidationError("recommendation evidence ids are invalid")
        if any(source_id not in evidence_by_id for source_id in evidence_ids):
            raise ProposalValidationError("recommendation cites an unknown source")

        recommendation_tokens = lexical_tokens(text)
        source_tokens = set()
        for source_id in evidence_ids:
            source = evidence_by_id[source_id]
            source_tokens.update(lexical_tokens(source.title + " " + source.text))
        if not recommendation_tokens or not recommendation_tokens.intersection(source_tokens):
            raise ProposalValidationError("recommendation is not grounded in its cited source")
        normalized_recommendations.append({"text": text, "evidence_ids": list(evidence_ids)})

    return {"recommendations": normalized_recommendations, "labels": list(labels)}


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


def _evidence_gate(recommendations: Sequence[Mapping[str, Any]], evidence_by_id: Mapping[str, Document]) -> List[tuple]:
    seen_sources = set()
    for recommendation in recommendations:
        for source_id in recommendation["evidence_ids"]:
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


def render_comment(proposal: Mapping[str, Any], evidence: Sequence[Document], event_id: str) -> str:
    """Render comment format v1: header, recommendations, evidence, labels, marker.

    The final line is the ``voc-nexus-comment|v1|<event_id>`` marker, which
    integration lookups use as the dedupe key before posting (see
    docs/INTEGRATION.md completion condition 2 and docs/TEMPLATES.md).
    """

    marker_id = _marker_event_id(event_id)
    evidence_by_id = {document.id: document for document in evidence}
    recommendations = proposal["recommendations"]
    lines = ["VOC triage recommendations (dry-run):", ""]
    if recommendations:
        for recommendation in recommendations:
            lines.append("- " + recommendation["text"])
    else:
        lines.append("No grounded recommendation found; manual triage required.")
    sources = _evidence_gate(recommendations, evidence_by_id)
    if sources:
        lines.extend(["", "Evidence:"])
        for source_id, url in sources:
            lines.append("- " + source_id + ": " + url)
    lines.extend(["", "Labels: " + ", ".join(sorted(proposal["labels"]))])
    lines.extend(["", "voc-nexus-comment|v1|" + marker_id])
    return "\n".join(lines)


def render_issue(event: Event, proposal: Mapping[str, Any], evidence: Sequence[Document]) -> Dict[str, Any]:
    """Render issue format v1: summary and a structured description.

    Not published by the current CLI; this is the template a future write
    lifecycle would create issues from (see docs/TEMPLATES.md).
    """

    evidence_by_id = {document.id: document for document in evidence}
    summary = normalize_text("[VOC] " + event.summary)[:80]
    marker_id = _marker_event_id(event.event_id)
    recommendations = proposal["recommendations"]
    description_lines = [
        "Context:",
        "",
        "- event_id: " + event.event_id,
        "- issue_key: " + event.issue_key,
        "- project: " + event.project,
        "",
        "Recommendations:",
    ]
    if recommendations:
        for recommendation in recommendations:
            description_lines.append("- " + recommendation["text"])
    else:
        description_lines.append("No grounded recommendation found; manual triage required.")

    sources = _evidence_gate(recommendations, evidence_by_id)
    if sources:
        description_lines.extend(["", "Evidence:"])
        for source_id, url in sources:
            description_lines.append("- " + source_id + ": " + url)

    description_lines.extend(["", "Labels: " + ", ".join(sorted(proposal["labels"]))])
    marker = "voc-nexus-issue|v1|" + marker_id
    description_lines.extend(["", marker])
    description = "\n".join(description_lines)
    return {"summary": summary, "description": description, "marker": marker}


def fixture_proposal(event: Event, evidence: Sequence[Document]) -> Dict[str, Any]:
    """Deterministic demo heuristic; this is not a production recommendation engine."""

    if not evidence:
        return {"recommendations": [], "labels": ["needs-triage"]}

    recommendations = []
    for source in evidence:
        if not source.resolved:
            continue
        source_tokens = sorted(lexical_tokens(source.title + " " + source.text))
        if not source_tokens:
            continue
        keyword = source_tokens[0]
        recommendations.append(
            {
                "text": "Review the resolved guidance for {0} concerning {1}.".format(
                    source.id, keyword
                ),
                "evidence_ids": [source.id],
            }
        )
        if len(recommendations) == 3:
            break
    labels = ["possible-duplicate"]
    if not recommendations:
        labels.append("needs-triage")
    return {"recommendations": recommendations, "labels": labels}
