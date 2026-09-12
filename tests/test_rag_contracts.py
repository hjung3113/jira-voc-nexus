from __future__ import annotations

import dataclasses
import json
import unittest
from pathlib import Path

from rag.contracts import (
    issue_to_documents,
    parse_index_document,
    parse_normalized_issue,
    parse_wiki_page,
    wiki_to_document,
)
from rag.errors import RagInputError

ROOT = Path(__file__).resolve().parents[1]


def load_fixture(name):
    with (ROOT / "fixtures" / "rag" / name).open(encoding="utf-8") as stream:
        return json.load(stream)


VALID_ISSUE = {
    "issue_key": "OPS-201",
    "project": "OPS",
    "metadata": {"system": "LogWarehouse", "component": "Parser", "updated_at": "2026-01-12T09:30:00Z"},
    "problem": {
        "summary": "Parser aborts on insert",
        "symptom": "파서가 예외를 던집니다.",
        "environment": "LogWarehouse ParserJob",
        "error": "error code 4107",
    },
    "investigation": ["확인 중"],
    "resolution": {
        "root_cause": "stale connection",
        "action": "added reconnect",
        "verification": "재발 없음 확인",
    },
}

VALID_WIKI = {
    "page_id": "p1",
    "title": "Parser overview",
    "text": "Parser parses equipment logs.",
    "page_type": "systems",
    "system": "LogWarehouse",
    "component": "Parser",
    "owner": "DataPlatform",
    "status": "canonical",
    "related_entities": ["component:parser"],
}


class NormalizedIssueParsingTests(unittest.TestCase):
    def test_valid_issue_round_trips(self):
        issue = parse_normalized_issue(VALID_ISSUE)
        self.assertEqual(issue.issue_key, "OPS-201")
        self.assertEqual(issue.metadata["system"], "LogWarehouse")

    def test_unknown_key_rejected(self):
        payload = dict(VALID_ISSUE)
        payload["extra"] = "nope"
        with self.assertRaises(RagInputError):
            parse_normalized_issue(payload)

    def test_missing_key_rejected(self):
        payload = dict(VALID_ISSUE)
        del payload["investigation"]
        with self.assertRaises(RagInputError):
            parse_normalized_issue(payload)

    def test_wrong_type_rejected(self):
        payload = dict(VALID_ISSUE)
        payload["problem"] = "not an object"
        with self.assertRaises(RagInputError):
            parse_normalized_issue(payload)

    def test_string_length_limit_enforced(self):
        payload = json.loads(json.dumps(VALID_ISSUE))
        payload["problem"]["summary"] = "x" * 10_001
        with self.assertRaises(RagInputError):
            parse_normalized_issue(payload)

    def test_metadata_too_many_keys_rejected(self):
        payload = json.loads(json.dumps(VALID_ISSUE))
        payload["metadata"] = {f"k{i}": "v" for i in range(51)}
        with self.assertRaises(RagInputError):
            parse_normalized_issue(payload)

    def test_investigation_too_many_items_rejected(self):
        payload = json.loads(json.dumps(VALID_ISSUE))
        payload["investigation"] = ["note"] * 201
        with self.assertRaises(RagInputError):
            parse_normalized_issue(payload)

    def test_resolution_may_be_null(self):
        payload = json.loads(json.dumps(VALID_ISSUE))
        payload["resolution"] = None
        issue = parse_normalized_issue(payload)
        self.assertIsNone(issue.resolution)

    def test_trust_level_verified_resolution(self):
        issue = parse_normalized_issue(VALID_ISSUE)
        self.assertEqual(issue.trust_level(), "verified-resolution")

    def test_trust_level_supporting_when_no_resolution(self):
        payload = json.loads(json.dumps(VALID_ISSUE))
        payload["resolution"] = None
        issue = parse_normalized_issue(payload)
        self.assertEqual(issue.trust_level(), "supporting")

    def test_trust_level_supporting_when_verification_blank(self):
        payload = json.loads(json.dumps(VALID_ISSUE))
        payload["resolution"]["verification"] = "   "
        issue = parse_normalized_issue(payload)
        self.assertEqual(issue.trust_level(), "supporting")

    def test_fixture_issues_all_parse(self):
        for payload in load_fixture("normalized_issues.json"):
            parse_normalized_issue(payload)

    def test_metadata_updated_at_must_be_string(self):
        payload = json.loads(json.dumps(VALID_ISSUE))
        payload["metadata"]["updated_at"] = 20260112
        with self.assertRaises(RagInputError):
            parse_normalized_issue(payload)

    def test_metadata_updated_at_must_be_valid_iso8601(self):
        payload = json.loads(json.dumps(VALID_ISSUE))
        payload["metadata"]["updated_at"] = "2026-01-12garbage"
        with self.assertRaises(RagInputError):
            parse_normalized_issue(payload)

    def test_metadata_updated_at_accepts_date_only(self):
        payload = json.loads(json.dumps(VALID_ISSUE))
        payload["metadata"]["updated_at"] = "2026-01-12"
        issue = parse_normalized_issue(payload)
        self.assertEqual(issue.metadata["updated_at"], "2026-01-12")


class WikiPageParsingTests(unittest.TestCase):
    def test_valid_wiki_round_trips(self):
        page = parse_wiki_page(VALID_WIKI)
        self.assertEqual(page.page_type, "systems")

    def test_invalid_page_type_rejected(self):
        payload = dict(VALID_WIKI)
        payload["page_type"] = "bogus"
        with self.assertRaises(RagInputError):
            parse_wiki_page(payload)

    def test_invalid_status_rejected(self):
        payload = dict(VALID_WIKI)
        payload["status"] = "bogus"
        with self.assertRaises(RagInputError):
            parse_wiki_page(payload)

    def test_trust_level_canonical(self):
        page = parse_wiki_page(VALID_WIKI)
        self.assertEqual(page.trust_level(), "canonical")

    def test_trust_level_supporting_when_draft(self):
        payload = dict(VALID_WIKI)
        payload["status"] = "draft"
        page = parse_wiki_page(payload)
        self.assertEqual(page.trust_level(), "supporting")

    def test_fixture_wiki_pages_all_parse(self):
        for payload in load_fixture("wiki_pages.json"):
            parse_wiki_page(payload)


class IndexDocumentParsingTests(unittest.TestCase):
    def test_invalid_source_type_rejected(self):
        payload = {
            "doc_id": "d1",
            "source_type": "bogus",
            "document_type": "jira_problem",
            "project": "",
            "system": "",
            "component": "",
            "entity_ids": [],
            "trust_level": "supporting",
            "source_id": "d1",
            "updated_at": "",
            "title": "t",
            "text": "t",
        }
        with self.assertRaises(RagInputError):
            parse_index_document(payload)

    def test_invalid_updated_at_rejected(self):
        payload = {
            "doc_id": "d1",
            "source_type": "jira",
            "document_type": "jira_problem",
            "project": "",
            "system": "",
            "component": "",
            "entity_ids": [],
            "trust_level": "supporting",
            "source_id": "d1",
            "updated_at": "not-a-date",
            "title": "t",
            "text": "t",
        }
        with self.assertRaises(RagInputError):
            parse_index_document(payload)


class DocumentProjectionTests(unittest.TestCase):
    def test_issue_with_resolution_yields_two_documents(self):
        issue = parse_normalized_issue(VALID_ISSUE)
        docs = issue_to_documents(issue)
        self.assertEqual(len(docs), 2)
        self.assertEqual(docs[0].doc_id, "OPS-201:problem")
        self.assertEqual(docs[0].document_type, "jira_problem")
        self.assertEqual(docs[0].project, "OPS")
        self.assertEqual(docs[1].doc_id, "OPS-201:resolution")
        self.assertEqual(docs[1].document_type, "jira_resolution")
        self.assertEqual(docs[1].project, "OPS")
        self.assertEqual(docs[1].trust_level, "verified-resolution")

    def test_issue_without_resolution_yields_one_document(self):
        payload = json.loads(json.dumps(VALID_ISSUE))
        payload["resolution"] = None
        issue = parse_normalized_issue(payload)
        docs = issue_to_documents(issue)
        self.assertEqual(len(docs), 1)
        self.assertEqual(docs[0].document_type, "jira_problem")

    def test_issue_without_metadata_labels_yields_empty_labels(self):
        issue = parse_normalized_issue(VALID_ISSUE)
        docs = issue_to_documents(issue)
        self.assertEqual(docs[0].labels, ())
        self.assertEqual(docs[1].labels, ())

    def test_metadata_labels_reach_both_projected_documents(self):
        payload = json.loads(json.dumps(VALID_ISSUE))
        payload["metadata"]["labels"] = ["parser", "reconnect"]
        issue = parse_normalized_issue(payload)
        docs = issue_to_documents(issue)
        self.assertEqual(docs[0].labels, ("parser", "reconnect"))
        self.assertEqual(docs[1].labels, ("parser", "reconnect"))

    def test_issue_to_documents_round_trips_through_parse_index_document(self):
        for payload in load_fixture("normalized_issues.json"):
            issue = parse_normalized_issue(payload)
            for doc in issue_to_documents(issue):
                doc_payload = dataclasses.asdict(doc)
                doc_payload["entity_ids"] = list(doc.entity_ids)
                doc_payload["labels"] = list(doc.labels)
                round_tripped = parse_index_document(doc_payload)
                self.assertEqual(round_tripped, doc)

    def test_wiki_to_document_type_mapping(self):
        cases = {"domain": "domain_knowledge", "systems": "system_knowledge", "data": "db_knowledge"}
        for page_type, expected_document_type in cases.items():
            payload = dict(VALID_WIKI)
            payload["page_type"] = page_type
            page = parse_wiki_page(payload)
            doc = wiki_to_document(page)
            self.assertEqual(doc.document_type, expected_document_type)
            self.assertEqual(doc.doc_id, f"wiki:{page.page_id}")
            self.assertEqual(doc.project, "")
            self.assertEqual(doc.labels, ())


if __name__ == "__main__":
    unittest.main()
