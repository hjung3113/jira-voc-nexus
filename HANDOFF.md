# Jira VOC Nexus handoff — 2026-09-10

## Current state

- The OSS/VOC reuse research gate is satisfied and recorded in
  [docs/OSS_RESEARCH.md](docs/OSS_RESEARCH.md) and
  [docs/TOOLING_DECISION.md](docs/TOOLING_DECISION.md).
- The baseline is Python 3.9+ stdlib/SQLite, the existing OpenCode native CLI,
  and the four shared local skills (`orca-cli`, `orchestration`, `voc-slice`,
  `voc-workflow`).
- Jira connector, Promptfoo, Pydantic AI/LangGraph, and n8n/Activepieces
  runtime are not installed. `atlassian-python-api==5.0.4` remains a future
  candidate for after real ACL/auth/server flavor exists; Promptfoo is an
  optional future eval for stored results.
- The CLI is a file-input local proposal scaffold. It provides no production
  ingress, Jira ACL/adapter, webhook, RAG, or write reconciliation. It runs one
  OpenCode process per event with evidence and skips the provider process when
  there is no evidence.
- **Format contract v1 landed** (this session): `render_comment` now emits
  header / recommendations / sorted Evidence / sorted Labels / final
  `voc-nexus-comment|v1|<event_id>` marker, and the new `render_issue` renders
  the escalation issue template (`[VOC] ` summary ≤ 80 chars, structured
  description, `voc-nexus-issue|v1|<event_id>` marker) exposed as the additive
  `issue` key in the public result. Exact templates, real examples, event/corpus
  input contracts, and the label taxonomy live in
  [docs/TEMPLATES.md](docs/TEMPLATES.md). The markers are the dedupe lookup
  keys required by [docs/INTEGRATION.md](docs/INTEGRATION.md) completion
  condition 2; renderers fail closed on `event_id` values containing `|` or
  newlines so markers stay single-line and unambiguous.
- Repo docs and agent rules are now English (AGENTS.md, README.md, all of
  docs/). `CLAUDE.md` remains a relative symlink to AGENTS.md.
- Replay caveat: an event first processed before format v1 keeps its
  originally stored comment/result when replayed (replay identity is
  `event_id` + payload fingerprint and does not include the renderer version).
  A fresh state file or a new event ID renders the new format. A future
  re-render policy is an open integration question, not a local bug.

## Verification (2026-09-10, by coordinator)

- `python3 -m unittest discover -s tests -v`: **20/20 passing** — includes the
  format-contract suite (marker-last, section order, sorted Evidence/Labels,
  79/80/81 summary boundary, URL-gate omission in both renderers, marker-safe
  `event_id` rejection, frozen public key set) plus the pre-existing
  fail-closed, replay-conflict, concurrency, and cross-project regressions.
- Fixture CLI smoke on a fresh state file: exit 0, `dry_run: true`,
  `published: false`, labels `["possible-duplicate"]`, comment and issue
  description both end with their `v1` markers.
- `python3 scripts/doctor.py`: all environment checks true (read-only by
  design; provider auth deliberately not checked).
- `git diff --check` clean; every relative link in AGENTS.md/README.md/docs/
  resolves; no Korean prose remains outside this-file-history.
- Review provenance: Grok 4.6 read-only review (1 high + 4 medium + 4 low
  findings) adjudicated and applied by the coordinator — the high finding
  (issue URL-gate test could not catch a leak) and all medium findings are
  fixed; the low doc findings (optional-Evidence skeletons, taxonomy wording)
  are fixed too.

## Orchestration record

- Run `run_d3f2ef5e6141`: impl task `task_8ad9817155f7` (Claude Sonnet 5
  medium; Codex was quota-blocked until 05:29 and the OMP injection path
  stalled on OMP's paste dialog), translation task `task_42a9c1038f8e` (same
  terminal, reused), review task `task_fb8db1150610` (Grok 4.6; prompt had to
  be submitted manually because its telemetry overlay blocked the injected
  Enter). All dispatches settled and terminals released.

## Next steps

- Real Jira/provider connection is a separate slice after the ACL/auth/server
  contracts in [docs/INTEGRATION.md](docs/INTEGRATION.md) are met. The write
  lifecycle will consume the TEMPLATES.md formats and marker contract.
- Coordinator commits/pushes this state; no runnable Jira adapter and no new
  required dependency are in this commit.
