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
