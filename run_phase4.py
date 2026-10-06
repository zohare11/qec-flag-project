#!/usr/bin/env python3
"""CLI for Phase 4 full-round Steane syndrome-extraction synthesis."""
from __future__ import annotations
import argparse
import json
import platform
import sys
from pathlib import Path

import numpy as np

from qecflag.phase4_experiment import run_all
from qecflag.phase4_physics import verification_summary
from qecflag.phase4_templates import ensure_action_table

ROOT = Path(__file__).resolve().parent


def load_config(path: str) -> dict:
    p = Path(path)
    if not p.is_absolute():
        p = ROOT / p
    return json.loads(p.read_text())


def doctor() -> None:
    import pytest
    print(json.dumps({
        'python': sys.version.split()[0],
        'executable': sys.executable,
        'platform': platform.platform(),
        'inside_virtual_environment': sys.prefix != getattr(sys, 'base_prefix', sys.prefix),
        'numpy': np.__version__,
        'pytest': pytest.__version__,
        'project_root': str(ROOT),
    }, indent=2))


def build_cache() -> None:
    table = ensure_action_table(ROOT)
    kinds = {str(k): int(np.count_nonzero(table.kinds == k)) for k in sorted(set(table.kinds.tolist()))}
    print('PHASE 4 ACTION TABLE')
    print(json.dumps({
        'actions': table.n_actions,
        'kinds': kinds,
        'full_round_space': int(table.n_actions ** 6),
        'reference_index': table.index('0A12A3'),
        'metadata': table.metadata,
    }, indent=2))
    print('PHASE 4 REFERENCE VERIFICATION')
    print(json.dumps(verification_summary(('0A12A3',) * 6), indent=2))


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('doctor')
    sub.add_parser('build-cache')
    p_all = sub.add_parser('all')
    p_all.add_argument('--config', required=True)
    p_all.add_argument('--out', required=True)
    args = parser.parse_args()

    if args.command == 'doctor':
        doctor(); return
    if args.command == 'build-cache':
        build_cache(); return
    config = load_config(args.config)
    out = Path(args.out)
    if not out.is_absolute():
        out = ROOT / out
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.exists():
        if any(out.iterdir()):
            raise SystemExit(f'Output directory already exists and is nonempty: {out}')
        out.rmdir()
    payload = run_all(ROOT, config, out)
    print(f'DONE Phase 4: {out} ({payload["elapsed_seconds"]:.2f} seconds)')


if __name__ == '__main__':
    main()
