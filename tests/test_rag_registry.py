from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from rag.contracts import KnowledgeEntity, KnowledgeRelation
from rag.errors import RagInputError
from rag.registry import SqliteKnowledgeRegistry

ROOT = Path(__file__).resolve().parents[1]


def load_registry_fixture():
    with (ROOT / "fixtures" / "rag" / "registry.json").open(encoding="utf-8") as stream:
        return json.load(stream)


def _new_db_path(test_case):
    tmp_dir = tempfile.TemporaryDirectory()
    test_case.addCleanup(tmp_dir.cleanup)
    return str(Path(tmp_dir.name) / "registry.db")


class RegistryFromPayloadTests(unittest.TestCase):
    def _path(self):
        return _new_db_path(self)

    def test_fixture_registry_loads(self):
        data = load_registry_fixture()
        registry = SqliteKnowledgeRegistry.from_payload(self._path(), data["entities"], data["relations"])
        dumped = registry.dump_payload()
        self.assertEqual(len(dumped["entities"]), len(data["entities"]))
        self.assertEqual(len(dumped["relations"]), len(data["relations"]))

    def test_duplicate_entity_id_rejected(self):
        entities = [
            {"id": "a", "type": "component", "name": "A", "system": "S", "description": ""},
            {"id": "a", "type": "component", "name": "A2", "system": "S", "description": ""},
        ]
        with self.assertRaises(RagInputError):
            SqliteKnowledgeRegistry.from_payload(self._path(), entities, [])

    def test_relation_with_unknown_entity_rejected(self):
        entities = [{"id": "a", "type": "component", "name": "A", "system": "S", "description": ""}]
        relations = [{"source_id": "a", "relation_type": "USES", "target_id": "missing"}]
        with self.assertRaises(RagInputError):
            SqliteKnowledgeRegistry.from_payload(self._path(), entities, relations)

    def test_dump_roundtrip(self):
        data = load_registry_fixture()
        first = SqliteKnowledgeRegistry.from_payload(self._path(), data["entities"], data["relations"])
        dumped = first.dump_payload()
        second = SqliteKnowledgeRegistry.from_payload(self._path(), dumped["entities"], dumped["relations"])
        self.assertEqual(second.dump_payload(), dumped)


class RegistryMutationTests(unittest.TestCase):
    def test_add_relation_rejects_unsupported_type(self):
        registry = SqliteKnowledgeRegistry(_new_db_path(self))
        registry.upsert_entity(KnowledgeEntity(id="a", type="component", name="A", system="S", description=""))
        registry.upsert_entity(KnowledgeEntity(id="b", type="component", name="B", system="S", description=""))
        with self.assertRaises(RagInputError):
            registry.add_relation(KnowledgeRelation(source_id="a", relation_type="DELETES", target_id="b"))

    def test_add_relation_rejects_unknown_endpoint(self):
        registry = SqliteKnowledgeRegistry(_new_db_path(self))
        registry.upsert_entity(KnowledgeEntity(id="a", type="component", name="A", system="S", description=""))
        with self.assertRaises(RagInputError):
            registry.add_relation(KnowledgeRelation(source_id="a", relation_type="USES", target_id="missing"))

    def test_neighbors_allowlist_enforced_at_write_time(self):
        registry = SqliteKnowledgeRegistry(_new_db_path(self))
        registry.upsert_entity(KnowledgeEntity(id="a", type="component", name="A", system="S", description=""))
        registry.upsert_entity(KnowledgeEntity(id="b", type="component", name="B", system="S", description=""))
        registry.add_relation(KnowledgeRelation(source_id="a", relation_type="USES", target_id="b"))
        neighbors = registry.neighbors("a")
        self.assertEqual(len(neighbors), 1)
        self.assertEqual(neighbors[0].relation_type, "USES")


class RegistryExpandTests(unittest.TestCase):
    def setUp(self):
        data = load_registry_fixture()
        self.registry = SqliteKnowledgeRegistry.from_payload(
            _new_db_path(self), data["entities"], data["relations"]
        )

    def test_expand_hop1_matches_hand_computed_expectation(self):
        expansion = self.registry.expand(["ParserJob"], max_hops=1)
        self.assertEqual(
            expansion.entity_ids, ("job:parser", "component:parser", "sp:insert_raw")
        )
        self.assertEqual(
            expansion.paths,
            (
                ("ParserJob",),
                ("ParserJob", "USES", "Parser"),
                ("ParserJob", "EXECUTES", "SP_INSERT_RAW"),
            ),
        )

    def test_expand_hop2_matches_hand_computed_expectation(self):
        expansion = self.registry.expand(["ParserJob"], max_hops=2)
        self.assertEqual(
            expansion.entity_ids,
            ("job:parser", "component:parser", "sp:insert_raw", "component:reconnect", "table:raw_data"),
        )
        self.assertEqual(
            expansion.paths,
            (
                ("ParserJob",),
                ("ParserJob", "USES", "Parser"),
                ("ParserJob", "EXECUTES", "SP_INSERT_RAW"),
                ("ParserJob", "USES", "Parser", "USES", "Reconnect"),
                ("ParserJob", "EXECUTES", "SP_INSERT_RAW", "WRITES", "RAW_DATA"),
            ),
        )

    def test_expand_unresolved_name_yields_empty_expansion(self):
        expansion = self.registry.expand(["NoSuchEntity"], max_hops=2)
        self.assertEqual(expansion.entity_ids, ())
        self.assertEqual(expansion.paths, ())

    def test_expand_caps_max_hops_at_three(self):
        expansion_capped = self.registry.expand(["ParserJob"], max_hops=99)
        expansion_three = self.registry.expand(["ParserJob"], max_hops=3)
        self.assertEqual(expansion_capped, expansion_three)


class RegistryCycleSafetyTests(unittest.TestCase):
    def test_cycle_a_b_a_terminates_and_is_deterministic(self):
        entities = [
            {"id": "a", "type": "component", "name": "A", "system": "S", "description": ""},
            {"id": "b", "type": "component", "name": "B", "system": "S", "description": ""},
        ]
        relations = [
            {"source_id": "a", "relation_type": "CALLS", "target_id": "b"},
            {"source_id": "b", "relation_type": "CALLS", "target_id": "a"},
        ]
        registry = SqliteKnowledgeRegistry.from_payload(_new_db_path(self), entities, relations)
        expansion = registry.expand(["A"], max_hops=3)
        self.assertEqual(expansion.entity_ids, ("a", "b"))
        self.assertEqual(expansion.paths, (("A",), ("A", "CALLS", "B")))


if __name__ == "__main__":
    unittest.main()
