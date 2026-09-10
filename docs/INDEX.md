# Documentation index

- [Current goal](GOAL.md): the request broken down into verifiable completion conditions
- [Project overview](PROJECT_OVERVIEW.md): the boundary between the future product MVP and the current local scaffold
- [Architecture and contracts](ARCHITECTURE.md): execution boundary, replay, proposal schema, open contracts
- [Knowledge Retrieval Platform design](RAG_DESIGN.md): proposed production retrieval architecture from issue #1; not an adoption decision
- [Local RAG toolkit and deployment guide](../guides/RAG_DEPLOYMENT.md): file-based `index|query|eval` usage and the OpenSearch/BGE/PostgreSQL swap steps
- [RAG evaluation gate](../guides/RAG_EVALUATION.md): golden-set construction, metrics, comparison variants, and the proposed-not-adopted gate
- [RAG company ingestion/registry/ACL guides](../guides/RAG_JIRA_INGESTION.md): source normalization, exact relation seeding, and ACL-before-search contracts
- [RAG operations runbook](../guides/RAG_OPERATIONS.md): backup/restore, reindex/rollback, monitoring signals, and fail-closed operational rules
- [Design review](REVIEW.md): Grok design findings and the adopted resolutions
- [Development environment and verification](DEVELOPMENT.md): install scope and what each verification command means
- [Tooling comparison and adoption](TOOLING_DECISION.md): open-source candidates and why the lightweight configuration was chosen
- [OSS/VOC automation research](OSS_RESEARCH.md): public source/license/template evidence and future candidates
- [Operational integration contract](INTEGRATION.md): conditions to meet before connecting the in-house LLM/Jira
- [Current handoff](../HANDOFF.md): actual implementation/verification status and next slice
