"""Local CLI persistence and malformed-input regressions."""

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from rag.__main__ import main


ROOT = Path(__file__).resolve().parents[1]


class ReindexTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.directory = Path(self.tmp.name)
        self.fixtures = self.directory / "fixtures"
        shutil.copytree(ROOT / "fixtures/rag", self.fixtures)
        self.state = self.directory / "state.json"
        self.args = ["index", "--fixtures-dir", str(self.fixtures), "--state", str(self.state)]
        self.assertEqual(main(self.args), 0)
        self.sidecar = self.directory / "state.registry.db"

    def test_invalid_registry_reindex_preserves_previous_files(self):
        previous = (self.state.read_bytes(), self.sidecar.read_bytes())
        registry_path = self.fixtures / "registry.json"
        payload = json.loads(registry_path.read_text())
        payload["entities"].append(payload["entities"][0])
        registry_path.write_text(json.dumps(payload))
        self.assertEqual(main(self.args), 1)
        self.assertEqual((self.state.read_bytes(), self.sidecar.read_bytes()), previous)
        self.assertEqual(list(self.directory.glob(".rag-index-*")), [])

    def test_interrupted_state_replace_keeps_authoritative_json_usable(self):
        previous = self.state.read_bytes()
        import os

        replace = os.replace

        def fail_state(source, destination):
            if str(destination) == str(self.state):
                raise OSError("simulated publication failure")
            return replace(source, destination)

        with patch("rag.__main__.os.replace", side_effect=fail_state):
            self.assertEqual(main(self.args), 1)
        self.assertEqual(self.state.read_bytes(), previous)
        self.assertEqual(main(["query", "--state", str(self.state), "--text", "4107"]), 0)

    def test_duplicate_issue_ids_rejected_before_state_replacement(self):
        previous = self.state.read_bytes()
        issues_path = self.fixtures / "normalized_issues.json"
        issues = json.loads(issues_path.read_text())
        issues.append(issues[0])
        issues_path.write_text(json.dumps(issues))
        self.assertEqual(main(self.args), 1)
        self.assertEqual(self.state.read_bytes(), previous)

    def test_query_closes_owned_temp_registry_once(self):
        closed = []

        from rag.registry import SqliteKnowledgeRegistry

        original_close = SqliteKnowledgeRegistry.close

        def record_close(registry):
            closed.append(registry)
            return original_close(registry)

        with patch("rag.__main__.SqliteKnowledgeRegistry.close", record_close):
            self.assertEqual(main(["query", "--state", str(self.state), "--text", "4107"]), 0)
        self.assertEqual(len(closed), 1)


class MalformedStateTests(unittest.TestCase):
    def test_invalid_container_shapes_fail_without_traceback(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp) / "state.json"
            for payload in (
                {"documents": None, "registry": {"entities": [], "relations": []}},
                {"documents": [], "registry": {"entities": None, "relations": []}},
                {"documents": {}, "registry": []},
            ):
                state.write_text(json.dumps(payload))
                result = subprocess.run(
                    [sys.executable, "-m", "rag", "query", "--state", str(state), "--text", "q"],
                    cwd=str(ROOT), text=True, capture_output=True,
                )
                with self.subTest(payload=payload):
                    self.assertEqual(result.returncode, 1)
                    self.assertIn("error:", result.stderr)
                    self.assertNotIn("Traceback", result.stderr)


if __name__ == "__main__":
    unittest.main()
