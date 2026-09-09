# Comment/Issue Templates (v1)

This document defines the exact output contract for `nexus/proposals.py`'s
`render_comment` and `render_issue`, the input contract those renderers
consume (`nexus/models.py`'s `parse_event`/`parse_corpus`), and the label
taxonomy. It is the reference other agents and the company-side producer
should match; the renderers themselves are the source of truth if this
document and the code ever disagree — file a fix here, not a code change to
match stale prose.

## 1. Comment format v1

`render_comment(proposal, evidence, event_id)` returns a single string with
this structure, in this exact order:

```text
VOC triage recommendations (dry-run):

<recommendation bullets, or the no-recommendation line>
[blank line]
Evidence:  ← optional: only when a cited URL passes the gate
<sorted "- <id>: <url>" bullets>
[blank line]
Labels: <sorted labels, comma+space joined>
[blank line]
voc-nexus-comment|v1|<event_id>
```

- The `Evidence:` block only appears when at least one cited source's URL
  passes the `_safe_http_url` gate (`http`/`https` scheme, has a netloc, no
  control/whitespace characters, at most 4,000 chars). A source whose URL
  fails the gate is silently omitted from `Evidence:` — it is never partially
  rendered.
- The `Labels:` line always appears, even when `labels` is empty (it then
  reads `Labels: `).
- The marker line is always the **last** line of the string and never has a
  trailing newline.

### Real example

Rendered from `fixtures/event.json` (`event_id: event-001`) and
`fixtures/corpus.json` via the default fixture engine:

```text
VOC triage recommendations (dry-run):

- Review the resolved guidance for PAY-42 concerning card.

Evidence:
- PAY-42: https://jira.example.local/browse/PAY-42

Labels: possible-duplicate

voc-nexus-comment|v1|event-001
```

When there is no evidence (and therefore no recommendation), the body line is
replaced and the `Evidence:` block is omitted entirely:

```text
VOC triage recommendations (dry-run):

No grounded recommendation found; manual triage required.

Labels: needs-triage

voc-nexus-comment|v1|event-001
```

### Marker purpose

The final line, `voc-nexus-comment|v1|<event_id>`, is the **dedupe lookup
key** for a future Jira comment adapter. It is deterministic: the same
`event_id` always renders the same marker string, regardless of proposal
content. [docs/INTEGRATION.md](INTEGRATION.md) completion condition 2 requires
querying this marker before posting a comment, precisely to prevent duplicate
posts when a producer retries or replays the same event. The marker format is
versioned (`v1`) so a future format change can coexist with old markers
already posted to Jira. The renderers reject an `event_id` containing `|`,
newline, or carriage return (`ProposalValidationError`, fail-closed) so the
marker always stays a single unambiguous line; producers should emit
`[A-Za-z0-9._-]`-style ids.

## 2. Issue format v1

`render_issue(event, proposal, evidence)` returns a dict with exactly three
keys: `summary`, `description`, `marker`.

**This is a template only.** The current CLI never publishes issues — there
is no write adapter yet. A future write lifecycle would use this template to
create Jira issues once the completion conditions in
[docs/INTEGRATION.md](INTEGRATION.md) are met.

### `summary`

`"[VOC] " + event.summary`, NFKC/whitespace-normalized (via the same
`normalize_text` used for input normalization — this also collapses any
newline in the summary to a single space), then truncated so the **whole**
string, prefix included, is at most 80 characters. Truncation is a plain
character-count cut at 80; it does not try to break on a word boundary.

### `description`

Built from five sections, always in this order:

```text
Context:

- event_id: <event.event_id>
- issue_key: <event.issue_key>
- project: <event.project>

Recommendations:
<recommendation bullets, or the no-recommendation line>

Evidence:  ← optional: only when a cited URL passes the gate
<sorted "- <id>: <url>" bullets>
[blank line]
Labels: <sorted labels, comma+space joined>

voc-nexus-issue|v1|<event_id>
```

- The `Evidence:` section is present only when at least one cited source's
  URL passes the `_safe_http_url` gate — same rule and same omission
  behavior as the comment format.
- `marker` is the exact same string as the description's last line
  (`voc-nexus-issue|v1|<event_id>`), returned separately so a caller does not
  have to parse it back out of `description`.

### Real example

```json
{
  "summary": "[VOC] Checkout card payment timeout",
  "description": "Context:\n\n- event_id: event-001\n- issue_key: VOC-100\n- project: PAY\n\nRecommendations:\n- Review the resolved guidance for PAY-42 concerning card.\n\nEvidence:\n- PAY-42: https://jira.example.local/browse/PAY-42\n\nLabels: possible-duplicate\n\nvoc-nexus-issue|v1|event-001",
  "marker": "voc-nexus-issue|v1|event-001"
}
```

## 3. Event input contract

`nexus/models.py`'s `parse_event` accepts a JSON object with **exactly** these
six fields — no more, no fewer:

| field | type | rules |
| --- | --- | --- |
| `event_id` | string | non-empty after normalization, max 500 chars |
| `issue_key` | string | non-empty after normalization, max 500 chars |
| `project` | string | non-empty after normalization, max 200 chars |
| `summary` | string | non-empty after normalization, max 10,000 chars |
| `description` | string | may be empty, max 50,000 chars |
| `labels` | list of strings | each non-empty after normalization, max 200 chars per label, max 100 labels total |

Every string field goes through `normalize_text`: NFKC Unicode
normalization, then all whitespace runs (including newlines) collapsed to a
single space, then stripped. Any string containing a control character other
than tab/newline/carriage-return is rejected outright before normalization.
A company-side producer must send event JSON matching this exact field set —
an unknown or missing field raises `InputError` and the event is rejected
before retrieval or any model call.

## 4. Corpus input contract

`parse_corpus` accepts a JSON list (max 10,000 items) of objects, each with
**exactly** these six fields:

| field | type | rules |
| --- | --- | --- |
| `id` | string | non-empty after normalization, max 500 chars, unique within the corpus |
| `project` | string | non-empty after normalization, max 200 chars |
| `title` | string | non-empty after normalization, max 10,000 chars |
| `text` | string | may be empty, max 100,000 chars |
| `resolved` | boolean | must be a JSON boolean, not a truthy string/number |
| `url` | string | may be empty, max 4,000 chars |

The same control-character rejection and `normalize_text` pass applies to
every string field. A duplicate `id` within the same corpus payload raises
`InputError`. `resolved: true` is a ranking/selection hint used by the
fixture heuristic and lexical retrieval, not proof that the linked text is
factually correct or still current — see
[docs/ARCHITECTURE.md](ARCHITECTURE.md) for how it feeds scoring.

## 5. Label taxonomy

`nexus/proposals.py`'s `ALLOWED_LABELS` is exactly `{"needs-triage",
"possible-duplicate"}`. No other label value passes `validate_proposal`.

- **`needs-triage`** — no grounded recommendation was produced (no evidence
  retrieved, or the evidence produced no proposal). Workflow meaning: a human
  must triage the event from scratch; there is nothing here to review against
  prior resolutions.
- **`possible-duplicate`** — workflow intent: prior evidence exists that a human
  should compare against before new investigation. It is emitted when evidence
  was retrieved, even if that evidence produced no recommendation (the fixture
  heuristic then pairs it with `needs-triage`). It is not a validator
  invariant: `validate_proposal` only checks the allowlist, never that this
  label implies a non-empty recommendation list.

Both labels are proposal-time hints for human review, not automated
dedupe/close decisions — the CLI never publishes or resolves anything.
