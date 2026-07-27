# Hybrid Fusion with Reciprocal Rank Fusion

Hybrid retrieval runs a vector search and a BM25 search independently, then
merges the two ranked lists into a single result set. This framework uses
Reciprocal Rank Fusion (RRF, Cormack et al. 2009): each document earns a
score of `weight / (rrf_k + rank)` from every list it appears in, and the
contributions are summed. A document that ranks well in both lists — a
strong semantic match that also contains the right keywords — rises to the
top; a document that ranks well in only one list still gets credit, but
less of it.

RRF needs no score normalization, because it only looks at rank position,
not the raw similarity or BM25 score, which are on incompatible scales. The
`vector_weight` and `bm25_weight` fields in a pipeline manifest (see
`manifests/presets/local-hybrid-rag.yaml`) scale each list's contribution
before summing, letting you bias the fusion toward semantic or lexical
matches without discarding the other signal entirely — set a weight to `0.0`
to fully exclude that source's influence, or push it toward `1.0` to trust
it almost exclusively.

In practice, hybrid retrieval recovers the strengths of both methods: it
finds paraphrased, conceptual matches like vector search, and it still
surfaces exact keyword/identifier matches like BM25 — cases a single method
alone would frequently miss.
