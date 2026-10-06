"""Tests for the Stim-based ftcompile core (skipped if stim/networkx are missing)."""
import json
from pathlib import Path

import pytest

stim = pytest.importorskip('stim')
pytest.importorskip('networkx')

from ftcompile.core import Noise, check_program, steane_flag_round, to_stim  # noqa: E402
from ftcompile.compilers import Graph, bridge_cnots, compile_bridge, compile_unrouted  # noqa: E402
from ftcompile.repair import repair_paths  # noqa: E402
from ftcompile.decode import logical_error_rate  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
META = json.loads((ROOT / 'cache' / 'phase7_certified_bridge_catalog.json').read_text())['metadata']
SHOWCASE = (tuple(META['base_labels']), tuple(META['base_hubs']))


@pytest.fixture(scope='module')
def graph():
    return Graph()


@pytest.mark.parametrize('d', range(1, 7))
def test_bridge_is_exactly_a_remote_cnot(d):
    path = tuple(range(d + 1))
    c = stim.Circuit()
    for a, b in bridge_cnots(path):
        c.append('CX', [a, b])
    ref = stim.Circuit(); ref.append('CX', [0, d]); ref.append('I', [d])
    assert c.to_tableau() == ref.to_tableau()
    assert len(bridge_cnots(path)) == (1 if d == 1 else 4 * d - 4)


def test_routing_choice_decides_fault_tolerance(graph):
    lr = steane_flag_round(*SHOWCASE)
    assert check_program(compile_unrouted(lr, graph)).passed
    assert check_program(compile_bridge(lr, graph, 'ancilla_first')).passed
    res = check_program(compile_bridge(lr, graph, 'shortest'))
    assert not res.passed and res.n_conflicts > 0 and res.witnesses
    tags = {t for w in res.witnesses for e in w.events for t, _ in e['locations']}
    assert any(t.startswith('bridge:') for t in tags)   # witnesses point at bridge gates


def test_matches_project_verifier(graph):
    """Same physical paths, two independent verifiers, same verdict."""
    from qecflag.phase5_noise import sample_hardware_contexts
    from qecflag.phase6_native import native_fault_records, build_native_decoder
    from ftrepair_v3.model import RoutingState, build_plan
    ctx = sample_hardware_contexts(1, 7101, 'hw_id').context(0)
    table = json.loads((ROOT / 'cache' / 'phase4_action_table.json').read_text())['labels']
    rounds = [SHOWCASE] + [((table[i],) * 6, (h,) * 6) for i, h in ((0, 0), (17, 1), (40, 0))]
    for labels, hubs in rounds:
        lr = steane_flag_round(labels, hubs)
        for policy in ('shortest', 'ancilla_first'):
            prog = compile_bridge(lr, graph, policy)
            paths = {(int(k[1:].split('.i')[0]), int(k.split('.i')[1])): p for k, p in prog.meta['paths'].items()}
            plan = build_plan(RoutingState.from_parts(labels, hubs, paths), ctx)
            dec = build_native_decoder(plan, native_fault_records(plan, ctx))
            theirs = dec.single_fault_conflicts == 0 and dec.single_fault_failures == 0 and dec.incoming_failures == 0
            assert check_program(prog, explain=False).passed == theirs, (labels[0], hubs[0], policy)


def test_repair_restores_fault_tolerance(graph):
    lr = steane_flag_round(*SHOWCASE)
    rr = repair_paths(lr, graph, 'shortest', max_calls=150)
    assert rr.success and rr.final_conflicts == 0 and rr.changed_routes
    assert check_program(rr.program, explain=False).passed


def test_qiskit_default_optimizer_strips_flags(graph):
    pytest.importorskip('qiskit')
    from ftcompile.compilers import compile_qiskit
    lr = steane_flag_round(*SHOWCASE)
    kept = compile_qiskit(lr, graph, routed=False, optimization_level=1)
    stripped = compile_qiskit(lr, graph, routed=False, optimization_level=None)
    assert kept.meta['logical_cx_kept'] == 36 and check_program(kept, explain=False).passed
    assert stripped.meta['logical_cx_kept'] == 24          # the 12 flag CNOTs are gone
    assert not check_program(stripped, explain=False).passed


def test_decoder_separates_ft_and_non_ft(graph):
    lr = steane_flag_round(*SHOWCASE)
    good = logical_error_rate(to_stim(compile_unrouted(lr, graph), Noise(p=2e-3)), 20_000, seed=3)
    bad = logical_error_rate(to_stim(compile_bridge(lr, graph, 'shortest'), Noise(p=2e-3)), 20_000, seed=3)
    assert good['rate'] < bad['rate'] / 3
