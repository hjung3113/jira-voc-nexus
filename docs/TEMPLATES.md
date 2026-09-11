# Comment/Issue Templates (v2 implemented, v1 historical)

This document defines the exact output contract for `nexus/proposals.py`'s
`render_comment` and `render_issue`, the input contract those renderers
consume (`nexus/models.py`'s `parse_event`/`parse_corpus`), and the label
taxonomy. It is the reference other agents and the company-side producer
should match; **the renderers are the source of truth** if this document and
the code ever disagree — file a fix here, not a code change to match stale
prose.

**v2 is now implemented** (per
[GitHub issue #9](https://github.com/hjung3113/jira-voc-nexus/issues/9)'s
dual-audience decision and
[docs/ARCHITECTURE.md](ARCHITECTURE.md)'s audience-split proposal contract).
This was a hard cutover — there is no v1 code path in `nexus/proposals.py`
today. §1 and §2's v1 subsections stay in this document as a historical
record of pre-cutover behavior only, because a v1-marker'd comment/issue
already stored before this cutover keeps rendering from its stored result on
replay (replay identity is `event_id` + payload fingerprint, not renderer
version — see `HANDOFF.md`'s replay caveat).

## 0. Format versions at a glance

- **v1** (historical, superseded) — one undifferentiated `recommendations`
  list. No longer produced by any renderer; kept here only so an old stored
  v1 comment/issue (from before this cutover) can still be read against its
  documented shape.
- **v2** (implemented, current behavior) — splits output into a
  `customer_reply` section and an `engineering_action` section, each
  independently evidence-grounded. The marker line names the version so old
  v1 markers and new v2 markers never collide.

## 1. Comment format v1 (historical) / v2 (implemented)

### v1 (historical — superseded, no longer produced)

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

### v2 (implemented — current renderer behavior)

`render_comment(proposal, evidence, event_id)` returns a single string with
this structure, in this exact order:

```text
VOC triage recommendations (dry-run):

Customer reply:
<customer_reply.text, or the no-grounded-reply line>

Engineering action:
<engineering_action.text, or the no-grounded-action line>
[blank line]
Evidence:  ← optional: only when a cited URL passes the gate
<sorted "- <id>: <url>" bullets, union of both audience fields' sources>
[blank line]
Labels: <sorted validated raw labels plus computed audience-coverage:<value>, comma+space joined>
Recipients: <comma+space joined recipients, or "none">
[blank line]
voc-nexus-comment|v2|<event_id>
```

- Each audience section renders its field's `text` verbatim when the field
  is non-`null`. When a field is `null`, its section renders a fixed line
  instead of being omitted — the section header always appears, so a reader
  never has to infer "no section" from a missing header:
  - `customer_reply: null` → `No grounded customer-facing response found;
    manual reply required.`
  - `engineering_action: null` → `No grounded engineering action found;
    manual triage required.`
- The `Evidence:` block gate is unchanged from v1 (`_safe_http_url`), but the
  source set is now the union of both audience fields' cited sources —
  still deduplicated and sorted by id, with no indication in this block of
  which audience cited which source (a reader wanting that mapping reads the
  two sections above it).
- The `Labels:` line contains the validated raw labels plus exactly one
  computed `audience-coverage:<customer-only|engineering-only|both|neither>`
  value, all sorted together and comma+space joined. The model never emits the
  computed value. The marker-always-last rule is unchanged from v1. The marker
  is `voc-nexus-comment|v2|<event_id>` — a new version segment,
  never `v1`, so a v1 marker already looked up by a future adapter is never
  confused with a v2 one.
- `event_id` marker-safety rejection (`|`, newline, carriage return) is
  unchanged.

### Real example (v2, current)

Same inputs as the v1 example above, once evidence supports both audiences:

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

When no evidence exists at all (`customer_reply` and `engineering_action`
both `null`), the two no-grounded lines both render and the `Evidence:`
block is omitted, matching v1's no-evidence behavior:

```text
VOC triage recommendations (dry-run):

Customer reply:
No grounded customer-facing response found; manual reply required.

Engineering action:
No grounded engineering action found; manual triage required.

Labels: audience-coverage:neither, needs-triage
Recipients: none

voc-nexus-comment|v2|event-001
```

## 2. Issue format v1 (historical) / v2 (implemented)

### v1 (historical — superseded, no longer produced)

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

### v2 (implemented — current renderer behavior)

`render_issue(event, proposal, evidence)` returns the same three keys —
`summary`, `description`, `marker` — unchanged. `summary` is unchanged. Only
`description`'s middle section changes, from one `Recommendations:` section
to two audience sections, built from six sections, always in this order:

```text
Context:

- event_id: <event.event_id>
- issue_key: <event.issue_key>
- project: <event.project>

Customer reply:
<customer_reply.text, or the no-grounded-reply line>

Engineering action:
<engineering_action.text, or the no-grounded-action line>

Evidence:  ← optional: only when a cited URL passes the gate
<sorted "- <id>: <url>" bullets, union of both audience fields' sources>
[blank line]
Labels: <sorted validated raw labels plus computed audience-coverage:<value>, comma+space joined>
Recipients: <comma+space joined recipients, or "none">

voc-nexus-issue|v2|<event_id>
```

- The no-grounded-reply/no-grounded-action lines and the `Evidence:` union
  rule are identical to the v2 comment format above.
- `marker` is `voc-nexus-issue|v2|<event_id>` — the exact same string as the
  description's last line, same as v1.

### Real example (v2, current)

```json
{
  "summary": "[VOC] Checkout card payment timeout",
  "description": "Context:\n\n- event_id: event-001\n- issue_key: VOC-100\n- project: PAY\n\nCustomer reply:\nFixture demo only: the card issue has prior resolved guidance in PAY-42 that may answer the customer.\n\nEngineering action:\nFixture demo only: review the resolved guidance for PAY-42 concerning card.\n\nEvidence:\n- PAY-42: https://jira.example.local/browse/PAY-42\n\nLabels: audience-coverage:both, possible-duplicate\nRecipients: user-support, dev-team\n\nvoc-nexus-issue|v2|event-001",
  "marker": "voc-nexus-issue|v2|event-001"
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

## 5. Label taxonomy (implemented)

[GitHub issue #4](https://github.com/hjung3113/jira-voc-nexus/issues/4) is
implemented as two additive dimensions on top of the original triage labels.
The raw engine/model `labels` list accepts exactly the values below; the
computed audience-coverage value is added by code at the public/rendered
surfaces and is never accepted from the model.

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
- **`severity:low`**, **`severity:medium`**, **`severity:high`**,
  **`severity:critical`** — optional in-runtime model judgments selected only
  when the cited evidence text itself signals severity. At most one severity
  value may appear in a raw `labels` list; the model omits the dimension rather
  than guessing when the evidence gives no severity signal.

`needs-triage` and `possible-duplicate` retain their original meaning and may
co-occur. Both remain proposal-time hints for human review, not automated
dedupe/close decisions — the CLI never publishes or resolves anything.

### Computed audience coverage

The asymmetric audience case is carried by a separate, deterministic
`audience-coverage:*` dimension, computed from the already-validated proposal
by `audience_coverage(proposal)` — never judged or emitted by the model:

- `audience-coverage:customer-only` — `customer_reply` grounded,
  `engineering_action` null
- `audience-coverage:engineering-only` — `engineering_action` grounded,
  `customer_reply` null
- `audience-coverage:both` — both fields grounded
- `audience-coverage:neither` — both fields null (the no-evidence path pairs
  this with `needs-triage`)

The public result exposes the same value as `audience_coverage`. Both
`render_comment` and `render_issue` add the prefixed value to the validated raw
labels before sorting the single `Labels:` line. `validate_proposal` rejects
unknown/disallowed labels, duplicate labels, more than one `severity:*` value,
and any attempted `audience-coverage:*` model label. Component, root-cause, and
fix-type dimensions remain explicitly deferred; see
[docs/ARCHITECTURE.md](ARCHITECTURE.md)'s label-taxonomy section.

### Real example (fixture CLI, current)

The fixture engine emits no severity judgment, so its raw label remains
`possible-duplicate`. This is the exact JSON line printed by the fixture CLI
for `fixtures/event.json` and `fixtures/corpus.json`:

```json
{"audience_coverage": "both", "comment": "VOC triage recommendations (dry-run):\n\nCustomer reply:\nFixture demo only: the card issue has prior resolved guidance in PAY-42 that may answer the customer.\n\nEngineering action:\nFixture demo only: review the resolved guidance for PAY-42 concerning card.\n\nEvidence:\n- PAY-42: https://jira.example.local/browse/PAY-42\n\nLabels: audience-coverage:both, possible-duplicate\nRecipients: user-support, dev-team\n\nvoc-nexus-comment|v2|event-001", "customer_reply": {"evidence_ids": ["PAY-42"], "text": "Fixture demo only: the card issue has prior resolved guidance in PAY-42 that may answer the customer."}, "demo_only": true, "dry_run": true, "engine": "fixture", "engineering_action": {"evidence_ids": ["PAY-42"], "text": "Fixture demo only: review the resolved guidance for PAY-42 concerning card."}, "event_id": "event-001", "issue": {"description": "Context:\n\n- event_id: event-001\n- issue_key: VOC-100\n- project: PAY\n\nCustomer reply:\nFixture demo only: the card issue has prior resolved guidance in PAY-42 that may answer the customer.\n\nEngineering action:\nFixture demo only: review the resolved guidance for PAY-42 concerning card.\n\nEvidence:\n- PAY-42: https://jira.example.local/browse/PAY-42\n\nLabels: audience-coverage:both, possible-duplicate\nRecipients: user-support, dev-team\n\nvoc-nexus-issue|v2|event-001", "marker": "voc-nexus-issue|v2|event-001", "summary": "[VOC] Checkout card payment timeout"}, "issue_key": "VOC-100", "labels": ["possible-duplicate"], "published": false, "recipients": ["user-support", "dev-team"], "state": "prepared"}
```

## 6. Recipient routing (implemented)

[GitHub issue #8](https://github.com/hjung3113/jira-voc-nexus/issues/8) is
implemented as a deterministic, renderer-level routing signal — see
[docs/ARCHITECTURE.md](ARCHITECTURE.md)'s "Recipient routing" section for
the full design. The public result carries the same ordered recipient list,
and both `render_comment` and `render_issue` emit one line,
`Recipients: <comma+space joined "user-support"/"dev-team", or "none">`,
positioned after `Labels:` and before the marker line in both v2 formats.
