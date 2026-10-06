"""Certified Phase-3 synthesis catalogs and compact exact C2 evaluation."""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import hashlib
import json
import numpy as np

from .phase3_physics import (
    candidate_schedules, decoder_and_certificate, quadratic_risk_upper_counts,
    quadratic_features, schedule_label, schedule_kind, schedule_from_label,
)

CACHE_SCHEMA = 1


@dataclass
class SynthesisCatalog:
    mode: str
    labels: list[str]
    kinds: np.ndarray
    risk_counts: np.ndarray  # uint8/uint16, shape (actions, triangular features)
    candidate_count: int
    certified_count: int
    _float_counts_cache: np.ndarray | None = None

    def __post_init__(self):
        self._index = {label: i for i, label in enumerate(self.labels)}

    @property
    def fingerprint(self) -> str:
        h = hashlib.sha256()
        h.update(self.mode.encode())
        h.update('|'.join(self.labels).encode())
        h.update(np.asarray(self.risk_counts).tobytes())
        return h.hexdigest()

    @property
    def reference(self) -> int:
        return self._index['0A12A3']

    def index(self, label: str) -> int | None:
        return self._index.get(label)

    def _float_counts(self) -> np.ndarray:
        if self._float_counts_cache is None:
            self._float_counts_cache = self.risk_counts.astype(np.float32)
        return self._float_counts_cache

    def all_costs(self, contexts: np.ndarray, chunk_size: int = 128) -> np.ndarray:
        features = quadratic_features(contexts, dtype=np.float32)
        result = np.empty((len(features), len(self.labels)), dtype=np.float32)
        counts_t = self._float_counts().T
        for start in range(0, len(features), chunk_size):
            block = features[start:start + chunk_size]
            result[start:start + len(block)] = block @ counts_t
        return result.astype(np.float64)

    def chosen_costs(self, contexts: np.ndarray, choices: np.ndarray) -> np.ndarray:
        features = quadratic_features(contexts, dtype=np.float32)
        selected = self.risk_counts[np.asarray(choices, dtype=np.int64)].astype(np.float32)
        return np.einsum('bf,bf->b', features, selected, optimize=True).astype(np.float64)

    def cost_for_labels(self, contexts: np.ndarray, labels: list[str]) -> np.ndarray:
        choices = []
        for label in labels:
            idx = self.index(label)
            if idx is None:
                choices.append(-1)
            else:
                choices.append(idx)
        choices = np.asarray(choices, dtype=int)
        result = np.full(len(choices), np.inf, dtype=np.float64)
        valid = choices >= 0
        if np.any(valid):
            result[valid] = self.chosen_costs(np.asarray(contexts)[valid], choices[valid])
        return result

    def subset(self, kind: str) -> np.ndarray:
        return np.flatnonzero(self.kinds == kind)


def build_catalog(mode: str = 'expanded', progress: bool = False) -> SynthesisCatalog:
    labels, kinds, rows = [], [], []
    candidate_count = 0
    for candidate_count, schedule in enumerate(candidate_schedules(mode), 1):
        decoder, report = decoder_and_certificate(schedule)
        if report['certified']:
            labels.append(schedule_label(schedule))
            kinds.append(schedule_kind(schedule))
            rows.append(quadratic_risk_upper_counts(schedule, decoder))
        if progress and candidate_count % 2000 == 0:
            print(f'CATALOG {candidate_count} candidates -> {len(labels)} certified')
    raw = np.stack(rows)
    max_count = int(raw.max())
    dtype = np.uint8 if max_count <= np.iinfo(np.uint8).max else np.uint16
    risk = raw.astype(dtype)
    return SynthesisCatalog(mode, labels, np.asarray(kinds, dtype='U8'), risk,
                            candidate_count=candidate_count, certified_count=len(labels))


def save_catalog(catalog: SynthesisCatalog, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    metadata = {
        'schema': CACHE_SCHEMA,
        'mode': catalog.mode,
        'candidate_count': catalog.candidate_count,
        'certified_count': catalog.certified_count,
        'fingerprint': catalog.fingerprint,
    }
    np.savez_compressed(path, labels=np.asarray(catalog.labels, dtype='U12'), kinds=catalog.kinds,
                        risk_counts=catalog.risk_counts, metadata=np.asarray(json.dumps(metadata)))


def load_catalog(path: Path, expected_mode: str | None = None) -> SynthesisCatalog:
    with np.load(path, allow_pickle=False) as saved:
        meta = json.loads(str(saved['metadata']))
        if meta.get('schema') != CACHE_SCHEMA:
            raise ValueError('Phase-3 catalog cache schema mismatch; rebuild the cache.')
        if expected_mode is not None and meta.get('mode') != expected_mode:
            raise ValueError(f'Catalog mode mismatch: expected {expected_mode}, found {meta.get("mode")}')
        catalog = SynthesisCatalog(meta['mode'], saved['labels'].astype(str).tolist(),
                                   saved['kinds'].astype(str), saved['risk_counts'].copy(),
                                   int(meta['candidate_count']), int(meta['certified_count']))
    if catalog.fingerprint != meta.get('fingerprint'):
        raise ValueError('Catalog fingerprint mismatch; cache may be corrupted.')
    return catalog


def ensure_catalog(path: Path, mode: str = 'expanded', progress: bool = True) -> SynthesisCatalog:
    if path.exists():
        return load_catalog(path, mode)
    catalog = build_catalog(mode, progress=progress)
    save_catalog(catalog, path)
    return catalog


def catalog_verification_summary(catalog: SynthesisCatalog) -> dict:
    kinds = {kind: int(np.count_nonzero(catalog.kinds == kind)) for kind in sorted(set(catalog.kinds.tolist()))}
    return {
        'mode': catalog.mode,
        'candidate_schedules': catalog.candidate_count,
        'certified_schedules': catalog.certified_count,
        'certified_by_kind': kinds,
        'risk_count_dtype': str(catalog.risk_counts.dtype),
        'risk_count_max': int(catalog.risk_counts.max()),
        'fingerprint': catalog.fingerprint,
    }
