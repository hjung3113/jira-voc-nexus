from __future__ import annotations

import json
import math
import subprocess
import sys
import tempfile
import unittest
from dataclasses import replace
from types import SimpleNamespace
from pathlib import Path

from rag.contracts import IndexDocument
from rag.errors import RagInputError
from rag.registry import SqliteKnowledgeRegistry
from rag.eval import (
    GoldenEntry,
    PipelineVariant,
    default_local_variants,
    load_golden_set,
    mrr_at_k,
    ndcg_at_k,
    recall_at_k,
    render_markdown_table,
    run_evaluation,
)
from rag.retrieval import RetrievalQuery

ROOT = Path(__file__).resolve().parents[1]


def _write_json(test_case, payload):
    tmp_dir = tempfile.TemporaryDirectory()
    test_case.addCleanup(tmp_dir.cleanup)
    path = Path(tmp_dir.name) / "data.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return str(path)


VALID_QUERY_PAYLOAD = {
    "text": "parser error 4107",
    "project": "",
    "component": "",
    "error_codes": ["4107"],
    "entities": [],
    "document_types": ["jira_problem"],
}


class MetricTests(unittest.TestCase):
    def test_recall_at_k_hand_computed(self):
        results = ["a", "b", "c", "d", "e"]
        relevant = ["c", "z"]
        # top-5 hits {c}; |relevant|=2 -> 1/2
        self.assertAlmostEqual(recall_at_k(results, relevant, 5), 0.5)

    def test_recall_at_k_truncates_to_k(self):
        results = ["a", "b", "c"]
        relevant = ["c"]
        self.assertEqual(recall_at_k(results, relevant, 2), 0.0)
        self.assertEqual(recall_at_k(results, relevant, 3), 1.0)

    def test_recall_at_k_empty_relevant_is_zero(self):
        self.assertEqual(recall_at_k(["a"], [], 5), 0.0)

    def test_recall_at_k_empty_results_is_zero(self):
        self.assertEqual(recall_at_k([], ["a"], 5), 0.0)

    def test_mrr_at_k_hand_computed(self):
        # first relevant doc at rank 3 -> 1/3
        results = ["a", "b", "c", "d"]
        relevant = ["c", "d"]
        self.assertAlmostEqual(mrr_at_k(results, relevant, k=10), 1 / 3)

    def test_mrr_at_k_no_hit_is_zero(self):
        self.assertEqual(mrr_at_k(["a", "b"], ["z"], k=10), 0.0)

    def test_mrr_at_k_respects_k_cutoff(self):
        results = ["a", "b", "c"]
        relevant = ["c"]
        self.assertEqual(mrr_at_k(results, relevant, k=2), 0.0)
        self.assertAlmostEqual(mrr_at_k(results, relevant, k=3), 1 / 3)

    def test_ndcg_at_k_hand_computed(self):
        # relevant = {b, d}; results ranked a,b,c,d -> hits at rank 2 and 4
        # DCG = 1/log2(3) + 1/log2(5)
        # IDCG (2 relevant, ideal ranks 1,2) = 1/log2(2) + 1/log2(3)
        results = ["a", "b", "c", "d"]
        relevant = ["b", "d"]
        dcg = 1 / math.log2(3) + 1 / math.log2(5)
        idcg = 1 / math.log2(2) + 1 / math.log2(3)
        self.assertAlmostEqual(ndcg_at_k(results, relevant, k=10), dcg / idcg)

    def test_ndcg_at_k_perfect_ranking_is_one(self):
        results = ["a", "b", "c"]
        relevant = ["a", "b"]
        self.assertAlmostEqual(ndcg_at_k(results, relevant, k=10), 1.0)

    def test_duplicate_hits_cannot_inflate_ndcg(self):
        self.assertEqual(ndcg_at_k(["a", "a", "a"], ["a"]), 1.0)

    def test_ndcg_at_k_no_relevant_is_zero(self):
        self.assertEqual(ndcg_at_k(["a", "b"], [], k=10), 0.0)

    def test_ndcg_at_k_ties_binary_gain(self):
        # Two relevant docs both present but out of ideal order still yields
        # the same DCG regardless of which specific doc occupies which rank
        # (binary gain has no notion of "better" among the relevant set).
        relevant = ["x", "y"]
        self.assertAlmostEqual(
            ndcg_at_k(["x", "y", "z"], relevant, k=10),
            ndcg_at_k(["y", "x", "z"], relevant, k=10),
        )


class LoadGoldenSetTests(unittest.TestCase):
    def test_valid_entry_round_trips(self):
        path = _write_json(self, [{"query": VALID_QUERY_PAYLOAD, "relevant_doc_ids": ["OPS-201:problem"]}])
        entries = load_golden_set(path)
        self.assertEqual(len(entries), 1)
        self.assertIsInstance(entries[0], GoldenEntry)
        self.assertIsInstance(entries[0].query, RetrievalQuery)
        self.assertEqual(entries[0].query.error_codes, ("4107",))
        self.assertEqual(entries[0].relevant_doc_ids, ("OPS-201:problem",))

    def test_top_level_must_be_a_list(self):
        path = _write_json(self, {"query": VALID_QUERY_PAYLOAD, "relevant_doc_ids": ["a"]})
        with self.assertRaises(RagInputError):
            load_golden_set(path)

    def test_unknown_entry_key_rejected(self):
        payload = [{"query": VALID_QUERY_PAYLOAD, "relevant_doc_ids": ["a"], "extra": 1}]
        path = _write_json(self, payload)
        with self.assertRaises(RagInputError):
            load_golden_set(path)

    def test_query_missing_key_rejected(self):
        bad_query = dict(VALID_QUERY_PAYLOAD)
        del bad_query["component"]
        path = _write_json(self, [{"query": bad_query, "relevant_doc_ids": ["a"]}])
        with self.assertRaises(RagInputError):
            load_golden_set(path)

    def test_empty_relevant_doc_ids_rejected(self):
        path = _write_json(self, [{"query": VALID_QUERY_PAYLOAD, "relevant_doc_ids": []}])
        with self.assertRaises(RagInputError):
            load_golden_set(path)

    def test_blank_query_text_rejected(self):
        bad_query = dict(VALID_QUERY_PAYLOAD)
        bad_query["text"] = ""
        path = _write_json(self, [{"query": bad_query, "relevant_doc_ids": ["a"]}])
        with self.assertRaises(RagInputError):
            load_golden_set(path)

    def test_fixture_golden_set_loads(self):
        entries = load_golden_set(str(ROOT / "fixtures" / "rag" / "golden_set.json"))
        self.assertGreaterEqual(len(entries), 8)

    def test_empty_set_and_invalid_relevance_ids_rejected(self):
        payloads = [[]] + [
            [{"query": VALID_QUERY_PAYLOAD, "relevant_doc_ids": ids}]
            for ids in (["a", "a"], [""], ["   "])
        ]
        for payload in payloads:
            with self.subTest(payload=payload), self.assertRaises(RagInputError):
                load_golden_set(_write_json(self, payload))


def _tiny_corpus():
    def doc(doc_id, title, text, document_type="jira_problem"):
        return IndexDocument(
            doc_id=doc_id, source_type="jira", document_type=document_type, project="OPS", system="OPS", component="Parser",
            entity_ids=(), labels=(), trust_level="supporting", source_id=doc_id.split(":")[0], updated_at="",
            title=title, text=text,
        )

    return [
        doc("A:problem", "parser error 4107", "parser aborts with error code 4107 during insert"),
        doc("B:problem", "scheduler duplicate", "scheduler runs job twice causing duplicate rows"),
        doc("C:problem", "refund duplicate", "refund request double submits over slow network"),
    ]


class RunEvaluationTests(unittest.TestCase):
    def test_report_shape_on_tiny_synthetic_corpus(self):
        documents = _tiny_corpus()
        golden = [
            GoldenEntry(
                query=RetrievalQuery(text="parser error 4107", document_types=("jira_problem",)),
                relevant_doc_ids=("A:problem",),
            )
        ]
        variants = default_local_variants(documents, "")
        report = run_evaluation(variants, golden, ks=(5, 10))

        self.assertEqual(set(report.keys()), {v.name for v in variants})
        for metrics in report.values():
            self.assertEqual(
                set(metrics.keys()),
                {"recall@5", "recall@10", "mrr@10", "ndcg@10", "latency_ms_p50", "latency_ms_p95"},
            )
            for value in metrics.values():
                self.assertIsInstance(value, float)
                self.assertGreaterEqual(value, 0.0)

    def test_bm25_only_variant_finds_the_relevant_doc(self):
        documents = _tiny_corpus()
        golden = [
            GoldenEntry(
                query=RetrievalQuery(text="parser error 4107", document_types=("jira_problem",)),
                relevant_doc_ids=("A:problem",),
            )
        ]
        variants = {v.name: v for v in default_local_variants(documents, "")}
        report = run_evaluation([variants["bm25-only"]], golden)
        self.assertEqual(report["bm25-only"]["recall@5"], 1.0)

    def test_empty_golden_set_rejected(self):
        documents = _tiny_corpus()
        variants = default_local_variants(documents, "")
        with self.assertRaises(RagInputError):
            run_evaluation(variants, [])

    def test_evaluation_retrieves_beyond_serving_top_five(self):
        documents = [replace(_tiny_corpus()[0], doc_id=f"{i:02}:problem", source_id=str(i),
                             title="same", text="same") for i in range(12)]
        golden = [GoldenEntry(RetrievalQuery(text="same"), ("08:problem",))]
        variant = default_local_variants(documents, "")[0]
        self.assertEqual(len(variant.build().retrieve(golden[0].query).final), 5)
        metrics = run_evaluation([variant], golden)[variant.name]
        self.assertEqual(metrics["recall@5"], 0.0)
        self.assertEqual(metrics["recall@10"], 1.0)
        self.assertAlmostEqual(metrics["mrr@10"], 1 / 9)
        metrics = run_evaluation([variant], [GoldenEntry(golden[0].query, ("11:problem",))], ks=(12,))[variant.name]
        self.assertEqual(metrics["recall@12"], 1.0)
        self.assertEqual(metrics["mrr@10"], 0.0)

    def test_unknown_or_filtered_relevance_ids_fail_before_retrieval(self):
        docs = _tiny_corpus()
        calls = []
        pipeline = SimpleNamespace(documents=docs, retrieve=lambda *a, **kw: calls.append(a))
        variants = [PipelineVariant("fake", lambda: pipeline)]
        for query, ids in ((RetrievalQuery(text="q"), ("missing",)),
                           (RetrievalQuery(text="q", document_types=("domain_knowledge",)), ("A:problem",)),
                           (RetrievalQuery(text=" "), ("A:problem",)),
                           (RetrievalQuery(text="q"), ("A:problem", "A:problem"))):
            with self.subTest(ids=ids, query=query), self.assertRaises(RagInputError):
                run_evaluation(variants, [GoldenEntry(query, ids)])
        self.assertEqual(calls, [])

    def test_invalid_cutoffs_and_duplicate_variant_names_rejected(self):
        variant = default_local_variants(_tiny_corpus(), "")[0]
        golden = [GoldenEntry(RetrievalQuery(text="q"), ("A:problem",))]
        for ks in ((), (0,), (-1,), (True,), (5, 5)):
            with self.subTest(ks=ks), self.assertRaises(RagInputError):
                run_evaluation([variant], golden, ks=ks)
        for variants in ([], [variant, variant]):
            with self.assertRaises(RagInputError):
                run_evaluation(variants, golden)

    def test_duplicate_or_unknown_pipeline_results_fail_closed(self):
        docs = _tiny_corpus()
        golden = [GoldenEntry(RetrievalQuery(text="q"), ("A:problem",))]
        for ids in (("A:problem", "A:problem"), ("unknown",)):
            final = [SimpleNamespace(doc_id=doc_id) for doc_id in ids]
            pipeline = SimpleNamespace(documents=docs, retrieve=lambda *a, **kw: SimpleNamespace(final=final))
            with self.subTest(ids=ids), self.assertRaises(RagInputError):
                run_evaluation([PipelineVariant("bad", lambda: pipeline)], golden)

    def test_variant_cleanup_runs_after_a_fail_closed_result(self):
        docs = _tiny_corpus()
        golden = [GoldenEntry(RetrievalQuery(text="q"), ("A:problem",))]
        final = [SimpleNamespace(doc_id="A:problem"), SimpleNamespace(doc_id="A:problem")]
        pipeline = SimpleNamespace(
            documents=docs,
            retrieve=lambda *a, **kw: SimpleNamespace(final=final),
        )
        closed = []
        variant = PipelineVariant("bad", lambda: pipeline, cleanup=lambda _: closed.append(True))

        with self.assertRaises(RagInputError):
            run_evaluation([variant], golden)
        self.assertEqual(closed, [True])

    def test_fixture_hybrid_rerank_meets_recall_floor(self):
        # Locks the >= 0.5 recall@5 floor to the committed fixture content
        # (golden_set.json + normalized_issues.json + wiki_pages.json), not
        # to the metric implementation -- a regression here means the
        # fixtures drifted, not that recall_at_k/run_evaluation was loosened.
        from rag.contracts import issue_to_documents, parse_normalized_issue, parse_wiki_page, wiki_to_document

        fixtures_dir = ROOT / "fixtures" / "rag"
        with (fixtures_dir / "normalized_issues.json").open(encoding="utf-8") as stream:
            issues = [parse_normalized_issue(item) for item in json.load(stream)]
        with (fixtures_dir / "wiki_pages.json").open(encoding="utf-8") as stream:
            pages = [parse_wiki_page(item) for item in json.load(stream)]

        documents = []
        for issue in issues:
            documents.extend(issue_to_documents(issue))
        for page in pages:
            documents.append(wiki_to_document(page))

        golden = load_golden_set(str(fixtures_dir / "golden_set.json"))
        variants = {v.name: v for v in default_local_variants(documents, "")}
        report = run_evaluation([variants["hybrid+rerank"]], golden)
        self.assertGreaterEqual(report["hybrid+rerank"]["recall@5"], 0.5)

    def test_calibrated_default_preserves_all_fixture_relevance_metrics(self):
        # This evaluates every committed golden query through the public
        # evaluation/retrieval seam. Latency is intentionally not asserted:
        # this test protects ranking behavior, not machine-load timing.
        from rag.contracts import issue_to_documents, parse_normalized_issue, parse_wiki_page, wiki_to_document

        fixtures_dir = ROOT / "fixtures" / "rag"
        with (fixtures_dir / "normalized_issues.json").open(encoding="utf-8") as stream:
            issues = [parse_normalized_issue(item) for item in json.load(stream)]
        with (fixtures_dir / "wiki_pages.json").open(encoding="utf-8") as stream:
            pages = [parse_wiki_page(item) for item in json.load(stream)]

        documents = []
        for issue in issues:
            documents.extend(issue_to_documents(issue))
        for page in pages:
            documents.append(wiki_to_document(page))

        golden = load_golden_set(str(fixtures_dir / "golden_set.json"))
        with (fixtures_dir / "registry.json").open(encoding="utf-8") as stream:
            registry_payload = json.load(stream)
        registry_tmp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(registry_tmp_dir.cleanup)
        registry_path = str(Path(registry_tmp_dir.name) / "registry.db")
        # Seed exactly as the CLI does, then close the seeding connection
        # before evaluation opens its own expansion-variant connection.
        seed_registry = SqliteKnowledgeRegistry.from_payload(
            registry_path, registry_payload["entities"], registry_payload["relations"]
        )
        seed_registry.close()
        report = run_evaluation(default_local_variants(documents, registry_path), golden)
        expected = {
            "bm25-only": (1.0, 1.0, 1.0, 1.0),
            "vector-only": (1.0, 1.0, 1.0, 1.0),
            "hybrid": (1.0, 1.0, 1.0, 1.0),
            "hybrid+rerank": (1.0, 1.0, 1.0, 0.989),
            "hybrid+rerank+expansion": (1.0, 1.0, 1.0, 0.989),
        }
        for name, (recall5, recall10, mrr10, ndcg10) in expected.items():
            with self.subTest(variant=name):
                self.assertAlmostEqual(report[name]["recall@5"], recall5, places=3)
                self.assertAlmostEqual(report[name]["recall@10"], recall10, places=3)
                self.assertAlmostEqual(report[name]["mrr@10"], mrr10, places=3)
                self.assertAlmostEqual(report[name]["ndcg@10"], ndcg10, places=3)


class RenderMarkdownTableTests(unittest.TestCase):
    def test_columns_and_variant_rows(self):
        report = {
            "bm25-only": {"recall@5": 1.0, "recall@10": 1.0, "mrr@10": 1.0, "ndcg@10": 1.0, "latency_ms_p50": 0.1, "latency_ms_p95": 0.2},
            "hybrid+rerank": {"recall@5": 0.5, "recall@10": 0.75, "mrr@10": 0.5, "ndcg@10": 0.6, "latency_ms_p50": 1.1, "latency_ms_p95": 1.5},
        }
        table = render_markdown_table(report)
        lines = table.splitlines()
        self.assertEqual(
            lines[0], "| variant | recall@5 | recall@10 | mrr@10 | ndcg@10 | latency_ms_p50 | latency_ms_p95 |"
        )
        self.assertIn("bm25-only", lines[2])
        self.assertIn("hybrid+rerank", lines[3])

    def test_empty_report_is_empty_string(self):
        self.assertEqual(render_markdown_table({}), "")


class DefaultLocalVariantsTests(unittest.TestCase):
    def test_produces_five_named_variants(self):
        variants = default_local_variants(_tiny_corpus(), "")
        names = [v.name for v in variants]
        self.assertEqual(
            names, ["bm25-only", "vector-only", "hybrid", "hybrid+rerank", "hybrid+rerank+expansion"]
        )
        for variant in variants:
            self.assertIsInstance(variant, PipelineVariant)
            pipeline = variant.build()
            self.assertTrue(hasattr(pipeline, "retrieve"))


class EvalCliTests(unittest.TestCase):
    def test_eval_cli_prints_all_five_variant_names(self):
        proc = subprocess.run(
            [
                sys.executable, "-m", "rag", "eval",
                "--fixtures-dir", "fixtures/rag",
                "--golden", "fixtures/rag/golden_set.json",
            ],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        for name in ("bm25-only", "vector-only", "hybrid", "hybrid+rerank", "hybrid+rerank+expansion"):
            self.assertIn(name, proc.stdout)
        self.assertIn("recall@5", proc.stdout)

    def test_eval_cli_json_output_is_valid(self):
        proc = subprocess.run(
            [
                sys.executable, "-m", "rag", "eval",
                "--fixtures-dir", "fixtures/rag",
                "--golden", "fixtures/rag/golden_set.json",
                "--json",
            ],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        report = json.loads(proc.stdout)
        self.assertEqual(len(report), 5)

    def test_index_cli_exit_zero(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = str(Path(tmp_dir) / "state.json")
            proc = subprocess.run(
                [sys.executable, "-m", "rag", "index", "--fixtures-dir", "fixtures/rag", "--state", state_path],
                cwd=str(ROOT),
                capture_output=True,
                text=True,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertTrue(Path(state_path).exists())

    def test_invalid_golden_set_exits_nonzero_with_message(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            bad_path = Path(tmp_dir) / "bad_golden.json"
            bad_path.write_text(json.dumps({"not": "a list"}), encoding="utf-8")
            proc = subprocess.run(
                [
                    sys.executable, "-m", "rag", "eval",
                    "--fixtures-dir", "fixtures/rag",
                    "--golden", str(bad_path),
                ],
                cwd=str(ROOT),
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(proc.returncode, 0)
            self.assertIn("error", proc.stderr.lower())


if __name__ == "__main__":
    unittest.main()
