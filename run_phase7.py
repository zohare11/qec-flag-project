#!/usr/bin/env python3
from __future__ import annotations

import argparse, json, platform, sys
from pathlib import Path
import numpy as np

from qecflag.phase5_actions import ensure_hardware_action_table, actions_to_round
from qecflag.phase5_noise import sample_hardware_contexts
from qecflag.phase7_catalog import ensure_catalog
from qecflag.phase7_experiment import run_all
from qecflag.phase7_forensics import forensic_comparison
from qecflag.phase7_routing import bridge_native_risk

ROOT = Path(__file__).resolve().parent


def doctor():
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


def load_config(path):
    p = Path(path)
    p = p if p.is_absolute() else ROOT / p
    return json.loads(p.read_text())


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest='command', required=True)
    sub.add_parser('doctor')
    sub.add_parser('build-cache')
    sub.add_parser('forensics')
    sub.add_parser('inspect-certified')
    a = sub.add_parser('all')
    a.add_argument('--config', required=True)
    a.add_argument('--out', required=True)
    args = ap.parse_args()

    if args.command == 'doctor':
        doctor(); return

    if args.command == 'build-cache':
        path = ROOT / 'cache' / 'phase7_certified_bridge_catalog.json'
        if path.exists():
            path.unlink()
        cat = ensure_catalog(ROOT, progress=True)
        print(json.dumps(cat.metadata, indent=2)); return

    table = ensure_hardware_action_table(ROOT)
    context = sample_hardware_contexts(1, 7102, 'hw_id').context(0)
    ref = table.index('H0|0A12A3')
    if ref is None:
        raise SystemExit('Reference action H0|0A12A3 missing')
    labels, hubs = actions_to_round((ref,) * 6, table)

    if args.command == 'forensics':
        out = forensic_comparison(labels, hubs, context, pair_block=128)
        print(json.dumps(out, indent=2)); return

    if args.command == 'inspect-certified':
        cat = ensure_catalog(ROOT, progress=False)
        labels, hubs = cat.labels_hubs(0)
        risk = bridge_native_risk(labels, hubs, context, pair_block=128)
        print(json.dumps({
            'catalog_size': len(cat),
            'catalog_metadata': cat.metadata,
            'labels': list(labels),
            'hubs': list(hubs),
            'native_cx': risk.plan.native_cx,
            'duration_us': risk.plan.duration_ns / 1000.0,
            'fault_outcomes': len(risk.records.data),
            'C1': risk.c1,
            'C2': risk.c2,
            'single_fault_conflicts': risk.decoder.single_fault_conflicts,
            'single_fault_failures': risk.decoder.single_fault_failures,
            'incoming_failures': risk.decoder.incoming_failures,
            'single_fault_FT_pass': risk.fault_tolerant_single_fault,
        }, indent=2)); return

    cfg = load_config(args.config)
    out = Path(args.out)
    out = out if out.is_absolute() else ROOT / out
    if out.exists() and any(out.iterdir()):
        raise SystemExit(f'Output directory already exists and is nonempty: {out}')
    if out.exists(): out.rmdir()
    payload = run_all(ROOT, cfg, out)
    print(f'DONE Phase 7: {out} ({payload["elapsed_seconds"]:.2f} seconds)')


if __name__ == '__main__':
    main()
