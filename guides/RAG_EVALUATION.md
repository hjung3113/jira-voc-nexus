# RAG evaluation guide

## What this covers

How to build a real golden set (sampling, grading rules, size guidance),
the exact metric formulas `rag.eval` implements, how to run and read the 5
local-variant comparison, the adoption-gate thresholds from
`docs/RAG_DESIGN.md`, and how to record results. Self-contained: restates
the metric contracts rather than assuming `rag/eval.py` is open. See
[docs/RAG_DESIGN.md](../docs/RAG_DESIGN.md#evaluation-gate-before-adoption)
for why this gate exists ("Tool adoption happens only through an
evaluation slice and operational constraints, not by [the design document]
alone").

## Prerequisites

- A representative sample of real (ideally real-but-sanitized -- see
  sanitization rules in
  [guides/RAG_JIRA_INGESTION.md](RAG_JIRA_INGESTION.md)) historical issues,
  large enough to sample a real golden set from (see size guidance below).
- `rag.eval.load_golden_set` / `rag.eval.run_evaluation` /
  `rag.eval.render_markdown_table` -- already wired into
  `python3 -m rag eval` for the local-only comparison.
- For an ACL leakage evaluation alongside this one, see
  [guides/RAG_ACL.md](RAG_ACL.md#the-acl-leakage--0-evaluation-method).

## Golden set construction

### Sampling

- Sample from real, resolved issues wherever your data-handling policy
  allows it, sanitized per
  [guides/RAG_JIRA_INGESTION.md](RAG_JIRA_INGESTION.md)'s sanitization
  rules before the sample ever leaves the source system. Do not construct
  a golden set purely from synthetic/fixture-style text for a real
  adoption decision -- synthetic text (like this repo's
  `fixtures/rag/golden_set.json`, which exists only to unit-test the
  harness itself) is written to match the toolkit's own tokenizer/scoring
  behavior and will systematically overstate recall relative to real
  queries.
- Stratify the sample across: multiple projects/systems (to catch
  cross-project retrieval failures, not just within-project), Korean and
  English (and any other language your VOC data actually contains) at a
  ratio matching real traffic, resolved and unresolved issues, and a
  spread of components -- do not sample only "easy" issues with an exact
  error code in the summary.
- For each sampled *query* issue, identify its **real historical near-
  duplicates or genuinely relevant prior issues** by asking someone who
  actually worked the queue (or by mining Jira "duplicate of"/"relates to"
  links plus a human spot-check) -- not by running the candidate retrieval
  system itself and calling whatever it returns "relevant" (that would
  make the evaluation circular).

### Grading rules

- A candidate `doc_id` belongs in `relevant_doc_ids` for a query if a
  domain expert would actually cite it as directly relevant evidence for
  diagnosing/resolving the query issue -- not merely "same component" or
  "same error code" if the underlying cause was actually different.
- Grade problem docs and resolution docs as separate candidate ids (they
  are separate `IndexDocument`s, `f"{issue_key}:problem"` and
  `f"{issue_key}:resolution"`) -- a query's "true problem match" and its
  "true resolution evidence" may not be identical if, e.g., the right
  problem match is unresolved and the right resolution evidence comes from
  a *different*, related issue.
- Grade binary (relevant / not relevant) -- `rag.eval`'s metrics
  (`recall_at_k`, `mrr_at_k`, `ndcg_at_k`) are all binary-gain by design
  (see formulas below); do not introduce graded relevance without also
  changing the metric implementations to match (and updating this guide).
- Two-grader agreement: for any golden-set entry where the grading isn't
  obvious, have a second person grade independently and resolve
  disagreement by discussion, not by one grader's default. Record the
  disagreement rate as a data-quality signal for the golden set itself.

### Size guidance

- **>= 100 queries** for a real adoption decision. Fewer than that and a
  single hard/easy query swings `recall@5` by a full percentage point or
  more, which is not a stable enough signal to gate a production decision
  on. The 11-query set checked into `fixtures/rag/golden_set.json` is
  sized only to exercise the harness in unit tests
  (`tests/test_rag_eval.py`) and the CLI smoke check in
  [guides/RAG_DEPLOYMENT.md](RAG_DEPLOYMENT.md) -- it is explicitly not a
  real evaluation.
- Re-derive this size guidance if your query volume/diversity is
  unusually low or high for your VOC domain; 100 is a floor, not a target
  to stop at if your domain has enough real variety to sample more usefully.

## Metric formulas

`rag.eval` implements these exactly (docstrings in the module say the
same thing; repeated here so this guide stands alone):

- **`recall_at_k(results, relevant, k)`**:
  `|top-k(results) ∩ relevant| / |relevant|`. Returns `0.0` if `relevant`
  is empty (undefined recall treated as zero, not skipped/NaN, so it
  always averages cleanly).
- **`mrr_at_k(results, relevant, k=10)`**: `1 / rank` of the first
  relevant doc within the top `k` results (1-indexed rank); `0.0` if none
  of the top `k` are relevant.
- **`ndcg_at_k(results, relevant, k=10)`**: binary-gain nDCG.
  `DCG = sum(1 / log2(rank + 1))` over ranks (1-indexed) within the top
  `k` whose doc is relevant; `IDCG` is the same sum for the *ideal*
  ordering (all relevant docs ranked first, up to
  `min(|relevant|, k)`); `nDCG = DCG / IDCG`, or `0.0` if `IDCG` is `0`
  (no relevant docs at all).
- **Latency**: `time.perf_counter()` wall-clock around each
  `pipeline.retrieve()` call, in milliseconds; `latency_ms_p50`/
  `latency_ms_p95` are `sorted(latencies)[round(pct * (n - 1))]` -- a
  simple sorted-index percentile, not an interpolated one. With a small
  `n` (as in a smoke run), `p50`/`p95` can coincide or jump in coarse
  steps; this is expected and not a bug -- use a golden set large enough
  (see size guidance) that the percentile is meaningful for latency
  decisions specifically, independent of the >= 100 recall/relevance
  guidance above.

`run_evaluation`'s report always includes `recall@5`, `recall@10` (or
whatever `ks` you pass), plus `mrr@10` and `ndcg@10` **always computed at
k=10** regardless of `ks` -- matching the fixed schema
`{"recall@5": x, "recall@10": x, "mrr@10": x, "ndcg@10": x,
"latency_ms_p50": x, "latency_ms_p95": x}`.

## Running the 5 variants

```sh
python3 -m rag eval --fixtures-dir fixtures/rag --golden <path-to-your-golden-set.json> [--json]
```

Add `--report detailed` for the deterministic subset/per-query report
(see the next section).

Or programmatically, against your own corpus (real ingested documents, not
just the fixtures):

```python
from rag.eval import default_local_variants, load_golden_set, render_markdown_table, run_evaluation

golden = load_golden_set("<path-to-your-golden-set.json>")
variants = default_local_variants(documents, registry_db_path)  # registry_db_path: "" to skip expansion
report = run_evaluation(variants, golden)
print(render_markdown_table(report))
```

The 5 variants, in the order `default_local_variants` returns them and the
table renders them:

| Variant | What it isolates |
| --- | --- |
| `bm25-only` | Lexical (BM25) signal alone -- vector search returns nothing |
| `vector-only` | Vector (embedding) signal alone -- lexical search returns nothing |
| `hybrid` | BM25 + vector, fused via `rrf_fuse`, no reranking |
| `hybrid+rerank` | Adds `LexicalOverlapReranker` (or, after a swap, `BgeRerankerAdapter`) |
| `hybrid+rerank+expansion` | Adds relation expansion via the knowledge registry when the query names entities |

Every variant uses the *same* underlying `LexicalIndex`/`VectorIndex`
instances (built once from your document corpus) -- the differences
between rows are purely in what each variant's `RetrievalPipeline` wiring
does with those same indexes, so the comparison isolates each component's
marginal contribution.

## Detailed subset report (opt-in, local-only)

`python3 -m rag eval --report detailed` (same `--fixtures-dir`/`--golden`
arguments as above) prints a deterministic JSON report that extends the
aggregate run with the subset breakdowns the adoption-gate list asks for,
computed from the **same retrieval runs** as the aggregate numbers -- there
is no second pass over the golden set:

```json
{
  "<variant-name>": {
    "aggregate": {"count": 2, "recall@5": 0.75, "recall@10": 1.0, "mrr@10": 0.75, "ndcg@10": 0.803},
    "subsets": {
      "language": {
        "ko": {"count": 1, "recall@5": 1.0, "recall@10": 1.0, "mrr@10": 1.0, "ndcg@10": 1.0},
        "unknown": {"count": 1, "recall@5": 0.5, "recall@10": 1.0, "mrr@10": 0.5, "ndcg@10": 0.605}
      },
      "error_code": {"count": 0, "recall@5": null, "recall@10": null, "mrr@10": null, "ndcg@10": null},
      "cross_project": {"count": 1, "recall@5": 1.0, "recall@10": 1.0, "mrr@10": 1.0, "ndcg@10": 1.0}
    },
    "queries": [
      {"query_index": 0, "text": "결제 중복", "language": "ko", "project": "PAY",
       "relevant_doc_ids": ["OPS-201:problem"],
       "ranked_doc_ids": ["OPS-201:problem", "OPS-102:problem"],
       "missing_relevant_doc_ids_by_cutoff": {"5": [], "10": []},
       "recall@5": 1.0, "recall@10": 1.0, "mrr@10": 1.0, "ndcg@10": 1.0},
      {"query_index": 1, "text": "parser aborts", "language": "unknown", "project": "OPS",
       "relevant_doc_ids": ["OPS-300:problem", "OPS-301:problem"],
       "ranked_doc_ids": ["OPS-102:problem", "OPS-300:problem", "OPS-999:problem",
                          "OPS-103:problem", "OPS-104:problem", "OPS-301:problem"],
       "missing_relevant_doc_ids_by_cutoff": {"5": ["OPS-301:problem"], "10": []},
       "recall@5": 0.5, "recall@10": 1.0, "mrr@10": 0.5, "ndcg@10": 0.605}
    ]
  }
}
```

(A tiny illustrative two-query example, not real fixture output. Query 1's
relevant doc is in another project (`cross_project`); query 2's second
relevant doc ranks 6th, so it appears under cutoff `"5"` but not `"10"` --
making the `recall@5` miss directly readable from the report.)


- Every metric block carries exactly `count` plus `recall@5`, `recall@10`
  (or the `ks` passed programmatically), `mrr@10`, `ndcg@10`. A subset with
  `count: 0` reports `null` for every metric key rather than a fabricated 0.
- Aggregate, subset, and per-query numbers all come from the same
  retrieval runs: the shared internal core runs `retrieve` exactly once
  per golden query per variant, and both report paths consume that one run.
- **Latency is intentionally absent** from the detailed report so the output
  is byte-for-byte deterministic across runs; latency stays in the default
  aggregate report only.
- **Language metadata is optional and strictly validated.** A golden-set
  entry may carry `"language": "ko"` (any non-blank string, in the JSON
  loader and in programmatically constructed `GoldenEntry`s alike). When
  absent, the report says `"unknown"` explicitly -- it never guesses from
  query text, and language subsets only contain the labels actually present
  in the golden set (including `"unknown"`).
- **Error-code subset**: queries whose `error_codes` list is non-empty.
- **Cross-project subset**: a query qualifies only when its own `project`
  is non-empty **and** at least one relevant document has a non-empty,
  different `project` field. Relevant documents with an empty `project`
  (unknown provenance, e.g. wiki pages) are never asserted to be
  cross-project.
- Each `queries` row carries `query_index` (position in the golden set),
  `relevant_doc_ids`, `ranked_doc_ids` (to the same depth as the aggregate
  run, i.e. `max(10, ks)`), and `missing_relevant_doc_ids_by_cutoff`:
  relevant IDs absent from the top `k` for every configured recall cutoff
  plus 10 -- so a rank-6 relevant doc shows up as a clear `recall@5` miss
  while being present at cutoff 10.
- Failures (invalid golden set, unknown/duplicate result IDs, blank query
  text, relevance IDs outside the corpus) raise before any output is
  printed; variant cleanup still runs, and the CLI exits nonzero with no
  partial report on stdout.

The same report is available programmatically via
`rag.eval.run_detailed_evaluation(variants, golden)` (same input validation
as `run_evaluation`). This is a local-only operator convenience: it makes
the subset numbers reproducible and auditable, but it does **not** add any
quality threshold or pass/fail judgment -- the >= 100-query, ACL-leakage,
and adoption-gate criteria in this guide are unchanged, and a synthetic
run remains harness smoke evidence only.

## Same-project boost calibration (local fixture only)

The local toolkit keeps `RetrievalQuery.project` as a soft preference, never
as authorization or a hard project filter. `BoostConfig.same_project` defaults
to `+0.0001`, a small positive preference calibrated against the committed
fixture's full 11-query set and two synthetic `RetrievalPipeline.retrieve`
cases (an equal fused RRF-score tie and a strong cross-project match). The
full sweep, before/after five-variant metrics, and bounded local-only evidence
are in
[docs/RAG_SAME_PROJECT_CALIBRATION.md](../docs/RAG_SAME_PROJECT_CALIBRATION.md).

These are synthetic local-harness results only. The fixture has 11 queries,
is not a real adoption golden set, and cannot establish production relevance,
latency, ACL leakage, OpenSearch/BGE/PostgreSQL behavior, or a production
default; the adoption gate in `docs/RAG_DESIGN.md` remains unchanged.

To evaluate a real adapter swap (per
[guides/RAG_DEPLOYMENT.md](RAG_DEPLOYMENT.md)), build your own
`PipelineVariant` list with the swapped component substituted for one
local one at a time (e.g. `hybrid+rerank` using `BgeRerankerAdapter`
instead of `LexicalOverlapReranker`, everything else unchanged) and pass
that list to `run_evaluation` -- comparing against the local baseline for
the same golden set is exactly how you attribute a metric change to the
swap rather than to golden-set noise.

## Reading the table

```
| variant | recall@5 | recall@10 | mrr@10 | ndcg@10 | latency_ms_p50 | latency_ms_p95 |
| --- | --- | --- | --- | --- | --- | --- |
| bm25-only | 1.000 | 1.000 | 1.000 | 1.000 | 0.07 | 0.27 |
| vector-only | 1.000 | 1.000 | 1.000 | 1.000 | 0.23 | 0.26 |
| hybrid | 1.000 | 1.000 | 1.000 | 1.000 | 0.28 | 0.30 |
| hybrid+rerank | 1.000 | 1.000 | 1.000 | 0.989 | 1.26 | 1.33 |
| hybrid+rerank+expansion | 1.000 | 1.000 | 1.000 | 0.989 | 1.30 | 1.42 |
```

(actual output on this repo's `fixtures/rag/golden_set.json`, 11 queries --
see the caveat above: this small set is a harness smoke check, not
adoption evidence.)

- Compare rows, not just columns: `hybrid+rerank`'s value only matters
  relative to `hybrid`'s on the *same* golden set -- a reranker that adds
  latency without moving recall/nDCG is not earning its cost.
- A near-1.0 `recall@5` on a small/synthetic golden set (as above) is
  expected and not evidence of production readiness -- it mainly says the
  harness and the fixture corpus/golden set are internally consistent
  with each other, per the sampling caveat above.
- `ndcg@10` dropping slightly from `hybrid` to `hybrid+rerank` while
  `recall`/`mrr` stay flat (as in the table above) can mean the reranker
  changed *ordering among already-found* relevant docs without changing
  *whether* they were found -- read `ndcg` and `recall`/`mrr` together,
  not `ndcg` alone.
- Latency percentiles from a run this small are not meaningful on their
  own (see the sorted-index-percentile caveat above); only compare them
  once your golden set is large enough that `p50`/`p95` are stable across
  repeated runs.

## Adoption gate thresholds (from `docs/RAG_DESIGN.md`)

Per
[docs/RAG_DESIGN.md](../docs/RAG_DESIGN.md#evaluation-gate-before-adoption),
before adopting any pipeline configuration (local or a real-adapter swap)
for production, gather and record:

- Recall@5, Recall@10, MRR@10, nDCG@10 -- via this guide's process, on a
  real (>= 100 query) golden set, across all 5 comparison variants.
- Retrieval latency p50/p95.
- Indexing throughput and re-index cost.
- Korean + English mixed issue quality (the golden set's language
  stratification, above, is what makes this measurable rather than
  anecdotal).
- Exact error/code identifier recall specifically (a golden-set subset
  filtered to queries with an `error_codes` entry -- compute
  `recall_at_k` restricted to that subset, since exact-identifier recall
  can differ meaningfully from overall recall).
- Cross-project false positives (a golden-set subset of queries whose
  correct answer is *not* in `query.project`, per the "cross-project"
  golden-set requirement mirrored from this repo's own
  `fixtures/rag/golden_set.json`).
- **ACL leakage = 0** -- see
  [guides/RAG_ACL.md](RAG_ACL.md#the-acl-leakage--0-evaluation-method);
  this is a hard pass/fail gate, run alongside (not instead of) the metric
  table above.

None of the above is satisfied by a single run of `python3 -m rag eval`
against `fixtures/rag/golden_set.json` -- that command exists to smoke-test
the harness itself (see
[guides/RAG_DEPLOYMENT.md](RAG_DEPLOYMENT.md#local-first-run-verify-before-touching-any-adapter)), not to
produce adoption evidence.

## Recording results

Adoption evidence updates
[docs/TOOLING_DECISION.md](../docs/TOOLING_DECISION.md) "only after this
evidence exists" (per `docs/RAG_DESIGN.md`'s evaluation gate section) --
it is not this guide's job to make that update, but whoever runs an
adoption evaluation should record, at minimum, alongside the metric table:

- Golden set size, sampling method, and date range of sampled issues.
- The exact `PipelineVariant` list evaluated (including any real-adapter
  swap, with its configuration -- model name/version, index settings).
- The full metric table (`render_markdown_table` output or the raw JSON
  report) for every variant compared.
- The subset breakdowns (error-code, cross-project, language) from the
  adoption-gate list above, not just the aggregate numbers.
- The ACL leakage golden set result (pass/fail, and the leakage golden set
  size/coverage) from [guides/RAG_ACL.md](RAG_ACL.md).
- Indexing throughput and re-index cost measurements (wall-clock time to
  build the indexes over the real corpus size, not just the fixture
  corpus).

## Verification checklist

- [ ] Golden set has >= 100 queries for any real adoption decision (the
      committed fixture set is explicitly exempt -- it is a harness test,
      not adoption evidence).
- [ ] Golden set is stratified across project/system, language, resolved
      status, and component per the sampling rules above.
- [ ] `load_golden_set` accepts the file with no `RagInputError` (schema
      correctness) before any metric run.
- [ ] `run_evaluation`'s report has all 6 expected keys per variant
      (`recall@5`, `recall@10`, `mrr@10`, `ndcg@10`, `latency_ms_p50`,
      `latency_ms_p95`) for all 5 variants.
- [ ] Error-code-subset and cross-project-subset recall computed
      separately from the aggregate, per the adoption gate list.
- [ ] ACL leakage evaluation run and recorded alongside the metric table,
      not as a separate/forgotten step.
- [ ] Results recorded with enough detail (golden set provenance, exact
      variant configuration) that someone else could reproduce the
      comparison later.

## Failure modes

| Symptom | Likely cause | Fix |
| --- | --- | --- |
| `RagInputError` from `load_golden_set` | Golden set JSON missing a required key, `query` object missing one of the 6 `RetrievalQuery` fields, or `relevant_doc_ids` empty for an entry | Check the entry against the schema in this repo's `rag.eval.load_golden_set` docstring; every `query` key is required, even if empty (`""`/`[]`) |
| All 5 variants show identical `recall@5` | Golden set too small/easy to differentiate them (the committed fixture set can show this), or the golden set's `document_types` filter excludes the doc types your relevant ids actually belong to | Check each entry's `document_types` matches where its `relevant_doc_ids` actually live; grow the golden set |
| `hybrid+rerank+expansion` performs identically to `hybrid+rerank` | Golden set queries don't populate `entities`, so `RetrievalPipeline.retrieve` never calls `registry.expand()` (only happens "when registry and entities given") | Add `entities` to golden-set queries that should exercise relation expansion, or accept that this variant is only differentiated on entity-bearing queries |
| Metric numbers change between identical runs | A real adapter (embedding endpoint, reranker model) is non-deterministic, or the corpus/registry changed between runs | Local components are deterministic by construction; a run-to-run difference points at a real-adapter swap or a data change, not the harness |
