# Operational integration contract

What is currently provided is a local proposal-generation scaffold. The CLI
is a local execution boundary that reads files; it is not a webhook server or
internet ingress. A webhook server, real-time queue, real RAG, Jira write, and
feedback indexing are not yet connected.

No Jira connector, Promptfoo, or framework dependency is currently installed.
`atlassian-python-api==5.0.4` is a future read-only adapter candidate to
reconsider once real ACL/auth and Jira server flavor are secured, and
Promptfoo is an optional future tool to consider only for evaluating stored
results. n8n/Activepieces were referenced only for their flow-step,
deterministic-branch, and human-review design — no template code or
credentials were imported.

## Input/search contract

A real Jira adapter uses infrastructure-verified webhooks and a trusted
service principal to build the following normalized event: `event_id`,
`issue_key`, `project`, `summary`, `description`, `labels`. Even though the
current CLI validates this structure, it is never treated as evidence of
principal or ACL.

Search candidates must provide at least `id`, `project`, `title`, `text`,
`resolved`, `url`. `text` must include the source-derived actual remediation
and outcome, and must not be replaced with a mere status description.
`resolved` is a ranking/selection hint, not proof of factual accuracy. In the
real environment, the principal/issue ACL obtained by the server is applied
before search and prompt assembly, and search results are re-verified as
well. A candidate that is not readable within the comment's visibility scope
is never cited.

The first operational slice is limited to past Jira issues whose permission/
provenance contract is closed. The wiki and code graph are connected only
after securing the same ACL, source identity, and retention policy.

## Proposal/model contract

A proposal has only `recommendations` and `labels`. A recommendation has only
`text` and `evidence_ids`, allowing at most 5 recommendations, at most 2,000
characters of recommendation text, and 1 to 5 unique evidence IDs per item.
Evidence IDs must already be present in the ACL-filtered top-5 result, and the
label allowlist is only `needs-triage` and `possible-duplicate`. The
validator checks JSON shape, bounds, duplicates, source membership, and
conservative lexical grounding.

When there is no evidence, no provider process is started, and a
`needs-triage` proposal is produced instead. Exactly one OpenCode process
runs per new event with evidence. Auxiliary work such as titling may cause
multiple HTTP requests to the same approved model, so the actual count and
cost must be measured. Semantic rerank is not currently a separate stage.
The model is given no Jira/search/write tools. Model errors, timeouts,
truncated streams, and schema/evidence shortfalls are treated as failure or
hold, and public provider fallback, unbounded retry, and automatic escalation
to a costlier model are prohibited.

The production provider configuration is injected by the deployment
environment.

- `NEXUS_OPENCODE_MODEL`: an approved `provider/model` value
- `NEXUS_APPROVED_PROVIDER`: the approved provider, which must exactly match
  the model prefix
- `NEXUS_OPENCODE_CONFIG`: a runtime JSON configuration file holding only the
  selected provider

The adapter leaves only the one approved provider plus `enabled_providers`,
`small_model`, `share: disabled`, deny-all permission for the global and
`voc-triage` agent, and an agent prompt that ignores untrusted input in the
temporary runtime config. The child process is given `OPENCODE_CONFIG` and
`OPENCODE_CONFIG_CONTENT` pointing at the temporary runtime config, and
project/default/skill/model-fetch/share are disabled. The real endpoint,
model ID, credential injection method, session/log retention, and provider
containment are verified in the actual provider-connection slice. No
arbitrary value or certificate is put in code or docs for now.

## Jira comment/label adapter completion conditions

1. Assign the validated proposal a stable operation key based on the
   event/workflow version.
2. Query the comment marker before posting to prevent duplicate posts. The
   marker format is comment format v1's `voc-nexus-comment|v1|<event_id>`
   (issue: `voc-nexus-issue|v1|<event_id>`); see
   [docs/TEMPLATES.md](TEMPLATES.md) for the exact render and examples. The
   same `event_id` always produces the same marker, so querying the marker
   before posting is itself the dedupe lookup.
3. Record a lost publish response as `unknown`, and do not repost until
   confirmed by a marker lookup.
4. Store the comment ID and success status, preserving existing labels while
   only adding from the allowlist.
5. A label-failure retry must not repost the comment. 429/5xx get bounded
   backoff; 401/403 are classified as an operational error.
6. Multiple workers atomically acquire task ownership in the DB. Test the
   uncertainty between the external Jira effect and the DB transaction.

This is the acceptance contract for the next integration slice; the current
CLI provides neither a publish feature nor a publish-success status. In the
current environment, without a provider and Jira, only fixture verification
is performed, and it is never reported as a successful connection.
