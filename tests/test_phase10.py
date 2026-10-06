from pathlib import Path
import numpy as np

from qecflag.phase5_noise import sample_hardware_contexts
from qecflag.phase8_experiment import ensure_continuous_catalog, _choose_proxy, _labels_hubs
from qecflag.phase10_scheduler import (
    schedule_parallel, validate_resource_schedule, certify_parallel_schedule,
    local_priority_search, beam_priority_search, simulate_parallel_round,
)
from qecflag.phase10_repeated import parallel_repeated_fault_records, simulate_parallel_detector_finite_p

ROOT = Path(__file__).resolve().parents[1]


def _case(seed=10201):
    cat = ensure_continuous_catalog(ROOT)
    ctx = sample_hardware_contexts(1, seed, 'hw_id').context(0)
    e = _choose_proxy(cat['entries'], ctx, 4)[0]
    labels, hubs = _labels_hubs(e)
    return ctx, labels, hubs


def test_phase10_resource_valid_schedulers():
    ctx, labels, hubs = _case()
    for method in ('serialized','ancilla_overlap','asap','shortest_greedy','critical_greedy','noise_greedy','css_block'):
        s = schedule_parallel(labels, hubs, ctx, method)
        assert validate_resource_schedule(s)
        assert s.total_native_cx > 0
        assert s.duration_ns > 0


def test_phase10_parallel_reduces_or_matches_serial_time():
    ctx, labels, hubs = _case()
    serial = schedule_parallel(labels, hubs, ctx, 'serialized')
    asap = schedule_parallel(labels, hubs, ctx, 'asap')
    assert asap.duration_ns <= serial.duration_ns
    assert asap.total_native_cx == serial.total_native_cx
    assert asap.max_parallel_cx >= 1


def test_phase10_ancilla_overlap_preserves_ft_in_reference_case():
    ctx, labels, hubs = _case()
    serial = schedule_parallel(labels, hubs, ctx, 'serialized')
    anc = schedule_parallel(labels, hubs, ctx, 'ancilla_overlap')
    cs = certify_parallel_schedule(serial, ctx)
    ca = certify_parallel_schedule(anc, ctx)
    assert cs.passed and ca.passed
    assert cs.c1 == 0.0 and ca.c1 == 0.0
    assert anc.duration_ns <= serial.duration_ns


def test_phase10_aggressive_asap_is_not_silently_assumed_ft():
    ctx, labels, hubs = _case()
    asap = schedule_parallel(labels, hubs, ctx, 'asap')
    cert = certify_parallel_schedule(asap, ctx)
    # This fixed regression case is intentionally unsafe: Phase 10 must catch
    # that resource-valid concurrency can destroy the single-fault guarantee.
    assert not cert.passed
    assert cert.c1 > 0 or cert.single_fault_failures > 0 or cert.conflicts > 0


def test_phase10_local_and_beam_are_deterministic_and_valid():
    ctx, labels, hubs = _case()
    a = local_priority_search(labels, hubs, ctx)
    b = local_priority_search(labels, hubs, ctx)
    assert a.priority == b.priority
    assert np.isclose(a.duration_ns, b.duration_ns)
    beam1 = beam_priority_search(labels, hubs, ctx, width=4)
    beam2 = beam_priority_search(labels, hubs, ctx, width=4)
    assert [x.priority for x in beam1] == [x.priority for x in beam2]
    assert all(validate_resource_schedule(x) for x in beam1)


def test_phase10_serial_ideal_round_is_identity():
    ctx, labels, hubs = _case()
    s = schedule_parallel(labels, hubs, ctx, 'serialized')
    data, obs = simulate_parallel_round(s)
    assert data == 0
    assert obs == 0


def test_phase10_repeated_records_keep_round_location_ids_distinct():
    ctx, labels, hubs = _case()
    s = schedule_parallel(labels, hubs, ctx, 'ancilla_overlap')
    rec = parallel_repeated_fault_records(s, ctx, 3)
    assert len(rec.data) == len(rec.syndrome_history) == len(rec.flag_history) == len(rec.location)
    assert len(np.unique(rec.location)) > 0
    assert rec.location.max() > rec.location.min()


def test_phase10_detector_smoke_preserves_single_fault_guarantee():
    ctx, labels, hubs = _case()
    s = schedule_parallel(labels, hubs, ctx, 'ancilla_overlap')
    r = simulate_parallel_detector_finite_p(s, ctx, rounds=3, p=2e-4, shots=20, seed=7)
    assert r['detector_single_fault_conflicts'] == 0
    assert r['detector_single_fault_failures'] == 0
    assert r['detector_incoming_failures'] == 0
    assert 0.0 <= r['logical_failure_rate'] <= 1.0
