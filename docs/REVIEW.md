# Final code review and adjudication — 2026-09-10

This review records the bounded fixes made after the read-only review in
`.local/review-final.md`.  The installed binary reported
`opencode --version` = `1.18.21`; the OpenCode source links below are the exact
`v1.18.21` release.  No provider, Jira, or external integration call was made.

## Finding adjudication

### 1 — Accepted with a bounded fail-closed fix (medium)

OpenCode merges configuration sources rather than replacing them: its merge
helper concatenates arrays and instructions, and managed configuration is
loaded after injected config content.  The [config merge and source-order
code](https://github.com/anomalyco/opencode/blob/v1.18.21/packages/opencode/src/config/config.ts#L37-L47)
and [managed-source loading
code](https://github.com/anomalyco/opencode/blob/v1.18.21/packages/opencode/src/config/config.ts#L370-L495)
confirm that the injected overlay cannot claim to clear ambient configuration.

The adapter now refuses to start when a known OpenCode managed source exists:
the [managed-path implementation](https://github.com/anomalyco/opencode/blob/v1.18.21/packages/opencode/src/config/managed.ts#L18-L60)
defines the macOS, Linux, and Windows paths checked by the preflight.  This is
a presence check, not an assertion that the source is harmless; unreadable
paths also fail closed.  The adapter intentionally does not add
`OPENCODE_DISABLE_GLOBAL_CONFIG`: the [1.18.21 flag
definition](https://github.com/anomalyco/opencode/blob/v1.18.21/packages/core/src/flag/flag.ts#L376-L488)
does not define that flag.  It also does not add empty `mcp`, `plugin`, or
`instructions` values and claim that they erase merged sources.

The existing environment whitelist, temporary HOME/XDG directories, project
config disable flag, and deny-all injected permissions remain.  A regression
test verifies that a detected managed source prevents the runner from being
invoked.

### 2 — Accepted (medium)

The request contract now uses the legal label example `possible-duplicate`
instead of the invalid combined string `needs-triage|possible-duplicate`.
The [request contract](../nexus/opencode.py) and
[regression test](../tests/test_nexus.py) parse the request and assert that
its example labels are a subset of `ALLOWED_LABELS`; proposal validation
remains the final boundary.

### 3 — Rejected; fail-closed behavior retained (medium)

The review's suggestion to accept an omitted completion reason is not
supported by the exact installed release.  OpenCode's [V1
`StepFinishPart` schema](https://github.com/anomalyco/opencode/blob/v1.18.21/packages/schema/src/v1/session.ts#L212-L235)
requires a `reason` string, and the [JSON run command](https://github.com/anomalyco/opencode/blob/v1.18.21/packages/opencode/src/cli/cmd/run.ts#L643-L712)
emits the finish part as-is.  Therefore a missing reason is not unambiguously
successful: the parser continues to require `reason == "stop"`, and a
regression test confirms that the missing-reason stream fails closed.

### 4 — Accepted (low)

Runtime config publication now writes a temporary file with mode `0600`,
flushes and fsyncs it, and atomically publishes it with `os.replace`.  The
[runtime config implementation](../nexus/opencode.py) and
[fake-runner regression test](../tests/test_nexus.py) observe the final file
mode while the child would run.  Provider credentials are still not copied
from the parent environment; an explicitly supplied approved provider block
remains subject to the local configuration contract.

### 5 — Accepted (low)

Retrieval and proposal-validation comments now call the equality check a
synthetic fixture project filter and explicitly state that production ACL
enforcement belongs to the integration adapter before retrieval.  The local
filter behavior is unchanged, as shown by the [retrieval implementation](../nexus/retrieval.py)
and [cross-project regression test](../tests/test_nexus.py), while the
comments no longer describe the client-supplied project field as a trusted
production authorization basis.

## Existing contracts that remain in force

- OpenCode output parsing fails closed on empty, malformed, direct-object,
  error, truncated, incomplete, tool, and trailing streams.
- Evidence IDs must belong to the retrieved synthetic-fixture evidence, and
  recommendations must pass the conservative lexical grounding check.
- SQLite replay uses `event_id` plus the canonical event-payload fingerprint;
  changed payloads conflict and concurrent same-event producers invoke the
  engine once.
- The public result remains a local dry-run (`dry_run: true`,
  `published: false`, `state: "prepared"`).

## Verification boundary

The unit suite and fixture CLI are local checks only.  They do not prove a
live provider, Jira webhook/ACL, Jira write adapter, or managed-device
deployment; those require a separate integration slice with an explicit
trusted principal and approved endpoint.
