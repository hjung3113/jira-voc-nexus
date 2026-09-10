from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from rag.context import ContextBuilder, ContextConfig
from rag.contracts import IndexDocument
from rag.errors import RagInputError
from rag.registry import RegistryExpansion
from rag.retrieval import RetrievalQuery, RetrievalResult, ScoredDoc

ROOT = Path(__file__).resolve().parents[1]


def _doc(doc_id, title, text, document_type, source_id=None):
    return IndexDocument(
        doc_id=doc_id,
        source_type="jira" if document_type.startswith("jira") else "wiki",
        document_type=document_type,
        system="LogWarehouse",
        component="Parser",
        entity_ids=(),
        trust_level="supporting" if document_type.startswith("jira") else "canonical",
        source_id=source_id if source_id is not None else doc_id,
        updated_at="",
        title=title,
        text=text,
    )


def _sd(doc):
    return ScoredDoc(doc_id=doc.doc_id, score=1.0, doc=doc, reasons=())


class SectionOrderTests(unittest.TestCase):
    def test_draft_wiki_is_not_presented_as_canonical_or_budgeted_first(self):
        canonical = _doc("wiki:c", "Approved", "definition", "domain_knowledge")
        draft = replace(canonical, doc_id="wiki:d", title="Draft", text="speculation", trust_level="supporting")
        result = RetrievalResult(fused=(), final=(_sd(draft), _sd(canonical)), expansion=None, acl_filtered_count=0)
        built = ContextBuilder().build(RetrievalQuery(text="q"), result)
        self.assertEqual([s.heading for s in built.sections], ["Canonical Domain", "Supporting Knowledge"])
        self.assertEqual(built.sections[0].source, "wiki:c")
        budget = len("Canonical Domain\nApproved\ndefinition")
        limited = ContextBuilder(ContextConfig(max_chars=budget)).build(RetrievalQuery(text="q"), result)
        self.assertEqual([s.source for s in limited.sections], ["wiki:c"])
        self.assertNotIn("speculation", limited.text)

    def test_section_order_is_domain_system_relationship_jira(self):
        domain = _doc("wiki:domain-1", "Domain title", "domain text", "domain_knowledge")
        system = _doc("wiki:system-1", "System title", "system text", "system_knowledge")
        problem = _doc("OPS-201:problem", "Problem title", "problem text", "jira_problem", source_id="OPS-201")
        resolution = _doc("OPS-201:resolution", "Resolution title", "resolution text", "jira_resolution", source_id="OPS-201")

        # Deliberately out-of-order input to prove the builder re-buckets by
        # category rather than trusting caller order.
        final = (_sd(resolution), _sd(problem), _sd(system), _sd(domain))
        result = RetrievalResult(fused=(), final=final, expansion=None, acl_filtered_count=0)
        expansion = RegistryExpansion(entity_ids=("job:parser", "component:parser"), paths=(("ParserJob",), ("ParserJob", "USES", "Parser")))

        built = ContextBuilder().build(RetrievalQuery(text="q"), result, registry_expansion=expansion)

        headings = [section.heading for section in built.sections]
        self.assertEqual(
            headings,
            ["Canonical Domain", "System", "Relationship Evidence", "Historical Jira OPS-201"],
        )

    def test_relationship_evidence_skips_seed_only_paths(self):
        # A path of length 1 (just the seed, no edges) carries no relation
        # evidence and must not produce an empty/degenerate line.
        expansion = RegistryExpansion(entity_ids=("job:parser",), paths=(("ParserJob",),))
        result = RetrievalResult(fused=(), final=(), expansion=None, acl_filtered_count=0)
        built = ContextBuilder().build(RetrievalQuery(text="q"), result, registry_expansion=expansion)
        self.assertEqual(built.sections, ())

    def test_registry_path_rendering(self):
        expansion = RegistryExpansion(
            entity_ids=("job:parser", "component:parser", "sp:insert_raw"),
            paths=(("ParserJob",), ("ParserJob", "USES", "Parser"), ("ParserJob", "EXECUTES", "SP_INSERT_RAW")),
        )
        result = RetrievalResult(fused=(), final=(), expansion=None, acl_filtered_count=0)
        built = ContextBuilder().build(RetrievalQuery(text="q"), result, registry_expansion=expansion)
        self.assertEqual(len(built.sections), 1)
        section = built.sections[0]
        self.assertEqual(section.heading, "Relationship Evidence")
        self.assertEqual(section.source, "registry")
        self.assertEqual(
            section.lines,
            ("ParserJob -> USES -> Parser", "ParserJob -> EXECUTES -> SP_INSERT_RAW"),
        )

    def test_result_expansion_used_when_explicit_expansion_omitted(self):
        expansion = RegistryExpansion(entity_ids=("a", "b"), paths=(("A",), ("A", "USES", "B")))
        result = RetrievalResult(fused=(), final=(), expansion=expansion, acl_filtered_count=0)
        built = ContextBuilder().build(RetrievalQuery(text="q"), result)
        self.assertEqual(len(built.sections), 1)
        self.assertEqual(built.sections[0].heading, "Relationship Evidence")

    def test_historical_jira_groups_problem_then_resolution_per_issue(self):
        problem = _doc("OPS-201:problem", "Problem title", "problem body", "jira_problem", source_id="OPS-201")
        resolution_docs = [_doc("OPS-201:resolution", "Resolution title", "resolution body", "jira_resolution", source_id="OPS-201")]
        result = RetrievalResult(fused=(), final=(_sd(problem),), expansion=None, acl_filtered_count=0)
        built = ContextBuilder().build(RetrievalQuery(text="q"), result, resolution_docs=resolution_docs)
        self.assertEqual(len(built.sections), 1)
        section = built.sections[0]
        self.assertEqual(section.heading, "Historical Jira OPS-201")
        self.assertEqual(section.source, "OPS-201:problem")
        self.assertEqual(
            section.lines,
            ("Problem: Problem title", "problem body", "Resolution: Resolution title", "resolution body"),
        )


class BudgetTests(unittest.TestCase):
    def test_budget_enforcement_and_omitted_list(self):
        small_doc = _doc("wiki:d1", "Domain", "x" * 10, "domain_knowledge")
        big_doc = _doc("wiki:d2", "System", "y" * 1000, "system_knowledge")
        result = RetrievalResult(fused=(), final=(_sd(small_doc), _sd(big_doc)), expansion=None, acl_filtered_count=0)

        # Budget fits the small "Canonical Domain" section but not the big
        # "System" section.
        config = ContextConfig(max_chars=40)
        built = ContextBuilder(config).build(RetrievalQuery(text="q"), result)

        self.assertEqual([s.heading for s in built.sections], ["Canonical Domain"])
        self.assertEqual(built.omitted_sections, ("System",))
        self.assertLessEqual(len(built.text), 40)
        self.assertNotIn("Omitted:", built.text)

    def test_no_mid_line_truncation(self):
        # A section that alone exceeds the budget is entirely omitted, never
        # partially included with a cut line.
        big_doc = _doc("wiki:d1", "Domain", "z" * 500, "domain_knowledge")
        result = RetrievalResult(fused=(), final=(_sd(big_doc),), expansion=None, acl_filtered_count=0)
        built = ContextBuilder(ContextConfig(max_chars=10)).build(RetrievalQuery(text="q"), result)
        self.assertEqual(built.sections, ())
        self.assertEqual(built.omitted_sections, ("Canonical Domain",))
        self.assertEqual(built.text, "")
        self.assertNotIn("z", built.text)  # the oversized section's content never leaks in partially

    def test_zero_budget_and_invalid_budgets(self):
        doc = _doc("a", "Domain", "body", "domain_knowledge")
        result = RetrievalResult(fused=(), final=(_sd(doc),), expansion=None, acl_filtered_count=0)
        built = ContextBuilder(ContextConfig(max_chars=0)).build(RetrievalQuery(text="q"), result)
        self.assertEqual(built.text, "")
        self.assertEqual(built.omitted_sections, ("Canonical Domain",))
        for value in (-1, True, 2.5, "10"):
            with self.subTest(value=value), self.assertRaises(RagInputError):
                ContextConfig(max_chars=value)

    def test_omission_notice_included_only_when_it_fits(self):
        doc = _doc("a", "Domain", "x" * 500, "domain_knowledge")
        result = RetrievalResult(fused=(), final=(_sd(doc),), expansion=None, acl_filtered_count=0)
        built = ContextBuilder(ContextConfig(max_chars=40)).build(RetrievalQuery(text="q"), result)
        self.assertEqual(built.text, "Omitted: Canonical Domain")
        self.assertLessEqual(len(built.text), 40)

    def test_duplicate_hits_do_not_consume_budget_twice(self):
        doc = _doc("a", "Domain", "body", "domain_knowledge")
        result = RetrievalResult(fused=(), final=(_sd(doc), _sd(doc)), expansion=None, acl_filtered_count=0)
        built = ContextBuilder().build(RetrievalQuery(text="q"), result)
        self.assertEqual(len(built.sections), 1)

    def test_orphan_resolution_cannot_enter_selected_problem_context(self):
        problem = _doc("A:problem", "Problem", "body", "jira_problem", "A")
        orphan = _doc("B:resolution", "Resolution", "unselected evidence", "jira_resolution", "B")
        result = RetrievalResult(fused=(), final=(_sd(problem), _sd(orphan)), expansion=None, acl_filtered_count=0)
        built = ContextBuilder().build(RetrievalQuery(text="q"), result, resolution_docs=(orphan,))
        self.assertEqual([s.heading for s in built.sections], ["Historical Jira A"])
        self.assertNotIn("unselected evidence", built.text)

    def test_everything_fits_yields_no_omissions(self):
        small_doc = _doc("wiki:d1", "Domain", "short text", "domain_knowledge")
        result = RetrievalResult(fused=(), final=(_sd(small_doc),), expansion=None, acl_filtered_count=0)
        built = ContextBuilder(ContextConfig(max_chars=8_000)).build(RetrievalQuery(text="q"), result)
        self.assertEqual(built.omitted_sections, ())
        self.assertNotIn("Omitted:", built.text)


class QueryCliContextTests(unittest.TestCase):
    def setUp(self):
        self._tmp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp_dir.cleanup)
        self.state_path = str(Path(self._tmp_dir.name) / "state.json")
        index_proc = subprocess.run(
            [sys.executable, "-m", "rag", "index", "--fixtures-dir", "fixtures/rag", "--state", self.state_path],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
        )
        self.assertEqual(index_proc.returncode, 0, index_proc.stderr)

    def test_query_cli_prints_context_with_error_code_issue_and_resolution(self):
        proc = subprocess.run(
            [
                sys.executable, "-m", "rag", "query",
                "--state", self.state_path,
                "--text", "4107 오류",
                "--error-code", "4107",
            ],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("Historical Jira", proc.stdout)
        self.assertIn("OPS-201", proc.stdout)
        self.assertIn("4107", proc.stdout)
        self.assertIn("Resolution:", proc.stdout)

    def test_query_cli_json_output_is_valid(self):
        import json

        proc = subprocess.run(
            [sys.executable, "-m", "rag", "query", "--state", self.state_path, "--text", "parser 4107", "--json"],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertIn("context", payload)
        self.assertIn("text", payload["context"])

    def test_query_still_works_and_expands_after_sidecar_registry_deleted(self):
        import json

        with open(self.state_path, encoding="utf-8") as stream:
            state = json.load(stream)
        sidecar_path = Path(state["registry_db_path"])
        self.assertTrue(sidecar_path.exists(), "setUp should have written the sidecar registry db")
        sidecar_path.unlink()
        self.assertFalse(sidecar_path.exists())

        # The CLI still works end to end with only state.json present.
        proc = subprocess.run(
            [sys.executable, "-m", "rag", "query", "--state", self.state_path, "--text", "4107 오류", "--error-code", "4107"],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("Historical Jira", proc.stdout)

        # And relation expansion specifically still works, rebuilt purely
        # from the embedded "registry" payload in state.json (proves this
        # is not silently degrading to registry=None).
        from rag.__main__ import _build_pipeline, _load_state

        documents, registry_payload = _load_state(self.state_path)
        with tempfile.TemporaryDirectory() as rebuild_dir:
            pipeline = _build_pipeline(documents, registry_payload, str(Path(rebuild_dir) / "registry.db"))
            self.assertIsNotNone(pipeline._registry)
            expansion = pipeline._registry.expand(["ParserJob"], max_hops=1)
            self.assertIn("job:parser", expansion.entity_ids)
            self.assertIn("sp:insert_raw", expansion.entity_ids)


class CorruptInputCliTests(unittest.TestCase):
    def test_query_on_corrupt_state_json_exits_nonzero_with_no_traceback(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = Path(tmp_dir) / "state.json"
            state_path.write_text("{not valid json", encoding="utf-8")
            proc = subprocess.run(
                [sys.executable, "-m", "rag", "query", "--state", str(state_path), "--text", "q"],
                cwd=str(ROOT),
                capture_output=True,
                text=True,
            )
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("error:", proc.stderr.lower())
        self.assertNotIn("Traceback", proc.stderr)

    def test_index_on_corrupt_fixture_json_exits_nonzero_with_no_traceback(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            fixtures_dir = Path(tmp_dir) / "fixtures"
            fixtures_dir.mkdir()
            for name in ("normalized_issues.json", "wiki_pages.json", "registry.json"):
                (fixtures_dir / name).write_text("[]", encoding="utf-8")
            (fixtures_dir / "normalized_issues.json").write_text("{not valid json", encoding="utf-8")
            state_path = Path(tmp_dir) / "state.json"
            proc = subprocess.run(
                [sys.executable, "-m", "rag", "index", "--fixtures-dir", str(fixtures_dir), "--state", str(state_path)],
                cwd=str(ROOT),
                capture_output=True,
                text=True,
            )
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("error:", proc.stderr.lower())
        self.assertNotIn("Traceback", proc.stderr)

    def test_index_on_fixture_missing_registry_keys_exits_nonzero_with_no_traceback(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            fixtures_dir = Path(tmp_dir) / "fixtures"
            fixtures_dir.mkdir()
            (fixtures_dir / "normalized_issues.json").write_text("[]", encoding="utf-8")
            (fixtures_dir / "wiki_pages.json").write_text("[]", encoding="utf-8")
            # Missing "entities"/"relations" keys -> KeyError inside the handler.
            (fixtures_dir / "registry.json").write_text("{}", encoding="utf-8")
            state_path = Path(tmp_dir) / "state.json"
            proc = subprocess.run(
                [sys.executable, "-m", "rag", "index", "--fixtures-dir", str(fixtures_dir), "--state", str(state_path)],
                cwd=str(ROOT),
                capture_output=True,
                text=True,
            )
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("error:", proc.stderr.lower())
        self.assertNotIn("Traceback", proc.stderr)


if __name__ == "__main__":
    unittest.main()
