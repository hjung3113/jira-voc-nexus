# Tooling comparison and adoption decision — 2026-09-10

## Current decision

The OSS/VOC reuse research is recorded in [OSS_RESEARCH.md](OSS_RESEARCH.md),
and its research gate is satisfied. The current commit's baseline is the
following four things:

- Python 3.9+ standard library and SQLite runtime
- The existing OpenCode native CLI headless boundary
- The four shared local skills under `.agents/skills/`: `orca-cli`,
  `orchestration`, `voc-slice`, `voc-workflow`
- The current scope of file input, synthetic fixtures, and local proposals
  only

No Jira connector, Promptfoo, Pydantic AI/LangGraph, or n8n/Activepieces is
installed or adopted in the runtime. Python 3.9 is only the current
scaffold's compatibility floor, not a permanent decision about the product's
runtime ceiling/floor, and can be re-evaluated once real connection
contracts and operational grounds exist.

| Candidate | Current status | Rationale and re-evaluation trigger |
| --- | --- | --- |
| OpenCode native CLI | **Currently used** | Keep the `opencode run --pure --format json --model ... --agent voc-triage` boundary. Start one process per evidence event, and never interpret auxiliary events/titles in a single stream as a count of provider HTTP requests. |
| OpenCode SDK/`serve` | Not installed, on hold | SDK structured output is useful. Python can call `serve` HTTP directly, so a Node bridge is not required, but a persistent server's health/auth/shutdown/log lifecycle is added. Reconsider only once that cost is justified. |
| `atlassian-python-api==5.0.4` | **Future leading candidate, not installed** | No runnable adapter is built now, absent real Jira ACL/auth and server flavor. Once the contract is closed, wrap it behind a read-only `JiraPort` and independently verify ACL-before-search, pagination, bounded retry, and reconciliation. |
| `pycontribs/jira==3.10.5` | Not installed, on hold | Does not fit the current 3.9 scaffold directly and has a broad object API. A Python floor change is not treated as a blanket prohibition; re-compare once a future runtime/adapter need arises. |
| `mcp-atlassian==0.23.1` | **Rejected for runtime** | Its agent-facing tool surface and server/dependency/security burden are large. read-only/project filter is not a substitute for a real ACL contract, so it is not brought in as a product connector. |
| Promptfoo `0.122.2` | Not installed, future option | Useful only for an isolated eval job that verifies stored model output. Current golden-set/Node-eval operational need is not demonstrated, so it is not added as a Python/runtime dependency. |
| n8n / Activepieces | Not installed, flow reference only | Reference only the official support-ticket flow's steps, dedupe, human review, and branch design. Template code/credentials are not imported; since both platforms can express deterministic steps, we do not assume AI must always own the write. |
| Pydantic AI / LangGraph | Not installed, on hold | No grounds yet to add a second orchestration runtime to the current fixed single-proposal flow. Reconsider once multi-approval waits, complex resumption, or direct Python provider calls become an actual need. |

## Execution boundary

Python owns normalization, project filtering, lexical retrieval, the evidence
cap, proposal validation, comment rendering, and replay/dedupe. When there is
no evidence, the OpenCode process is not even started, and `needs-triage` is
returned. Exactly one OpenCode process runs per new event with evidence, and
semantic rerank is never added as a separate process.

The production provider/model is never put in the repository. The current
preference, for when a real in-house model is connected, is Z.AI's
`zai/glm-5.3`; the OpenRouter path is not used. No claim of provider success
or Jira operational connectivity is made before the endpoint, credential, and
ACL principal are secured.

## Priorities

1. Source-derived remediation and outcome from resolved issues, obtained with
   real permission
2. Similar-issue hit rate and recommendation-evidence linkage against a
   golden VOC set
3. Holding back on insufficient evidence, and short comments a human can
   easily edit
4. Reproducible tests for model-output failure, replay/conflict, and
   duplicate/retry writes
5. Only expand connector/eval/orchestration scope once the above data shows
   the need

## Proposed retrieval platform (not adopted)

[RAG_DESIGN.md](RAG_DESIGN.md) records the proposed production retrieval
platform from issue #1 — Haystack, OpenSearch (BM25/Nori + vectors + RRF),
BGE-M3, BGE-Reranker-v2-m3, and a PostgreSQL knowledge registry. It is a
design reference only: none of it is installed, and adoption happens only
after the evaluation gate defined there (golden set, Recall/MRR/nDCG,
latency, ACL-leakage = 0) is measured through the implementation slices.

External model fallback or automatic production deployment must never be
routed around by a tooling choice. Real Jira comment/label writes remain a
separate, approved integration slice and are not part of the current decision.
