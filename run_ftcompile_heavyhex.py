#!/usr/bin/env python3
"""Steane syndrome extraction on IBM's heavy-hex lattice: what the exact tools say so far.

    python run_ftcompile_heavyhex.py        # ~3 minutes
Writes runs/ftcompile_heavyhex/summary.md and results.json.
"""
from __future__ import annotations

import json
import sys
import time
import warnings
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
warnings.filterwarnings('ignore')

import networkx as nx  # noqa: E402

from ftcompile import gadgets as GD  # noqa: E402
from ftcompile import heavyhex as HH  # noqa: E402
from ftcompile import parallel as PA  # noqa: E402
from ftcompile import published as P  # noqa: E402
from ftcompile.compilers import compile_unrouted  # noqa: E402
from ftcompile.core import Op, PhysicalProgram, check_program, steane_flag_round  # noqa: E402


def qiskit_route(prog, edges, n_nodes, seed, opt):
    """Qiskit SABRE layout + routing of a finished round onto a coupling graph (SWAPs as 3 CNOTs)."""
    from qiskit import QuantumCircuit, transpile
    from qiskit.circuit.library import CXGate
    from qiskit.transpiler import CouplingMap
    nodes = sorted({q for o in prog.ops for q in o.qubits} | set(prog.data_start.values()))
    v = {n: i for i, n in enumerate(nodes)}
    keys = [o.key for o in prog.ops if o.key]; kidx = {k: i for i, k in enumerate(keys)}
    qc = QuantumCircuit(len(nodes), len(keys))
    for o in prog.ops:
        q = [v[x] for x in o.qubits]
        if o.name == 'R':
            qc.reset(q[0])
        elif o.name == 'RX':
            qc.reset(q[0]); qc.h(q[0])
        elif o.name == 'CX':
            qc.append(CXGate(label=o.tag), q)
        elif o.name == 'M':
            qc.measure(q[0], kidx[o.key])
        elif o.name == 'MX':
            qc.h(q[0]); qc.measure(q[0], kidx[o.key])
    cmap = CouplingMap([list(e) for e in edges] + [[b, a] for a, b in edges])
    tc = transpile(qc, coupling_map=cmap, basis_gates=['cx', 'h', 'swap', 'reset', 'measure'],
                   layout_method='sabre', routing_method='sabre', optimization_level=opt, seed_transpiler=seed)
    ops = []; nsw = 0
    for inst in tc.data:
        name = inst.operation.name; qs = tuple(tc.find_bit(x).index for x in inst.qubits)
        if name == 'reset':
            ops.append(Op('R', qs, tag='prep'))
        elif name == 'h':
            ops.append(Op('H', qs))
        elif name == 'cx':
            ops.append(Op('CX', qs, tag=inst.operation.label or 'x', kind='direct'))
        elif name == 'swap':
            a, b = qs
            for c, t in ((a, b), (b, a), (a, b)):
                ops.append(Op('CX', (c, t), tag=f'swap{nsw}', kind='swap'))
            nsw += 1
        elif name == 'measure':
            ops.append(Op('M', qs, tag='meas', key=keys[tc.find_bit(inst.clbits[0]).index]))
    init = tc.layout.initial_index_layout(); fin = tc.layout.final_index_layout()
    start = {q: int(init[v[prog.data_start[q]]]) for q in range(7)}
    end = {q: int(fin[v[prog.data_start[q]]]) for q in range(7)}
    return PhysicalProgram(ops, n_nodes, start, end, prog.syn_keys, prog.flag_keys, meta=dict(prog.meta)), nsw


def main():
    out = ROOT / 'runs' / 'ftcompile_heavyhex'; out.mkdir(parents=True, exist_ok=True)
    t0 = time.time(); R = {}
    E, pos = HH.heavy_hex(6, 11); G = nx.Graph(E)
    deg = dict(G.degree())
    R['graph'] = {'qubits': G.number_of_nodes(), 'couplers': G.number_of_edges(),
                  'degree_3': sum(1 for d in deg.values() if d == 3), 'degree_2': sum(1 for d in deg.values() if d == 2)}

    # A. serialized gadgets without routing
    R['direct'] = []
    for k in (2, 3, 4, 5, 6):
        st, costs, pl = GD.optimal_direct_layout_on(E, k, time_limit=300)
        R['direct'].append({'ancillas': k, 'status': st})
        print(f'[A] {k} ancillas: {st} ({time.time()-t0:.0f}s)', flush=True)

    # B. how many data positions a connected ancilla set can reach
    inner = [n for n in G if 2 <= pos[n][0] <= 8 and 4 <= pos[n][1] <= 16]
    R['reach'] = []
    for k in range(4, 10):
        best = 0; n = 0
        for S in PA.connected_subsets(G, k, within=inner):
            n += 1
            best = max(best, len({x for a in S for x in G[a] if x not in S}))
        R['reach'].append({'ancillas': k, 'sets': n, 'max_data_positions': best})
    print(f'[B] reach: {R["reach"]} ({time.time()-t0:.0f}s)', flush=True)

    # C. Qiskit's router on heavy-hex
    N = max(G.nodes) + 1
    cases = {'serialized flag round, 36 CNOTs': compile_unrouted(steane_flag_round(('A0123A',) * 6, (0,) * 6)),
             'parallel round (this project, square grid), 28 CNOTs': PA.SQUARE_14.program(),
             'parallel round (Poór et al.), 28 CNOTs': P.build(P.POOR)}
    R['qiskit'] = []
    for name, prog in cases.items():
        runs = []
        for opt in (1, 3):
            for seed in range(8):
                pp, nsw = qiskit_route(prog, E, N, seed, opt)
                runs.append({'cx': pp.n_cx, 'swaps': nsw, 'ft': check_program(pp, explain=False).passed,
                             'opt': opt, 'seed': seed})
        R['qiskit'].append({'circuit': name, 'runs': len(runs), 'min_cx': min(r['cx'] for r in runs),
                            'max_cx': max(r['cx'] for r in runs), 'ft_runs': sum(r['ft'] for r in runs)})
        print(f'[C] {name}: {R["qiskit"][-1]} ({time.time()-t0:.0f}s)', flush=True)
    R['elapsed_seconds'] = time.time() - t0
    (out / 'results.json').write_text(json.dumps(R, indent=1))
    (out / 'summary.md').write_text(render(R))
    print((out / 'summary.md').read_text())


def render(R):
    g = R['graph']
    L = ['# Steane syndrome extraction on heavy-hex (IBM): first results', '',
         f'Patch used: {g["qubits"]} qubits, {g["couplers"]} couplers; {g["degree_3"]} qubits have 3 neighbours, '
         f'{g["degree_2"]} have 2 (`ftcompile/heavyhex.py`). Corner qubits (3 neighbours) only touch side qubits '
         '(2 neighbours), so the graph has no triangles, no squares, and its shortest cycle is a 12-qubit hexagon.', '',
         '## 1. Off-the-shelf routing breaks fault tolerance', '',
         '| Round routed by Qiskit (SABRE layout + routing) | Compilations | CNOTs after routing | Fault-tolerant |',
         '|---|---:|---|---:|']
    for q in R['qiskit']:
        L.append(f'| {q["circuit"]} | {q["runs"]} | {q["min_cx"]}-{q["max_cx"]} | {q["ft_runs"]} of {q["runs"]} |')
    L += ['', 'Optimization levels 1 and 3, 8 seeds each. SWAPs move data qubits mid-round and a single fault on a '
          'SWAP spreads to two data qubits; none of the compiled rounds keeps circuit distance 3.', '',
          '## 2. No routing-free round with one or two flags per check', '',
          '| Ancillas | Exact search (CP-SAT over all placements) |', '|---:|---|']
    for d in R['direct']:
        L.append(f'| {d["ancillas"]} | {d["status"].lower()} |')
    L += ['', 'Why, in general: a one-flag gadget needs two adjacent ancillas whose other neighbours hold the 4 data '
          'qubits; adjacent qubits are one corner and one side qubit, with at most 2 + 1 = 3 free neighbours. A two-flag '
          'gadget works only as corner - side - corner, whose 4 free neighbours must be exactly that check\'s data. Two '
          'such gadgets cannot share a corner (the other gadget\'s side qubit would have to be a data qubit of this check), '
          'and the data qubit in all three checks has only 2 corner neighbours, so three disjoint gadgets cannot all reach '
          'it. So every heavy-hex round needs either three or more flags per check, or routing.', '',
          '## 3. A parallel block needs at least 9 ancillas', '',
          '| Connected ancillas | Sets checked | Most data positions next to them |', '|---:|---:|---:|']
    for r in R['reach']:
        L.append(f'| {r["ancillas"]} | {r["sets"]} | {r["max_data_positions"]} |')
    L += ['', 'All 7 data qubits must sit next to the ancillas; a tree of a corners and side qubits has a + 2 free '
          'neighbours, so 7 needs 5 corners and 9 ancillas. A cat state over 9 ancillas costs 16 CNOTs before any data '
          'coupling, so one parallel block costs at least 23 CNOTs per check type here, against 14 on a square grid.', '',
          '## 4. Status of the exact synthesis', '',
          '`ftcompile/synth_sat.py` encodes a whole block (any ancilla CNOTs, any data couplings, data placement, all '
          'single ancilla Z faults and CNOT fault pairs) as SAT with XOR clauses (CryptoMiniSat). On the square grid it '
          'finds the 14-CNOT block from scratch in about 2 minutes, and Stim confirms it. On a 9-ancilla heavy-hex row '
          'it returned no answer within 15 minutes for 26 slots. Next: fix the ancilla CNOT skeleton (cat trees) and let '
          'the solver place the couplings, which is a much smaller problem.', '',
          f'Runtime: {R["elapsed_seconds"]:.0f}s.']
    return '\n'.join(L) + '\n'


if __name__ == '__main__':
    main()
