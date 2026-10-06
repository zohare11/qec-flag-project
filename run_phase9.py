#!/usr/bin/env python3
from pathlib import Path
import argparse, json, subprocess, sys, tempfile

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from qecflag.phase8_experiment import ensure_continuous_catalog
from qecflag.phase8_timing import build_timed_bridge_plan
from qecflag.phase5_noise import sample_hardware_contexts
from qecflag.phase9_analysis import (
    build_detector_pair_decoder, low_order_expansion,
    syndrome_history_to_detectors, detectors_to_syndrome_history,
)
from qecflag.phase9_experiment import run_all, _markdown


def _split_full(config_path: Path, out: Path):
    """Run each family in a fresh Python process, then merge deterministic results.

    Phase-9 exact pair enumeration creates large temporary arrays.  Isolating
    families keeps peak memory stable on laptops while preserving exactly the
    same family-specific seeds as a monolithic run.
    """
    cfg = json.loads(config_path.read_text())
    families = list(cfg.get('families', ['hw_id']))
    out.mkdir(parents=True, exist_ok=True)
    parts_dir = out / 'parts'; parts_dir.mkdir(exist_ok=True)
    parts = []
    for fam in families:
        subcfg = dict(cfg)
        subcfg['families'] = [fam]
        subcfg['rare_event_families'] = [fam] if fam in set(cfg.get('rare_event_families', families)) else []
        cfg_path = parts_dir / f'{fam}_config.json'
        cfg_path.write_text(json.dumps(subcfg, indent=2) + '\n')
        fam_out = parts_dir / fam
        cmd = [sys.executable, str(ROOT / 'run_phase9.py'), 'all', '--config', str(cfg_path), '--out', str(fam_out)]
        print('P9 SPLIT:', fam)
        subprocess.run(cmd, check=True)
        parts.append(json.loads((fam_out / 'phase9_results.json').read_text()))

    payload = {
        'config': cfg,
        'catalog_size': parts[0]['catalog_size'] if parts else 0,
        'rare_event_rows': sum((p['rare_event_rows'] for p in parts), []),
        'decoder_summary': {},
        'continuous_validation': {'checked': 0, 'passed': 0, 'failed': 0},
        'elapsed_seconds': sum(float(p.get('elapsed_seconds', 0.0)) for p in parts),
        'execution_mode': 'split-family subprocesses',
    }
    for p in parts:
        payload['decoder_summary'].update(p['decoder_summary'])
        for k in ('checked', 'passed', 'failed'):
            payload['continuous_validation'][k] += int(p['continuous_validation'][k])
    (out / 'phase9_results.json').write_text(json.dumps(payload, indent=2) + '\n')
    (out / 'phase9_summary.md').write_text(_markdown(payload) + '\n')
    print('PHASE 9 MERGED REPORT:', out / 'phase9_summary.md')


def main():
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest='cmd', required=True)
    sub.add_parser('doctor')
    sub.add_parser('inspect-decoder')
    sub.add_parser('inspect-scaling')
    a = sub.add_parser('all'); a.add_argument('--config', required=True); a.add_argument('--out', required=True)
    s = sub.add_parser('split'); s.add_argument('--config', required=True); s.add_argument('--out', required=True)
    args = p.parse_args()
    if args.cmd == 'doctor':
        print(json.dumps({
            'python': sys.executable, 'project_root': str(ROOT),
            'inside_virtual_environment': sys.prefix != getattr(sys, 'base_prefix', sys.prefix),
        }, indent=2)); return
    if args.cmd == 'split':
        _split_full(Path(args.config), Path(args.out)); return
    cat = ensure_continuous_catalog(ROOT)
    e = cat['entries'][0]
    ctx = sample_hardware_contexts(1, 9301, 'hw_id').context(0)
    plan = build_timed_bridge_plan(e['labels'], e['hubs'], ctx)
    if args.cmd == 'inspect-decoder':
        dec = build_detector_pair_decoder(plan, ctx, 3, 2e-4)
        example = 0b101011 | (0b001110 << 6) | (0b000101 << 12) | (0b000001 << 18)
        d = syndrome_history_to_detectors(example, 3)
        print(json.dumps({
            'rounds': 3,
            'detector_primitives': dec.primitive_count,
            'order2_map_entries': dec.map_entries,
            'single_fault_conflicts': dec.single_fault_conflicts,
            'single_fault_failures': dec.single_fault_failures,
            'incoming_failures': dec.incoming_failures,
            'detector_transform_roundtrip_ok': detectors_to_syndrome_history(d, 3) == example,
        }, indent=2)); return
    if args.cmd == 'inspect-scaling':
        exp, _ = low_order_expansion(plan, ctx, 3, 'history', 2e-4, 5000, 9302, 64)
        out = dict(exp.__dict__)
        out['prediction'] = {str(p): exp.predict(p) for p in (5e-5, 1e-4, 2e-4, 5e-4)}
        print(json.dumps(out, indent=2)); return
    cfg = json.loads(Path(args.config).read_text())
    run_all(ROOT, cfg, Path(args.out))


if __name__ == '__main__':
    main()
