# Same-project boost calibration

## Decision

The local retrieval default for `BoostConfig.same_project` is `+0.0001`.
It remains a positive soft preference: an equal-relevance same-project result
can win a tie, but `RetrievalQuery.project` is not an authorization basis or a
hard project filter. The other boost defaults, ACL ordering, nexus runtime,
and adoption gate are unchanged.

## Method and scope

This is a local-only calibration on 2026-09-12. The sweep used the complete
committed `fixtures/rag/golden_set.json` (11 queries), the documents built from
`normalized_issues.json` and `wiki_pages.json`, and all five variants returned
by the local evaluation harness. Each candidate used
`RetrievalConfig(boosts=BoostConfig(same_project=value))`; every evaluation
went through `RetrievalPipeline.retrieve` via `run_evaluation`, requesting
depth 10 so the MRR@10 and nDCG@10 measurements use the full evaluation cutoff.
No fixture or relevance label was changed.

The candidate sweep was:

`0`, `0.00001`, `0.00005`, `0.0001`, `0.00025`, `0.0005`, `0.001`,
`0.0025`, `0.005`, `0.01`, `0.05`, `0.1`, `0.25`, `0.5`.

In the table below, each golden-set cell is
`recall@5 / recall@10 / MRR@10 / nDCG@10`. The synthetic columns report the
first result returned through the public `retrieve` seam:

- **tie** uses two equal channel rankings inverted across the two channels,
  producing an exact RRF tie before boosts; a positive candidate must return
  the same-project document first while retaining the cross-project document;
- **strong cross-project** uses the local lexical and hashing-vector indexes,
  with an exact cross-project match and a weaker same-project distractor; the
  cross-project document must remain first.

## Sweep results

| same_project | bm25-only | vector-only | hybrid | hybrid+rerank | hybrid+rerank+expansion | tie | strong cross-project |
| ---: | --- | --- | --- | --- | --- | --- | --- |
| 0 | 1.000 / 1.000 / 1.000 / 1.000 | 1.000 / 1.000 / 1.000 / 1.000 | 1.000 / 1.000 / 1.000 / 1.000 | 1.000 / 1.000 / 1.000 / 0.989 | 1.000 / 1.000 / 1.000 / 0.989 | `a-cross` | `a-cross` |
| 0.00001 | 1.000 / 1.000 / 1.000 / 1.000 | 1.000 / 1.000 / 1.000 / 1.000 | 1.000 / 1.000 / 1.000 / 1.000 | 1.000 / 1.000 / 1.000 / 0.989 | 1.000 / 1.000 / 1.000 / 0.989 | `z-same` | `a-cross` |
| 0.00005 | 1.000 / 1.000 / 1.000 / 1.000 | 1.000 / 1.000 / 1.000 / 1.000 | 1.000 / 1.000 / 1.000 / 1.000 | 1.000 / 1.000 / 1.000 / 0.989 | 1.000 / 1.000 / 1.000 / 0.989 | `z-same` | `a-cross` |
| 0.0001 (selected) | 1.000 / 1.000 / 1.000 / 1.000 | 1.000 / 1.000 / 1.000 / 1.000 | 1.000 / 1.000 / 1.000 / 1.000 | 1.000 / 1.000 / 1.000 / 0.989 | 1.000 / 1.000 / 1.000 / 0.989 | `z-same` | `a-cross` |
| 0.00025 | 1.000 / 1.000 / 1.000 / 1.000 | 1.000 / 1.000 / 1.000 / 1.000 | 1.000 / 1.000 / 1.000 / 1.000 | 1.000 / 1.000 / 1.000 / 0.989 | 1.000 / 1.000 / 1.000 / 0.989 | `z-same` | `a-cross` |
| 0.0005 | 1.000 / 1.000 / 0.955 / 0.966 | 1.000 / 1.000 / 0.955 / 0.966 | 1.000 / 1.000 / 1.000 / 1.000 | 1.000 / 1.000 / 1.000 / 0.989 | 1.000 / 1.000 / 1.000 / 0.989 | `z-same` | `a-cross` |
| 0.001 | 1.000 / 1.000 / 0.955 / 0.966 | 1.000 / 1.000 / 0.955 / 0.966 | 1.000 / 1.000 / 0.955 / 0.966 | 1.000 / 1.000 / 1.000 / 0.989 | 1.000 / 1.000 / 1.000 / 0.989 | `z-same` | `z-same` |
| 0.0025 | 1.000 / 1.000 / 0.927 / 0.944 | 0.909 / 1.000 / 0.924 / 0.941 | 1.000 / 1.000 / 0.939 / 0.955 | 1.000 / 1.000 / 1.000 / 0.989 | 1.000 / 1.000 / 1.000 / 0.989 | `z-same` | `z-same` |
| 0.005 | 1.000 / 1.000 / 0.927 / 0.944 | 0.909 / 1.000 / 0.924 / 0.941 | 1.000 / 1.000 / 0.927 / 0.944 | 1.000 / 1.000 / 1.000 / 0.989 | 1.000 / 1.000 / 1.000 / 0.989 | `z-same` | `z-same` |
| 0.01 | 1.000 / 1.000 / 0.927 / 0.944 | 0.909 / 1.000 / 0.924 / 0.941 | 1.000 / 1.000 / 0.927 / 0.944 | 1.000 / 1.000 / 1.000 / 0.989 | 1.000 / 1.000 / 1.000 / 0.989 | `z-same` | `z-same` |
| 0.05 | 1.000 / 1.000 / 0.927 / 0.944 | 0.909 / 1.000 / 0.924 / 0.941 | 0.909 / 1.000 / 0.924 / 0.941 | 1.000 / 1.000 / 1.000 / 0.989 | 1.000 / 1.000 / 1.000 / 0.989 | `z-same` | `z-same` |
| 0.1 | 1.000 / 1.000 / 0.927 / 0.944 | 0.909 / 1.000 / 0.924 / 0.941 | 0.909 / 1.000 / 0.924 / 0.941 | 1.000 / 1.000 / 1.000 / 0.989 | 1.000 / 1.000 / 1.000 / 0.989 | `z-same` | `z-same` |
| 0.25 | 1.000 / 1.000 / 0.927 / 0.944 | 0.909 / 1.000 / 0.924 / 0.941 | 0.909 / 1.000 / 0.924 / 0.941 | 1.000 / 1.000 / 1.000 / 0.989 | 1.000 / 1.000 / 1.000 / 0.989 | `z-same` | `z-same` |
| 0.5 (previous) | 1.000 / 1.000 / 0.927 / 0.944 | 0.909 / 1.000 / 0.924 / 0.941 | 0.909 / 1.000 / 0.924 / 0.941 | 1.000 / 1.000 / 1.000 / 0.989 | 1.000 / 1.000 / 1.000 / 0.989 | `z-same` | `z-same` |

The selected value is the conservative positive candidate that preserves all
fixture relevance metrics while leaving substantial headroom below the first
observed regressions. `0.00025` also passes this fixture sweep, but `0.0001`
reduces the chance that a small corpus or rank-order change turns a close RRF
comparison into a cross-project regression.

## Full before/after CLI metrics

These are two local CLI runs against the same 11-query fixture golden set.
The previous run used the old default `same_project=0.5`; the calibrated run
uses `same_project=0.0001`. Latency is included for completeness but is
machine-load dependent and is not a quality or adoption claim.

| variant | previous recall@5 | previous recall@10 | previous MRR@10 | previous nDCG@10 | previous p50 ms | previous p95 ms | calibrated recall@5 | calibrated recall@10 | calibrated MRR@10 | calibrated nDCG@10 | calibrated p50 ms | calibrated p95 ms |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| bm25-only | 1.000 | 1.000 | 0.927 | 0.944 | 0.07 | 0.27 | 1.000 | 1.000 | 1.000 | 1.000 | 0.07 | 0.27 |
| vector-only | 0.909 | 1.000 | 0.924 | 0.941 | 0.24 | 0.25 | 1.000 | 1.000 | 1.000 | 1.000 | 0.23 | 0.26 |
| hybrid | 0.909 | 1.000 | 0.924 | 0.941 | 0.29 | 0.31 | 1.000 | 1.000 | 1.000 | 1.000 | 0.28 | 0.30 |
| hybrid+rerank | 1.000 | 1.000 | 1.000 | 0.989 | 1.32 | 1.37 | 1.000 | 1.000 | 1.000 | 0.989 | 1.26 | 1.33 |
| hybrid+rerank+expansion | 1.000 | 1.000 | 1.000 | 0.989 | 1.28 | 1.40 | 1.000 | 1.000 | 1.000 | 0.989 | 1.30 | 1.42 |

The fixture file remained byte-for-byte unchanged:

```text
9f1f02a9f66ffbcf7699a0a40dd845409c6e2652011b1cdda66f1470b14f1c92  fixtures/rag/golden_set.json
```

## Limits and adoption boundary

This evidence is deliberately bounded. The 11-query fixture is synthetic and
exists to exercise the harness; it is not the required real, sanitized golden
set of at least 100 queries. The synthetic tie isolates the soft-preference
behavior with controlled channel ranks, and the strong-match case uses local
BM25 and hashing-vector stand-ins rather than OpenSearch or BGE. No real
provider, Jira, PostgreSQL, OpenSearch, network, latency, or production ACL
verification was performed. A production decision still requires the full
five-variant real-corpus evaluation, cross-project false-positive analysis,
latency/indexing measurements, and ACL leakage = 0 from the unchanged
adoption gate in `docs/RAG_DESIGN.md` and `guides/RAG_EVALUATION.md`.
