"""Phase 5 fixed hardware graph, routing model, and hardware-aware round cost.

This module deliberately uses a *reduced hardware model*.  A logical CNOT that is
not adjacent on the fixed 12-node coupling graph is assigned a SWAP-out / CNOT /
SWAP-back route.  Native-edge error multipliers and durations are compounded into
an effective logical-location calibration, and memory-idle exposure is added as
single-data-qubit Pauli weight before the existing exact Phase-4 malignant-pair
calculation is applied.

The inserted native routing gates are therefore not individually fault-enumerated.
Phase 5 tests whether hardware/timing context makes proposal search more useful;
it is not a transistor-level or backend-calibrated simulation.
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import heapq
import numpy as np

from .phase3_physics import schedule_from_label, FLAG_A, FLAG_B
from .phase4_physics import CHECKS, round_c2

# 3x4 nearest-neighbour grid, kept explicit so the experiment is reproducible.
N_PHYSICAL = 12
GRID_ROWS = 3
GRID_COLS = 4
EDGES = tuple(sorted(
    [(r * GRID_COLS + c, r * GRID_COLS + c + 1)
     for r in range(GRID_ROWS) for c in range(GRID_COLS - 1)] +
    [(r * GRID_COLS + c, (r + 1) * GRID_COLS + c)
     for r in range(GRID_ROWS - 1) for c in range(GRID_COLS)]
))
EDGE_INDEX = {edge: i for i, edge in enumerate(EDGES)}
N_EDGES = len(EDGES)

# Seven persistent data qubits, two alternative syndrome hubs, and two flag
# ancillas. Node 2 is intentionally unused as a routing waypoint.
DATA_NODES = (0, 3, 8, 11, 1, 10, 9)
HUB_NODES = (5, 6)
FLAG_NODES = {FLAG_A: 4, FLAG_B: 7}
LOGICAL_OCCUPIED = tuple(DATA_NODES) + HUB_NODES + tuple(FLAG_NODES.values())

BASE_CX_NS = 250.0


@dataclass(frozen=True)
class HardwareContext:
    logical: np.ndarray       # (6,96), Phase-4 synthetic logical calibration
    edge_error: np.ndarray    # (17,), relative native-CX error multiplier
    edge_duration: np.ndarray # (17,), ns per native CX
    prep_scale: np.ndarray    # (12,), preparation multiplier
    meas_scale: np.ndarray    # (12,), measurement multiplier
    idle_rate: np.ndarray     # (12,), effective Pauli weight per ns

    def validate(self) -> "HardwareContext":
        if np.asarray(self.logical).shape != (6, 96):
            raise ValueError('logical must have shape (6,96)')
        for name, value, shape in (
            ('edge_error', self.edge_error, (N_EDGES,)),
            ('edge_duration', self.edge_duration, (N_EDGES,)),
            ('prep_scale', self.prep_scale, (N_PHYSICAL,)),
            ('meas_scale', self.meas_scale, (N_PHYSICAL,)),
            ('idle_rate', self.idle_rate, (N_PHYSICAL,)),
        ):
            arr = np.asarray(value, dtype=np.float64)
            if arr.shape != shape or not np.isfinite(arr).all() or np.any(arr < 0):
                raise ValueError(f'invalid {name}')
        return self


@dataclass
class HardwareBatch:
    logical: np.ndarray
    edge_error: np.ndarray
    edge_duration: np.ndarray
    prep_scale: np.ndarray
    meas_scale: np.ndarray
    idle_rate: np.ndarray

    def __len__(self) -> int:
        return int(self.logical.shape[0])

    def context(self, i: int) -> HardwareContext:
        return HardwareContext(
            self.logical[i], self.edge_error[i], self.edge_duration[i],
            self.prep_scale[i], self.meas_scale[i], self.idle_rate[i],
        ).validate()

    def take(self, indices) -> "HardwareBatch":
        idx = np.asarray(indices, dtype=np.int64)
        return HardwareBatch(
            self.logical[idx], self.edge_error[idx], self.edge_duration[idx],
            self.prep_scale[idx], self.meas_scale[idx], self.idle_rate[idx],
        )


@dataclass(frozen=True)
class RouteStats:
    path: tuple[int, ...]
    native_cx: int
    duration_ns: float
    gate_scale: float


@dataclass(frozen=True)
class HardwareRoundMetrics:
    c2: float
    native_cx: int
    duration_ns: float
    total_data_idle_ns: float
    hub0_fraction: float
    two_flag_fraction: float


def _adjacency():
    adj = [[] for _ in range(N_PHYSICAL)]
    for u, v in EDGES:
        adj[u].append(v); adj[v].append(u)
    return tuple(tuple(sorted(x)) for x in adj)

ADJACENCY = _adjacency()


@lru_cache(maxsize=None)
def candidate_paths(source: int, target: int) -> tuple[tuple[int, ...], ...]:
    """All simple paths up to two hops longer than graph distance."""
    if source == target:
        return ((source,),)
    # BFS distance.
    dist = {source: 0}
    queue = [source]
    for u in queue:
        for v in ADJACENCY[u]:
            if v not in dist:
                dist[v] = dist[u] + 1; queue.append(v)
    cutoff = dist[target] + 2
    result = []
    def dfs(u: int, path: list[int]):
        if len(path) - 1 > cutoff:
            return
        if u == target:
            result.append(tuple(path)); return
        for v in ADJACENCY[u]:
            if v not in path:
                dfs(v, path + [v])
    dfs(source, [source])
    result.sort(key=lambda p: (len(p), p))
    return tuple(result)


def _edge_id(u: int, v: int) -> int:
    return EDGE_INDEX[(u, v) if u < v else (v, u)]


def _route_edge_counts(path: tuple[int, ...]) -> list[tuple[int, int]]:
    """SWAP-forward / CNOT / SWAP-back native-CX multiplicities.

    For d hops, the first d-1 path edges each carry two SWAPs (6 CX total),
    and the final adjacency carries the desired CX once.  The logical mapping is
    restored after the routed operation.
    """
    if len(path) < 2:
        return []
    edges = [_edge_id(path[i], path[i + 1]) for i in range(len(path) - 1)]
    return [(eid, 6 if i < len(edges) - 1 else 1) for i, eid in enumerate(edges)]


def route_stats(source: int, target: int, context: HardwareContext) -> RouteStats:
    """Choose the lowest first-order routed-CX + idle-risk path."""
    context.validate()
    if source == target:
        raise ValueError('A CNOT requires distinct physical qubits')
    mean_idle = float(np.mean(context.idle_rate[list(DATA_NODES)]))
    best = None
    for path in candidate_paths(source, target):
        pairs = _route_edge_counts(path)
        native = int(sum(count for _, count in pairs))
        duration = float(sum(count * context.edge_duration[eid] for eid, count in pairs))
        gate_scale = float(sum(count * context.edge_error[eid] for eid, count in pairs))
        # While a routed operation runs, persistent memory qubits are exposed to
        # idle error.  This term is used only to select a physical path; the full
        # idle contribution is added explicitly later.
        route_risk = gate_scale + duration * mean_idle * len(DATA_NODES)
        key = (route_risk, native, duration, path)
        if best is None or key < best[0]:
            best = (key, RouteStats(path, native, duration, gate_scale))
    assert best is not None
    return best[1]


def _token_node(token: int, support: tuple[int, ...]) -> int:
    if 0 <= token < 4:
        return DATA_NODES[support[token]]
    return FLAG_NODES[token]


def _gate_category_slice(token: int) -> slice:
    edge_slot = token if 0 <= token < 4 else (4 if token == FLAG_A else 5)
    start = 3 + 15 * edge_slot
    return slice(start, start + 15)


def _single_data_indices(check_type: str, data_code: int) -> int:
    """Index within a 15-outcome two-qubit Pauli block for data-only error."""
    if check_type == 'Z':
        pa, pb = data_code, 0  # data is control
    else:
        pa, pb = 0, data_code # data is target
    return 4 * pa + pb - 1


def hardware_effective_context(labels: tuple[str, ...], hubs: tuple[int, ...],
                               context: HardwareContext) -> tuple[np.ndarray, dict]:
    """Map hardware calibration/timing onto the Phase-4 6x96 fault weights."""
    if len(labels) != 6 or len(hubs) != 6:
        raise ValueError('Expected six labels and six hub choices')
    if any(h not in (0, 1) for h in hubs):
        raise ValueError('hub choices must be 0 or 1')
    context.validate()
    eff = np.asarray(context.logical, dtype=np.float64).copy()
    total_duration = 0.0
    native_cx = 0
    active_by_data = np.zeros(7, dtype=np.float64)
    data_locations: list[list[tuple[int, int]]] = [[] for _ in range(7)]

    for ci, ((check_type, support), label, hub) in enumerate(zip(CHECKS, labels, hubs)):
        hub_node = HUB_NODES[hub]
        template = schedule_from_label(label)
        used_a = FLAG_A in template
        used_b = FLAG_B in template
        # syndrome prep/readout + flag prep/readout physical scaling
        eff[ci, 0] *= context.prep_scale[hub_node]
        eff[ci, 93] *= context.meas_scale[hub_node]
        if used_a:
            eff[ci, 1] *= context.prep_scale[FLAG_NODES[FLAG_A]]
            eff[ci, 94] *= context.meas_scale[FLAG_NODES[FLAG_A]]
        if used_b:
            eff[ci, 2] *= context.prep_scale[FLAG_NODES[FLAG_B]]
            eff[ci, 95] *= context.meas_scale[FLAG_NODES[FLAG_B]]

        for token in template:
            endpoint = _token_node(token, support)
            source, target = (hub_node, endpoint) if check_type == 'X' else (endpoint, hub_node)
            stats = route_stats(source, target, context)
            eff[ci, _gate_category_slice(token)] *= stats.gate_scale
            total_duration += stats.duration_ns
            native_cx += stats.native_cx
            if 0 <= token < 4:
                logical_q = support[token]
                active_by_data[logical_q] += stats.duration_ns
                data_locations[logical_q].append((ci, token))

    # Persistent data memory idles whenever it is not participating in a routed
    # logical data-syndrome interaction.  Smear each qubit's accumulated idle
    # exposure over its existing data-CNOT locations, as isotropic X/Y/Z weight.
    # This is the reduced-model approximation that makes round timing matter.
    idle_by_data = np.maximum(0.0, total_duration - active_by_data)
    for q in range(7):
        locations = data_locations[q]
        if not locations:
            continue
        idle_weight = float(context.idle_rate[DATA_NODES[q]] * idle_by_data[q])
        share = idle_weight / len(locations)
        for ci, token in locations:
            check_type, _support = CHECKS[ci]
            start = _gate_category_slice(token).start
            for code in (1, 2, 3):
                eff[ci, start + _single_data_indices(check_type, code)] += share / 3.0

    details = {
        'native_cx': int(native_cx),
        'duration_ns': float(total_duration),
        'total_data_idle_ns': float(idle_by_data.sum()),
        'hub0_fraction': float(np.mean(np.asarray(hubs) == 0)),
        'two_flag_fraction': float(np.mean(['A' in label and 'B' in label for label in labels])),
        'idle_by_data_ns': idle_by_data.tolist(),
    }
    return eff, details


def hardware_round_metrics(labels: tuple[str, ...], hubs: tuple[int, ...],
                           context: HardwareContext) -> HardwareRoundMetrics:
    eff, d = hardware_effective_context(labels, hubs, context)
    return HardwareRoundMetrics(
        c2=float(round_c2(labels, eff)), native_cx=d['native_cx'],
        duration_ns=d['duration_ns'], total_data_idle_ns=d['total_data_idle_ns'],
        hub0_fraction=d['hub0_fraction'], two_flag_fraction=d['two_flag_fraction'],
    )


def topology_summary() -> dict:
    return {
        'graph': '3x4 nearest-neighbour grid (synthetic, not a named device)',
        'physical_qubits': N_PHYSICAL,
        'edges': [list(e) for e in EDGES],
        'data_nodes': list(DATA_NODES),
        'hub_nodes': list(HUB_NODES),
        'flag_nodes': {'A': FLAG_NODES[FLAG_A], 'B': FLAG_NODES[FLAG_B]},
        'routing_model': 'SWAP-forward / native-CX / SWAP-back; mapping restored',
        'native_cx_count_for_distance_d': '6*(d-1)+1',
        'idle_model': 'persistent-data idle exposure smeared onto existing logical data-CNOT Pauli categories',
    }


def local_hardware_effective_context(check_index: int, label: str, hub: int,
                                     context: HardwareContext, route_cache: dict | None = None) -> tuple[np.ndarray, dict]:
    """96-feature local approximation used only as a cheap search/training proxy."""
    if check_index < 0 or check_index >= 6 or hub not in (0, 1):
        raise ValueError('invalid check or hub')
    context.validate()
    check_type, support = CHECKS[check_index]
    eff = np.asarray(context.logical[check_index], dtype=np.float64).copy()
    hub_node = HUB_NODES[hub]
    template = schedule_from_label(label)
    used_a = FLAG_A in template; used_b = FLAG_B in template
    eff[0] *= context.prep_scale[hub_node]; eff[93] *= context.meas_scale[hub_node]
    if used_a:
        eff[1] *= context.prep_scale[FLAG_NODES[FLAG_A]]; eff[94] *= context.meas_scale[FLAG_NODES[FLAG_A]]
    if used_b:
        eff[2] *= context.prep_scale[FLAG_NODES[FLAG_B]]; eff[95] *= context.meas_scale[FLAG_NODES[FLAG_B]]
    duration = 0.0; native = 0
    active = {q: 0.0 for q in support}
    locations = {q: [] for q in support}
    for token in template:
        endpoint = _token_node(token, support)
        source, target = (hub_node, endpoint) if check_type == 'X' else (endpoint, hub_node)
        key = (check_index, hub, token)
        stats = route_cache[key] if route_cache is not None and key in route_cache else route_stats(source, target, context)
        eff[_gate_category_slice(token)] *= stats.gate_scale
        duration += stats.duration_ns; native += stats.native_cx
        if 0 <= token < 4:
            q = support[token]; active[q] += stats.duration_ns; locations[q].append(token)
    for q in support:
        idle = max(0.0, duration - active[q])
        weight = context.idle_rate[DATA_NODES[q]] * idle
        if locations[q]:
            share = weight / len(locations[q])
            for token in locations[q]:
                start = _gate_category_slice(token).start
                for code in (1, 2, 3):
                    eff[start + _single_data_indices(check_type, code)] += share / 3.0
    return eff, {'native_cx': int(native), 'duration_ns': float(duration)}


def build_local_route_cache(context: HardwareContext) -> dict:
    """Precompute the 72 check/hub/token routed-CNOT choices for one context."""
    cache = {}
    for check_index, (check_type, support) in enumerate(CHECKS):
        for hub in (0, 1):
            hub_node = HUB_NODES[hub]
            for token in (0, 1, 2, 3, FLAG_A, FLAG_B):
                endpoint = _token_node(token, support)
                source, target = (hub_node, endpoint) if check_type == 'X' else (endpoint, hub_node)
                cache[(check_index, hub, token)] = route_stats(source, target, context)
    return cache
