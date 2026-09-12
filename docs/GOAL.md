# Original scaffold goal — 2026-09-10

This is the original scaffold acceptance record, not the current task list.
For current status and remaining work, start at the latest entry in
[HANDOFF.md](../HANDOFF.md).

Original request: review the overview and autonomously assemble a lightweight
harness/skills/rules, completing scaffolding, verification, record-keeping,
and commit/push.

| Completion condition | How to verify |
| --- | --- |
| Lightweight tooling selected | Candidates, rationale, and adopt/hold decisions in `TOOLING_DECISION.md` |
| Static/heuristic role separation | `ARCHITECTURE.md` and the actual execution code |
| Skills/rules installed | `scripts/doctor.py` succeeds, `CLAUDE.md -> AGENTS.md` |
| Local flow runs | Synthetic event → evidence → validated comment/label proposal CLI |
| Failure/dedupe protection | ACL, evidence, failure-stream, and replay verification in unittest |
| Independent review | Orca Grok 4.6 high or GLM 5.3 high results and recorded actions taken |
| Docs/handoff organized | `INDEX.md`, operational contract, root `HANDOFF.md` |
| Stored and shared | Confirmed match between verified commits and the origin push |

Additional gate: research into reusable open source's actual source, license,
dependencies, and integration cost is recorded in `OSS_RESEARCH.md`, and the
current tooling decision reflecting that result is finalized in
`TOOLING_DECISION.md`. The current commit adds no Jira/Promptfoo/framework
dependency or runnable adapter; those are re-evaluated in a separate
integration slice once real ACL/auth/server flavor is available.

Real Jira publishing/deployment and real in-house provider quality
verification are a later slice, once integration information is secured. For
this goal, passing the synthetic fixture is not treated as operational
completion. Progress and remaining work are updated only in `HANDOFF.md`.
