# OSS/VOC automation research

Research date: 2026-09-10. Scope is code, protocols, and templates actually
reusable in the current Python 3.9+ standard-library scaffold; only public
primary sources — repositories, manifests, LICENSE files, official
docs/APIs, and real template JSON — were checked. No package was installed
and no real Jira/LLM call was made. Below, "confirmed" means a fact read from
source, and "recommendation" means a judgment applying that fact to this
project's [product scope](PROJECT_OVERVIEW.md) and
[execution boundary](ARCHITECTURE.md).

## Conclusion

- **Currently adopted:** keep only the current `opencode run --format json`
  subprocess boundary, the stdlib/SQLite runtime, and the four shared local
  skills. Run one OpenCode process per evidence event, but do not treat a
  single process's stream — which may include auxiliary events/titles — as a
  contract of "exactly one provider HTTP request."
- **Not installed, future candidate:** `atlassian-python-api==5.0.4` is the
  leading candidate for a future Jira adapter, but it is not installed or
  adopted in implementation now, absent real ACL/auth/server flavor. This
  library provides JQL/issue/comment/Jira Service Management calls, but not
  ACL, an evidence cap, retry/dedupe, or a publish lifecycle.
- **Optional future evaluation:** when inspecting stored OpenCode results,
  consider `promptfoo==0.122.2` only inside an isolated Node 22+ eval job. It
  is not installed now, and n8n/Activepieces flows are referenced only for
  their deterministic-step/human-review design — no template code is
  imported.
- **On hold / rejected:** `pycontribs/jira==3.10.5` cannot be installed
  directly into the current Python 3.9 scaffold and has a separate object
  surface, so it is on hold for now — though this does not treat a Python
  floor change as a permanent prohibition. The OpenCode JS SDK/serve and
  Inspect AI are on hold due to separate lifecycle/operational overhead, and
  `mcp-atlassian==0.23.1` is rejected as a runtime connector due to its broad
  agent-facing surface, large dependencies, and history of security
  advisories.

## Candidate comparison

| Candidate | Confirmed source/version/license | Code/feature reusable now | Python 3.9/deployment burden and product fit | Decision |
|---|---|---|---|---|
| OpenCode CLI/headless | [CLI](https://opencode.ai/docs/cli/), [repo LICENSE](https://github.com/anomalyco/opencode/blob/dev/LICENSE), MIT. `run` is non-interactive execution, `--format json` is a raw JSON event stream, `serve` is a headless HTTP server, `acp` is stdin/stdout NDJSON. | The `run` boundary and JSON event parser already in use. Python continues to own evidence selection, deny-all, one process per event, and failure classification. | Node/provider configuration is an external runtime, and internal provider compatibility is not yet confirmed. The CLI stream still requires maintaining a completion parser directly, but this does not break the current Python boundary. | **Adopted/kept now** |
| OpenCode JS SDK/plugin | [SDK docs](https://opencode.ai/docs/sdk/), [SDK manifest](https://github.com/anomalyco/opencode/blob/dev/packages/sdk/js/package.json), [npm package](https://www.npmjs.com/package/@opencode-ai/sdk), [plugin docs](https://opencode.ai/v2/docs/plugins), npm latest `@opencode-ai/sdk@1.18.30` (2026-09-09 metadata), MIT. The SDK provides a typed client and JSON Schema structured output/retry. | A future Node service could reuse the typed API, schema output, and server event stream. `opencode serve`'s HTTP API can also be called from a Python client, so a Node bridge is not required. The plugin adds tools/hooks/agents, but none are needed now. | The SDK package itself cannot go into the Python runtime, but using serve over HTTP connects without a separate Node bridge. In exchange, a persistent server's health/auth/shutdown/timeout/log lifecycle must be operated, and maintaining both the CLI JSON parser and the SDK result/error boundary at once creates duplication. | **Optional dev use / on hold.** The existing CLI process is small enough for now. |
| `pycontribs/jira` | [repo](https://github.com/pycontribs/jira), [3.10.5 release](https://github.com/pycontribs/jira/releases/tag/3.10.5), [manifest](https://raw.githubusercontent.com/pycontribs/jira/3.10.5/pyproject.toml), [LICENSE](https://raw.githubusercontent.com/pycontribs/jira/3.10.5/LICENSE). BSD-2-Clause, released 2025-07-28, `requires-python >=3.10`; requests-family with optional extras. | Avoids rewriting the REST object API and issue/search/comment calls directly. | Cannot be installed directly into the current 3.9 scaffold, but the Python floor is not a permanent product constraint. The object API is broad and needs a thin facade plus a separate ACL/JQL allowlist; on hold for now since there is no smaller runnable slice. | **On hold.** Re-compare once the runtime/ACL contract is secured or the Python floor changes. |
| `atlassian-python-api` | [repo](https://github.com/atlassian-api/atlassian-python-api), [5.0.4 release](https://github.com/atlassian-api/atlassian-python-api/releases/tag/5.0.4), [setup.py](https://raw.githubusercontent.com/atlassian-api/atlassian-python-api/5.0.4/setup.py), [LICENSE](https://raw.githubusercontent.com/atlassian-api/atlassian-python-api/5.0.4/LICENSE). Apache-2.0, released 2026-08-28, `requires-python >=3.9`; JQL/enhanced JQL, issue/comment, and ServiceDesk modules are real, per the README. | The leading candidate for a future slice — once real ACL/auth and Jira server flavor are secured — to use `search_issues`, `get_issue`, `issue_get_comments`/JSM calls read-only behind our own Port. | Adds `requests`, `oauthlib`, `beautifulsoup4`, `jmespath`, `typing-extensions`, etc. Library auth is not an ACL determination, so server principal/issue security must be applied separately **before search and LLM calls**. Not installed now. | **Future leading candidate**, currently not installed/adopted. |
| `sooperset/mcp-atlassian` | [repo README](https://github.com/sooperset/mcp-atlassian/blob/v0.23.1/README.md), [0.23.1 release](https://github.com/sooperset/mcp-atlassian/releases/tag/v0.23.1), [manifest](https://raw.githubusercontent.com/sooperset/mcp-atlassian/v0.23.1/pyproject.toml), [config](https://github.com/sooperset/mcp-atlassian/blob/v0.23.1/docs/configuration.mdx), [tools reference](https://github.com/sooperset/mcp-atlassian/blob/v0.23.1/docs/tools-reference.mdx), [LICENSE](https://raw.githubusercontent.com/sooperset/mcp-atlassian/v0.23.1/LICENSE). MIT, released 2026-08-19, `requires-python >=3.10`; the tools reference lists 96 and the README lists 93 Jira/Confluence tools, with `READ_ONLY_MODE`, `ENABLED_TOOLS`, `JIRA_PROJECTS_FILTER`. | Can be referenced for its MCP wiring, tool filtering, and Jira/Confluence action implementation. | Requires a large dependency graph (anyio/httpx/mcp/fastmcp/pydantic/trio, etc.) and a separate server process. project filter/read-only is not a substitute for product ACL. A public advisory from 2026-07-10 records an HTTP auth bypass and server-local file read/upload issues ([advisory list](https://github.com/sooperset/mcp-atlassian/security/advisories), [auth bypass](https://github.com/sooperset/mcp-atlassian/security/advisories/GHSA-wrhw-j3f9-8vc6)). | **Rejected.** Not brought in as this product's deterministic adapter. |
| Promptfoo | [package manifest](https://raw.githubusercontent.com/promptfoo/promptfoo/main/package.json), [npm package](https://www.npmjs.com/package/promptfoo), [LICENSE](https://raw.githubusercontent.com/promptfoo/promptfoo/main/LICENSE), [config](https://www.promptfoo.dev/docs/configuration/guide/), [expected outputs](https://www.promptfoo.dev/docs/configuration/expected-outputs/), [offline FAQ](https://www.promptfoo.dev/docs/faq/). MIT, npm latest `0.122.2` (2026-08-28), Node `>=22.22.0`. | `promptfoo eval --model-outputs outputs.json --assertions asserts.yaml` applies deterministic assertions such as `equals`/`contains`/JSON to already-stored model results. It's an offline regression harness that never calls a provider, useful for repeating prompt/schema/evidence checks. | Not brought into the Python runtime. Needs Node 22 and a large npm dependency graph; even local-first, it is not a network firewall, so internal provider/egress must still be explicitly restricted. | **Future option, not installed now.** No runtime dependency or production VOC raw text allowed. |
| n8n | [source package](https://raw.githubusercontent.com/n8n-io/n8n/master/packages/cli/package.json), [latest stable release](https://github.com/n8n-io/n8n/releases/tag/n8n%402.38.5), [LICENSE](https://raw.githubusercontent.com/n8n-io/n8n/master/LICENSE.md), [docs](https://docs.n8n.io/). release `2.38.5` (2026-09-09), source `main` manifest is `2.39.0`, Node `>=24`; `LicenseRef-n8n-sustainable-use` is a fair-code/source-available term, not OSI OSS. | References only the **node design** of the official support-triage template's Jira query, dedupe, structured AI, and similar-issue/comment aggregation. | Requires Node 24 and considerable workflow runtime/credentials/DB operation. Because the template wires an LLM step and Jira read/update/comment nodes into one workflow, applying our ACL-before-search and "LLM never owns Jira tools" contract requires re-wrapping the flow. Internal business-use scope and redistribution/hosting terms under the license need separate review. | **Not adopted now**, design reference only. |
| Activepieces | [repo LICENSE](https://raw.githubusercontent.com/activepieces/activepieces/main/LICENSE), [release 0.90.4](https://github.com/activepieces/activepieces/releases/tag/0.90.4), [root manifest](https://raw.githubusercontent.com/activepieces/activepieces/main/package.json), [Docker Compose requirements](https://www.activepieces.com/docs/install/options/docker-compose), [Jira piece source](https://raw.githubusercontent.com/activepieces/activepieces/main/packages/pieces/community/jira-cloud/src/index.ts). Core is MIT, but `packages/ee` etc. carry a separate license. release 0.90.4 (2026-09-08), Bun monorepo; self-host Compose documents an app/worker/Postgres/Redis four-container setup. | Reuse/reference the Jira piece's `searchIssues`, issue/comment/transition, issue triggers, and flow template JSON format. | A much larger separate service than the current Python CLI, needing Postgres/Redis and webhook/secret operations. Only the MIT core scope was confirmed — the whole product is not assumed to be single-license MIT. Platform workflows can wire AI steps to Jira write steps, so our deterministic ownership/ACL boundary must be applied separately. | **Not adopted now**, template/piece design reference only. |

### Note on eval-tool alternatives

[Inspect AI's manifest](https://raw.githubusercontent.com/UKGovernmentBEIS/inspect_ai/main/pyproject.toml)
and [security docs](https://github.com/UKGovernmentBEIS/inspect_ai/blob/main/SECURITY.md)
were also checked. It is MIT, but `requires-python >=3.10`, and it explicitly
states that tasks/solvers/scorers can execute model-generated code and
commands, and that the local sandbox does not guarantee isolation. For the
current Python 3.9 deterministic regression, Promptfoo's stored-result
assertions are therefore the smaller fit; Inspect AI is re-evaluated only when
a separate isolated eval environment is built.

## Real VOC/support-ticket template review

### n8n: Jira support triage/resolution

- Official template description: [Automate support ticket triage and resolution with JIRA and AI](https://n8n.io/workflows/3868-automate-support-ticket-triage-and-resolution-with-jira-and-ai/).
- Read the public template API [JSON](https://api.n8n.io/api/templates/workflows/3868)
  and confirmed 27 `workflow.workflow.nodes` and 21 connections (no
  storage/execution/credential use). The real nodes include a Schedule
  Trigger, Jira `Get Open Tickets`, `Remove Duplicates/Mark as Seen`,
  structured LLM `Label, Prioritize & Rewrite`, a Jira update, similar
  resolved-issue search, comment collection, resolution summarization,
  `Attempt to Resolve Issue`, and Jira `Add Comment to Issue`.
- **Reusable part:** the step decomposition of our pipeline
  (collect → dedupe → normalize → similar evidence → summarize/recommend →
  human review) and the idempotency-marker design. **Not reusable:** the
  template's OpenAI/Jira credentials and an execution graph whose ACL,
  approval, and write ownership were never verified. Each template's
  author/usage terms were not separately confirmed, so importing the JSON
  into the product is never assumed to resolve licensing.

### Activepieces: HubSpot customer support ticketing

- The official template API [JSON](https://cloud.activepieces.com/api/v1/templates/miLjdP1BihsBes8EzexpT)
  returns the real flow for `Customer Support Ticketing` (author `Activepieces
  Team`, updated `2025-12-28`). It is an end-to-end structure of
  `new_ticket` trigger → AI rewrite → AI category (Sales/Tech/Customer
  Support) → router → per-assignee Slack direct message, and the piece/
  version, prompt, branch condition, and connection placeholders were
  confirmed directly in the JSON.
- The official [Jira Cloud piece](https://raw.githubusercontent.com/activepieces/activepieces/main/packages/pieces/community/jira-cloud/src/index.ts)
  also provides `createIssue`, `updateIssue`, `searchIssues`, comments,
  transition, and new/updated issue triggers as real source.
- **Reusable part:** the trigger/action mapping, schema/branch format, and
  human-notification step. **Not reusable:** the template's `gpt-4o`,
  connection IDs, recipient IDs, and the policy of wiring AI steps to
  external write steps without ACL/approval. This template is neither
  execution verification nor proof of internal ACL, and no real provider/
  Jira call was made during this research.

Both templates are commercial automation examples with "a real flow artifact"
— they are not a production-ready implementation for this project or a
guarantee of OSS licensing. Both must sit behind our static adapter/
verifiable proposal in our architecture, leaving automatic Jira writes as a
separate, approved integration slice.

## SDK vs. subprocess, and the in-house LLM/ACL boundary

The CLI the current adapter uses emits raw JSON events, so Python must judge
process lifecycle, timeout, malformed/truncated streams, error events, and
terminal completion. This is a completion-parser maintenance cost, but it is
a single boundary that avoids adding a persistent service to the Python 3.9
scaffold.

The OpenCode SDK's structured output provides schema validation and default
retry, so a future service could reduce parser duplication. Python can call
the `opencode serve` HTTP API directly, so a Node bridge is not required, but
doing so adds the health/auth/shutdown/timeout/log lifecycle of a persistent
server to operate. Therefore **the CLI is kept for now**, switching to
serve/SDK as a single-call boundary only once that lifecycle cost needs to be
justified. Even if the SDK is adopted, the OpenCode plugin does not add Jira
tools.

Whether the internal LLM endpoint/model configuration is compatible with the
OpenCode provider contract was not confirmed by this research alone. Until a
real ACL/principal is obtained, the connector never interprets any project
filter as authorization, and Jira body text/search results are treated as
untrusted data that may carry prompt injection. That is, the allowed order is
`trusted principal/ACL → Jira query/filter → evidence cap → heuristic
OpenCode call → schema/evidence validator`, and the only stage allowed to call
OpenCode is the heuristic step — for example, semantic symptom/remediation
sentences.

## Minimal probes for the next implementation

This document change makes no package install, external call, or code
change. The current commit has no runnable Jira adapter; the items below run
in a separate integration slice once real ACL/auth/server flavor is secured.

1. Pin `atlassian-python-api==5.0.4` as an optional extra and start
   `JiraPort` as read-only `search_issues/get_issue/get_comments`. Using fake
   HTTP/session fixtures, verify that the ACL/JQL allowlist runs before the
   library call, and that pagination and 429/5xx bounded retry plus the event
   marker work. Do not put write methods in the Port. Do not start this step
   without a real connection contract.
2. Add synthetic OpenCode `--format json` event fixtures that regress every
   terminal path — success/error/timeout/malformed/truncated — through the
   existing parser. Pass both the current evidence and no-evidence branches
   without any real provider/Jira call.
3. Feed only stored proposal/model output into `promptfoo@0.122.2` inside an
   isolated Node `>=22.22.0` job, asserting allowed labels, max
   recommendations, known evidence ID, token overlap, and the empty-evidence
   no-call behavior. Never put production raw text, tokens, or prompt secrets
   into Promptfoo output — use fixtures.
4. Do not import n8n/Activepieces templates; reproduce only the needed steps
   as Mermaid/fixtures. Pass a separate ACL/reconciliation/approval contract
   and license inventory only once a real connector/Jira write is actually
   needed.

## What the current scaffold changes before commit

This docs-only pass does not change the runtime. This document and the
current baseline can be committed first; only in a later, separate
integration slice — once real ACL/auth/server flavor is ready — will we (a)
keep the synthetic `project ==` boundary, explicitly stated as not a
production ACL, unchanged; (b) evaluate `atlassian-python-api` as an optional
thin adapter; and (c) keep the OpenCode subprocess parser and the no-evidence
provider skip. `pycontribs/jira`, `mcp-atlassian`, the n8n/Activepieces
runtime, Inspect AI, and the OpenCode plugin/SDK are not added to
`pyproject.toml`'s default dependencies now.

When a dependency is actually adopted, preserve the MIT/BSD-2-Clause/
Apache-2.0 notice alongside the lock/manifest, and — as with
Activepieces/n8n, where the whole product's license is not a single
permissive OSS license — record the subtree and distribution scope. The
versions/release dates in this document reflect publicly available sources
as of the research date; re-check the release/manifest and transitive
licenses again right before the implementation PR.
