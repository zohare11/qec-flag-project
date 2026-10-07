"""Rebuilt published rounds (skipped without stim/networkx/ortools)."""
import pytest

pytest.importorskip('stim')
pytest.importorskip('networkx')
pytest.importorskip('ortools')

from ftcompile import gadgets as GD  # noqa: E402
from ftcompile import published as P  # noqa: E402
from ftcompile.compilers import Graph  # noqa: E402
from ftcompile.core import check_program  # noqa: E402


@pytest.mark.parametrize('pr, n_cx', [(P.RB_CITADEL, 48), (P.LAO_C3, 30), (P.lao_c1((0, 0, 0)), 36)])
def test_published_rounds_are_single_fault_tolerant(pr, n_cx):
    prog = P.build(pr)                       # also asserts every CNOT is a hardware coupler
    assert prog.n_cx == n_cx
    assert check_program(prog, explain=False).passed


def test_fig1b_circuit3_as_drawn_is_not_a_valid_measurement():
    with pytest.raises(ValueError):
        check_program(P.build(P.rb_with_fig1b_circuit3()), explain=False)


def test_lao_readings_match_the_couplers():
    assert [len(P.lao_c1_readings(k)) for k in range(3)] == [14, 20, 8]


def test_ibm20_needs_only_two_ancillas_for_36():
    status, costs, pl = GD.optimal_direct_layout_on(P.IBM20_EDGES, 2)
    assert status == 'OPTIMAL' and costs == [6, 6, 6]
    prog, _ = GD.best_direct_round(pl, Graph(list(P.IBM20_EDGES), pl), (7, 8))
    assert prog.n_cx == 36 and check_program(prog, explain=False).passed
