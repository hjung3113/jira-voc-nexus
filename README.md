# Jira VOC Nexus

`Jira VOC Nexus` is intended to connect in-house Jira VOC with past resolution
cases and prepare recommendations for human review. The product direction and
future MVP are described in the [project overview](docs/PROJECT_OVERVIEW.md);
the current repository is a pair of independent local Python surfaces, not a
connected Jira service.

Start with the [quickstart](#python-only-fixture-quickstart),
[development guide](docs/DEVELOPMENT.md), or
[company onboarding guide](guides/COMPANY_ONBOARDING.md).
The [documentation index](docs/INDEX.md) connects each task to its code and tests.

## What is in this checkout?

### `nexus/`: local proposal-generation scaffold

The `nexus` CLI reads normalized event and corpus JSON files supplied by the
caller, validates them, applies a synthetic same-project filter, retrieves up
to five lexical evidence documents, validates an audience-split proposal, and
stores the result in local SQLite. The default `fixture` engine is deterministic
and demo-only. The optional `opencode` engine runs only when an explicitly
approved provider configuration is supplied; it does not give the model Jira,
search, or write tools.

This path is file-based and local. It is not an HTTP/webhook server, Jira
ingress, production ACL, RAG connection, or Jira comment/label writer. Every
current result is `dry_run=true`, `published=false`, and `state="prepared"`.
The fixture `project == event.project` comparison is a leak-prevention check
for synthetic data, not authorization for a real principal.

### `rag/`: standalone local retrieval toolkit

The `rag` package is a separate proof-of-concept for indexing, querying, and
evaluating synthetic knowledge fixtures. Use the executable
[quickstart below](#python-only-fixture-quickstart) for `index`, `query`, and `eval`.

It is not wired into `nexus`: the Nexus command does not read `fixtures/rag`,
and the RAG command does not create a Nexus proposal or SQLite replay record.
The local RAG CLI uses an `AllowAllAcl` over one already-authorized fixture
corpus, has no Jira ingress or write path, and makes no network calls. The
repository contains code-level seams for optional OpenSearch, PostgreSQL, and
BGE adapters, but those seams are not an adopted production deployment.

## Python-only fixture quickstart

Run from the repository root in a POSIX shell (for example, bash or zsh).
Python 3.9+ and the standard library are enough for this local path. No package
installation, OpenCode process, agent session, optional RAG extra, provider, or
network access is required. Create a new temporary state directory each time;
do not reuse a prior `.local/` database when checking the fixture boundary.

```sh
smoke_dir="$(python3 -c 'import tempfile; print(tempfile.mkdtemp(prefix="jira-voc-nexus-"))')"

python3 -m nexus \
  --event fixtures/event.json \
  --corpus fixtures/corpus.json \
  --state "$smoke_dir/nexus.sqlite3" \
  > "$smoke_dir/nexus.json"
cat "$smoke_dir/nexus.json"

python3 -m rag index \
  --fixtures-dir fixtures/rag \
  --state "$smoke_dir/rag/state.json"
python3 -m rag query \
  --state "$smoke_dir/rag/state.json" \
  --text "4107 오류" \
  --error-code 4107
python3 -m rag eval \
  --fixtures-dir fixtures/rag \
  --golden fixtures/rag/golden_set.json
```

The Nexus JSON should contain `"engine": "fixture"`, `"demo_only": true`,
`"dry_run": true`, `"published": false`, and `"state": "prepared"`. The RAG
commands should index the synthetic corpus, print context containing the
matching historical problem and resolution, and print the five local variant
rows. These are fixture/runtime checks only; they do not prove Jira access,
company ACL behavior, provider success, OpenSearch, PostgreSQL, BGE, or product
adoption.

## Fresh fixture comment (v2)

The following is the current `result["comment"]` from the default fixture
engine using `fixtures/event.json` and `fixtures/corpus.json` with a fresh
state file. Comment and issue rendering are documented in
[docs/TEMPLATES.md](docs/TEMPLATES.md); v1 is historical and no longer
produced for new events.

```text
VOC triage recommendations (dry-run):

Customer reply:
Fixture demo only: the card issue has prior resolved guidance in PAY-42 that may answer the customer.

Engineering action:
Fixture demo only: review the resolved guidance for PAY-42 concerning card.

Evidence:
- PAY-42: https://jira.example.local/browse/PAY-42

Labels: audience-coverage:both, possible-duplicate
Recipients: user-support, dev-team

voc-nexus-comment|v2|event-001
```

## Current execution boundary

- Python owns input normalization, the synthetic fixture filter, lexical
  retrieval, evidence limits, proposal validation, comment rendering, and
  SQLite replay.
- The fixture engine never calls a model. With evidence, the OpenCode adapter
  runs one process for a new event; auxiliary work may result in more than one
  HTTP request to the same approved model, so request count and cost require
  real internal measurement. With no evidence, no provider process starts.
- The event ID is the local replay key. The same ID and event payload reuse the
  stored result; the same ID with a changed payload fails as a conflict. The
  corpus is not part of that identity, so a corpus or logic change needs a new
  event ID/version policy.
- Real Jira ingestion, trusted principal/ACL resolution, Nexus↔RAG wiring,
  automatic writes, webhook/queue delivery, and feedback indexing remain
  future integration work. See the [operational integration contract](docs/INTEGRATION.md).

## Optional adapters and agent tools

The local fixture quickstart has no optional Python dependencies. Install only
the extra needed for a separately justified RAG adapter:

| Extra | Packages | Used by |
| --- | --- | --- |
| `rag-platform` | `opensearch-py` | `rag.retrieval.OpenSearchBackend` |
| `rag-pg` | `psycopg[binary]` | `rag.registry_pg.PostgresKnowledgeRegistry` |
| `rag-reranker` | `torch`, `transformers` | `rag.retrieval.BgeRerankerAdapter` |

For example, an adapter environment may install
`python3 -m pip install -e ".[rag-platform]"`; local fixture mode does not
need it. OpenCode is an external executable used only by `nexus --engine
opencode` after provider configuration is approved. Orca, the project skills
under `.agents/skills/`, and their linked agent tooling coordinate development;
they are not Nexus or RAG runtime dependencies. See
[development and verification](docs/DEVELOPMENT.md) for setup boundaries and
the [documentation index](docs/INDEX.md) for task-oriented routes.

```text
nexus/           local event/corpus proposal path and SQLite replay
rag/             standalone local retrieval, context, registry, and eval path
tests/           synthetic regression tests for both paths
fixtures/        publishable synthetic Nexus and RAG inputs
scripts/         read-only local development checks
docs/            scope, contracts, decisions, and historical research records
guides/          RAG operations/evaluation and company-internal preparation
.agents/skills/  canonical shared project skills
AGENTS.md        repository agent rules
HANDOFF.md       current status and remaining work
```

[docs index](docs/INDEX.md) · [goal record](docs/GOAL.md) ·
[design review](docs/REVIEW.md) · [tooling decision](docs/TOOLING_DECISION.md) ·
[OSS research](docs/OSS_RESEARCH.md)
