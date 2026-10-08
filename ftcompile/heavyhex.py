"""Heavy-hex coupling graphs (IBM Falcon/Eagle/Heron style).

A heavy-hex lattice is a hexagonal (honeycomb) lattice with an extra qubit on every edge:
degree-3 qubits at the hexagon corners, degree-2 qubits on the sides.  Built here from a
brick-wall honeycomb of R x C corner qubits: horizontal edges along every row, vertical edges
where (r + c) is even, every edge subdivided.

Picture coordinates: corner (r, c) sits at (2r, 2c), the qubit on a horizontal edge at
(2r, 2c + 1), the qubit on a vertical edge at (2r + 1, 2c).  So each picture row is a chain,
and rows are joined by single qubits every fourth column, alternating, as on IBM devices.
Node id = picture row * (2C - 1) + picture column.
"""
from __future__ import annotations


def heavy_hex(R: int, C: int):
    """(edges, positions): positions[node] = (picture row, picture column)."""
    W = 2 * C - 1
    nid = lambda pr, pc: pr * W + pc
    edges = set(); pos = {}
    for r in range(R):
        for c in range(C):
            pos[nid(2 * r, 2 * c)] = (2 * r, 2 * c)
            if c + 1 < C:                                   # horizontal edge, subdivided
                m = nid(2 * r, 2 * c + 1); pos[m] = (2 * r, 2 * c + 1)
                edges |= {(nid(2 * r, 2 * c), m), (m, nid(2 * r, 2 * c + 2))}
            if r + 1 < R and (r + c) % 2 == 0:              # vertical edge, subdivided
                m = nid(2 * r + 1, 2 * c); pos[m] = (2 * r + 1, 2 * c)
                edges |= {(nid(2 * r, 2 * c), m), (m, nid(2 * r + 2, 2 * c))}
    return tuple(sorted(tuple(sorted(e)) for e in edges)), pos


def picture(placement: dict, pos: dict, names: dict | None = None) -> str:
    """placement: virtual qubit -> node; names: virtual qubit -> label (default d<q> / a<k>)."""
    names = names or {q: (f'd{q}' if q < 7 else f'a{q - 7}') for q in placement}
    label = {n: names[q] for q, n in placement.items()}
    rows = [p[0] for p in pos.values()]; cols = [p[1] for p in pos.values()]
    used = [pos[n] for n in label]
    r0, r1 = min(r for r, _ in used) - 1, max(r for r, _ in used) + 1
    c0, c1 = min(c for _, c in used) - 1, max(c for _, c in used) + 1
    inv = {p: n for n, p in pos.items()}
    out = []
    for r in range(max(r0, min(rows)), min(r1, max(rows)) + 1):
        line = []
        for c in range(max(c0, min(cols)), min(c1, max(cols)) + 1):
            n = inv.get((r, c))
            line.append(f'{label[n]:>3}' if n in label else ('  o' if n is not None else '   '))
        out.append(''.join(line).rstrip())
    return '\n'.join(out)
