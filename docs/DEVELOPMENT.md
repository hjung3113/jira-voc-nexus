# Development environment and verification

## Chosen tooling

- Python 3.9+ stdlib: input normalization, lexical retrieval, proposal
  validation, SQLite state, CLI. No Jira/Promptfoo/framework package is
  currently installed; only the fixture runs.
- OpenCode native CLI headless: an adapter that runs one process per evidence
  event once an approved in-house provider is ready. Auxiliary events/titles
  within a single process stream are not counted as separate provider
  requests, and a developer's default provider configuration is never used as
  the production configuration.
- Orca CLI + orchestration: used only to coordinate supervised work.
- Canonical project skills: `orca-cli`, `orchestration`, `voc-slice`,
  `voc-workflow` under `.agents/skills/`; `.claude/skills`, `.opencode/skills`,
  `.omp/skills` are links pointing to them.

Global shell configuration, other repositories, tool versions/auth, and
Jira/MCP connections are never changed automatically.

## Installed vs. not-yet-installed candidates

The current run only needs the Python standard library, SQLite, the existing
OpenCode CLI, and the four shared local skills. `atlassian-python-api==5.0.4`
is a future Jira adapter candidate to reconsider once real ACL/auth/server
flavor is secured; it is not installed or adopted now. Promptfoo `0.122.2` is
likewise only an optional future eval candidate for stored results and is not
installed, nor are pycontribs/jira, mcp-atlassian, Pydantic AI, LangGraph,
n8n, or the Activepieces runtime added.

Python 3.9 is the current scaffold's compatibility floor, not a permanent
runtime constraint of the product. Tooling will be re-evaluated once real
connection work and operational grounds justify a different Python floor or
service lifecycle. The current model preference for when a real provider is
needed is Z.AI's `zai/glm-5.3`; OpenRouter credentials or private config are
never put in the repository.

## Verification commands

```sh
python3 scripts/doctor.py
python3 -m unittest discover -s tests -v
python3 -m nexus --event fixtures/event.json --corpus fixtures/corpus.json --state .local/demo.sqlite3
git diff --check
```

`doctor.py` is a read-only **environment check** confirming the Python
version, executable presence, skill/symlinks, and repository entry files. It
does not verify provider authentication and does not run the runtime or tests
in its place. unittest is the **runtime gate** for replay/ACL/failure-
response/grounding behavior, and the fixture CLI is a smoke test at the file
boundary. Neither proves real provider or Jira success. This docs pass does
not run tests; the final test count and results are updated by the
coordinator after a narrow runtime review.

Feeding the same event to the CLI again reuses the stored SQLite result. A
conflict must occur when the event ID stays the same but the payload changes;
a corpus change is not part of event identity. An intentional update uses a
new event ID/version.

## Separation of local and production

The fixture corpus is publishable synthetic data. Real VOC data, tokens, raw
text, prompts, and provider responses are never sent to Git, external models
used for development, or public artifacts. `.local/` state and CLI output can
be sensitive and are excluded from log collection.

The current final runtime gate and real in-house connection verification are
recorded in [HANDOFF](../HANDOFF.md).
