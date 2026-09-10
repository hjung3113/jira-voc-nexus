"""Local-only CLI for the RAG core: index fixtures, run a query, run eval.

No flags imply a network service. Swapping in OpenSearch / PostgreSQL / BGE
adapters is Python-API-and-guides territory (see guides/RAG_DEPLOYMENT.md),
not something exposed here.

    python3 -m rag index --fixtures-dir fixtures/rag --state .local/rag/state.json
    python3 -m rag query --state .local/rag/state.json --text "<q>" [--project P] [--error-code E]... [--json]
    python3 -m rag eval  --fixtures-dir fixtures/rag --golden fixtures/rag/golden_set.json [--json]
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import os
import sys
import tempfile
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .acl import AllowAllAcl
from .context import ContextBuilder
from .contracts import (
    IndexDocument,
    issue_to_documents,
    parse_index_document,
    parse_normalized_issue,
    parse_wiki_page,
    wiki_to_document,
)
from .errors import RagInputError
from .eval import default_local_variants, load_golden_set, render_markdown_table, run_evaluation
from .registry import KnowledgeRegistry, SqliteKnowledgeRegistry
from .retrieval import (
    HashingEmbedding,
    LexicalIndex,
    LexicalOverlapReranker,
    RetrievalPipeline,
    RetrievalQuery,
    RetrievalResult,
    ScoredDoc,
    VectorIndex,
    fetch_resolution_context,
)


def _load_fixture_payloads(fixtures_dir: str) -> Dict[str, Any]:
    def read(name: str) -> Any:
        path = os.path.join(fixtures_dir, name)
        with open(path, encoding="utf-8") as stream:
            return json.load(stream)

    payloads = {
        "issues": read("normalized_issues.json"),
        "wiki_pages": read("wiki_pages.json"),
        "registry": read("registry.json"),
    }
    for name in ("issues", "wiki_pages"):
        if not isinstance(payloads[name], list):
            raise RagInputError(f"fixture {name} must be a JSON list")
    _validate_registry_payload(payloads["registry"])
    return payloads


def _validate_registry_payload(payload: Any) -> None:
    if (not isinstance(payload, dict) or set(payload) != {"entities", "relations"}
            or any(not isinstance(payload[name], list) for name in ("entities", "relations"))):
        raise RagInputError("registry must contain entities and relations JSON lists")


def _validate_document_ids(documents: Sequence[IndexDocument]) -> None:
    if len({doc.doc_id for doc in documents}) != len(documents):
        raise RagInputError("corpus contains duplicate document IDs")


def _build_documents(payloads: Dict[str, Any]) -> List[IndexDocument]:
    documents: List[IndexDocument] = []
    for raw_issue in payloads["issues"]:
        issue = parse_normalized_issue(raw_issue)
        documents.extend(issue_to_documents(issue))
    for raw_page in payloads["wiki_pages"]:
        page = parse_wiki_page(raw_page)
        documents.append(wiki_to_document(page))
    _validate_document_ids(documents)
    return documents


def _document_to_payload(doc: IndexDocument) -> Dict[str, Any]:
    payload = dataclasses.asdict(doc)
    payload["entity_ids"] = list(doc.entity_ids)
    return payload


def _state_paths(state_path: str) -> Tuple[str, str]:
    # Preserve whatever style (relative/absolute) the caller passed via
    # --state, so the printed registry path matches what _cmd_index reports.
    state_dir = os.path.dirname(state_path) or "."
    stem = os.path.splitext(os.path.basename(state_path))[0]
    registry_db_path = os.path.join(state_dir, f"{stem}.registry.db")
    return state_dir, registry_db_path


def _cmd_index(args: argparse.Namespace) -> int:
    payloads = _load_fixture_payloads(args.fixtures_dir)
    documents = _build_documents(payloads)

    state_dir, registry_db_path = _state_paths(args.state)
    os.makedirs(state_dir, exist_ok=True)
    # The registry is embedded in the state file itself (one file holds
    # everything needed to reconstruct every pipeline). registry_db_path is
    # written too, but only as an optional cache for external tools -- query
    # never requires it and rebuilds a fresh registry from the embedded
    # payload instead (see _cmd_query / _build_pipeline).
    # Stage on the same filesystem so each replacement is atomic. JSON is
    # authoritative; the disposable sidecar may be newer if interrupted
    # between replacements, but query never reads that cache.
    with tempfile.TemporaryDirectory(prefix=".rag-index-", dir=state_dir) as staging:
        staged_registry = os.path.join(staging, "registry.db")
        registry = SqliteKnowledgeRegistry.from_payload(
            staged_registry, payloads["registry"]["entities"], payloads["registry"]["relations"]
        )
        try:
            state = {
                "documents": [_document_to_payload(doc) for doc in documents],
                "registry": registry.dump_payload(),
                "registry_db_path": registry_db_path,
            }
        finally:
            registry.close()
        staged_state = os.path.join(staging, "state.json")
        with open(staged_state, "w", encoding="utf-8") as stream:
            json.dump(state, stream, ensure_ascii=False, indent=2, sort_keys=True)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(staged_registry, registry_db_path)
        os.replace(staged_state, args.state)

    print(f"indexed {len(documents)} documents -> {args.state}")
    print(f"registry -> {registry_db_path}")
    return 0


def _load_state(state_path: str) -> Tuple[List[IndexDocument], Dict[str, Any]]:
    with open(state_path, encoding="utf-8") as stream:
        state = json.load(stream)
    if not isinstance(state, dict) or "documents" not in state or "registry" not in state:
        raise RagInputError("state file must contain 'documents' and 'registry'")
    if not isinstance(state["documents"], list):
        raise RagInputError("state documents must be a JSON list")
    documents = [parse_index_document(item) for item in state["documents"]]
    _validate_document_ids(documents)
    registry_payload = state["registry"]
    _validate_registry_payload(registry_payload)
    return documents, registry_payload


def _build_pipeline(
    documents: Sequence[IndexDocument],
    registry_payload: Dict[str, Any],
    registry_build_path: str,
    *,
    registry: Optional[KnowledgeRegistry] = None,
) -> RetrievalPipeline:
    lexical = LexicalIndex(documents)
    vector = VectorIndex(documents, HashingEmbedding())
    reranker = LexicalOverlapReranker()
    # Always rebuilt fresh from the state file's embedded registry payload
    # (a temp DB), never from the sidecar .registry.db cache -- so query
    # works even if the sidecar was never copied alongside state.json.
    if registry is None:
        registry = SqliteKnowledgeRegistry.from_payload(
            registry_build_path, registry_payload["entities"], registry_payload["relations"]
        )
    return RetrievalPipeline(lexical=lexical, vector=vector, reranker=reranker, registry=registry, acl=AllowAllAcl())


def _scored_doc_payload(sd: ScoredDoc) -> Dict[str, Any]:
    return {"doc_id": sd.doc_id, "score": sd.score, "reasons": list(sd.reasons), "title": sd.doc.title}


_KNOWLEDGE_DOCUMENT_TYPES = ("domain_knowledge", "system_knowledge", "code_knowledge", "db_knowledge")


def _cmd_query(args: argparse.Namespace) -> int:
    documents, registry_payload = _load_state(args.state)

    with tempfile.TemporaryDirectory() as tmp_dir:
        registry = SqliteKnowledgeRegistry.from_payload(
            os.path.join(tmp_dir, "registry.db"), registry_payload["entities"], registry_payload["relations"]
        )
        try:
            pipeline = _build_pipeline(
                documents, registry_payload, os.path.join(tmp_dir, "registry.db"), registry=registry
            )

            error_codes = tuple(args.error_code or ())
            project = args.project or ""

            problem_query = RetrievalQuery(
                text=args.text, project=project, error_codes=error_codes, document_types=("jira_problem",)
            )
            problem_result = pipeline.retrieve(problem_query)

            knowledge_query = RetrievalQuery(
                text=args.text, project=project, error_codes=error_codes, document_types=_KNOWLEDGE_DOCUMENT_TYPES
            )
            knowledge_result = pipeline.retrieve(knowledge_query)

            resolution_corpus = [doc for doc in documents if doc.document_type == "jira_resolution"]
            issue_keys = [sd.doc.source_id for sd in problem_result.final if sd.doc.document_type == "jira_problem"]
            resolution_docs = fetch_resolution_context(issue_keys, resolution_corpus, AllowAllAcl())

            merged_result = RetrievalResult(
                fused=problem_result.fused,
                final=knowledge_result.final + problem_result.final,
                expansion=problem_result.expansion,
                acl_filtered_count=problem_result.acl_filtered_count + knowledge_result.acl_filtered_count,
            )

            built = ContextBuilder().build(problem_query, merged_result, resolution_docs=resolution_docs)

            if args.json:
                payload = {
                    "query": {"text": args.text, "project": project, "error_codes": list(error_codes)},
                    "problem_final": [_scored_doc_payload(sd) for sd in problem_result.final],
                    "resolution_docs": [doc.doc_id for doc in resolution_docs],
                    "context": {
                        "text": built.text,
                        "sections": [
                            {"heading": section.heading, "lines": list(section.lines), "source": section.source}
                            for section in built.sections
                        ],
                        "omitted_sections": list(built.omitted_sections),
                    },
                }
                print(json.dumps(payload, ensure_ascii=False, indent=2))
            else:
                print(built.text)
        finally:
            # The temporary registry is owned by this command.  The lexical
            # and vector indexes are shared by both query passes and have no
            # close lifecycle, so only the registry connection is closed.
            registry.close()
    return 0


def _cmd_eval(args: argparse.Namespace) -> int:
    payloads = _load_fixture_payloads(args.fixtures_dir)
    documents = _build_documents(payloads)
    golden = load_golden_set(args.golden)

    with tempfile.TemporaryDirectory() as tmp_dir:
        registry_db_path = os.path.join(tmp_dir, "registry.db")
        seed_registry = SqliteKnowledgeRegistry.from_payload(
            registry_db_path, payloads["registry"]["entities"], payloads["registry"]["relations"]
        )
        try:
            # The seed connection is needed only to materialize the database
            # file.  Each expansion pipeline opens its own connection and
            # run_evaluation closes that owned connection via its variant
            # cleanup callback.
            variants = default_local_variants(documents, registry_db_path)
            report = run_evaluation(variants, golden)
        finally:
            seed_registry.close()

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(render_markdown_table(report))
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python3 -m rag", description="Local-only RAG core CLI (fixtures/state only, no network)."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    index_parser = subparsers.add_parser("index", help="Build documents/registry from fixtures into a state file.")
    index_parser.add_argument("--fixtures-dir", required=True)
    index_parser.add_argument("--state", required=True)
    index_parser.set_defaults(handler=_cmd_index)

    query_parser = subparsers.add_parser("query", help="Retrieve + build context for a query against a state file.")
    query_parser.add_argument("--state", required=True)
    query_parser.add_argument("--text", required=True)
    query_parser.add_argument("--project", default="")
    query_parser.add_argument("--error-code", action="append", default=[])
    query_parser.add_argument("--json", action="store_true")
    query_parser.set_defaults(handler=_cmd_query)

    eval_parser = subparsers.add_parser("eval", help="Run the 5 local variants against a golden set.")
    eval_parser.add_argument("--fixtures-dir", required=True)
    eval_parser.add_argument("--golden", required=True)
    eval_parser.add_argument("--json", action="store_true")
    eval_parser.set_defaults(handler=_cmd_eval)

    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        return args.handler(args)
    except (RagInputError, FileNotFoundError, json.JSONDecodeError, KeyError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except OSError:
        print("error: unable to read or write local RAG files", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
