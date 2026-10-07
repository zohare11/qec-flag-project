"""Tests for the exact repairability oracle (skipped without stim/networkx/ortools)."""
import json
import random
from pathlib import Path

import pytest

pytest.importorskip('stim')
pytest.importorskip('networkx')
pytest.importorskip('ortools')

from ftcompile.core import check_program, steane_flag_round  # noqa: E402
from ftcompile.compilers import Graph, compile_bridge  # noqa: E402
from ftcompile.exact import build_model, solve, validate_decomposition  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
META = json.loads((ROOT / 'cache' / 'phase7_certified_bridge_catalog.json').read_text())['metadata']
SHOWCASE = (tuple(META['base_labels']), tuple(META['base_hubs']))


@pytest.fixture(scope='module')
def graph():
    return Graph()


@pytest.fixture(scope='module')
def showcase(graph):
    lr = steane_flag_round(*SHOWCASE)
    return lr, build_model(lr, graph)


def test_route_decomposition_is_exact(graph, showcase):
    lr, m = showcase
    rng = random.Random(0)
    choices = [{r: m.candidates[r].index(p) for r, p in compile_bridge(lr, graph, pol).meta['paths'].items()}
               for pol in ('shortest', 'ancilla_first')]
    choices += [{r: rng.randrange(len(m.candidates[r])) for r in m.routes} for _ in range(4)]
    for ch in choices:
        assert validate_decomposition(m, lr, graph, ch)


def test_oracle_solution_verifies_and_is_minimal(graph, showcase):
    lr, m = showcase
    start = compile_bridge(lr, graph, 'shortest').meta['paths']
    res = solve(m, 'edits', start=start)
    assert res.status == 'feasible'
    assert check_program(compile_bridge(lr, graph, 'shortest', overrides=res.paths), explain=False).passed
    assert res.objective <= 6        # greedy repair needed 6 route changes on this round
    assert solve(m, 'edits', start=compile_bridge(lr, graph, 'ancilla_first').meta['paths']).objective == 0


def test_oracle_reports_infeasible_round(graph):
    lr = steane_flag_round(('A2301A',) * 6, (0,) * 6)
    m = build_model(lr, graph)
    assert solve(m).status == 'infeasible'
    rng = random.Random(1)
    for _ in range(5):   # spot check: random assignments indeed fail
        paths = {r: rng.choice(m.candidates[r]) for r in m.routes}
        assert not check_program(compile_bridge(lr, graph, 'shortest', overrides=paths), explain=False).passed
