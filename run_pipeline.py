#!/usr/bin/env python3
"""Run verification, diagnosis, RL training, baselines, and noisy diagnostics.

Examples:
  python run_pipeline.py doctor
  python run_pipeline.py all --config configs/smoke.json --out runs/smoke
  python run_pipeline.py all --config configs/full.json --out runs/full
"""
from __future__ import annotations
import os
# Limit implicit BLAS parallelism before importing NumPy. No GPU is needed.
for variable in ('OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS', 'VECLIB_MAXIMUM_THREADS'):
    os.environ.setdefault(variable, '1')
os.environ.setdefault('PYTEST_DISABLE_PLUGIN_AUTOLOAD', '1')
import argparse
from contextlib import contextmanager, redirect_stdout, redirect_stderr
import hashlib
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
        self.terminal.write(text)
        self.log.write(text)
        self.log.flush()
        return len(text)
    def flush(self):
        self.terminal.flush()
        self.log.flush()


def doctor() -> dict:
    if sys.version_info < (3, 11):
        raise RuntimeError('Use Python 3.11 or newer. This bundle was tested on Python 3.13.5.')
    versions = {name: importlib.metadata.version(name) for name in ('numpy', 'pytest')}
    result = {'python': sys.version, 'executable': sys.executable, 'platform': platform.platform(),
              'machine': platform.machine(), 'project': str(ROOT), 'packages': versions,
              'inside_virtual_environment': sys.prefix != sys.base_prefix}
    print('ENVIRONMENT\n' + json.dumps(result, indent=2), flush=True)
    if not result['inside_virtual_environment']:
        print('WARNING: this interpreter is not in a virtual environment. For your Mac, activate .venv first.')
    for package, expected in (('numpy', '2.3.5'), ('pytest', '9.0.2')):
        if versions[package] != expected:
            print(f'WARNING: {package} is {versions[package]}; reference run used {expected}.')
    return result


def load_config(path: Path) -> dict:
    config = json.loads(path.read_text())
    seeds = list(config['data_seeds'].values())
    if len(set(seeds)) != 4:
        raise ValueError('Training, validation, test, and shifted-test data seeds must be distinct.')
    for key in ('train_contexts', 'validation_contexts', 'test_contexts', 'updates', 'batch_size',
                'hidden', 'log_every', 'search_budget', 'noise_shots'):
        if not isinstance(config[key], int) or config[key] <= 0:
            raise ValueError(f'{key} must be a positive integer')
    if not config['training_seeds'] or len(set(config['training_seeds'])) != len(config['training_seeds']):
        raise ValueError('Use at least one distinct training seed.')
    if config['learning_rate'] <= 0 or config['entropy_coefficient'] < 0:
        raise ValueError('Invalid learning-rate/entropy configuration.')
    return config


def verify(output: Path) -> dict:
    from qecflag.catalog import build_catalog
    from qecflag.physics import candidate_schedules, fault_records, decoder_and_certificate, schedule_from_label
    from qecflag.dense_check import ideal_measurement_valid, crosscheck_records
    from qecflag.experiment import write_json, write_csv
    start = time.perf_counter()
    schedules = candidate_schedules()
    total = 0
    for k, schedule in enumerate(schedules, 1):
        if not ideal_measurement_valid(schedule):
            raise AssertionError('Incorrect ideal parity-measurement instrument')
        total += crosscheck_records(schedule, fault_records(schedule))
        if k % 90 == 0:
            print(f'VERIFY {k}/{len(schedules)} ideal maps and dense fault cross-checks', flush=True)
    catalog = build_catalog()
    bare = decoder_and_certificate(schedule_from_label('0123'))[1]
    misplaced = decoder_and_certificate(schedule_from_label('0F1F23'))[1]
    missing = ideal_measurement_valid((0, 8, 1, 2, 8))
    if bare['certified'] or misplaced['certified'] or missing:
        raise AssertionError('A deliberately invalid control was accepted')
    report = {'candidate_schedules': len(schedules), 'correct_ideal_instruments': len(schedules),
              'certified_schedules': len(catalog.labels), 'dense_single_fault_crosschecks': total,
              'faults_per_six_cnot_schedule': 94, 'single_incoming_data_errors_per_schedule': 21,
              'catalog_fingerprint': catalog.fingerprint,
              'negative_controls': {'bare_ancilla_rejected': not bare['certified'],
                                    'misplaced_flag_rejected': not misplaced['certified'],
                                    'missing_data_coupling_rejected': not missing},
              'elapsed_seconds': time.perf_counter() - start,
              'scope': 'One Steane Z-check; independent stochastic Pauli gate/preparation/readout faults; ideal final recovery.'}
    write_json(output / 'verification.json', report)
    write_csv(output / 'candidate_certificates.csv', catalog.reports)
    # Circuit text is both human-readable and machine-readable in Stim syntax,
    # but Stim is not a dependency and was not used to validate this bundle.
    lines = ['# 7 data qubits, syndrome=7, flag=8', 'R 7', 'RX 8']
    for control in schedule_from_label('0F12F3'):
        lines.append(f'CX {control} 7')
    lines.extend(['M 7', 'MX 8'])
    (output / 'reference_circuit.stim').write_text('\n'.join(lines) + '\n')
    print('VERIFICATION PASSED\n' + json.dumps(report, indent=2), flush=True)
    return report


def diagnose(catalog, config, output):
    import numpy as np
    from qecflag.experiment import splits, best_fixed_choice, write_json
    data = splits(config)
    # Diagnosis is restricted to validation; final test is not used here.
    fixed = best_fixed_choice(catalog, data['train'])
    costs = catalog.costs(data['validation'])
    minima = costs.min(axis=1)
    regret = costs[:, fixed] / minima - 1
    report = {'split': 'validation only', 'best_fixed_trained_schedule': catalog.labels[fixed],
              'distinct_oracle_argmin_labels': int(len(set(costs.argmin(axis=1)))),
              'fixed_matches_oracle_cases': int(np.isclose(costs[:, fixed], minima, atol=1e-10, rtol=1e-9).sum()),
              'cases': len(costs), 'fixed_mean_relative_regret': float(regret.mean()),
              'nontriviality_condition': bool(regret.mean() > 0.01),
              'interpretation': 'A gap motivates conditional choice in this finite pilot; it does not prove a need for RL.'}
    write_json(output / 'diagnosis.json', report)
    print('DIAGNOSIS\n' + json.dumps(report, indent=2), flush=True)
    return report


def noise_diagnostic(catalog, config, output):
    import numpy as np
    from qecflag.agent import Policy
    from qecflag.physics import schedule_from_label
    from qecflag.experiment import splits, best_fixed_choice, write_json
    from qecflag.simulation import simulate, low_order_bounds
    data = splits(config)
    # Predeclared one-context diagnostic; not used for model/checkpoint selection.
    context = data['test'][0]
    fixed = best_fixed_choice(catalog, data['train'])
    model, metadata = Policy.load(output / f'policy_seed{config["training_seeds"][0]}.npz')
    if metadata['catalog_fingerprint'] != catalog.fingerprint or metadata['config'] != config:
        raise ValueError('Checkpoint does not match the current config/catalog.')
    choices = {'reference': catalog.reference, 'best_fixed_train': fixed,
               'learned_first_seed': int(model.predict(context)[0]),
               'exhaustive_oracle': int(catalog.costs(context)[0].argmin())}
    rows = []
    sample_cache = {}
    for p_index, p in enumerate(config['noise_p']):
        for method_index, (name, choice) in enumerate(choices.items()):
            schedule = schedule_from_label(catalog.labels[choice])
            print(f'NOISE {name} schedule={catalog.labels[choice]} p={p} shots={config["noise_shots"]}', flush=True)
            cache_key = (choice, p)
            if cache_key not in sample_cache:
                sampled = simulate(schedule, catalog.decoders[choice], context, p,
                                   config['noise_shots'], 85000 + p_index * 10 + method_index)
                sampled.update(low_order_bounds(schedule, catalog.decoders[choice], context, p))
                sample_cache[cache_key] = sampled
            row = dict(sample_cache[cache_key])
            row['identical_circuits_share_the_same_monte_carlo_samples'] = True
            coefficient = float(context @ catalog.matrices[choice] @ context)
            row.update({'method': name, 'schedule': catalog.labels[choice], 'C2': coefficient,
                        'leading_order_C2_p_squared': coefficient * p * p})
            rows.append(row)
    result = {'context': context.tolist(), 'context_selection': 'first held-out test context, fixed in advance',
              'results': rows,
              'scope': 'No postselection; noiseless final full syndrome and recovery; not a full FT QEC cycle.'}
    write_json(output / 'noise.json', result)
    print('NOISE DIAGNOSTICS COMPLETE. See noise.json for counts, confidence intervals, and model bounds.')
    return result


def report(output):
    from qecflag.experiment import write_json
    evaluation = json.loads((output / 'evaluation.json').read_text())
    noise = json.loads((output / 'noise.json').read_text()) if (output / 'noise.json').exists() else None
    text = ['# Run summary', '', 'Scope: one flagged Z-check with a perfect final recovery oracle.',
            'C2 is a second-order logical-failure coefficient, not a measured device error rate.', '',
            'All selected circuits have the same six CNOT gates; this is not a gate-count reduction study.', '']
    for split in ('test', 'shift'):
        text += [f'## {split}', '', '| Method | Mean C2 | Mean relative regret | Oracle-match fraction |',
                 '|---|---:|---:|---:|']
        for name, result in evaluation[split]['methods'].items():
            text.append(f'| {name} | {result["mean_C2"]:.6f} | {100*result["mean_relative_regret"]:.2f}% | '
                        f'{100*result["oracle_match_fraction"]:.2f}% |')
        text.append('')
    text += ['## Interpretation', '',
             'Compare learned policies with best_fixed_train, random_search, greedy_search, and exhaustive_oracle.',
             'Beating a fixed circuit is not the same as beating a search heuristic.',
             'The oracle is exact only within the certified finite candidate library.',
             'The learned policy is not supplied oracle argmin labels during training.',
             'No novelty, full QEC-cycle fault tolerance, or hardware advantage is established by this run.', '']
    if noise:
        text += ['## Noisy component diagnostics', '',
                 '| Method | p | Failures/shots | Rate | Wilson 95% interval |', '|---|---:|---:|---:|---:|']
        for r in noise['results']:
            text.append(f'| {r["method"]} | {r["p"]} | {r["logical_failures"]}/{r["shots"]} | '
                        f'{r["logical_failure_rate_with_perfect_final_recovery"]:.7f} | '
                        f'[{r["wilson95_low"]:.7f}, {r["wilson95_high"]:.7f}] |')
        text += ['', 'These rows use only one predeclared noise context, not the entire test set.']
    (output / 'summary.md').write_text('\n'.join(text) + '\n')
    print(f'REPORT: {output / "summary.md"}')


def execute(args):
    from qecflag.catalog import build_catalog
    from qecflag.experiment import train, evaluate, write_json
    config = load_config(args.config)
    if args.command == 'doctor':
        doctor()
        return
    output = args.out.resolve()
    if args.command == 'all' and output.exists() and any(output.iterdir()):
        raise FileExistsError(f'{output} is not empty. Use a new --out path to preserve previous results.')
    output.mkdir(parents=True, exist_ok=True)
    config_path = output / 'config.json'
    if config_path.exists() and json.loads(config_path.read_text()) != config:
        raise ValueError('Output directory contains a different configuration. Use a new --out directory.')
    write_json(config_path, config)
    with (output / 'console.log').open('a') as handle:
        with redirect_stdout(Tee(sys.stdout, handle)), redirect_stderr(Tee(sys.stderr, handle)):
            start = time.perf_counter()
            environment = doctor()
            hashes = {}
            for path in sorted(ROOT.rglob('*.py')):
                if not any(part in ('runs', '.venv', '__pycache__', 'reference_runs') for part in path.parts):
                    hashes[str(path.relative_to(ROOT))] = hashlib.sha256(path.read_bytes()).hexdigest()
            write_json(output / 'environment.json', {'environment': environment, 'source_sha256': hashes})
            if args.command == 'all':
                print('\nRUNNING UNIT TESTS', flush=True)
                completed = subprocess.run([sys.executable, '-m', 'pytest', '-q'], cwd=ROOT,
                                           text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
                print(completed.stdout, flush=True)
                (output / 'pytest.txt').write_text(completed.stdout)
                if completed.returncode:
                    raise RuntimeError('Unit tests failed; the pipeline stopped before training.')
            if args.command in ('all', 'verify'):
                verify(output)
            catalog = build_catalog()
            if args.command in ('all', 'diagnose'):
                diagnosis = diagnose(catalog, config, output)
                if not diagnosis['nontriviality_condition']:
                    print('WARNING: this calibration distribution leaves <1% gap for conditional selection.')
            if args.command in ('all', 'train'):
                for seed in config['training_seeds']:
                    train(catalog, config, output, seed)
            if args.command in ('all', 'evaluate'):
                evaluate(catalog, config, output)
            if args.command in ('all', 'noise'):
                noise_diagnostic(catalog, config, output)
            if args.command in ('all', 'report'):
                report(output)
            print(f'\nDONE {args.command}: {output} ({time.perf_counter()-start:.2f} seconds)', flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('command', choices=('doctor', 'verify', 'diagnose', 'train', 'evaluate', 'noise', 'report', 'all'))
    parser.add_argument('--config', type=Path, default=ROOT / 'configs/smoke.json')
    parser.add_argument('--out', type=Path, default=ROOT / 'runs/smoke')
    args = parser.parse_args()
    try:
        execute(args)
    except (ValueError, RuntimeError, FileNotFoundError, FileExistsError, importlib.metadata.PackageNotFoundError) as exc:
        print(f'ERROR: {exc}', file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == '__main__':
    main()
