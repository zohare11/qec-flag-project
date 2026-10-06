"""Phase 9 experiment: asymptotic scaling + detector-hypergraph decoder validation."""
from __future__ import annotations
from pathlib import Path
import csv, json, time
import numpy as np

from .phase5_noise import sample_hardware_contexts
from .phase7_routing import bridge_proxy_metrics
from .phase8_experiment import ensure_continuous_catalog
from .phase8_timing import build_timed_bridge_plan, timed_single_fault_certificate
from .phase9_analysis import (
    low_order_expansion, compare_decoders_sweep, fit_loglog_slope,
)


def _save_csv(path: Path, rows: list[dict]):
    if not rows:
        path.write_text('')
        return
    keys = []
    for row in rows:
        for k in row:
            if k not in keys:
                keys.append(k)
    with path.open('w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader(); w.writerows(rows)


def _labels_hubs(e):
    return tuple(e['labels']), tuple(int(x) for x in e['hubs'])


def _choose_proxy(entries, context, budget):
    scored = []
    for i, e in enumerate(entries):
        labels, hubs = _labels_hubs(e)
        m = bridge_proxy_metrics(labels, hubs, context)
        scored.append((m.c2, m.native_cx, m.duration_ns, i))
    scored.sort()
    return [entries[x[-1]] for x in scored[:min(budget, len(scored))]]


def _choose_fixed(entries, contexts):
    vals = []
    for i, e in enumerate(entries):
        labels, hubs = _labels_hubs(e)
        vals.append((np.mean([bridge_proxy_metrics(labels, hubs, c).c2 for c in contexts]), i))
    return entries[min(vals)[1]]


def _markdown(payload: dict) -> str:
    cfg = payload['config']
    lines = [
        '# Phase 9 summary', '',
        'Scope: low-order repeated-round scaling analysis and detector-event decoding for the Phase-8 physically certified Steane memory circuits.', '',
        f"- Repeated rounds: {cfg['rounds']}",
        f"- Physical catalog: {payload['catalog_size']} continuously-idle-certified routed circuits",
        '- Low-order analysis: exact C1/C2 for the primary history decoder plus importance-sampled raw three-fault weight and p^3 Taylor estimate.',
        '- Scalable baseline: order-2 detector-hypergraph decoder over syndrome-difference detector events plus flags; this is not MWPM/PyMatching.',
        '- Majority-vote decoding is retained only as a weak baseline.', '',
        '## Low-order rare-event analysis', '',
        '| Family | Method | C1 | exact C2 | raw T3 estimate | p^3 Taylor coeff estimate | T3 rel. SE | predicted leading order |',
        '|---|---|---:|---:|---:|---:|---:|---:|',
    ]
    for r in payload['rare_event_rows']:
        rel = (r['raw_t3_se'] / abs(r['raw_t3_estimate'])) if r['raw_t3_estimate'] else float('nan')
        lead = 1 if r['c1'] > 0 else (2 if r['c2'] > 0 else 3)
        lines.append(f"| {r['family']} | {r['method']} | {r['c1']:.6g} | {r['c2']:.6g} | {r['raw_t3_estimate']:.6g} | {r['c3_taylor_estimate']:.6g} | {rel:.2%} | {lead} |")
    lines += ['', '## Decoder comparison', '']
    for fam, block in payload['decoder_summary'].items():
        lines += [f'### {fam}', '', '| p | History lookup | Detector hypergraph | Temporal majority |', '|---:|---:|---:|---:|']
        for row in block['rates']:
            lines.append(f"| {row['p']} | {row['history_lookup']:.7f} | {row['detector_pair']:.7f} | {row['temporal_majority']:.7f} |")
        lines += ['', f"- Log-log slope, history lookup: {block['history_slope']:.3f}",
                  f"- Log-log slope, detector hypergraph: {block['detector_slope']:.3f}",
                  f"- Log-log slope, temporal majority: {block['majority_slope']:.3f}",
                  f"- Detector single-fault failures: {block['detector_single_fault_failures']}",
                  f"- Detector single-fault conflicts: {block['detector_single_fault_conflicts']}", '']
    lines += [
        '## Interpretation constraints', '',
        '- C2 is evaluated exactly only for the selected rare-event circuit/context rows; the three-fault term is importance-sampled and therefore has sampling uncertainty.',
        '- The reported p^3 Taylor estimate is meaningful when C1=0; it subtracts the cubic no-fault expansion associated with malignant pairs.',
        '- The detector decoder is a fixed-order hypergraph decoder. It scales polynomially in the number of repeated rounds for this fixed Steane circuit family, but it is not a large-code decoder.',
        '- The exact history lookup remains the small-code reference decoder and still uses the ideal final memory-boundary syndrome.',
        '- Native bridge-CNOT faults and serialized per-interval data idling remain explicit; the hardware graph and calibration families remain synthetic.',
        '- Checks remain serialized and no crosstalk, leakage, or real-backend calibration is modeled.',
        '- Phase 9 is a decoder/scaling validation phase; it does not retrain the proposal policy.', '',
    ]
    return '\n'.join(lines)


def run_all(project_root: Path, cfg: dict, out_dir: Path):
    t0 = time.time()
    root = Path(project_root); out = Path(out_dir); out.mkdir(parents=True, exist_ok=True)
    cat = ensure_continuous_catalog(root, progress=True)
    entries = cat['entries']
    if not entries:
        raise RuntimeError('No continuously-certified Phase-8 circuits')

    seed = int(cfg.get('seed', 9201))
    rounds = int(cfg.get('rounds', 3))
    budget = int(cfg.get('search_budget', 4))
    nctx = int(cfg.get('contexts_per_family', 1))
    ps = [float(x) for x in cfg.get('p', [1e-4, 2e-4, 5e-4])]
    shots = int(cfg.get('shots', 10000))
    triple_samples = int(cfg.get('triple_samples', 30000))
    pair_block = int(cfg.get('pair_block', 48))
    families = list(cfg.get('families', ['hw_id']))
    rare_families = set(cfg.get('rare_event_families', families))
    rare_contexts = int(cfg.get('rare_event_contexts_per_family', 1))

    train = sample_hardware_contexts(int(cfg.get('fixed_train_contexts', 8)), seed + 1, 'hw_train')
    fixed = _choose_fixed(entries, [train.context(i) for i in range(len(train))])

    rare_rows: list[dict] = []
    mc_rows: list[dict] = []
    cert_rows: list[dict] = []
    decoder_summary: dict[str, dict] = {}

    canonical_slots = {'hw_id': 0, 'ood_idle_hotspot': 1, 'ood_slow_link': 2, 'ood_logical_shift': 3, 'ood_mixed': 4}
    for fi, fam in enumerate(families):
        slot = canonical_slots.get(fam, fi)
        batch = sample_hardware_contexts(nctx, seed + 100 * slot + 10, fam)
        family_rates = {'history_lookup': [], 'detector_pair': [], 'temporal_majority': []}
        detector_sf = 0; detector_conf = 0
        for ci in range(nctx):
            ctx = batch.context(ci)
            proxy = _choose_proxy(entries, ctx, budget)[0]
            methods = {'certified_fixed': fixed, 'certified_proxy': proxy}
            for method, e in methods.items():
                labels, hubs = _labels_hubs(e)
                cert = timed_single_fault_certificate(labels, hubs, ctx)
                cert_rows.append({
                    'family': fam, 'context': ci, 'method': method,
                    'ft_pass': cert.passed, 'c1': cert.c1,
                    'single_fault_failures': cert.single_fault_failures,
                    'conflicts': cert.conflicts, 'incoming_failures': cert.incoming_failures,
                    'native_cx': cert.native_cx, 'duration_us': cert.duration_ns / 1000.0,
                })
            # Decoder/scaling comparison is performed on the context-conditioned proxy circuit.
            labels, hubs = _labels_hubs(proxy)
            plan = build_timed_bridge_plan(labels, hubs, ctx)
            sweep = compare_decoders_sweep(
                plan, ctx, rounds, ps, shots,
                [seed + 100000 * slot + 10000 * ci + 100 * pi for pi in range(len(ps))],
            )
            for rr in sweep:
                p = rr['p']
                row = {'family': fam, 'context': ci, **rr}
                for name in ('history_lookup', 'detector_pair', 'temporal_majority'):
                    row[f'{name}_failures'] = rr[name]['failures']
                    row[f'{name}_rate'] = rr[name]['logical_failure_rate']
                    family_rates[name].append((p, rr[name]['logical_failure_rate']))
                detector_sf += int(rr['detector_single_fault_failures'])
                detector_conf += int(rr['detector_single_fault_conflicts'])
                mc_rows.append(row)
            if fam in rare_families and ci < rare_contexts:
                exp, _ = low_order_expansion(
                    plan, ctx, rounds, decoder_kind='history',
                    reference_p=float(cfg.get('detector_reference_p', 2e-4)),
                    triple_samples=triple_samples,
                    seed=seed + 777000 + 1000 * slot + ci,
                    pair_block=pair_block,
                )
                rr = {'family': fam, 'context': ci, 'method': 'certified_proxy_history', **exp.__dict__}
                for p in ps:
                    rr[f'predicted_p_{p:g}'] = exp.predict(p)
                rare_rows.append(rr)
                print(f"P9 RARE {fam} {ci+1}/{min(nctx,rare_contexts)}: C1={exp.c1:.6g} C2={exp.c2:.6g} C3~={exp.c3_taylor_estimate:.6g}")
            print(f'P9 EVAL {fam} {ci+1}/{nctx}: proxy_ft={cert_rows[-1]["ft_pass"]}')

        # Aggregate equal-p rates across contexts before fitting slopes.
        rates_table = []
        for p in ps:
            row = {'p': p}
            for name in family_rates:
                vals = [r for pp, r in family_rates[name] if pp == p]
                row[name] = float(np.mean(vals)) if vals else float('nan')
            rates_table.append(row)
        decoder_summary[fam] = {
            'rates': rates_table,
            'history_slope': fit_loglog_slope([(r['p'], r['history_lookup']) for r in rates_table]),
            'detector_slope': fit_loglog_slope([(r['p'], r['detector_pair']) for r in rates_table]),
            'majority_slope': fit_loglog_slope([(r['p'], r['temporal_majority']) for r in rates_table]),
            'detector_single_fault_failures': int(detector_sf),
            'detector_single_fault_conflicts': int(detector_conf),
        }

    _save_csv(out / 'phase9_low_order.csv', rare_rows)
    flat_mc = []
    for r in mc_rows:
        flat_mc.append({k: v for k, v in r.items() if not isinstance(v, dict)})
    _save_csv(out / 'phase9_decoder_comparison.csv', flat_mc)
    _save_csv(out / 'phase9_certification.csv', cert_rows)

    payload = {
        'config': cfg,
        'catalog_size': len(entries),
        'rare_event_rows': rare_rows,
        'decoder_summary': decoder_summary,
        'continuous_validation': {
            'checked': len(cert_rows),
            'passed': sum(bool(r['ft_pass']) for r in cert_rows),
            'failed': sum(not bool(r['ft_pass']) for r in cert_rows),
        },
        'elapsed_seconds': time.time() - t0,
    }
    (out / 'phase9_results.json').write_text(json.dumps(payload, indent=2) + '\n')
    (out / 'phase9_summary.md').write_text(_markdown(payload) + '\n')
    print('PHASE 9 REPORT:', out / 'phase9_summary.md')
    return payload
