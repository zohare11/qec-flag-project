#!/usr/bin/env python3
"""Run Phase 2: REINFORCE vs supervised learning plus domain-randomized robustness.

Examples:
  python run_phase2.py doctor
  python run_phase2.py all --config configs/phase2_smoke.json --out runs/phase2_smoke
  python run_phase2.py all --config configs/phase2_full.json --out runs/phase2_full
"""
from __future__ import annotations
import os
for variable in ('OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS', 'VECLIB_MAXIMUM_THREADS'):
    os.environ.setdefault(variable, '1')
os.environ.setdefault('PYTEST_DISABLE_PLUGIN_AUTOLOAD', '1')
import argparse
from contextlib import redirect_stdout, redirect_stderr
import importlib.metadata
import json
from pathlib import Path
import platform
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))


class Tee:
    def __init__(self, terminal, log):
        self.terminal, self.log = terminal, log
    def write(self, text):
        self.terminal.write(text); self.log.write(text); self.log.flush(); return len(text)
    def flush(self):
        self.terminal.flush(); self.log.flush()


def doctor():
    versions = {name: importlib.metadata.version(name) for name in ('numpy', 'pytest')}
    result = {'python': sys.version, 'executable': sys.executable, 'platform': platform.platform(),
              'project': str(ROOT), 'packages': versions, 'inside_virtual_environment': sys.prefix != sys.base_prefix}
    print('PHASE2 ENVIRONMENT\n' + json.dumps(result, indent=2), flush=True)
    return result


def load_config(path: Path) -> dict:
    c = json.loads(path.read_text())
    required_positive_int = ('train_contexts', 'validation_contexts', 'test_contexts', 'hidden', 'batch_size',
                             'reinforce_updates', 'supervised_updates', 'log_every', 'search_budget', 'data_seed_base')
    for key in required_positive_int:
        if not isinstance(c.get(key), int) or c[key] <= 0:
            raise ValueError(f'{key} must be a positive integer')
    if c.get('training_regimes') != ['narrow', 'domain_randomized']:
        raise ValueError('training_regimes must be ["narrow", "domain_randomized"] for the planned comparison')
    expected = ['narrow', 'broad_shift', 'ood_edge_hotspot', 'ood_flag_hotspot', 'ood_readout_hotspot', 'ood_pauli_sparse']
    if c.get('test_families') != expected:
        raise ValueError(f'test_families must be exactly {expected}')
    if not c.get('training_seeds') or len(set(c['training_seeds'])) != len(c['training_seeds']):
        raise ValueError('training_seeds must contain distinct values')
    for key in ('reinforce_learning_rate', 'supervised_learning_rate', 'regression_learning_rate'):
        if c.get(key, 0) <= 0:
            raise ValueError(f'{key} must be positive')
    if not 0 <= c.get('entropy_coefficient', -1):
        raise ValueError('entropy_coefficient must be nonnegative')
    if not 0 <= c.get('label_smoothing', -1) < 1:
        raise ValueError('label_smoothing must be in [0, 1)')
    return c


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('doctor', 'train', 'evaluate', 'report', 'all'))
    parser.add_argument('--config', type=Path, default=ROOT / 'configs/phase2_smoke.json')
    parser.add_argument('--out', type=Path, default=ROOT / 'runs/phase2_smoke')
    args = parser.parse_args()
    if args.command == 'doctor':
        doctor(); return
    config = load_config(args.config)
    output = args.out.resolve()
    if args.command == 'all' and output.exists() and any(output.iterdir()):
        raise SystemExit(f'ERROR: {output} is not empty; use a new output directory.')
    output.mkdir(parents=True, exist_ok=True)
    config_file = output / 'phase2_config.json'
    if config_file.exists() and json.loads(config_file.read_text()) != config:
        raise SystemExit('ERROR: output directory contains a different Phase-2 configuration.')
    config_file.write_text(json.dumps(config, indent=2) + '\n')

    from qecflag.catalog import build_catalog
    from qecflag.phase2_experiment import (train_phase2, evaluate_phase2, write_phase2_report,
                                           write_learning_curve_svg, write_robustness_svg)
    with (output / 'phase2_console.log').open('a') as handle:
        with redirect_stdout(Tee(sys.stdout, handle)), redirect_stderr(Tee(sys.stderr, handle)):
            start = time.perf_counter()
            doctor()
            if args.command == 'all':
                print('\nRUNNING COMPLETE UNIT TEST SUITE', flush=True)
                completed = subprocess.run([sys.executable, '-m', 'pytest', '-q'], cwd=ROOT,
                                           text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
                print(completed.stdout, flush=True)
                (output / 'phase2_pytest.txt').write_text(completed.stdout)
                if completed.returncode:
                    raise SystemExit('ERROR: tests failed; Phase 2 stopped before training.')
            catalog = build_catalog()
            if args.command in ('all', 'train'):
                train_phase2(catalog, config, output)
                for regime in config['training_regimes']:
                    write_learning_curve_svg(output, config, regime)
            if args.command in ('all', 'evaluate'):
                evaluation = evaluate_phase2(catalog, config, output)
                write_robustness_svg(output, evaluation)
            if args.command in ('all', 'report'):
                path = output / 'phase2_evaluation.json'
                if not path.exists():
                    raise SystemExit('ERROR: phase2_evaluation.json is missing; run evaluate first.')
                evaluation = json.loads(path.read_text())
                write_phase2_report(output, evaluation, config)
                print(f'PHASE2 REPORT: {output / "phase2_summary.md"}', flush=True)
            print(f'\nDONE PHASE2 {args.command}: {output} ({time.perf_counter()-start:.2f} seconds)', flush=True)


if __name__ == '__main__':
    main()
