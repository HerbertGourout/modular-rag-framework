"""Deterministic, dependency-free embedding adapter — no model download, no
external API. Registered as `embedder.type: "deterministic"` (Lot 4, secure
preset e2e correction) so a real e2e pipeline can wire a contract-conformant
`Embedder` with no external LLM key and no first-run model download,
alongside `generation.synthesizers.deterministic_gen.DeterministicGenerator`.
"""
from __future__ import annotations

import hashlib
import math
import re

from modular_rag.core.errors import ConfigurationError

_TOKEN_PATTERN = re.compile(r"\w+")


class DeterministicEmbedder:
    """Feature-hashed ("hashing trick") embedding: every lowercased word
    token is hashed into one of `dimensions` signed buckets and summed, then
    L2-normalized — the same technique behind Vowpal Wabbit's and
    scikit-learn's `HashingVectorizer`'s feature hashing. Fully deterministic
    (identical text always produces the identical vector, on any machine,
    forever — `hashlib.sha256` has no run-to-run or process-to-process
    variance) and captures real lexical similarity — texts sharing
    vocabulary land closer together in cosine space, since shared tokens
    hash to the same bucket with the same sign — without a trained model, a
    network call, or an API key.

    Not a substitute for a real embedding model's semantic quality — it has
    none beyond token overlap. Intended for e2e/integration tests and
    dependency-free local pipelines only, where `HybridRetriever`'s BM25 half
    already carries the real lexical-relevance signal regardless of what
    this embedder contributes.
    """

    def __init__(self, dimensions: int = 256) -> None:
        # test-specialist review (Lot 4): 64 collides too heavily — with few
        # buckets, unrelated tokens routinely land on the same signed bucket,
        # pushing most vectors toward mutual similarity and making top-k
        # ordering effectively decided by tie-breaking noise instead of real
        # lexical overlap. 256 keeps collisions rare for realistic test-sized
        # vocabularies while staying far cheaper than a real embedding model.
        #
        # Codex review: `dimensions` reaches here from manifest config
        # (`embedder.config.dimensions`) unvalidated. A non-positive value
        # used to wire and validate successfully, then crash deep inside
        # `_embed_one()` on first real use — `% 0` raises ZeroDivisionError,
        # and both 0 and negative values leave `vector = [0.0] * dimensions`
        # empty, so the degenerate-input fallback's `vector[0] = 1.0` raises
        # IndexError. Rejecting it here instead surfaces one clear,
        # actionable ConfigurationError at construction time, matching how
        # every other manifest-configuration mistake in this codebase fails.
        if dimensions < 1:
            raise ConfigurationError(
                f"DeterministicEmbedder dimensions must be a positive integer, got {dimensions}."
            )
        self._dimensions = dimensions

    def name(self) -> str:
        return "deterministic"

    @property
    def dimensions(self) -> int:
        return self._dimensions

    def _embed_one(self, text: str) -> list[float]:
        vector = [0.0] * self._dimensions
        for token in _TOKEN_PATTERN.findall(text.lower()):
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            index = int.from_bytes(digest[:4], "big") % self._dimensions
            sign = 1.0 if digest[4] & 1 == 0 else -1.0
            vector[index] += sign
        norm = math.sqrt(sum(v * v for v in vector))
        if norm > 0:
            return [v / norm for v in vector]
        # Degenerate input (empty string, or a string with no \w tokens) hashes
        # to an all-zero vector, which cosine similarity cannot compare against
        # anything (undefined direction) — Qdrant's cosine distance rejects a
        # zero vector outright. Fall back to a fixed unit vector (bucket 0) so
        # `embed()` always returns a usable vector; this is a degenerate-input
        # fallback, not a meaningful embedding of "no content."
        vector[0] = 1.0
        return vector

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._embed_one(text) for text in texts]

    async def aembed(self, texts: list[str]) -> list[list[float]]:
        return self.embed(texts)
