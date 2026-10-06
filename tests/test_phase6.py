from pathlib import Path
import numpy as np

from qecflag.phase4_physics import simulate_round
from qecflag.phase5_actions import ensure_hardware_action_table, actions_to_round
from qecflag.phase5_hardware import hardware_round_metrics
from qecflag.phase5_noise import sample_hardware_contexts
from qecflag.phase6_native import (
    build_native_plan, simulate_native, explicit_native_risk, simulate_native_finite_p,
)

ROOT = Path(__file__).resolve().parents[1]


def _case(seed=701):
    t = ensure_hardware_action_table(ROOT)
    c = sample_hardware_contexts(1, seed, 'hw_id').context(0)
    row = tuple([t.index('H0|0A12A3')] * 6)
    labels, hubs = actions_to_round(row, t)
    return t, c, labels, hubs


def test_native_plan_matches_phase5_count_and_duration():
    _, c, labels, hubs = _case()
    plan = build_native_plan(labels, hubs, c)
    phase5 = hardware_round_metrics(labels, hubs, c)
    assert plan.native_cx == phase5.native_cx
    assert np.isclose(plan.duration_ns, phase5.duration_ns)


def test_native_ideal_matches_logical_round_for_single_incoming_errors():
    _, c, labels, hubs = _case(702)
    plan = build_native_plan(labels, hubs, c)
    errors = [0]
    for q in range(7):
        errors += [1 << q, 1 << (7 + q), (1 << q) | (1 << (7 + q))]
    for error in errors:
        assert simulate_native(plan, incoming_data=error) == simulate_round(labels, incoming_data=error)


def test_explicit_native_risk_is_finite_and_detects_routing_single_fault_problem():
    _, c, labels, hubs = _case(703)
    risk = explicit_native_risk(labels, hubs, c, pair_block=128)
    assert len(risk.records.data) > 1000
    assert risk.c1 >= 0 and np.isfinite(risk.c1)
    assert risk.c2 >= 0 and np.isfinite(risk.c2)
    # Naive SWAP routing through the occupied grid introduces unflagged native
    # hook faults for this reproducible reference case. Phase 6 is meant to
    # detect, not hide, this failure of the Phase-5 reduced model.
    assert risk.c1 > 0
    assert risk.decoder.single_fault_failures > 0


def test_native_zero_p_has_no_failures():
    _, c, labels, hubs = _case(704)
    risk = explicit_native_risk(labels, hubs, c, pair_block=128)
    out = simulate_native_finite_p(risk, 0.0, 200, 5)
    assert out['failures'] == 0
    assert out['logical_failure_rate'] == 0


def test_small_p_formula_includes_first_order_term():
    _, c, labels, hubs = _case(705)
    risk = explicit_native_risk(labels, hubs, c, pair_block=128)
    p = 1e-4
    assert np.isclose(risk.small_p(p), p * risk.c1 + p * p * risk.c2)
