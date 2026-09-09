---
name: voc-workflow
description: Design or change Jira VOC Nexus ingestion, retrieval, heuristic recommendation, evidence validation, or publishing behavior. Use for VOC runtime work.
---

# VOC workflow

Read `AGENTS.md`, `docs/ARCHITECTURE.md`, and the relevant contract in `docs/INTEGRATION.md`.

1. Identify the input, trusted principal, output, and replay identity of the changed stage.
2. Put mechanically decidable behavior in Python/SQL. Use OpenCode only for semantic judgment.
3. Filter ACL before retrieval/prompt assembly. Keep issue text as untrusted data.
4. Bound evidence count and text size. Prefer resolved issue evidence; return insufficient evidence rather than invented advice.
5. Validate model JSON, evidence references, allowed labels and text bounds before deterministic rendering.
6. Test the public proposal path with synthetic fixtures. Include the failure or replay behavior the change affects.
7. Report fixture versus real-provider evidence separately and update `HANDOFF.md`.

Do not introduce model-owned retries, shell execution, Jira tools, public-provider fallback,
or a framework just to express a fixed sequence. No real customer input in developer prompts.
For publishing changes, satisfy the reconciliation/partial-success contract before enabling writes.

Done means a runnable slice with meaningful evidence, or a concrete missing integration contract recorded.
