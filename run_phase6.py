#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, platform, sys
from pathlib import Path
import numpy as np

from qecflag.phase5_actions import ensure_hardware_action_table, actions_to_round
from qecflag.phase5_noise import sample_hardware_contexts
from qecflag.phase6_native import build_native_plan, explicit_native_risk
from qecflag.phase6_experiment import run_all

ROOT = Path(__file__).resolve().parent


def doctor():
    import pytest
    print(json.dumps({
        'python': sys.version.split()[0], 'executable': sys.executable,
        'platform': platform.platform(),
        'inside_virtual_environment': sys.prefix != getattr(sys, 'base_prefix', sys.prefix),
        'numpy': np.__version__, 'pytest': pytest.__version__, 'project_root': str(ROOT),
    }, indent=2))


def load_config(path):
    p = Path(path); p = p if p.is_absolute() else ROOT / p
    return json.loads(p.read_text())


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest='command', required=True)
    sub.add_parser('doctor')
    sub.add_parser('inspect-native')
    a = sub.add_parser('all')
    a.add_argument('--config', required=True)
    a.add_argument('--phase5-run', required=True)
    a.add_argument('--out', required=True)
    args = ap.parse_args()
    if args.command == 'doctor':
        doctor(); return
    if args.command == 'inspect-native':
        table = ensure_hardware_action_table(ROOT)
        context = sample_hardware_contexts(1, 6100, 'hw_id').context(0)
        row = tuple([table.index('H0|0A12A3')] * 6)
        labels, hubs = actions_to_round(row, table)
        plan = build_native_plan(labels, hubs, context)
        risk = explicit_native_risk(labels, hubs, context)
        print(json.dumps({
            'labels': list(labels), 'hubs': list(hubs),
            'native_cx': plan.native_cx, 'duration_us': plan.duration_ns / 1000.0,
            'fault_outcomes': len(risk.records.data),
            'physical_fault_locations': int(len(np.unique(risk.records.location))),
            'decoder_conflicts': risk.decoder.single_fault_conflicts,
            'single_fault_failures': risk.decoder.single_fault_failures,
            'incoming_failures': risk.decoder.incoming_failures,
            'C1': risk.c1, 'C2': risk.c2,
            'single_fault_FT_pass': risk.fault_tolerant_single_fault,
        }, indent=2)); return
    cfg = load_config(args.config)
    phase5_run = Path(args.phase5_run); phase5_run = phase5_run if phase5_run.is_absolute() else ROOT / phase5_run
    if not phase5_run.exists():
        raise SystemExit(f'Phase-5 run directory not found: {phase5_run}')
    out = Path(args.out); out = out if out.is_absolute() else ROOT / out
    if out.exists() and any(out.iterdir()):
        raise SystemExit(f'Output directory already exists and is nonempty: {out}')
    if out.exists(): out.rmdir()
    payload = run_all(ROOT, phase5_run, cfg, out)
    print(f'DONE Phase 6: {out} ({payload["elapsed_seconds"]:.2f} seconds)')


if __name__ == '__main__':
    main()
