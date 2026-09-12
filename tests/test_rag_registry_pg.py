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
import uuid
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
        self._schema_name = f"nexus_rag_test_{uuid.uuid4().hex}"
        self._control_conn = None
        self.registry = None

        try:
            import psycopg
            from psycopg import sql
            from rag.contracts import KnowledgeEntity, KnowledgeRelation
            from rag.registry_pg import PostgresKnowledgeRegistry

            self.KnowledgeEntity = KnowledgeEntity
            self.KnowledgeRelation = KnowledgeRelation

            self._control_conn = psycopg.connect(DATASOURCE)
            with self._control_conn.cursor() as cur:
                cur.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(self._schema_name)))
            self._control_conn.commit()

            # The adapter creates its DDL during construction, so the schema
            # must be selected as a connection option rather than afterward.
            # Keep this search_path restricted to the owned schema: in
            # particular, do not add PostgreSQL's public fallback.
            quoted_schema = sql.Identifier(self._schema_name).as_string(self._control_conn)
            self.registry = PostgresKnowledgeRegistry(
                datasource=DATASOURCE,
                options=f"-c search_path={quoted_schema}",
            )
            self.addCleanup(self._cleanup_pg)
        except BaseException:
            # Clean up resources acquired before setup failed.
            self._cleanup_pg()
            raise

    def _cleanup_pg(self):
        registry = self.registry
        control_conn = self._control_conn
        schema_name = self._schema_name
        self.registry = None
        self._control_conn = None

        close_error = None
        if registry is not None:
            try:
                registry.close()
            except BaseException as exc:  # preserve cleanup of the schema/connection
                close_error = exc

        try:
            if control_conn is not None:
                from psycopg import sql

                # A failed setup or a final SELECT can leave the control
                # connection in a transaction; clear it before DROP SCHEMA.
                control_conn.rollback()
                with control_conn.cursor() as cur:
                    cur.execute(
                        sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(sql.Identifier(schema_name))
                    )
                control_conn.commit()
        finally:
            if control_conn is not None:
                control_conn.close()

        if close_error is not None:
            raise close_error

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

    def test_rejected_relations_leave_registry_usable_for_valid_write_and_read(self):
        entities = [
            self.KnowledgeEntity(id="a", type="component", name="A", system="S", description=""),
            self.KnowledgeEntity(id="b", type="component", name="B", system="S", description=""),
            self.KnowledgeEntity(id="c", type="component", name="C", system="S", description=""),
        ]
        for entity in entities:
            self.registry.upsert_entity(entity)
        self.registry.add_relation(self.KnowledgeRelation(source_id="a", relation_type="USES", target_id="b"))
        with self.assertRaises(RagInputError):
            self.registry.add_relation(self.KnowledgeRelation(source_id="a", relation_type="USES", target_id="b"))
        with self.assertRaises(RagInputError):
            self.registry.add_relation(self.KnowledgeRelation(source_id="b", relation_type="USES", target_id="missing"))

        self.registry.add_relation(self.KnowledgeRelation(source_id="b", relation_type="USES", target_id="c"))
        self.assertEqual(
            self.registry.neighbors("b"),
            [
                self.KnowledgeRelation(source_id="a", relation_type="USES", target_id="b"),
                self.KnowledgeRelation(source_id="b", relation_type="USES", target_id="c"),
            ],
        )

    def test_allowed_entity_ids_exclude_hidden_bridge_from_neighbors_and_expand(self):
        entities = [
            self.KnowledgeEntity(id="source", type="component", name="Source", system="S", description=""),
            self.KnowledgeEntity(id="bridge", type="component", name="HiddenBridge", system="S", description=""),
            self.KnowledgeEntity(id="target", type="component", name="Target", system="S", description=""),
            self.KnowledgeEntity(id="direct", type="component", name="Direct", system="S", description=""),
        ]
        for entity in entities:
            self.registry.upsert_entity(entity)
        self.registry.add_relation(
            self.KnowledgeRelation(source_id="source", relation_type="USES", target_id="bridge")
        )
        self.registry.add_relation(
            self.KnowledgeRelation(source_id="bridge", relation_type="USES", target_id="target")
        )
        self.registry.add_relation(
            self.KnowledgeRelation(source_id="source", relation_type="USES", target_id="direct")
        )

        allowed = {"source", "target", "direct"}
        self.assertEqual(
            self.registry.neighbors("source", allowed_entity_ids=allowed),
            [self.KnowledgeRelation(source_id="source", relation_type="USES", target_id="direct")],
        )
        expansion = self.registry.expand(["Source"], max_hops=2, allowed_entity_ids=allowed)
        self.assertEqual(expansion.entity_ids, ("source", "direct"))
        self.assertNotIn("target", expansion.entity_ids)


if __name__ == "__main__":
    unittest.main()
