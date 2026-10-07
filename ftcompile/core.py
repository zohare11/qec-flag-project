"""Stim-based core: logical flag rounds, physical programs, and the exact single-fault check.

Pipeline
--------
    logical round (virtual qubits)  --compiler-->  physical program (graph nodes)
    physical program  --to_stim-->  stim.Circuit with noise, detectors, observables
    stim.Circuit      --single_fault_check-->  pass/fail + fault witnesses

"Single-fault FT" here means: after one noisy syndrome-extraction round followed
by an ideal (noiseless) stabilizer read-out, no single fault and no single
incoming data error can be confused with a different single event that has a
different logical effect.  Equivalently the circuit-level distance is >= 3.
This is the same criterion as the project's C1 = 0 certification.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Iterable

import stim

# --------------------------------------------------------------------------
# Steane [[7,1,3]] code
# --------------------------------------------------------------------------
SUPPORT_MASKS = (0b0001111, 0b0110011, 0b1010101)
SUPPORTS = tuple(tuple(q for q in range(7) if (m >> q) & 1) for m in SUPPORT_MASKS)
# Check order used throughout the project: X0, X1, X2, Z0, Z1, Z2.
CHECKS = tuple([('X', s) for s in SUPPORTS] + [('Z', s) for s in SUPPORTS])
N_DATA = 7

# Virtual qubit ids: data 0..6, syndrome hubs, flags.
SYN = (7, 8)            # hub 0, hub 1
FLAG = {'A': 9, 'B': 10}
N_VIRTUAL = 11


@dataclass(frozen=True)
class Op:
    """One operation. qubits are virtual ids (logical round) or graph nodes (physical)."""
    name: str                   # R, RX, H, CX, M, MX
    qubits: tuple[int, ...]
    tag: str = ''               # route id for CX ('c2.i3'), check id for prep/meas ('c2')
    key: str = ''               # measurement key ('syn2', 'flag2')
    kind: str = ''              # CX provenance: direct | bridge | swap


@dataclass
class LogicalRound:
    ops: list[Op]
    labels: tuple[str, ...]
    hubs: tuple[int, ...]
    syn_keys: tuple[str, ...]                 # one per check
    flag_keys: tuple[tuple[str, ...], ...]    # per check, keys of used flags


def steane_flag_round(labels: Iterable[str], hubs: Iterable[int]) -> LogicalRound:
    """Six serialized flagged checks.  Label tokens: digits index the check's
    support (sorted), 'A'/'B' are the two CNOTs of flag A or B (project convention).
    Z check: syndrome |0>, flags |+>, CX(data->syn), CX(flag->syn).
    X check: syndrome |+>, flags |0>, CX(syn->data), CX(syn->flag)."""
    labels = tuple(labels); hubs = tuple(int(h) for h in hubs)
    if len(labels) != 6 or len(hubs) != 6:
        raise ValueError('expected six labels and six hubs')
    ops: list[Op] = []; syn_keys = []; flag_keys = []
    for ci, ((ctype, support), label, hub) in enumerate(zip(CHECKS, labels, hubs)):
        syn = SYN[hub]
        flags = [f for f in ('A', 'B') if f in label]
        syn_prep, flag_prep = ('R', 'RX') if ctype == 'Z' else ('RX', 'R')
        syn_meas, flag_meas = ('M', 'MX') if ctype == 'Z' else ('MX', 'M')
        ops.append(Op(syn_prep, (syn,), tag=f'c{ci}'))
        for f in flags:
            ops.append(Op(flag_prep, (FLAG[f],), tag=f'c{ci}'))
        for ri, tok in enumerate(label):
            other = FLAG[tok] if tok in FLAG else support[int(tok)]
            c, t = (other, syn) if ctype == 'Z' else (syn, other)
            ops.append(Op('CX', (c, t), tag=f'c{ci}.i{ri}', kind='direct'))
        ops.append(Op(syn_meas, (syn,), tag=f'c{ci}', key=f'syn{ci}'))
        for f in flags:
            ops.append(Op(flag_meas, (FLAG[f],), tag=f'c{ci}', key=f'flag{ci}{f}'))
        syn_keys.append(f'syn{ci}'); flag_keys.append(tuple(f'flag{ci}{f}' for f in flags))
    return LogicalRound(ops, labels, hubs, tuple(syn_keys), tuple(flag_keys))


# --------------------------------------------------------------------------
# Hardware: the project's synthetic 3x4 grid and placement
# --------------------------------------------------------------------------
def grid_edges(rows: int = 3, cols: int = 4) -> list[tuple[int, int]]:
    e = [(r * cols + c, r * cols + c + 1) for r in range(rows) for c in range(cols - 1)]
    e += [(r * cols + c, (r + 1) * cols + c) for r in range(rows - 1) for c in range(cols)]
    return sorted(e)


GRID_EDGES = grid_edges()
# Same placement as qecflag.phase5_hardware: data -> (0,3,8,11,1,10,9), hubs 5,6, flags A=4, B=7.
GRID_PLACEMENT = {0: 0, 1: 3, 2: 8, 3: 11, 4: 1, 5: 10, 6: 9, 7: 5, 8: 6, 9: 4, 10: 7}


@dataclass
class PhysicalProgram:
    ops: list[Op]
    n_nodes: int
    data_start: dict[int, int]     # data index -> node at start
    data_end: dict[int, int]       # data index -> node at end (differs only if a router moved data)
    syn_keys: tuple[str, ...]
    flag_keys: tuple[tuple[str, ...], ...]
    meta: dict = field(default_factory=dict)

    @property
    def n_cx(self) -> int:
        return sum(1 for o in self.ops if o.name == 'CX')


# --------------------------------------------------------------------------
# Stim circuit
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class Noise:
    p: float = 1e-3            # DEPOLARIZE2 after every CX
    p_prep: float | None = None
    p_meas: float | None = None
    p_incoming: float | None = None   # single data error entering the round
    p_idle: float | None = None       # DEPOLARIZE1 on every other active qubit per CX (default p/10)

    def get(self, name):
        v = getattr(self, name)
        if v is not None:
            return v
        return self.p / 10 if name == 'p_idle' else self.p


def _pauli_product(kind: str, nodes: Iterable[int]) -> list:
    t = []
    for q in nodes:
        t += [stim.target_x(q) if kind == 'X' else stim.target_z(q), stim.target_combiner()]
    return t[:-1]


def to_stim(prog: PhysicalProgram, noise: Noise = Noise(), keep=None) -> stim.Circuit:
    """Noisy Stim circuit with detectors (all syndrome/flag bits + ideal final
    boundary) and two observables (X_L.X_R, Z_L.Z_R) against a noiseless
    reference qubit.  Noise instructions are tagged with their route/check id so
    fault witnesses can be traced back to compiler decisions.

    keep: optional predicate on a noise tag; noise whose tag fails it is left out
    (used to isolate the faults of one route)."""
    ref = prog.n_nodes
    c = stim.Circuit()
    nm = 0
    meas_index: dict[str, int] = {}

    def mpp(targets):
        nonlocal nm
        c.append('MPP', targets); nm += 1
        return nm - 1

    def stabs(pos):
        out = []
        for ctype, support in CHECKS:
            out.append(mpp(_pauli_product(ctype, [pos[q] for q in support])))
        return out

    def logicals(pos):
        return (mpp(_pauli_product('X', [pos[q] for q in range(N_DATA)] ) + [stim.target_combiner(), stim.target_x(ref)]),
                mpp(_pauli_product('Z', [pos[q] for q in range(N_DATA)]) + [stim.target_combiner(), stim.target_z(ref)]))

    s0 = stabs(prog.data_start); l0 = logicals(prog.data_start)
    c.append('TICK')
    def noisy(name, targets, p, tag):
        if keep is None or keep(tag):
            c.append(name, targets, p, tag=tag)

    noisy('DEPOLARIZE1', [prog.data_start[q] for q in range(N_DATA)], noise.get('p_incoming'), 'incoming')
    active = sorted({q for o in prog.ops for q in o.qubits} | set(prog.data_start.values()))
    p_idle = noise.get('p_idle')
    for o in prog.ops:
        if o.name == 'R':
            c.append('R', o.qubits); noisy('X_ERROR', o.qubits, noise.get('p_prep'), f'prep:{o.tag}')
        elif o.name == 'RX':
            c.append('RX', o.qubits); noisy('Z_ERROR', o.qubits, noise.get('p_prep'), f'prep:{o.tag}')
        elif o.name == 'H':
            c.append('H', o.qubits)
        elif o.name == 'CX':
            c.append('CX', o.qubits)
            noisy('DEPOLARIZE2', o.qubits, noise.p, f'{o.kind}:{o.tag}')
            idle = [q for q in active if q not in o.qubits]
            if p_idle > 0 and idle:
                noisy('DEPOLARIZE1', idle, p_idle, f'idle:{o.tag}')
        elif o.name in ('M', 'MX'):
            noisy('X_ERROR' if o.name == 'M' else 'Z_ERROR', o.qubits, noise.get('p_meas'), f'meas:{o.tag}')
            c.append(o.name, o.qubits)
            meas_index[o.key] = nm; nm += 1
        else:
            raise ValueError(f'unsupported op {o.name}')
        if o.name == 'CX':
            c.append('TICK')
    s1 = stabs(prog.data_end); l1 = logicals(prog.data_end)

    def rec(i):
        return stim.target_rec(i - nm)

    for ci, key in enumerate(prog.syn_keys):
        c.append('DETECTOR', [rec(meas_index[key]), rec(s0[ci])], [ci, 0])
    for ci, keys in enumerate(prog.flag_keys):
        for key in keys:
            c.append('DETECTOR', [rec(meas_index[key])], [ci, 1])
    for ci in range(6):
        c.append('DETECTOR', [rec(s1[ci]), rec(s0[ci])], [ci, 2])
    c.append('OBSERVABLE_INCLUDE', [rec(l1[0]), rec(l0[0])], 0)
    c.append('OBSERVABLE_INCLUDE', [rec(l1[1]), rec(l0[1])], 1)
    return c


# --------------------------------------------------------------------------
# Exact single-fault check with witnesses
# --------------------------------------------------------------------------
@dataclass
class Witness:
    detectors: tuple[int, ...]
    events: list[dict]   # each: {'observables': (...), 'locations': [(noise_tag, pauli), ...]}


@dataclass
class FTResult:
    passed: bool
    n_conflicts: int
    witnesses: list[Witness]
    n_dem_errors: int
    first_order_failure: float = 0.0   # C1*p: probability an optimal decoder fails with one fault


def single_fault_check(circuit: stim.Circuit, explain: bool = True, max_witnesses: int = 50) -> FTResult:
    """Exact check that every pair of single events (incl. 'no error') with equal
    detector signatures has the same logical effect.  If not, return witnesses:
    the conflicting signatures and the circuit locations (noise tags) behind them."""
    dem = circuit.detector_error_model(decompose_errors=False)
    groups: dict[frozenset, dict[frozenset, list]] = defaultdict(lambda: defaultdict(list))
    groups[frozenset()][frozenset()].append(None)   # no-error event
    n = 0
    for inst in dem.flattened():
        if inst.type != 'error':
            continue
        n += 1
        t = inst.targets_copy()
        dets = frozenset(x.val for x in t if x.is_relative_detector_id())
        obs = frozenset(x.val for x in t if x.is_logical_observable_id())
        groups[dets][obs].append(inst)
    conflicts = [(d, g) for d, g in groups.items() if len(g) > 1]
    # First-order failure mass: in each conflicting signature an optimal decoder
    # picks the most likely logical class; the rest of the probability fails.
    f1 = 0.0
    for d, g in conflicts:
        mass = {o: (1.0 if any(i is None for i in insts) else 0.0) +
                   sum(i.args_copy()[0] for i in insts if i is not None) for o, insts in g.items()}
        f1 += sum(mass.values()) - max(mass.values())
    witnesses: list[Witness] = []
    if conflicts and explain:
        filt = stim.DetectorErrorModel()
        chosen = conflicts[:max_witnesses]
        for _, g in chosen:
            for insts in g.values():
                for inst in insts:
                    if inst is not None:
                        filt.append(inst)
        expl = circuit.explain_detector_error_model_errors(dem_filter=filt, reduce_to_one_representative_error=False)
        by_terms = {}
        for e in expl:
            dets = frozenset(t.dem_target.val for t in e.dem_error_terms if t.dem_target.is_relative_detector_id())
            obs = frozenset(t.dem_target.val for t in e.dem_error_terms if t.dem_target.is_logical_observable_id())
            locs = [(loc.noise_tag, _pauli_str(loc)) for loc in e.circuit_error_locations]
            by_terms[(dets, obs)] = locs
        for d, g in chosen:
            events = [{'observables': tuple(sorted(o)), 'locations': by_terms.get((d, o), [('no-error', '')])}
                      for o in g]
            witnesses.append(Witness(tuple(sorted(d)), events))
    return FTResult(not conflicts, len(conflicts), witnesses, n, f1)


def _pauli_str(loc) -> str:
    return ' '.join(f'{t.gate_target.pauli_type}{t.gate_target.value}' for t in loc.flipped_pauli_product)


def check_program(prog: PhysicalProgram, noise: Noise = Noise(), explain: bool = True) -> FTResult:
    return single_fault_check(to_stim(prog, noise), explain=explain)
