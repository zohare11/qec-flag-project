"""Counterexample localization for FT compiler repair v3."""
from __future__ import annotations
from dataclasses import dataclass, asdict
from collections import defaultdict
import numpy as np

from qecflag.phase7_forensics import failing_single_fault_rows


@dataclass(frozen=True)
class RoutingFailureCore:
    check: int
    route: int
    gate: int
    token: int
    edge: str
    path: str
    failure_count: int
    total_weight: float
    kinds: tuple[str, ...]

    def to_dict(self):
        return asdict(self)


def routing_failure_cores(risk, primitive: str = 'bridge') -> tuple[RoutingFailureCore, ...]:
    """Aggregate exact failing native faults down to physical operation cores."""
    rows = failing_single_fault_rows(risk, primitive)
    bucket = defaultdict(lambda: {'count': 0, 'weight': 0.0, 'kinds': set(), 'token': -1, 'edge': '', 'path': ''})
    for row in rows:
        key = (int(row['check_index']), int(row['route_index']), int(row['gate_index']))
        b = bucket[key]
        b['count'] += 1
        b['weight'] += float(row['weight'])
        b['kinds'].add(str(row['kind']))
        b['token'] = int(row.get('token', -1))
        b['edge'] = str(row.get('edge', ''))
        b['path'] = str(row.get('path', ''))
    out = []
    for (c, r, g), b in bucket.items():
        out.append(RoutingFailureCore(
            check=c, route=r, gate=g, token=b['token'], edge=b['edge'], path=b['path'],
            failure_count=int(b['count']), total_weight=float(b['weight']), kinds=tuple(sorted(b['kinds'])),
        ))
    out.sort(key=lambda x: (-x.total_weight, -x.failure_count, x.check, x.route, x.gate))
    return tuple(out)


def implicated_routes(risk, limit: int | None = None) -> tuple[tuple[int, int], ...]:
    scores = defaultdict(lambda: [0.0, 0])
    for core in routing_failure_cores(risk):
        k = (core.check, core.route)
        scores[k][0] += core.total_weight; scores[k][1] += core.failure_count
    items = sorted(scores, key=lambda k: (-scores[k][0], -scores[k][1], k))
    return tuple(items if limit is None else items[:int(limit)])


def implicated_checks(risk, limit: int | None = None) -> tuple[int, ...]:
    scores = defaultdict(lambda: [0.0, 0])
    for core in routing_failure_cores(risk):
        scores[core.check][0] += core.total_weight; scores[core.check][1] += core.failure_count
    items = sorted(scores, key=lambda c: (-scores[c][0], -scores[c][1], c))
    return tuple(items if limit is None else items[:int(limit)])


def localization_summary(risk) -> dict:
    cores = routing_failure_cores(risk)
    routes = implicated_routes(risk)
    checks = implicated_checks(risk)
    return {
        'single_fault_failures': int(risk.decoder.single_fault_failures),
        'c1': float(risk.c1),
        'implicated_checks': list(checks),
        'implicated_routes': [list(x) for x in routes],
        'top_operation_cores': [x.to_dict() for x in cores[:20]],
    }
