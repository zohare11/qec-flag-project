"""Parallel flag-bridge blocks (skipped without stim/networkx/ortools/scipy)."""
import pytest

pytest.importorskip('stim')
pytest.importorskip('networkx')
pytest.importorskip('ortools')
pytest.importorskip('scipy')

import networkx as nx  # noqa: E402

from ftcompile import parallel as PA  # noqa: E402
from ftcompile import published as P  # noqa: E402
from ftcompile.core import check_program, grid_edges  # noqa: E402


def test_square_grid_round_has_28_cnots_and_is_ft():
    d = PA.SQUARE_14
    prog = d.program()                       # build() asserts every CNOT is a grid coupler
    assert d.block_cx() == 14 and prog.n_cx == 28
    assert check_program(prog, explain=False).passed


def test_hook_test_accepts_14_and_rejects_13_for_the_design():
    d = PA.SQUARE_14
    G = nx.Graph(list(d.edges))
    assert PA.hook_feasible(G, d.anc, d.ops, d.root, 14)
    assert not PA.hook_feasible(G, d.anc, d.ops, d.root, 13)


def test_model_reproduces_lao_parallel_block():
    G = nx.Graph(list(P.IBM20_EDGES))
    ops = ((0, 1), (1, 2), (2, 3), (2, 3), (1, 2), (0, 1))
    assert min(c for c, *_ in PA.placements(G, (12, 8, 7, 6), ops, 0, 99)) == 15
    assert PA.hook_feasible(G, (12, 8, 7, 6), ops, 0, 15)


def test_nothing_at_13_on_the_2x2_ancilla_square():
    G = nx.Graph(grid_edges(9, 9))
    nodes = (30, 31, 39, 40)
    recs = PA.linear_records(G, nodes, 6, 13)
    assert recs                               # linearly there are cheap designs ...
    assert not any(PA.hook_feasible(G, nodes, ops, root, 13) for _, ops, root in recs)   # ... none survive the hooks


def test_z_spreads_from_target_to_control():
    Z = PA.z_propagation(((0, 1),), 2)
    assert Z[(1, 0)][1] == 0b11 and Z[(0, 0)][1] == 0b01
