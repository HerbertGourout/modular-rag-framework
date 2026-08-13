"""Deterministic, dependency-free BM25-style sparse text vectorization —
shared by index-time and query-time paths (both `adapters.vectorstores.
qdrant_sparse_store.QdrantSparseStore` and any future sparse backend) so both
land in the identical hashed feature space.

No corpus-wide statistics are collected here: unlike `rank_bm25.BM25Okapi`
(which holds the whole in-memory corpus and can compute a live IDF),
`index_sparse_vector()` sees one chunk at a time. IDF weighting is supplied
server-side by the persistent backend instead (Qdrant's `Modifier.IDF` on the
sparse vector field) — only the term-frequency-saturation half of BM25
(Robertson & Zaragoza, 2009, "The Probabilistic Relevance Framework: BM25 and
Beyond" — outside `docs/research/DIGEST-retrieval.md`'s corpus, which covers
fusion weights and rerank shaping but not persistent-sparse-backend
infrastructure or term-weighting scheme; CLAUDE.md rule 05.8) needs computing
client-side.

retrieval-specialist review (Lot 5): index-time and query-time vectors use
*different* weighting, not the same function twice, despite sharing the same
tokenizer/hasher — BM25 weights a query term as a flat presence signal (1.0
per distinct term, no document-length term), while an indexed chunk's terms
get the full saturated-TF treatment. Reusing the saturated-TF formula on the
query side would double-count a document-length effect that only means
something for what's being indexed.
"""
from __future__ import annotations

import hashlib
import re

_TOKEN_PATTERN = re.compile(r"\w+")

# retrieval-specialist review (Lot 5): hash into the full unsigned 32-bit
# space (Qdrant sparse-vector indices are `u32`) rather than a small fixed
# bucket count. Unlike `adapters.embeddings.deterministic_embedder`'s
# *dense* hashing trick — where a small `dimensions` keeps a fixed-size array
# small — a Qdrant sparse vector is a dict keyed by index: an unused index
# costs nothing, so shrinking the space buys no memory saving and only
# creates real collisions at enterprise vocabulary scale (product codes,
# ids, subwords). A dense vector tolerates a collision (two tokens summing
# into the same bucket); a sparse index does not — two terms landing on the
# same index share one IDF statistic, corrupting both.
_HASH_SPACE = 2**32


def tokenize(text: str) -> list[str]:
    return _TOKEN_PATTERN.findall(text.lower())


def hash_term(token: str) -> int:
    digest = hashlib.sha256(token.encode("utf-8")).digest()
    return int.from_bytes(digest[:4], "big") % _HASH_SPACE


def index_sparse_vector(
    content: str, *, avgdl: float, k1: float = 1.2, b: float = 0.75
) -> dict[int, float]:
    """BM25's saturated term-frequency component only (see module docstring
    for why IDF is deliberately not computed here). `k1`/`b` are the standard
    Robertson & Zaragoza (2009) defaults, matching the FastEmbed `Qdrant/bm25`
    sparse model's own choice. `avgdl` is a fixed, configured constant rather
    than a running corpus average (same reference): recomputing it on every
    incremental `index()` call would silently re-weight chunks indexed
    earlier, since their stored sparse vector is never rewritten after
    upsert. Returns `{}` for content with no tokens (e.g. empty string) —
    callers must treat that as "nothing to index/query", not attempt to
    upsert or search an empty sparse vector.
    """
    tokens = tokenize(content)
    if not tokens:
        return {}
    dl = len(tokens)
    counts: dict[str, int] = {}
    for token in tokens:
        counts[token] = counts.get(token, 0) + 1
    vector: dict[int, float] = {}
    for token, tf in counts.items():
        weight = (tf * (k1 + 1)) / (tf + k1 * (1 - b + b * dl / avgdl))
        vector[hash_term(token)] = weight
    return vector


def query_sparse_vector(text: str) -> dict[int, float]:
    """Flat presence weighting (1.0 per distinct query term) — see module
    docstring for why this must not reuse `index_sparse_vector`'s
    saturated-TF formula."""
    return {hash_term(token): 1.0 for token in set(tokenize(text))}
