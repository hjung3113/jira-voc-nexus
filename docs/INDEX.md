# Documentation index

Use this page as the task-oriented map. Read the current code and tests with
the contract document named for the task; this index is navigation, not a
second source of runtime truth.

## Start with current truth

- [README](../README.md): fresh Python-only fixture quickstart, the separate
  `nexus`/`rag` boundaries, and the current v2 fixture comment.
- [Current handoff](../HANDOFF.md): latest status and remaining work. The top
  entry is the current checkpoint; older entries are historical records.
- [Project overview](PROJECT_OVERVIEW.md): product direction and the boundary
  between the future MVP and the current local scaffold.
- [Architecture and contracts](ARCHITECTURE.md): current execution flow,
  proposal/result contracts, local RAG boundary, and adopted decisions.
- [Templates](TEMPLATES.md): current v2 comment/issue/input templates; v1
  examples are historical. Renderer code is the source of truth if prose and
  implementation disagree.
- [Operational integration contract](INTEGRATION.md): the future provider,
  ACL, and Jira read/write conditions; no write adapter is current runtime.
- [Development and verification](DEVELOPMENT.md): Python baseline, optional
  adapter extras, separate agent tooling, provider boundary, and test routes.
- [Tooling decision](TOOLING_DECISION.md): current lightweight-tooling choice;
  its retrieval-platform section remains explicitly proposed/not adopted.
- [Same-project calibration](RAG_SAME_PROJECT_CALIBRATION.md): current
  fixture-only local RAG ranking decision, with its synthetic limitations.

## Choose a task route

| Task | Read first | Code seam | Regression/evidence check |
| --- | --- | --- | --- |
| Run or change the Nexus fixture proposal path | [README](../README.md#python-only-fixture-quickstart), [architecture](ARCHITECTURE.md#current-boundary), [templates](TEMPLATES.md) | [nexus/cli.py](../nexus/cli.py), [nexus/models.py](../nexus/models.py), [nexus/service.py](../nexus/service.py), [nexus/retrieval.py](../nexus/retrieval.py), [nexus/proposals.py](../nexus/proposals.py), [nexus/opencode.py](../nexus/opencode.py), [nexus/storage.py](../nexus/storage.py) | [tests/test_nexus.py](../tests/test_nexus.py) plus the fresh Nexus CLI smoke |
| Run standalone local RAG index/query | [RAG deployment local-first run](../guides/RAG_DEPLOYMENT.md#local-first-run-verify-before-touching-any-adapter), [RAG operations boundary](../guides/RAG_OPERATIONS.md#current-deployment-boundary-read-this-before-promising-an-sla) | [rag/__main__.py](../rag/__main__.py), [rag/contracts.py](../rag/contracts.py), [rag/retrieval.py](../rag/retrieval.py), [rag/context.py](../rag/context.py), [rag/registry.py](../rag/registry.py) | [tests/test_rag_cli.py](../tests/test_rag_cli.py), [tests/test_rag_contracts.py](../tests/test_rag_contracts.py), [tests/test_rag_context.py](../tests/test_rag_context.py), [tests/test_rag_registry.py](../tests/test_rag_registry.py), [tests/test_rag_retrieval.py](../tests/test_rag_retrieval.py) |
| Evaluate the five local retrieval variants | [RAG evaluation](../guides/RAG_EVALUATION.md), [RAG design evaluation gate](RAG_DESIGN.md#evaluation-gate-before-adoption) | [rag/eval.py](../rag/eval.py), [rag/__main__.py](../rag/__main__.py) | [tests/test_rag_eval.py](../tests/test_rag_eval.py) plus `python3 -m rag eval ...` |
| Change ingestion, ACL, registry, or context contracts | [RAG Jira ingestion](../guides/RAG_JIRA_INGESTION.md), [RAG ACL](../guides/RAG_ACL.md), [RAG registry](../guides/RAG_REGISTRY.md), [RAG wiki ingestion](../guides/RAG_WIKI_INGESTION.md) | [rag/contracts.py](../rag/contracts.py), [rag/acl.py](../rag/acl.py), [rag/registry.py](../rag/registry.py), [rag/registry_pg.py](../rag/registry_pg.py), [rag/retrieval.py](../rag/retrieval.py), [rag/context.py](../rag/context.py) | [tests/test_rag_contracts.py](../tests/test_rag_contracts.py), [tests/test_rag_registry.py](../tests/test_rag_registry.py), [tests/test_rag_registry_pg.py](../tests/test_rag_registry_pg.py), [tests/test_rag_retrieval.py](../tests/test_rag_retrieval.py), [tests/test_rag_context.py](../tests/test_rag_context.py) |
| Prepare or operate an internal deployment | [Company onboarding](../guides/COMPANY_ONBOARDING.md), [onboarding checklist](../guides/COMPANY_ONBOARDING_CHECKLIST.md), [RAG deployment](../guides/RAG_DEPLOYMENT.md), [RAG operations](../guides/RAG_OPERATIONS.md) | [scripts/doctor.py](../scripts/doctor.py), [rag/__main__.py](../rag/__main__.py), and the explicitly selected adapter seam | Documented fixture/adapter commands; [tests/test_rag_cli.py](../tests/test_rag_cli.py), [tests/test_rag_eval.py](../tests/test_rag_eval.py), and [tests/test_rag_registry_pg.py](../tests/test_rag_registry_pg.py) where applicable. `doctor.py` has no dedicated test. |
| Set up a worker or verify repository rules | [AGENTS](../AGENTS.md), [development](DEVELOPMENT.md) | [pyproject.toml](../pyproject.toml), [scripts/doctor.py](../scripts/doctor.py), [project skills](../.agents/skills/) | `python3 scripts/doctor.py`; agent tooling is not a runtime test |

## Current guides and contracts

These documents describe current local behavior or the explicit conditions for
a future, separately approved integration. Follow their scope labels; a guide
describing an adapter does not mean that adapter is connected.

- [RAG deployment](../guides/RAG_DEPLOYMENT.md): local index/query/eval flow,
  optional dependency extras, and adapter swap procedures.
- [RAG evaluation](../guides/RAG_EVALUATION.md): golden sets, metrics,
  five-variant comparison, detailed reports, and adoption evidence rules.
- [RAG ACL](../guides/RAG_ACL.md): pre-retrieval principal filtering,
  leakage-zero evaluation, and fail-closed checks.
- [RAG Jira ingestion](../guides/RAG_JIRA_INGESTION.md): normalized issue,
  comments, metadata, sanitization, and incremental-indexing contracts.
- [RAG wiki ingestion](../guides/RAG_WIKI_INGESTION.md): domain/system/wiki
  metadata, trust levels, and re-index rules.
- [RAG registry](../guides/RAG_REGISTRY.md): entity/relation validation,
  SQLite/PostgreSQL registry behavior, and seeding checks.
- [RAG operations](../guides/RAG_OPERATIONS.md): backup/restore, reindex,
  rollback, monitoring, and fail-closed operational rules.
- [Company onboarding](../guides/COMPANY_ONBOARDING.md): internal-only phases,
  separate Jira/provider/retrieval gates, and evidence-record boundaries.
- [Company onboarding checklist](../guides/COMPANY_ONBOARDING_CHECKLIST.md):
  copyable role-owned checklist; the Git file is a template, not an approval
  or execution record.

## Proposed, research, and historical records

Use these for rationale and open questions, then verify any claimed behavior
against the current sections above and the implementation.

- [Proposed RAG design](RAG_DESIGN.md): issue #1 production retrieval design;
  explicitly not adopted production architecture.
- [Gap analysis](GAP_ANALYSIS.md): historical pre-v2 research; several findings are now
  resolved. It is not an active backlog or runtime contract.
- [OSS/VOC research](OSS_RESEARCH.md): public source/license/dependency review
  and future candidates; it does not install or adopt a connector.
- [Original scaffold goal](GOAL.md): dated acceptance record for the original
  scaffold, not the current task list.
- [Final code review](REVIEW.md): dated review findings and adjudication; useful
  rationale, not a live status report.

The current handoff and Git/runtime state always take precedence over dates,
claims, or test counts copied from historical records.
