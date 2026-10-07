"""Tests for the fast placement evaluator (skipped without stim/networkx/ortools)."""
import random

import pytest

pytest.importorskip('stim')
pytest.importorskip('networkx')
pytest.importorskip('ortools')

from ftcompile import placement as PL  # noqa: E402
from ftcompile.compilers import Graph, compile_bridge  # noqa: E402
from ftcompile.core import GRID_EDGES, GRID_PLACEMENT, check_program, steane_flag_round  # noqa: E402

# A layout from the search where every one of the 96 rounds can be routed FT:
#   d3 d2 H1 d4
#   FA .. H0 d5
#   d6 d0 d1 FB
FULL_COVERAGE = {0: 9, 1: 10, 2: 1, 3: 0, 4: 3, 5: 7, 6: 8, 7: 6, 8: 2, 9: 4, 10: 11}


def test_residual_table_sizes():
    assert len(PL.residual_table(1)[0]) == 15          # a direct CNOT: the 15 two-qubit Paulis
    assert all(len(PL.residual_table(d)[0]) > 15 for d in range(2, 6))


def test_predicted_signatures_match_full_stim():
    rng = random.Random(5)
    labels = [('B0213B',) * 6, ('A2301A',) * 6, ('A2301ABB',) * 6]
    for k in range(9):
        perm = rng.sample(range(12), 11) if k else [GRID_PLACEMENT[q] for q in range(11)]
        pl = {q: perm[q] for q in range(11)}
        lr = steane_flag_round(labels[k % 3], (k % 2,) * 6)
        tb = PL.round_tables(lr)
        paths = {r: rng.choice(PL.candidate_paths(pl[c], pl[t])) for r, c, t in tb.routes}
        assert PL.validate(lr, tb, pl, paths)


def test_placement_decides_repairability():
    lr = steane_flag_round(('A2301A',) * 6, (0,) * 6)
    tb = PL.round_tables(lr)
    assert PL.solve(PL.build(tb, GRID_PLACEMENT))[0] == 'infeasible'      # blocked corner on the current layout
    st, paths, _ = PL.solve(PL.build(tb, FULL_COVERAGE))
    assert st == 'feasible'
    prog = compile_bridge(lr, Graph(GRID_EDGES, FULL_COVERAGE), 'shortest', overrides=paths)
    assert check_program(prog, explain=False).passed
