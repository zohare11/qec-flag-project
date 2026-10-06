"""Order-2 maximum-likelihood lookup decoder and logical-error sampling.

For each detector signature reachable by at most two error mechanisms of the
detector error model, predict the most likely observable flip.  Exact enough
for a distance-3 code with flags; unseen signatures predict 'no flip'.
"""
from __future__ import annotations

import numpy as np
import stim


def _dem_arrays(dem: stim.DetectorErrorModel):
    dets, obs, probs = [], [], []
    for inst in dem.flattened():
        if inst.type != 'error':
            continue
        d = o = 0
        for t in inst.targets_copy():
            if t.is_relative_detector_id():
                d ^= 1 << t.val
            elif t.is_logical_observable_id():
                o ^= 1 << t.val
        dets.append(d); obs.append(o); probs.append(inst.args_copy()[0])
    return np.array(dets, dtype=np.uint64), np.array(obs, dtype=np.uint64), np.array(probs)


class LookupDecoder:
    def __init__(self, dem: stim.DetectorErrorModel):
        if dem.num_detectors > 60:
            raise ValueError('lookup decoder supports at most 60 detectors')
        d, o, p = _dem_arrays(dem)
        keys = [np.array([0], dtype=np.uint64), (d << np.uint64(2)) | o]
        weights = [np.array([1.0]), p]
        n = len(d)
        for i in range(n - 1):           # all unordered pairs, row by row
            dd = d[i] ^ d[i + 1:]; oo = o[i] ^ o[i + 1:]
            keys.append((dd << np.uint64(2)) | oo); weights.append(p[i] * p[i + 1:])
        keys = np.concatenate(keys); weights = np.concatenate(weights)
        uk, inv = np.unique(keys, return_inverse=True)
        w = np.bincount(inv, weights=weights)
        syn = uk >> np.uint64(2); ob = uk & np.uint64(3)
        order = np.lexsort((-w, syn))        # per syndrome, heaviest observable first
        syn, ob = syn[order], ob[order]
        first = np.ones(len(syn), dtype=bool); first[1:] = syn[1:] != syn[:-1]
        self.syndromes = syn[first]; self.prediction = ob[first]
        self.n_detectors = dem.num_detectors

    def decode(self, det_bits: np.ndarray) -> np.ndarray:
        """det_bits: (shots, n_detectors) bool -> predicted observable mask per shot."""
        weights = np.uint64(1) << np.arange(det_bits.shape[1], dtype=np.uint64)
        syn = (det_bits.astype(np.uint64) * weights).sum(axis=1, dtype=np.uint64)
        idx = np.searchsorted(self.syndromes, syn)
        idx = np.minimum(idx, len(self.syndromes) - 1)
        hit = self.syndromes[idx] == syn
        return np.where(hit, self.prediction[idx], np.uint64(0))


def logical_error_rate(circuit: stim.Circuit, shots: int, seed: int = 0, batch: int = 200_000,
                       min_failures: int | None = None) -> dict:
    """Sample up to `shots` shots, stopping early once `min_failures` failures are seen."""
    dem = circuit.detector_error_model(decompose_errors=False)
    dec = LookupDecoder(dem)
    sampler = circuit.compile_detector_sampler(seed=seed)
    fails = done = 0
    while done < shots and (min_failures is None or fails < min_failures):
        n = min(batch, shots - done)
        det, obs = sampler.sample(n, separate_observables=True)
        actual = (obs.astype(np.uint64) * (np.uint64(1) << np.arange(obs.shape[1], dtype=np.uint64))).sum(axis=1, dtype=np.uint64)
        fails += int(np.count_nonzero(dec.decode(det) != actual)); done += n
    rate = fails / done
    z = 1.959963984540054
    denom = 1 + z * z / done
    centre = (rate + z * z / (2 * done)) / denom
    half = z * np.sqrt(rate * (1 - rate) / done + z * z / (4 * done * done)) / denom
    return {'shots': done, 'failures': fails, 'rate': rate, 'ci95': (max(0.0, centre - half), centre + half)}
