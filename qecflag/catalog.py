"""Build a finite, exhaustively certified candidate library."""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import hashlib
import numpy as np
from .physics import (candidate_schedules, decoder_and_certificate, quadratic_risk_matrix,
                      labels, schedule_from_label)

SCHEMA = 1


@dataclass
class Catalog:
    labels: list[str]
    matrices: np.ndarray
    decoders: np.ndarray
    reports: list[dict]

    @property
    def reference(self) -> int:
        return self.labels.index('0F12F3')

    @property
    def fingerprint(self) -> str:
        h = hashlib.sha256()
        h.update('|'.join(self.labels).encode())
        h.update(np.asarray(self.matrices, dtype='<f8').tobytes())
        h.update(np.asarray(self.decoders, dtype='<i4').tobytes())
        return h.hexdigest()

    def costs(self, contexts: np.ndarray) -> np.ndarray:
        w = np.atleast_2d(contexts).astype(np.float64)
        # Bounded intermediates and deterministic CPU-only execution.
        return np.einsum('bf,afg,bg->ba', w, self.matrices, w, optimize=True)

    def chosen_costs(self, contexts: np.ndarray, choices: np.ndarray) -> np.ndarray:
        return np.einsum('bf,bfg,bg->b', contexts, self.matrices[choices], contexts, optimize=True)


def build_catalog() -> Catalog:
    names, matrices, decoders, reports = [], [], [], []
    for schedule in candidate_schedules():
        decoder, report = decoder_and_certificate(schedule)
        reports.append(report)
        if report['certified']:
            names.append(labels(schedule))
            matrices.append(quadratic_risk_matrix(schedule, decoder))
            decoders.append(decoder)
    return Catalog(names, np.stack(matrices), np.stack(decoders), reports)


def greedy_choice(catalog: Catalog, costs: np.ndarray, budget: int = 16) -> tuple[int, int]:
    """Deterministic best-improvement pair swaps; counts unique evaluations."""
    if budget < 1:
        raise ValueError('budget must be >= 1')
    current = catalog.reference
    seen = {current}
    lookup = {label: i for i, label in enumerate(catalog.labels)}
    while len(seen) < budget:
        label = catalog.labels[current]
        neighbors = set()
        for i in range(len(label)):
            for j in range(i + 1, len(label)):
                candidate = list(label)
                candidate[i], candidate[j] = candidate[j], candidate[i]
                text = ''.join(candidate)
                if text in lookup and lookup[text] not in seen:
                    neighbors.add(lookup[text])
        if not neighbors:
            break
        to_check = sorted(neighbors)[:budget - len(seen)]
        seen.update(to_check)
        best = min([current] + to_check, key=lambda i: (costs[i], i))
        if costs[best] >= costs[current] - 1e-12:
            break
        current = best
    # Do not accidentally discard an already-evaluated better candidate.
    return min(seen, key=lambda i: (costs[i], i)), len(seen)
