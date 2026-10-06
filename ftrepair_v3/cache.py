"""In-memory exact-verifier caches for FT repair v3.

The caches are intentionally process-local.  A CEGIS run repeatedly revisits
nearby compiler states; exact certification is expensive enough that identical
states should never be recomputed inside one run.  No cached heuristic result is
used in place of exact verification.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any

from .model import RoutingState, context_fingerprint, native_risk


@dataclass
class CacheStats:
    misses: int = 0
    hits: int = 0

    @property
    def exact_calls(self) -> int:
        return int(self.misses)


class RoutingVerifierCache:
    def __init__(self):
        self._store: dict[tuple, Any] = {}
        self.stats = CacheStats()

    def key(self, state: RoutingState, context) -> tuple:
        return (context_fingerprint(context), state.signature())

    def evaluate(self, state: RoutingState, context, compute_c2: bool = False):
        # C2 is not cached under a C1-only entry because it is substantially more
        # expensive and callers explicitly request it.
        k = self.key(state, context) + (bool(compute_c2),)
        if k in self._store:
            self.stats.hits += 1
            return self._store[k]
        r = native_risk(state, context, compute_c2=compute_c2)
        self._store[k] = r
        self.stats.misses += 1
        return r

    def __len__(self):
        return len(self._store)


class GenericVerifierCache:
    """Hashable-key cache used by operation-level schedule verification."""
    def __init__(self):
        self._store: dict[tuple, Any] = {}
        self.stats = CacheStats()

    def get(self, key):
        if key in self._store:
            self.stats.hits += 1
            return True, self._store[key]
        return False, None

    def put(self, key, value):
        self._store[key] = value
        self.stats.misses += 1
        return value

    def __len__(self):
        return len(self._store)
