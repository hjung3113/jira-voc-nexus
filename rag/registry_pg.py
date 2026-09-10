"""PostgreSQL adapter for the knowledge registry (real, integration-unverified here).

``psycopg`` is imported lazily so importing this module -- or ``rag`` as a
whole -- never requires it. Install the ``pg`` extra to use this adapter:

    pip install 'jira-voc-nexus[rag-pg]'

No PostgreSQL instance is available in this environment. The unit tests for
this module are skipped unless ``NEXUS_RAG_PG_TEST_DATASOURCE`` is set to a
reachable Postgres connection string; until then this adapter's SQL has been
reviewed against the SQLite implementation's semantics but not executed
against a real server.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from .contracts import KnowledgeEntity, KnowledgeRelation, RELATION_TYPES
from .errors import RagInputError
from .registry import (
    RegistryExpansion,
    SqliteKnowledgeRegistry,
    _normalize_entity_scope,
    _validate_max_hops,
)

DDL = """
CREATE TABLE IF NOT EXISTS knowledge_entity (
    id TEXT PRIMARY KEY,
    type TEXT NOT NULL,
    name TEXT NOT NULL,
    system TEXT NOT NULL,
    description TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS knowledge_relation (
    source_id TEXT NOT NULL REFERENCES knowledge_entity(id),
    relation_type TEXT NOT NULL,
    target_id TEXT NOT NULL REFERENCES knowledge_entity(id),
    PRIMARY KEY (source_id, relation_type, target_id)
);

CREATE INDEX IF NOT EXISTS knowledge_relation_type_idx
    ON knowledge_relation (relation_type);
"""


def _import_psycopg():
    try:
        import psycopg  # type: ignore
    except ImportError as exc:  # pragma: no cover - exercised only without the extra
        raise RagInputError(
            "psycopg is required for PostgresKnowledgeRegistry; "
            "install it with: pip install 'jira-voc-nexus[rag-pg]'"
        ) from exc
    return psycopg


class PostgresKnowledgeRegistry:
    """Same entity/relation semantics as :class:`SqliteKnowledgeRegistry`, over Postgres."""

    def __init__(self, datasource: str = "", **connect_kwargs: Any) -> None:
        psycopg = _import_psycopg()
        self._conn = psycopg.connect(datasource, **connect_kwargs) if datasource else psycopg.connect(**connect_kwargs)
        with self._conn.cursor() as cur:
            cur.execute(DDL)
        self._conn.commit()

    def upsert_entity(self, entity: KnowledgeEntity) -> None:
        with self._conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO knowledge_entity (id, type, name, system, description)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (id) DO UPDATE SET
                    type = EXCLUDED.type,
                    name = EXCLUDED.name,
                    system = EXCLUDED.system,
                    description = EXCLUDED.description
                """,
                (entity.id, entity.type, entity.name, entity.system, entity.description),
            )
        self._conn.commit()

    def add_relation(self, relation: KnowledgeRelation) -> None:
        if relation.relation_type not in RELATION_TYPES:
            raise RagInputError(f"unsupported relation_type: {relation.relation_type}")
        psycopg = _import_psycopg()
        with self._conn.cursor() as cur:
            for entity_id in (relation.source_id, relation.target_id):
                cur.execute("SELECT 1 FROM knowledge_entity WHERE id = %s", (entity_id,))
                if cur.fetchone() is None:
                    raise RagInputError(f"relation references unknown entity: {entity_id}")
            try:
                cur.execute(
                    """
                    INSERT INTO knowledge_relation (source_id, relation_type, target_id)
                    VALUES (%s, %s, %s)
                    """,
                    (relation.source_id, relation.relation_type, relation.target_id),
                )
            except psycopg.errors.UniqueViolation as exc:
                self._conn.rollback()
                raise RagInputError(
                    f"duplicate relation: {relation.source_id} {relation.relation_type} {relation.target_id}"
                ) from exc
        self._conn.commit()

    def neighbors(
        self,
        entity_id: str,
        *,
        allowed_entity_ids: Optional[Iterable[str]] = None,
        entity_allowlist: Optional[Iterable[str]] = None,
    ) -> List[KnowledgeRelation]:
        scope = _normalize_entity_scope(allowed_entity_ids, entity_allowlist)
        if not isinstance(entity_id, str) or not entity_id:
            raise RagInputError("entity_id must be a non-empty string")
        if scope is not None and entity_id not in scope:
            return []
        with self._conn.cursor() as cur:
            if scope is None:
                cur.execute(
                    """
                    SELECT source_id, relation_type, target_id FROM knowledge_relation
                    WHERE source_id = %s OR target_id = %s
                    ORDER BY relation_type, source_id, target_id
                    """,
                    (entity_id, entity_id),
                )
            else:
                allowed = list(sorted(scope))
                cur.execute(
                    """
                    SELECT source_id, relation_type, target_id FROM knowledge_relation
                    WHERE (source_id = %s OR target_id = %s)
                      AND source_id = ANY(%s)
                      AND target_id = ANY(%s)
                    ORDER BY relation_type, source_id, target_id
                    """,
                    (entity_id, entity_id, allowed, allowed),
                )
            rows = cur.fetchall()
        return [KnowledgeRelation(source_id=r[0], relation_type=r[1], target_id=r[2]) for r in rows]

    def expand(
        self,
        entity_names: Iterable[str],
        max_hops: int = 1,
        *,
        allowed_entity_ids: Optional[Iterable[str]] = None,
        entity_allowlist: Optional[Iterable[str]] = None,
    ) -> RegistryExpansion:
        # Same BFS contract as SqliteKnowledgeRegistry.expand; delegated via
        # an in-memory mirror built from this connection's rows so the
        # traversal algorithm has exactly one implementation to keep in sync.
        # The mirror is a throwaway sqlite connection per call -- close it
        # once the expansion is computed instead of leaking it.
        max_hops = _validate_max_hops(max_hops)
        scope = _normalize_entity_scope(allowed_entity_ids, entity_allowlist)
        if scope == frozenset():
            return RegistryExpansion(entity_ids=(), paths=())
        mirror = SqliteKnowledgeRegistry(":memory:")
        try:
            with self._conn.cursor() as cur:
                if scope is None:
                    cur.execute("SELECT id, type, name, system, description FROM knowledge_entity")
                else:
                    allowed = list(sorted(scope))
                    cur.execute(
                        "SELECT id, type, name, system, description FROM knowledge_entity "
                        "WHERE id = ANY(%s)",
                        (allowed,),
                    )
                for row in cur.fetchall():
                    mirror.upsert_entity(KnowledgeEntity(id=row[0], type=row[1], name=row[2], system=row[3], description=row[4]))
                if scope is None:
                    cur.execute("SELECT source_id, relation_type, target_id FROM knowledge_relation")
                else:
                    cur.execute(
                        "SELECT source_id, relation_type, target_id FROM knowledge_relation "
                        "WHERE source_id = ANY(%s) AND target_id = ANY(%s)",
                        (allowed, allowed),
                    )
                for row in cur.fetchall():
                    mirror.add_relation(KnowledgeRelation(source_id=row[0], relation_type=row[1], target_id=row[2]))
            return mirror.expand(entity_names, max_hops=max_hops, allowed_entity_ids=scope)
        finally:
            mirror.close()

    def close(self) -> None:
        self._conn.close()

    def dump_payload(self) -> Dict[str, Any]:
        with self._conn.cursor() as cur:
            cur.execute("SELECT id, type, name, system, description FROM knowledge_entity ORDER BY id")
            entities = cur.fetchall()
            cur.execute(
                "SELECT source_id, relation_type, target_id FROM knowledge_relation "
                "ORDER BY source_id, relation_type, target_id"
            )
            relations = cur.fetchall()
        return {
            "entities": [
                {"id": r[0], "type": r[1], "name": r[2], "system": r[3], "description": r[4]}
                for r in entities
            ],
            "relations": [
                {"source_id": r[0], "relation_type": r[1], "target_id": r[2]} for r in relations
            ],
        }
