#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, platform, sys
from pathlib import Path
import numpy as np

from qecflag.phase5_actions import ensure_hardware_action_table
from qecflag.phase5_experiment import run_all
from qecflag.phase5_hardware import topology_summary

ROOT=Path(__file__).resolve().parent

def doctor():
    import pytest
    print(json.dumps({'python':sys.version.split()[0],'executable':sys.executable,'platform':platform.platform(),
                      'inside_virtual_environment':sys.prefix!=getattr(sys,'base_prefix',sys.prefix),
                      'numpy':np.__version__,'pytest':pytest.__version__,'project_root':str(ROOT)},indent=2))

def load_config(path):
    p=Path(path); p=p if p.is_absolute() else ROOT/p
    return json.loads(p.read_text())

def main():
    ap=argparse.ArgumentParser(); sub=ap.add_subparsers(dest='command',required=True)
    sub.add_parser('doctor'); sub.add_parser('build-cache')
    a=sub.add_parser('all'); a.add_argument('--config',required=True); a.add_argument('--out',required=True)
    args=ap.parse_args()
    if args.command=='doctor': doctor(); return
    if args.command=='build-cache':
        t=ensure_hardware_action_table(ROOT)
        print('PHASE 5 HARDWARE ACTION TABLE')
        print(json.dumps({'actions':t.n_actions,'schedule_space':int(t.n_actions**6),
                          'reference_index':t.index('H0|0A12A3'),'topology':topology_summary()},indent=2)); return
    out=Path(args.out); out=out if out.is_absolute() else ROOT/out
    if out.exists() and any(out.iterdir()): raise SystemExit(f'Output directory already exists and is nonempty: {out}')
    if out.exists(): out.rmdir()
    payload=run_all(ROOT,load_config(args.config),out)
    print(f'DONE Phase 5: {out} ({payload["elapsed_seconds"]:.2f} seconds)')

if __name__=='__main__': main()
