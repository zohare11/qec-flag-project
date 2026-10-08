"""SAT synthesis and heavy-hex helpers (skipped without the solvers)."""
import pytest

pytest.importorskip('stim')
pytest.importorskip('networkx')
pytest.importorskip('pycryptosat')
pytest.importorskip('pysat')

import networkx as nx  # noqa: E402

from ftcompile import heavyhex as HH  # noqa: E402
from ftcompile import parallel as PA  # noqa: E402
from ftcompile import synth as SY  # noqa: E402
from ftcompile import synth_sat as SS  # noqa: E402
from ftcompile.core import check_program, grid_edges  # noqa: E402
from ftcompile.published import build  # noqa: E402

# the 14-CNOT square-grid block in 9x9-grid coordinates (data node, ancilla) and (ancilla, ancilla)
KNOWN = [(22, 31), (30, 31), (21, 30), (30, 39), (31, 40), (29, 30), (41, 40), (30, 31), (38, 39), (39, 40),
         (21, 30), (32, 31), (30, 39), (48, 39)]


def test_sat_model_accepts_the_known_block_and_stim_agrees():
    G = nx.Graph(grid_edges(9, 9)); anc = (30, 31, 39, 40)
    r = SS.solve(G, anc, 30, 14, readouts=(31, 39, 40), assume=SS.canonical(KNOWN, SS.gate_order(G, anc)))
    assert r.status == 'SAT'
    prog = build(SY.to_published(r, G))
    assert prog.n_cx == 28 and check_program(prog, explain=False).passed


def test_heavy_hex_shape_and_reach():
    E, pos = HH.heavy_hex(4, 7)
    G = nx.Graph(E)
    assert max(dict(G.degree()).values()) == 3 and nx.girth(G) == 12
    inner = [n for n in G if 2 <= pos[n][0] <= 4 and 2 <= pos[n][1] <= 10]
    for k in (6, 8):
        assert max(len({x for a in S for x in G[a] if x not in S}) for S in PA.connected_subsets(G, k, within=inner)) < 7
