"""Decoders for arbitrary (hook-error) DEMs: BP+OSD (`ldpc`) and Tesseract (`tesseract-decoder`); both optional."""
import numpy as np
import scipy.sparse as sp

def dem_matrices(dem):
    """Merge identical-symptom errors; return H (dets x errs), L (obs x errs), priors."""
    cols = {}
    for inst in dem.flattened():
        if inst.type != 'error':
            continue
        p = inst.args_copy()[0]
        dets = tuple(sorted(t.val for t in inst.targets_copy() if t.is_relative_detector_id()))
        obs = tuple(sorted(t.val for t in inst.targets_copy() if t.is_logical_observable_id()))
        if not dets and not obs:
            continue
        key = (dets, obs)
        q = cols.get(key, 0.0)
        cols[key] = q * (1 - p) + p * (1 - q)
    keys = list(cols)
    H = sp.lil_matrix((dem.num_detectors, len(keys)), dtype=np.uint8)
    L = sp.lil_matrix((dem.num_observables, len(keys)), dtype=np.uint8)
    for j, (dets, obs) in enumerate(keys):
        for d_ in dets:
            H[d_, j] = 1
        for o in obs:
            L[o, j] = 1
    return H.tocsr(), L.tocsr(), np.array([cols[k] for k in keys])

class BPOSD:
    def __init__(self, dem, osd_order=10, max_iter=None):
        from ldpc import BpOsdDecoder
        self.H, self.L, pri = dem_matrices(dem)
        self.dec = BpOsdDecoder(self.H, error_channel=list(pri), max_iter=max_iter or 30, bp_method='minimum_sum',
                                ms_scaling_factor=0.625, osd_method='osd_cs', osd_order=osd_order)
    def decode_batch(self, dets):
        out = np.zeros((dets.shape[0], self.L.shape[0]), dtype=bool)
        for i in range(dets.shape[0]):
            if dets[i].any():
                e = self.dec.decode(dets[i].astype(np.uint8))
                out[i] = (self.L @ e) % 2
        return out

class Tess:
    def __init__(self, dem, beam=5):
        from tesseract_decoder import tesseract as T
        self.dec = T.TesseractDecoder(T.TesseractConfig(dem=dem, det_beam=beam))
    def decode_batch(self, dets):
        return np.asarray(self.dec.decode_batch(dets), dtype=bool)
