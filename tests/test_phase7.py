from pathlib import Path
import numpy as np

from qecflag.phase4_physics import simulate_round
from qecflag.phase5_actions import ensure_hardware_action_table, actions_to_round
from qecflag.phase5_hardware import DATA_NODES, HUB_NODES, FLAG_NODES
from qecflag.phase5_noise import sample_hardware_contexts
from qecflag.phase6_native import _cx_frame, build_native_plan, explicit_native_risk, simulate_native
from qecflag.phase7_catalog import ensure_catalog
from qecflag.phase7_forensics import failing_single_fault_rows
from qecflag.phase7_routing import (
    bridge_cnot_pairs, build_bridge_plan, certify_bridge_round, bridge_native_risk,
    choose_ft_path,
)

ROOT = Path(__file__).resolve().parents[1]


def test_bridge_sequence_equals_direct_cnot_on_pauli_frames():
    rng = np.random.default_rng(7)
    for path in ((5, 4), (5, 4, 0), (5, 6, 2, 3)):
        c, t = path[0], path[-1]
        for _ in range(64):
            frame = int(rng.integers(0, 1 << 24))
            expected = _cx_frame(frame, c, t)
            got = frame
            for a, b in bridge_cnot_pairs(path):
                got = _cx_frame(got, a, b)
            assert got == expected


def test_ft_paths_avoid_data_interior_for_all_required_endpoints():
    endpoints = set(DATA_NODES) | set(FLAG_NODES.values())
    data = set(DATA_NODES)
    for hub in HUB_NODES:
        for endpoint in endpoints:
            if endpoint == hub:
                continue
            p = choose_ft_path(hub, endpoint)
            assert len(p) - 1 <= 3
            assert not any(x in data for x in p[1:-1])


def test_bridge_ideal_matches_logical_round():
    c = sample_hardware_contexts(1, 7120, 'hw_id').context(0)
    labels = ('B3021B',) * 6
    hubs = (1,) * 6
    plan = build_bridge_plan(labels, hubs, c)
    errors = [0]
    for q in range(7):
        errors += [1 << q, 1 << (7 + q), (1 << q) | (1 << (7 + q))]
    for error in errors:
        assert simulate_native(plan, incoming_data=error) == simulate_round(labels, incoming_data=error)


def test_known_bridge_round_restores_first_order_fault_tolerance():
    c = sample_hardware_contexts(1, 7121, 'hw_id').context(0)
    cert = certify_bridge_round(('B3021B',) * 6, (1,) * 6, c)
    assert cert.passed
    assert cert.c1 == 0.0
    assert cert.conflicts == 0
    assert cert.single_fault_failures == 0
    assert cert.incoming_failures == 0


def test_bridge_reference_uses_fewer_native_cx_than_swap_reference():
    c = sample_hardware_contexts(1, 7122, 'hw_id').context(0)
    labels = ('0A12A3',) * 6; hubs = (0,) * 6
    swap = build_native_plan(labels, hubs, c)
    bridge = build_bridge_plan(labels, hubs, c)
    assert bridge.native_cx < swap.native_cx


def test_phase6_reference_first_order_failures_are_inserted_swap_faults():
    c = sample_hardware_contexts(1, 7123, 'hw_id').context(0)
    labels = ('0A12A3',) * 6; hubs = (0,) * 6
    risk = explicit_native_risk(labels, hubs, c, pair_block=256)
    rows = failing_single_fault_rows(risk, 'swap_restore')
    assert rows
    assert {r['kind'] for r in rows} == {'cx'}
    assert not any(r['stage'] == 'logical_cx' for r in rows)
    assert {r['stage'] for r in rows} <= {'forward_swap', 'reverse_swap'}


def test_certified_catalog_is_nonempty_and_contains_expected_homogeneous_set():
    cat = ensure_catalog(ROOT)
    assert cat.metadata['certified_homogeneous'] == 32
    assert len(cat) == 74
    assert all(e['c1'] == 0.0 for e in cat.entries)
    assert all(e['single_fault_failures'] == 0 for e in cat.entries)


def test_certificate_is_stable_across_calibration_families_for_fixed_route():
    cat = ensure_catalog(ROOT)
    labels, hubs = cat.labels_hubs(0)
    for family, seed in [('hw_id', 7124), ('ood_hub0_bad', 7125), ('ood_logical_shift', 7126)]:
        c = sample_hardware_contexts(1, seed, family).context(0)
        cert = certify_bridge_round(labels, hubs, c)
        assert cert.passed
        assert cert.c1 == 0.0
