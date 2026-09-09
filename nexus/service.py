"""Composition root for retrieval, proposal generation, and dry-run output."""

from __future__ import annotations

from typing import Any, Dict, Optional, Sequence

from .errors import EngineError
from .models import Document, Event, parse_corpus, parse_event, payload_fingerprint
from .opencode import OpenCodeEngine
from .proposals import fixture_proposal, render_comment, render_issue, validate_proposal
from .retrieval import retrieve
from .storage import StateStore


class FixtureEngine:
    name = "fixture"
    demo_only = True

    def propose(self, event: Event, evidence: Sequence[Document]) -> Dict[str, Any]:
        return fixture_proposal(event, evidence)


class NexusService:
    """Prepare one validated local proposal and never publish it."""

    def __init__(self, state_path: str, *, engine: Optional[Any] = None, state_timeout: float = 35.0):
        self.store = StateStore(state_path, timeout=state_timeout)
        self.engine = engine or FixtureEngine()

    def process(self, event_payload: Any, corpus_payload: Any) -> Dict[str, Any]:
        event = parse_event(event_payload)
        corpus = parse_corpus(corpus_payload)
        fingerprint = payload_fingerprint(event_payload)
        evidence = retrieve(event, corpus)

        def produce() -> Dict[str, Any]:
            # A missing retrieval result is a hard no-provider path.  In
            # particular, selecting OpenCode cannot cause an ungrounded call.
            if not evidence:
                raw_proposal = {"recommendations": [], "labels": ["needs-triage"]}
            else:
                try:
                    raw_proposal = self.engine.propose(event, evidence)
                except EngineError:
                    raise
                except Exception as exc:
                    raise EngineError("proposal engine failed") from exc
            proposal = validate_proposal(raw_proposal, evidence)
            engine_name = str(getattr(self.engine, "name", "unknown"))
            result = {
                "comment": render_comment(proposal, evidence, event.event_id),
                "demo_only": bool(getattr(self.engine, "demo_only", False)),
                "dry_run": True,
                "engine": engine_name,
                "event_id": event.event_id,
                "issue": render_issue(event, proposal, evidence),
                "issue_key": event.issue_key,
                "labels": proposal["labels"],
                "published": False,
                "recommendations": proposal["recommendations"],
                "state": "prepared",
            }
            return result

        result, _replayed = self.store.run_once(event.event_id, fingerprint, produce)
        return result


def process_files(
    event_payload: Any,
    corpus_payload: Any,
    state_path: str,
    *,
    engine: str = "fixture",
    timeout: float = 30.0,
) -> Dict[str, Any]:
    if engine == "fixture":
        selected = FixtureEngine()
    elif engine == "opencode":
        selected = OpenCodeEngine(timeout=timeout)
    else:
        raise ValueError("unknown engine")
    return NexusService(state_path, engine=selected, state_timeout=max(35.0, timeout + 5.0)).process(
        event_payload, corpus_payload
    )
