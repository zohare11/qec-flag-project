"""Tests for flag-bridge gadgets (skipped without stim/networkx/ortools)."""
import pytest

pytest.importorskip('stim')
pytest.importorskip('networkx')
pytest.importorskip('ortools')

from ftcompile import gadgets as GD  # noqa: E402
from ftcompile.compilers import Graph  # noqa: E402
from ftcompile.core import check_program, grid_edges  # noqa: E402


def test_flag_bridge_pattern_measures_and_is_ft():
    # data 1 and 2 couple to the flag inside its window
    assert GD._isolated_ok(0, GD.Pattern('A0123A', '-SAAS-'))
    assert GD._isolated_ok(3, GD.Pattern('A0123A', '-SAAS-'))


def test_coupling_outside_flag_window_is_rejected():
    # flag A is not in a cat state with S yet -> the syndrome is not the stabilizer
    assert not GD._isolated_ok(0, GD.Pattern('0A123A', 'A-SSS-'))


def test_every_split_is_certified():
    for c in range(6):
        assert all(GD.pattern_for(c, s) is not None for s in GD.all_splits(False))


def test_exact_optimum_on_3x4_is_40_and_verifies():
    status, costs, pl = GD.optimal_direct_layout(3, 4, 4)
    assert status == 'OPTIMAL' and sorted(costs) == [6, 6, 8]
    prog, _ = GD.best_direct_round(pl, Graph(grid_edges(3, 4), pl))
    assert prog.n_cx == 40
    assert check_program(prog, explain=False).passed
