from pathlib import Path
import numpy as np

from qecflag.phase5_noise import sample_hardware_contexts
from qecflag.phase8_experiment import ensure_continuous_catalog
from qecflag.phase8_timing import build_timed_bridge_plan, repeated_fault_records
from qecflag.phase9_analysis import (
    syndrome_history_to_detectors, detectors_to_syndrome_history,
    build_detector_pair_decoder, exact_c1_c2, estimate_raw_t3,
)

ROOT = Path(__file__).resolve().parents[1]


def _fixture():
    e = ensure_continuous_catalog(ROOT)['entries'][0]
    c = sample_hardware_contexts(1, 9401, 'hw_id').context(0)
    p = build_timed_bridge_plan(e['labels'], e['hubs'], c)
    return e, c, p


def test_detector_transform_roundtrip():
    rng = np.random.default_rng(1)
    for _ in range(100):
        h = int(rng.integers(0, 1 << 24))
        d = syndrome_history_to_detectors(h, 3)
        assert detectors_to_syndrome_history(d, 3) == h


def test_detector_pair_decoder_preserves_single_fault_correction():
    _, c, p = _fixture()
    rec = repeated_fault_records(p, c, 3)
    dec = build_detector_pair_decoder(p, c, 3, 2e-4, records=rec)
    assert dec.single_fault_conflicts == 0
    assert dec.single_fault_failures == 0
    assert dec.incoming_failures == 0
    assert dec.primitive_count > 0
    assert dec.map_entries > dec.primitive_count


def test_exact_low_order_has_zero_c1_and_positive_c2():
    _, c, p = _fixture()
    rec = repeated_fault_records(p, c, 1)
    dec = build_detector_pair_decoder(p, c, 1, 2e-4, records=rec)
    c1, c2, n1, n2, pair_sub, total = exact_c1_c2(rec, dec, pair_block=128)
    assert c1 == 0.0
    assert n1 == 0
    assert c2 > 0
    assert n2 > 0
    assert pair_sub > 0
    assert total > 0


def test_triple_estimator_is_reproducible_and_finite():
    _, c, p = _fixture()
    rec = repeated_fault_records(p, c, 1)
    dec = build_detector_pair_decoder(p, c, 1, 2e-4, records=rec)
    a = estimate_raw_t3(rec, dec, 500, 7)
    b = estimate_raw_t3(rec, dec, 500, 7)
    assert a == b
    assert np.isfinite(a[0]) and a[0] >= 0
    assert np.isfinite(a[1]) and a[1] >= 0
    assert 0 <= a[2] <= 1
