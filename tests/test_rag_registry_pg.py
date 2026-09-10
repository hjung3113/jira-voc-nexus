"""Conformance tests for the PostgreSQL registry adapter.

Skipped unless ``NEXUS_RAG_PG_TEST_DATASOURCE`` points at a reachable
Postgres connection string -- see ``rag/registry_pg.py``'s module docstring.
The lazy-import error path (missing ``psycopg``) is exercised unconditionally
since it needs no database.
"""

from __future__ import annotations

import os
import sys
import unittest
from unittest import mock

from rag.errors import RagInputError

DATASOURCE = os.environ.get("NEXUS_RAG_PG_TEST_DATASOURCE", "")


class MissingPsycopgExtraTests(unittest.TestCase):
    def test_missing_extra_raises_clear_error(self):
        with mock.patch.dict(sys.modules, {"psycopg": None}):
            from rag.registry_pg import PostgresKnowledgeRegistry

            with self.assertRaises(RagInputError) as ctx:
                PostgresKnowledgeRegistry(datasource="postgresql://example/db")
        self.assertIn("rag-pg", str(ctx.exception))
        self.assertIn("pip install", str(ctx.exception))


def _fake_connected_registry():
    """Build a PostgresKnowledgeRegistry over a mocked psycopg connection so
    its lifecycle/adapter-shape behavior (close(), the expand() mirror) can
    be exercised without a real Postgres server. Returns (registry, fake_conn)."""

    fake_cursor = mock.MagicMock()
    fake_cursor.fetchall.return_value = []
    fake_conn = mock.MagicMock()
    fake_conn.cursor.return_value.__enter__.return_value = fake_cursor
    fake_psycopg = mock.MagicMock()
    fake_psycopg.connect.return_value = fake_conn

    with mock.patch.dict(sys.modules, {"psycopg": fake_psycopg}):
        from rag.registry_pg import PostgresKnowledgeRegistry

        registry = PostgresKnowledgeRegistry(datasource="postgresql://example/db")
    return registry, fake_conn


class LifecycleAndMirrorLeakTests(unittest.TestCase):
    def test_close_closes_the_underlying_connection(self):
        registry, fake_conn = _fake_connected_registry()
        registry.close()
        fake_conn.close.assert_called_once()

    def test_expand_closes_its_in_memory_mirror_after_use(self):
        # expand() builds a fresh in-memory SqliteKnowledgeRegistry mirror on
        # every call; that mirror connection must be closed once the BFS
        # result is computed instead of being leaked on every retrieval.
        registry, _fake_conn = _fake_connected_registry()
        with mock.patch("rag.registry_pg.SqliteKnowledgeRegistry") as MockMirror:
            mirror_instance = MockMirror.return_value
            mirror_instance.expand.return_value = "sentinel-expansion"

            result = registry.expand(["ParserJob"], max_hops=1)

            mirror_instance.close.assert_called_once()
            self.assertEqual(result, "sentinel-expansion")

    def test_expand_closes_its_mirror_even_when_the_bfs_raises(self):
        registry, _fake_conn = _fake_connected_registry()
        with mock.patch("rag.registry_pg.SqliteKnowledgeRegistry") as MockMirror:
            mirror_instance = MockMirror.return_value
            mirror_instance.expand.side_effect = RagInputError("boom")

            with self.assertRaises(RagInputError):
                registry.expand(["ParserJob"], max_hops=1)

            mirror_instance.close.assert_called_once()


@unittest.skipUnless(DATASOURCE, "set NEXUS_RAG_PG_TEST_DATASOURCE to run PG registry conformance tests")
class PostgresRegistryConformanceTests(unittest.TestCase):
    def setUp(self):
        from rag.contracts import KnowledgeEntity, KnowledgeRelation
        from rag.registry_pg import PostgresKnowledgeRegistry

        self.KnowledgeEntity = KnowledgeEntity
        self.KnowledgeRelation = KnowledgeRelation
        self.registry = PostgresKnowledgeRegistry(datasource=DATASOURCE)
        self.addCleanup(self._drop_tables)

    def _drop_tables(self):
        with self.registry._conn.cursor() as cur:
            cur.execute("DROP TABLE IF EXISTS knowledge_relation")
            cur.execute("DROP TABLE IF EXISTS knowledge_entity")
        self.registry._conn.commit()

    def test_expand_matches_sqlite_hand_computed_expectation(self):
        entities = [
            self.KnowledgeEntity(id="job:parser", type="job", name="ParserJob", system="LogWarehouse", description=""),
            self.KnowledgeEntity(id="component:parser", type="component", name="Parser", system="LogWarehouse", description=""),
            self.KnowledgeEntity(id="sp:insert_raw", type="stored_procedure", name="SP_INSERT_RAW", system="LogWarehouse", description=""),
        ]
        for entity in entities:
            self.registry.upsert_entity(entity)
        self.registry.add_relation(self.KnowledgeRelation(source_id="job:parser", relation_type="USES", target_id="component:parser"))
        self.registry.add_relation(self.KnowledgeRelation(source_id="job:parser", relation_type="EXECUTES", target_id="sp:insert_raw"))

        expansion = self.registry.expand(["ParserJob"], max_hops=1)
        self.assertEqual(expansion.entity_ids, ("job:parser", "component:parser", "sp:insert_raw"))
        self.assertEqual(
            expansion.paths,
            (
                ("ParserJob",),
                ("ParserJob", "USES", "Parser"),
                ("ParserJob", "EXECUTES", "SP_INSERT_RAW"),
            ),
        )

    def test_neighbors_reflects_written_relations(self):
        entities = [
            self.KnowledgeEntity(id="a", type="component", name="A", system="S", description=""),
            self.KnowledgeEntity(id="b", type="component", name="B", system="S", description=""),
        ]
        for entity in entities:
            self.registry.upsert_entity(entity)
        self.registry.add_relation(self.KnowledgeRelation(source_id="a", relation_type="USES", target_id="b"))
        neighbors = self.registry.neighbors("a")
        self.assertEqual(len(neighbors), 1)
        self.assertEqual(neighbors[0].relation_type, "USES")

    def test_duplicate_relation_rejected(self):
        entities = [
            self.KnowledgeEntity(id="a", type="component", name="A", system="S", description=""),
            self.KnowledgeEntity(id="b", type="component", name="B", system="S", description=""),
        ]
        for entity in entities:
            self.registry.upsert_entity(entity)
        self.registry.add_relation(self.KnowledgeRelation(source_id="a", relation_type="USES", target_id="b"))
        with self.assertRaises(RagInputError):
            self.registry.add_relation(self.KnowledgeRelation(source_id="a", relation_type="USES", target_id="b"))


if __name__ == "__main__":
    unittest.main()
