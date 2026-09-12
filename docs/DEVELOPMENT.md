# Development environment and verification

This document separates the Python application runtime, optional RAG adapter
dependencies, development-agent tooling, and the production provider boundary.
The [README quickstart](../README.md#python-only-fixture-quickstart) is the
shortest path for a fresh fixture run.

## Python runtime baseline

- Python `>=3.9` is the current compatibility floor. The base project has no
  required Python packages; `sqlite3` and all Nexus/local-RAG fixture behavior
  use the standard library.
- `nexus --engine fixture` is deterministic and never calls a model. The
  standalone `python3 -m rag index|query|eval` path reads synthetic fixtures,
  uses local state/SQLite, and makes no network calls.
- The `nexus --engine opencode` path is optional. It needs the external
  `opencode` executable plus the explicitly approved provider environment; it
  is not needed for the fixture quickstart.
- `scripts/doctor.py` is a read-only environment check. It does not run the
  runtime, tests, provider, Jira, or network integration.

## Optional RAG adapter dependencies

Install only the extra required by the adapter being wired in, and only in the
environment approved for that separate integration slice. Local fixture mode
needs none of these:

| Extra | Packages | Adapter surface |
| --- | --- | --- |
| `rag-platform` | `opensearch-py>=2.4` | `rag.retrieval.OpenSearchBackend` |
| `rag-pg` | `psycopg[binary]>=3.1` | `rag.registry_pg.PostgresKnowledgeRegistry` |
| `rag-reranker` | `torch>=2.2`, `transformers>=4.44` | `rag.retrieval.BgeRerankerAdapter` |

Example, only for a justified OpenSearch adapter environment:

```sh
python3 -m pip install -e ".[rag-platform]"
```

Network access, package resolution, CA/proxy policy, credentials, and version
pinning belong to the company-controlled integration environment. Do not treat
the optional extras as evidence that a backend is connected or adopted.

## Development-agent tooling is separate

Orca CLI and orchestration coordinate supervised workers; the canonical project
skills under `.agents/skills/` (and the `.claude/skills`, `.opencode/skills`,
and `.omp/skills` links) provide agent instructions. They are development
tools, not Python dependencies and not required to run Nexus or local RAG.

When a development worker is explicitly routed through the connected Z.AI
development path, `zai/glm-5.3` is an agent-model choice. That choice is not a
production provider selection, an application dependency, or proof of an
in-house endpoint.

## Production provider boundary

Production provider configuration is supplied by the deployment environment,
not selected from this repository and not inherited from a developer's agent
session. The integration contract requires one approved in-house
`provider/model` and matching `NEXUS_OPENCODE_MODEL` and
`NEXUS_APPROVED_PROVIDER` values; `NEXUS_OPENCODE_CONFIG` may provide the
selected provider block. Credentials, endpoint details, and private config
remain outside Git.

Do not substitute the development Z.AI route for the company's in-house model,
claim provider success from a fixture or fake-process check, enable public
fallback, or infer Jira authorization from a local project filter. The
OpenCode adapter's temporary deny-all configuration is process/environment
isolation, not an OS or network sandbox. See the
[integration contract](INTEGRATION.md) and
[company onboarding guide](../guides/COMPANY_ONBOARDING.md) for the separate
provider, ACL, retrieval, and write gates.

## Verification routes

### Fresh fixture route

From the repository root, use the README's Python-only quickstart with a new
temporary state directory for every run. It exercises both independent local
surfaces without installing optional adapters or contacting external systems.

### Default local gates

```sh
python3 scripts/doctor.py
python3 -m unittest discover -s tests -v
git diff --check
```

The unittest suite covers synthetic Nexus behavior, fake OpenCode processes,
local RAG contracts/retrieval/context/evaluation, and optional-adapter error
paths. PostgreSQL conformance cases run only when
`NEXUS_RAG_PG_TEST_DATASOURCE` explicitly points to a disposable approved
database; report those live-local results separately from the default skips.
The fixture CLIs are boundary smokes, not replacements for the unit gate.

### Adapter and integration route

Run the relevant adapter-specific checks only after its dependency and
company-controlled endpoint/ACL decisions are recorded. Start with
[RAG deployment's local-first run](../guides/RAG_DEPLOYMENT.md#local-first-run-verify-before-touching-any-adapter),
then follow the specific OpenSearch, PostgreSQL, embedding, or reranker swap
section. Report fixture, fake-process, local-backend, real in-house-provider,
and real Jira results separately. A passing local suite never means provider
authentication, Jira visibility, production ACL, deployment, or publishing is
complete.

The latest verified status and remaining work live in the top of the root
[HANDOFF](../HANDOFF.md); older handoff entries are records, not a substitute
for current filesystem, Git, or runtime checks.

## Data and state handling

Fixtures are synthetic and publishable. Never put production VOC data, tokens,
raw text, prompts, provider responses, or credentials in Git, public artifacts,
or development-model requests. `.local/` state and CLI output may be sensitive
and are excluded from log collection; use a new temporary path for disposable
fixture runs and keep any company-side evidence inside approved systems.
