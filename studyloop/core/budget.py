"""The token budget: how much an agent reads at once (docs/architecture.md, "Token budget").

Big inputs (a book, an episode, review data) are never read whole: they are split into parts
that fit a batch, and the agent reads one part at a time. Used by sources (book and PDF parts).
"""
from __future__ import annotations

TOKENS_PER_WORD = 1.35       # English prose; a rough estimate, good enough to size batches
DEFAULT_BATCH = 12000        # tokens per batch (a topic's brief overrides it: `batch:`)


def tokens(words: int) -> int:
    return int(words * TOKENS_PER_WORD)


def word_limit(batch: int) -> float:
    """How many words fit into a batch of `batch` tokens."""
    return batch / TOKENS_PER_WORD


def split(sizes: list[int], first: int, last: int, limit: float) -> list[tuple[int, int, int]]:
    """Units first..last (1-based; sizes[i - 1] words each) as consecutive runs of at most
    `limit` words (a single unit over it is its own run): [(first, last, words), ...]."""
    runs, a, acc = [], first, 0
    for i in range(first, last + 1):
        w = sizes[i - 1]
        if acc and acc + w > limit:
            runs.append((a, i - 1, acc))
            a, acc = i, 0
        acc += w
    runs.append((a, last, acc))
    return runs


def short(n: int | None) -> str:
    """12345 -> '12.3k'; None -> '?'."""
    if n is None:
        return "?"
    return f"{n / 1000:.1f}k" if n >= 1000 else str(n)
