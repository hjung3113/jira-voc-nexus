"""SQLite-backed knowledge registry: exact entity/relation traversal.

Relation expansion is a deterministic, undirected BFS over the
``knowledge_relation`` table. It exists to answer "what does this system
component actually touch" precisely -- it is not a substitute for lexical or
vector relevance ranking.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Sequence, Tuple

try:
    from typing import Protocol
except ImportError:  # pragma: no cover
    Protocol = object  # type: ignore[assignment,misc]

from nexus.models import normalize_text

from .contracts import (
    KnowledgeEntity,
    KnowledgeRelation,
    RELATION_TYPES,
    parse_knowledge_entity,
    parse_knowledge_relation,
)
from .errors import RagInputError

_MAX_HOPS = 3

_SCHEMA = """
CREATE TABLE IF NOT EXISTS entities (
    id TEXT PRIMARY KEY,
    type TEXT NOT NULL,
    name TEXT NOT NULL,
    system TEXT NOT NULL,
    description TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS relations (
    source_id TEXT NOT NULL,
    relation_type TEXT NOT NULL,
    target_id TEXT NOT NULL,
    FOREIGN KEY (source_id) REFERENCES entities(id),
    FOREIGN KEY (target_id) REFERENCES entities(id),
    UNIQUE(source_id, relation_type, target_id)
);
"""


@dataclass(frozen=True)
class RegistryExpansion:
    entity_ids: Tuple[str, ...]
    paths: Tuple[Tuple[str, ...], ...]


class KnowledgeRegistry(Protocol):
    def expand(self, entity_names: Iterable[str], max_hops: int = 1) -> RegistryExpansion: ...


class SqliteKnowledgeRegistry:
    def __init__(self, path: str) -> None:
        self._conn = sqlite3.connect(path)
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    @classmethod
    def from_payload(
        cls,
        path: str,
        entities: Sequence[Any],
        relations: Sequence[Any],
    ) -> "SqliteKnowledgeRegistry":
        parsed_entities = [parse_knowledge_entity(item) for item in entities]
        seen_ids = set()
        for entity in parsed_entities:
            if entity.id in seen_ids:
                raise RagInputError(f"duplicate entity id: {entity.id}")
            seen_ids.add(entity.id)

        parsed_relations = [parse_knowledge_relation(item) for item in relations]
        for relation in parsed_relations:
            if relation.source_id not in seen_ids:
                raise RagInputError(f"relation references unknown entity: {relation.source_id}")
            if relation.target_id not in seen_ids:
                raise RagInputError(f"relation references unknown entity: {relation.target_id}")

        registry = cls(path)
        for entity in parsed_entities:
            registry.upsert_entity(entity)
        for relation in parsed_relations:
            registry.add_relation(relation)
        return registry

    def upsert_entity(self, entity: KnowledgeEntity) -> None:
        self._conn.execute(
            """
            INSERT INTO entities (id, type, name, system, description)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                type=excluded.type,
                name=excluded.name,
                system=excluded.system,
                description=excluded.description
            """,
            (entity.id, entity.type, entity.name, entity.system, entity.description),
        )
        self._conn.commit()

    def add_relation(self, relation: KnowledgeRelation) -> None:
        if relation.relation_type not in RELATION_TYPES:
            raise RagInputError(f"unsupported relation_type: {relation.relation_type}")
        for entity_id in (relation.source_id, relation.target_id):
            row = self._conn.execute("SELECT 1 FROM entities WHERE id = ?", (entity_id,)).fetchone()
            if row is None:
                raise RagInputError(f"relation references unknown entity: {entity_id}")
        try:
            self._conn.execute(
                "INSERT INTO relations (source_id, relation_type, target_id) VALUES (?, ?, ?)",
                (relation.source_id, relation.relation_type, relation.target_id),
            )
        except sqlite3.IntegrityError as exc:
            raise RagInputError(
                f"duplicate relation: {relation.source_id} {relation.relation_type} {relation.target_id}"
            ) from exc
        self._conn.commit()

    def neighbors(self, entity_id: str) -> List[KnowledgeRelation]:
        rows = self._conn.execute(
            """
            SELECT source_id, relation_type, target_id FROM relations
            WHERE source_id = ? OR target_id = ?
            ORDER BY relation_type, source_id, target_id
            """,
            (entity_id, entity_id),
        ).fetchall()
        return [KnowledgeRelation(source_id=r[0], relation_type=r[1], target_id=r[2]) for r in rows]

    def _entity_name(self, entity_id: str) -> str:
        row = self._conn.execute("SELECT name FROM entities WHERE id = ?", (entity_id,)).fetchone()
        return row[0] if row else entity_id

    def _resolve_seed_ids(self, entity_names: Iterable[str]) -> List[Tuple[str, str]]:
        resolved: List[Tuple[str, str]] = []
        seen = set()
        for raw_name in entity_names:
            name = normalize_text(raw_name) if isinstance(raw_name, str) else raw_name
            rows = self._conn.execute(
                "SELECT id, name FROM entities WHERE name = ? ORDER BY id", (name,)
            ).fetchall()
            for entity_id, entity_name in rows:
                if entity_id not in seen:
                    seen.add(entity_id)
                    resolved.append((entity_id, entity_name))
        return resolved

    def expand(self, entity_names: Iterable[str], max_hops: int = 1) -> RegistryExpansion:
        max_hops = max(0, min(int(max_hops), _MAX_HOPS))
        seeds = self._resolve_seed_ids(entity_names)

        hop_of: Dict[str, int] = {}
        path_of: Dict[str, Tuple[str, ...]] = {}
        for entity_id, name in sorted(seeds, key=lambda item: item[0]):
            if entity_id not in hop_of:
                hop_of[entity_id] = 0
                path_of[entity_id] = (name,)

        frontier = sorted(hop_of.keys())
        visited = set(frontier)

        for hop in range(1, max_hops + 1):
            discovered: Dict[str, Tuple[str, ...]] = {}
            for current in frontier:
                for relation in self.neighbors(current):
                    other = relation.target_id if relation.source_id == current else relation.source_id
                    if other in visited:
                        continue
                    step = path_of[current] + (relation.relation_type, self._entity_name(other))
                    if other not in discovered or step < discovered[other]:
                        discovered[other] = step
            if not discovered:
                break
            for entity_id in sorted(discovered):
                hop_of[entity_id] = hop
                path_of[entity_id] = discovered[entity_id]
                visited.add(entity_id)
            frontier = sorted(discovered.keys())

        ordered_ids = sorted(visited, key=lambda entity_id: (hop_of[entity_id], entity_id))
        paths = tuple(path_of[entity_id] for entity_id in ordered_ids)
        return RegistryExpansion(entity_ids=tuple(ordered_ids), paths=paths)

    def dump_payload(self) -> Dict[str, Any]:
        entities = self._conn.execute(
            "SELECT id, type, name, system, description FROM entities ORDER BY id"
        ).fetchall()
        relations = self._conn.execute(
            "SELECT source_id, relation_type, target_id FROM relations ORDER BY source_id, relation_type, target_id"
        ).fetchall()
        return {
            "entities": [
                {"id": r[0], "type": r[1], "name": r[2], "system": r[3], "description": r[4]}
                for r in entities
            ],
            "relations": [
                {"source_id": r[0], "relation_type": r[1], "target_id": r[2]} for r in relations
            ],
        }
