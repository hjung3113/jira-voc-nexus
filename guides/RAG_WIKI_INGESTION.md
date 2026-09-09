# RAG wiki ingestion guide

## What this covers

The Domain/Systems/Data structure contract for company wiki pages, the
front-matter metadata schema, canonical-vs-draft handling, re-index policy,
and a worked example from wiki page to `IndexDocument`. Self-contained:
restates the target `WikiPage` contract rather than assuming
`rag/contracts.py` is open. See
[docs/RAG_DESIGN.md](../docs/RAG_DESIGN.md#domainsystem-wiki-design) for
the design rationale (wiki as canonical source, not an isolated chatbot
corpus).

## Prerequisites

- Read access to the company wiki (Confluence or equivalent) with pages
  organized under (or taggable as) Domain / Systems / Data, per the
  structure below.
- `rag.contracts.parse_wiki_page` as the validation gate.

## Domain / Systems / Data structure contract

```
Domain
├─ business terms
├─ Context / Carryover / Lot / Wafer definitions
├─ standard log specification
└─ business rules

Systems
├─ system overview
├─ architecture
├─ data flow
├─ components
└─ interfaces

Data
├─ Raw Data definitions
├─ tables/contracts
└─ generation/validation rules
```

Each of these three top-level categories maps to exactly one
`WikiPage.page_type` value: `Domain -> "domain"`, `Systems -> "systems"`,
`Data -> "data"`. A page that does not fit one of these three categories is
not a wiki ingestion candidate for this pipeline -- do not force-fit it;
leave it out of the index rather than mis-typing it.

## Front-matter metadata schema (verbatim)

Every ingestible wiki page must carry this YAML front matter block (or an
equivalent structured field set if your wiki tool does not support literal
YAML front matter -- e.g. Confluence page properties macros mapped 1:1 to
these same keys):

```yaml
page_type: domain
system: LogWarehouse
component: Parser
status: canonical
owner: DataPlatform
related_entities:
  - component:parser
  - table:raw_data
```

| Front-matter key | `WikiPage` field | Rule |
| --- | --- | --- |
| `page_type` | `page_type` | exactly one of `domain`, `systems`, `data` |
| `system` | `system` | the owning system name (e.g. `LogWarehouse`); `""` allowed for a page that is genuinely system-agnostic (e.g. general business terminology) |
| `component` | `component` | the owning component, if the page is component-scoped; `""` otherwise |
| `status` | `status` | exactly one of `canonical`, `draft` (see below) |
| `owner` | `owner` | the team/person accountable for keeping the page current; `""` only if truly unowned (should be rare, and should be fixed, not ingested as-is long-term) |
| `related_entities` | `related_entities` | a list of entity id strings matching `rag.registry` entity ids (e.g. `component:parser`, `table:raw_data`) -- see [guides/RAG_REGISTRY.md](RAG_REGISTRY.md) for the id format; every id listed here should resolve to a real registry entity, though the wiki parser itself does not enforce that cross-reference (validate it at index-build time, see Verification checklist) |

Page `title` and `text` come from the wiki page's own title and body text
(rendered to plain text; strip wiki markup/HTML, keep the prose). Both are
required by `WikiPage` (`text` may be an empty string but must be present).
`page_id` is the wiki tool's stable page id (Confluence page id or
equivalent) -- must be stable across edits so re-indexing upserts the same
`IndexDocument.doc_id` rather than creating a duplicate.

## Canonical / draft status rules

- `status: canonical` means: this page is the accepted source of truth for
  its subject right now. `WikiPage.trust_level()` returns `"canonical"`,
  which is the highest trust tier in `rag.contracts.TRUST_LEVELS` and
  ranks first in `LexicalOverlapReranker`'s trust tiebreak.
- `status: draft` means: under review, not yet accepted, or explicitly
  provisional (e.g. the fixture page
  `domain-error-code-glossary-draft` in `fixtures/rag/wiki_pages.json`,
  which tentatively classifies error codes pending review).
  `WikiPage.trust_level()` returns `"supporting"` for a draft -- the same
  tier as unverified Jira investigation comments. A draft is still
  indexed and retrievable (it can be genuinely useful evidence), it just
  never outranks canonical content on a trust tiebreak.
- A page must never be marked `canonical` by default or by omission -- the
  front matter always states `status` explicitly (`parse_wiki_page`
  requires the key; there is no default).
- Promotion (`draft -> canonical`) is a content-owner decision, not an
  ingestion-pipeline decision. The ingestion pipeline only reads whatever
  `status` the page currently declares; do not have the pipeline
  auto-promote a draft after N days or N views.

## Re-index policy

- Re-map and re-index a page whenever its wiki tool reports a content or
  front-matter change (edit timestamp, version number, or webhook,
  whichever the wiki tool provides).
- A `status` change (`draft -> canonical` or vice versa) must trigger
  re-indexing even if the body text did not change -- it changes
  `trust_level()` and therefore reranking behavior.
- `IndexDocument.doc_id` is `f"wiki:{page_id}"`, deterministic per page --
  re-indexing is an upsert by `doc_id`. Delete the corresponding
  `IndexDocument` if the source page is deleted or archived out of scope.
- Unlike Jira issues (which accumulate resolution evidence over time),
  wiki pages are edited in place -- there is no analogous "problem vs
  resolution" split; one page maps to exactly one `IndexDocument`.

## Worked example

Fixture page `systems-parser-component`
(`fixtures/rag/wiki_pages.json`):

```yaml
page_type: systems
system: LogWarehouse
component: Parser
status: canonical
owner: DataPlatform
related_entities:
  - component:parser
  - component:reconnect
  - sp:insert_raw
```

```json
{
  "page_id": "systems-parser-component",
  "title": "Parser component and reconnect handling",
  "text": "Parser 컴포넌트는 장비 로그 스트림을 파싱하며, 연결이 끊어졌을 때 Reconnect 컴포넌트를 통해 재연결을 시도한 뒤에만 SP_INSERT_RAW를 호출해야 한다.",
  "page_type": "systems",
  "system": "LogWarehouse",
  "component": "Parser",
  "owner": "DataPlatform",
  "status": "canonical",
  "related_entities": ["component:parser", "component:reconnect", "sp:insert_raw"]
}
```

```python
from rag.contracts import parse_wiki_page, wiki_to_document

page = parse_wiki_page(payload)   # raises RagInputError on any contract violation
document = wiki_to_document(page)
# document.doc_id == "wiki:systems-parser-component"
# document.document_type == "system_knowledge"   (systems -> system_knowledge)
# document.trust_level == "canonical"             (status == "canonical")
```

`page_type -> document_type` mapping (fixed, in `rag.contracts`):
`domain -> domain_knowledge`, `systems -> system_knowledge`,
`data -> db_knowledge`.

## Verification checklist

- [ ] Every mapped `WikiPage` payload passes `rag.contracts.parse_wiki_page`
      with no exception.
- [ ] Every `related_entities` id resolves to a real entity in the
      knowledge registry (`SqliteKnowledgeRegistry`/
      `PostgresKnowledgeRegistry` -- see
      [guides/RAG_REGISTRY.md](RAG_REGISTRY.md)); a dangling reference is a
      sign the wiki page and the registry have drifted apart.
- [ ] No page is `canonical` by accident -- spot-check that `status`
      reflects an actual editorial decision, not a copy-pasted default.
- [ ] `page_id` values are stable across a re-crawl (re-running ingestion
      twice on unchanged content produces the same `doc_id` set, not
      duplicates).
- [ ] A sample of `text` values has wiki markup/HTML fully stripped (no
      stray `<p>`, `{code}`, or similar markup leaking into retrieval
      text).

## Failure modes

| Symptom | Likely cause | Fix |
| --- | --- | --- |
| `RagInputError: page_type must be one of (...)` | Front matter uses a category name not in `domain`/`systems`/`data` (e.g. a literal `"Data"` capitalized, or an unmapped category) | Normalize the front-matter value before parsing |
| `RagInputError: status must be one of (...)` | Missing or misspelled `status` key | Add the front-matter key explicitly; there is no default |
| A draft outranking canonical content in results | Reranker/boost configuration bypassed, or `status` mis-set on the canonical page | Confirm `WikiPage.trust_level()` output for both pages; fix `status`, not the reranker |
| Duplicate `IndexDocument`s for one page | `page_id` not stable across edits/re-crawls | Use the wiki tool's persistent page id, not a URL slug that can change |
