"""Minimal durable run-once state backed by SQLite.

The database stores event id, a payload fingerprint, and the final proposal
only.  Proposals may contain sensitive business context, so callers should
treat the local state file as sensitive and protect it accordingly.
"""

from __future__ import annotations

import datetime as _datetime
import json
import pathlib
import sqlite3
from typing import Any, Callable, Dict, Tuple

from .errors import StateConflictError, StateError


ProposalFactory = Callable[[], Dict[str, Any]]


class StateStore:
    def __init__(self, path: str, *, timeout: float = 35.0):
        if timeout <= 0:
            raise ValueError("timeout must be positive")
        self.path = path
        self.timeout = timeout
        if path != ":memory:":
            try:
                pathlib.Path(path).expanduser().absolute().parent.mkdir(parents=True, exist_ok=True)
            except OSError as exc:
                raise StateError("state directory could not be created") from exc
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        try:
            connection = sqlite3.connect(self.path, timeout=self.timeout, isolation_level=None)
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute("PRAGMA busy_timeout = {0}".format(int(self.timeout * 1000)))
            return connection
        except sqlite3.Error as exc:
            raise StateError("state database could not be opened") from exc

    def _initialize(self) -> None:
        connection = self._connect()
        try:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS event_proposals (
                    event_id TEXT PRIMARY KEY,
                    payload_fingerprint TEXT NOT NULL,
                    proposal_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
        except sqlite3.Error as exc:
            raise StateError("state schema could not be initialized") from exc
        finally:
            connection.close()

    def run_once(
        self,
        event_id: str,
        payload_fingerprint: str,
        producer: ProposalFactory,
    ) -> Tuple[Dict[str, Any], bool]:
        """Return ``(proposal, replayed)`` while serializing same-event work.

        ``BEGIN IMMEDIATE`` is held around the producer.  That intentionally
        keeps a second same-event caller waiting until the first proposal is
        committed, so it cannot run the heuristic twice.  Producer failures
        roll back the transaction and leave a retryable state.
        """

        connection = self._connect()
        try:
            try:
                connection.execute("BEGIN IMMEDIATE")
                row = connection.execute(
                    "SELECT payload_fingerprint, proposal_json FROM event_proposals WHERE event_id = ?",
                    (event_id,),
                ).fetchone()
                if row is not None:
                    stored_fingerprint, proposal_json = row
                    if stored_fingerprint != payload_fingerprint:
                        raise StateConflictError("event id was already processed with a different payload")
                    try:
                        proposal = json.loads(proposal_json)
                    except (TypeError, ValueError) as exc:
                        raise StateError("stored proposal is invalid") from exc
                    if not isinstance(proposal, dict):
                        raise StateError("stored proposal is invalid")
                    connection.execute("COMMIT")
                    return proposal, True

                proposal = producer()
                proposal_json = json.dumps(
                    proposal, ensure_ascii=False, sort_keys=True, separators=(",", ":")
                )
                connection.execute(
                    "INSERT INTO event_proposals(event_id, payload_fingerprint, proposal_json, created_at) "
                    "VALUES (?, ?, ?, ?)",
                    (
                        event_id,
                        payload_fingerprint,
                        proposal_json,
                        _datetime.datetime.now(_datetime.timezone.utc).isoformat(),
                    ),
                )
                connection.execute("COMMIT")
                return proposal, False
            except StateConflictError:
                connection.execute("ROLLBACK")
                raise
            except StateError:
                connection.execute("ROLLBACK")
                raise
            except Exception:
                connection.execute("ROLLBACK")
                raise
        except sqlite3.Error as exc:
            try:
                connection.execute("ROLLBACK")
            except sqlite3.Error:
                pass
            raise StateError("state transaction failed") from exc
        finally:
            connection.close()
