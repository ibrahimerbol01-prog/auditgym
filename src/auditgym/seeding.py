"""Deterministic randomness.

Only ``random.Random.random()`` is guaranteed stable across Python versions, so every helper
here is built on it. Seeds are derived with sha256 (never the salted builtin ``hash``), one
stream per module/purpose, so adding a feature does not shift the others.
"""
from __future__ import annotations

import hashlib
import random
from typing import Any, List, Sequence, TypeVar

T = TypeVar("T")


def derive_seed(*parts: Any) -> int:
    """Stable 64-bit seed from any printable parts."""
    text = "|".join(str(p) for p in parts)
    return int.from_bytes(hashlib.sha256(text.encode("utf-8")).digest()[:8], "big")


class Rng:
    """Small RNG wrapper whose helpers only use ``random()``."""

    def __init__(self, *parts: Any) -> None:
        self._r = random.Random(derive_seed(*parts))

    def random(self) -> float:
        return self._r.random()

    def rand_int(self, lo: int, hi: int) -> int:
        """Uniform integer in [lo, hi] inclusive."""
        if hi < lo:
            raise ValueError("empty range")
        return lo + int(self._r.random() * (hi - lo + 1))

    def choice(self, seq: Sequence[T]) -> T:
        if not seq:
            raise ValueError("empty sequence")
        return seq[int(self._r.random() * len(seq))]

    def shuffle(self, items: List[T]) -> List[T]:
        """Fisher-Yates in place; returns the list for convenience."""
        for i in range(len(items) - 1, 0, -1):
            j = int(self._r.random() * (i + 1))
            items[i], items[j] = items[j], items[i]
        return items

    def sample(self, seq: Sequence[T], k: int) -> List[T]:
        pool = list(seq)
        self.shuffle(pool)
        return pool[:k]

    def weighted(self, options: Sequence[T], weights: Sequence[float]) -> T:
        total = float(sum(weights))
        x = self._r.random() * total
        acc = 0.0
        for opt, w in zip(options, weights):
            acc += w
            if x < acc:
                return opt
        return options[-1]

    def chance(self, p: float) -> bool:
        return self._r.random() < p
