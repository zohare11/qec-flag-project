"""Triangular 6.6.6 color code patch and plaquette CNOT schedules.

Honeycomb in integer coordinates: hexagon (q, r) has centre (3q, 2r + q) and vertices at the
offsets OFF.  The patch keeps the vertices with Y >= -3, Y - X <= -1, Y + X <= 3d - 7, which
gives n = (3d^2 + 1)/4 data qubits, hexagons in the bulk and weight-4 trapezoids on the edges.
Colours are named as in Kishony & Fowler Fig. 1: bottom trapezoids green, left blue, right red.

A schedule maps every plaquette index to {data vertex: time step}.  The X block and the Z block
use the same schedule (X block first in each round).
"""
from __future__ import annotations

import json

OFF = {'R': (2, 0), 'TR': (1, 1), 'TL': (-1, 1), 'L': (-2, 0), 'BL': (-1, -1), 'BR': (1, -1)}
LABELS = ('TL', 'TR', 'L', 'R', 'BL', 'BR')


def lattice(d: int):
    """(sorted data vertices, plaquettes); each plaquette has 'hex', 'c', 'center', 'sup' {label: vertex}, 'color'."""
    y0, a, b = -3, -1, 3 * d - 7
    inside = lambda p: p[1] >= y0 and p[1] - p[0] <= a and p[1] + p[0] <= b
    R = d + 4
    plaq = []
    data = set()
    for q in range(-R, 2 * R):
        for r in range(-2 * R, 2 * R):
            cx, cy = 3 * q, 2 * r + q
            sup = {k: (cx + dx, cy + dy) for k, (dx, dy) in OFF.items() if inside((cx + dx, cy + dy))}
            if len(sup) >= 3:
                plaq.append({'hex': (q, r), 'c': (q - r) % 3, 'center': (cx, cy), 'sup': sup})
                data |= set(sup.values())
    kind = lambda p: frozenset(p['sup'])
    bottom = {p['c'] for p in plaq if kind(p) == frozenset({'L', 'R', 'TL', 'TR'})}
    left = {p['c'] for p in plaq if kind(p) == frozenset({'BL', 'BR', 'R', 'TR'})}
    right = {p['c'] for p in plaq if kind(p) == frozenset({'BL', 'BR', 'L', 'TL'})}
    assert len(bottom) == len(left) == len(right) == 1 and len(bottom | left | right) == 3
    name = {bottom.pop(): 'green', left.pop(): 'blue', right.pop(): 'red'}
    for p in plaq:
        p['color'] = name[p['c']]
    assert len(data) == (3 * d * d + 1) // 4 and len(plaq) == (len(data) - 1) // 2
    return sorted(data), plaq


# Kishony & Fowler (arXiv:2603.28852) Fig. 1b: time step of each hexagon vertex, per plaquette colour
KF = {'red':   {'TL': 1, 'TR': 3, 'L': 6, 'R': 2, 'BL': 4, 'BR': 5},
      'green': {'TL': 5, 'TR': 1, 'L': 2, 'R': 4, 'BL': 6, 'BR': 3},
      'blue':  {'TL': 1, 'TR': 5, 'L': 4, 'R': 3, 'BL': 2, 'BR': 6}}


def schedule_from_colors(plaq, table=KF):
    """Colour-dependent schedule; boundary plaquettes keep the bulk times of the vertices they have."""
    return {i: {v: table[p['color']][k] for k, v in p['sup'].items()} for i, p in enumerate(plaq)}


def check_schedule(plaq, sched, steps=6):
    """Every time in 1..steps, distinct within a plaquette, and no data qubit in two CNOTs at once."""
    use = {}
    for i, s in sched.items():
        assert set(s) == set(plaq[i]['sup'].values()), f'plaquette {i}: wrong vertex set'
        assert len(set(s.values())) == len(s), f'plaquette {i}: repeated time'
        for v, t in s.items():
            assert 1 <= t <= steps
            assert (v, t) not in use, f'data {v} used twice at step {t} (plaquettes {use[(v, t)]} and {i})'
            use[(v, t)] = i
    return True


def schedule_to_json(d, plaq, sched, **meta):
    rows = []
    for i, p in enumerate(plaq):
        inv = {v: k for k, v in p['sup'].items()}
        rows.append({'center': list(p['center']), 'color': p['color'],
                     'steps': {inv[v]: t for v, t in sorted(sched[i].items(), key=lambda kv: kv[1])}})
    return json.dumps({'d': d, **meta, 'plaquettes': rows}, indent=1)


def schedule_from_json(text):
    obj = json.loads(text)
    d = obj['d']
    data, plaq = lattice(d)
    by_center = {tuple(r['center']): r['steps'] for r in obj['plaquettes']}
    sched = {i: {p['sup'][k]: t for k, t in by_center[p['center']].items()} for i, p in enumerate(plaq)}
    check_schedule(plaq, sched, steps=max(t for s in sched.values() for t in s.values()))
    return d, data, plaq, sched
