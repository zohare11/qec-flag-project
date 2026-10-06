#!/usr/bin/env python3
from __future__ import annotations
import argparse
import json
import os
import platform
import sys
from pathlib import Path

# These workloads use many small/medium dense NumPy operations. Large BLAS thread
# pools add overhead and make timing less reproducible; respect any user override.
for _name in ('OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'VECLIB_MAXIMUM_THREADS'):
    os.environ.setdefault(_name, '1')

from qecflag.phase3_catalog import ensure_catalog, catalog_verification_summary
from qecflag.phase3_experiment import run_all, write_json

ROOT = Path(__file__).resolve().parent


def load_config(path: Path) -> dict:
    with path.open() as handle:
        return json.load(handle)


def doctor() -> None:
    import numpy, pytest
    print(json.dumps({
        'python': sys.version.split()[0],
        'python_executable': sys.executable,
        'platform': platform.platform(),
        'inside_virtual_environment': sys.prefix != getattr(sys, 'base_prefix', sys.prefix),
        'numpy': numpy.__version__,
        'pytest': pytest.__version__,
        'project_root': str(ROOT),
    }, indent=2))


def main():
    parser = argparse.ArgumentParser(description='Phase 3 sequential flagged-circuit schedule synthesis')
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('doctor')
    build = sub.add_parser('build-cache'); build.add_argument('--cache-dir', default='cache')
    allp = sub.add_parser('all')
    allp.add_argument('--config', required=True)
    allp.add_argument('--out', required=True)
    allp.add_argument('--cache-dir', default='cache')
    args = parser.parse_args()
    if args.command == 'doctor':
        doctor(); return
    cache = ROOT / args.cache_dir
    if args.command == 'build-cache':
        a = ensure_catalog(cache / 'phase3_singleA_catalog.npz', 'single_A', progress=True)
        b = ensure_catalog(cache / 'phase3_expanded_catalog.npz', 'expanded', progress=True)
        print(json.dumps({'phase3A': catalog_verification_summary(a),
                          'phase3B': catalog_verification_summary(b)}, indent=2))
        return
    config_path = ROOT / args.config
    output = ROOT / args.out
    if output.exists() and any(output.iterdir()):
        raise SystemExit(f'Refusing to overwrite nonempty output directory: {output}')
    output.mkdir(parents=True, exist_ok=True)
    config = load_config(config_path)
    write_json(output / 'phase3_config.json', config)
    result = run_all(config, output, cache)
    print(f'PHASE 3 REPORT: {output / "phase3_summary.md"}')
    print('DONE Phase 3')


if __name__ == '__main__':
    main()
