"""Internal helpers for token-based chunking (shared by fixed + adaptive).

Intra-domain module (``ingestion/`` only). Imports nothing from other domain
modules and no heavy dependencies at module level — ``tiktoken`` is lazy-imported
inside the counter it powers (CLAUDE.md rule 7).
"""
from __future__ import annotations

import re
from collections.abc import Callable

TokenCounter = Callable[[str], int]

_WORD_RE = re.compile(r"\S+")


def whitespace_token_count(text: str) -> int:
    """Count tokens as whitespace-delimited words.

    Mirrors ``Chunk.token_estimate`` (``len(content.split())``) so that
    chunk-size thresholds expressed in tokens stay consistent with the core
    model. This is the default counter and requires no external dependency.
    """
    return len(text.split())


def resolve_token_counter(spec: TokenCounter | str | None) -> TokenCounter:
    """Resolve a token-counter spec into a callable ``str -> int``.

    Args:
        spec: One of:
            - ``None`` or ``"whitespace"`` -> whitespace word count (default).
            - ``"tiktoken"`` -> OpenAI ``cl100k_base`` encoding.
            - any other ``str`` -> a tiktoken encoding or model name.
            - a callable -> used as-is (for programmatic wiring).

    Returns:
        A callable mapping text to an integer token count.

    Notes:
        The tiktoken paths honour CLAUDE.md rule 7 (lazy import of heavy deps):
        ``tiktoken`` is imported only when the returned counter is first called,
        so the default whitespace path never touches it. String specs keep the
        counter manifest-wirable (a callable cannot come from YAML).
    """
    if spec is None or spec == "whitespace":
        return whitespace_token_count
    if callable(spec):
        return spec
    if isinstance(spec, str):
        encoding_name = "cl100k_base" if spec == "tiktoken" else spec
        return _make_tiktoken_counter(encoding_name)
    raise ValueError(f"Unsupported token_counter spec: {spec!r}")


def _make_tiktoken_counter(encoding_name: str) -> TokenCounter:
    """Build a tiktoken-backed counter that lazy-imports + caches its encoder."""
    state: dict[str, object] = {}

    def count(text: str) -> int:
        encoder = state.get("encoder")
        if encoder is None:
            import tiktoken  # lazy: heavy optional dep (CLAUDE.md rule 7)

            try:
                encoder = tiktoken.get_encoding(encoding_name)
            except (KeyError, ValueError):
                encoder = tiktoken.encoding_for_model(encoding_name)
            state["encoder"] = encoder
        return len(encoder.encode(text))  # type: ignore[attr-defined]

    return count


def _atoms(text: str, start: int, end: int) -> list[tuple[int, int]]:
    """Return character spans of whitespace-delimited atoms in ``text[start:end]``."""
    return [(start + m.start(), start + m.end()) for m in _WORD_RE.finditer(text[start:end])]


def window_by_tokens(
    text: str,
    start: int,
    end: int,
    chunk_size: int,
    chunk_overlap: int,
    count_tokens: TokenCounter,
) -> list[tuple[int, int]]:
    """Slide a token-bounded window over ``text[start:end]``.

    Returns character spans ``(start_char, end_char)`` — never splitting a
    whitespace atom. Each window holds up to ``chunk_size`` tokens and
    consecutive windows share roughly ``chunk_overlap`` tokens. Character
    offsets are preserved so ``Chunk.start_char``/``end_char`` stay meaningful.
    """
    atoms = _atoms(text, start, end)
    if not atoms:
        return []
    costs = [count_tokens(text[s:e]) for s, e in atoms]
    n = len(atoms)
    spans: list[tuple[int, int]] = []
    i = 0
    while i < n:
        tok = 0
        j = i
        # Always take at least one atom (j == i), then extend while it fits.
        while j < n and (j == i or tok + costs[j] <= chunk_size):
            tok += costs[j]
            j += 1
        spans.append((atoms[i][0], atoms[j - 1][1]))
        if j >= n:
            break
        if chunk_overlap <= 0:
            i = j
        else:
            # Step back from j until ~chunk_overlap tokens are re-included,
            # while guaranteeing forward progress (k > i + 1).
            k = j
            back = 0
            while k > i + 1 and back + costs[k - 1] <= chunk_overlap:
                back += costs[k - 1]
                k -= 1
            i = k
    return spans


def merge_small_spans(
    spans: list[tuple[int, int]],
    text: str,
    count_tokens: TokenCounter,
    min_tokens: int,
) -> list[tuple[int, int]]:
    """Fuse spans smaller than ``min_tokens`` into an adjacent span.

    Split-then-merge post-processing per arXiv:2603.25333: fragments below the
    minimum size are merged into their neighbour (forward into the next span
    when possible, otherwise into the preceding span) to avoid the
    retrieval-degrading tiny chunks that pure structural splitting produces.
    """
    if min_tokens <= 0 or len(spans) <= 1:
        return spans
    merged: list[tuple[int, int]] = [spans[0]]
    for span in spans[1:]:
        p_start, p_end = merged[-1]
        if count_tokens(text[p_start:p_end]) < min_tokens:
            merged[-1] = (p_start, span[1])
        else:
            merged.append(span)
    # Trailing fragment has no "next" neighbour: fold it into the previous span.
    if len(merged) > 1:
        l_start, l_end = merged[-1]
        if count_tokens(text[l_start:l_end]) < min_tokens:
            merged[-2] = (merged[-2][0], l_end)
            merged.pop()
    return merged


def iter_sections(text: str, pattern: re.Pattern[str]) -> list[tuple[int, int]]:
    """Return character spans of stripped sections split by ``pattern``.

    Unlike ``pattern.split``, this walks delimiter match boundaries so exact
    character offsets survive — keeping ``Chunk.start_char``/``end_char``
    accurate. Whitespace-only sections are dropped.
    """
    bounds: list[tuple[int, int]] = []
    pos = 0
    for m in pattern.finditer(text):
        bounds.append((pos, m.start()))
        pos = m.end()
    bounds.append((pos, len(text)))

    result: list[tuple[int, int]] = []
    for seg_start, seg_end in bounds:
        raw = text[seg_start:seg_end]
        stripped = raw.strip()
        if not stripped:
            continue
        lead = len(raw) - len(raw.lstrip())
        s = seg_start + lead
        result.append((s, s + len(stripped)))
    return result
