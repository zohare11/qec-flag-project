"""Repeated-round detector decoding for Phase-10 parallel schedules."""
from __future__ import annotations

from dataclasses import dataclass
import numpy as np

from .physics import code_tables
from .phase8_timing import RepeatedFaultRecords, build_timed_bridge_plan, _wilson
from .phase9_analysis import build_detector_pair_decoder
from .phase10_scheduler import (
    ParallelSchedule, ParallelFaultDescriptor, parallel_fault_catalog,
    _apply_parallel_round,
)
from .phase6_native import _data_frame_to_physical, _physical_to_data
from .phase5_hardware import HardwareContext


@dataclass(frozen=True)
class ParallelRepeatedFault:
    round_index: int
    descriptor: ParallelFaultDescriptor


def simulate_parallel_repeated_signature(schedule: ParallelSchedule, rounds: int,
                                         fault: ParallelRepeatedFault | None = None,
                                         incoming_data: int = 0,
                                         include_final_boundary: bool = True) -> tuple[int, int, int]:
    if rounds < 1:
        raise ValueError('rounds must be >=1')
    frame = _data_frame_to_physical(int(incoming_data))
    sh = 0; fh = 0
    for r in range(rounds):
        desc = fault.descriptor if fault is not None and fault.round_index == r else None
        frame, synd, flags = _apply_parallel_round(schedule, frame, fault=desc)
        sh |= int(synd) << (6 * r)
        fh |= int(flags) << (12 * r)
    data = int(_physical_to_data(frame))
    if include_final_boundary:
        _, _, syndromes, _ = code_tables()
        sh |= int(syndromes[data]) << (6 * rounds)
    return data, int(sh), int(fh)


def parallel_repeated_fault_records(schedule: ParallelSchedule, context: HardwareContext,
                                    rounds: int) -> RepeatedFaultRecords:
    desc, weights = parallel_fault_catalog(schedule, context)
    nloc = int(max((d.location for d in desc), default=-1) + 1)
    data=[]; sh=[]; fh=[]; loc=[]; ww=[]; faults=[]
    for r in range(rounds):
        for d, w in zip(desc, weights):
            rf = ParallelRepeatedFault(r, d)
            dd, ss, ff = simulate_parallel_repeated_signature(schedule, rounds, rf)
            data.append(dd); sh.append(ss); fh.append(ff)
            loc.append(r * nloc + d.location); ww.append(float(w)); faults.append(rf)
    return RepeatedFaultRecords(
        np.asarray(data,dtype=np.int32), np.asarray(sh,dtype=np.int64), np.asarray(fh,dtype=np.int64),
        np.asarray(loc,dtype=np.int32), np.asarray(ww,dtype=np.float64), tuple(faults),
    )


def simulate_parallel_detector_finite_p(schedule: ParallelSchedule, context: HardwareContext,
                                        rounds: int, p: float, shots: int, seed: int,
                                        reference_p: float | None = None,
                                        batch_size: int = 5000,
                                        records: RepeatedFaultRecords | None = None) -> dict:
    if p < 0 or shots <= 0:
        raise ValueError('invalid p/shots')
    rec = parallel_repeated_fault_records(schedule, context, rounds) if records is None else records
    # build_detector_pair_decoder only needs the supplied records for the noisy
    # signatures; the serialized plan argument is used as metadata/fallback.
    meta_plan = build_timed_bridge_plan(schedule.native.labels, schedule.native.hubs, context)
    dec = build_detector_pair_decoder(meta_plan, context, rounds,
                                      reference_p=float(reference_p or max(p,1e-12)), records=rec)
    locations=np.unique(rec.location); groups=[np.flatnonzero(rec.location==x) for x in locations]
    max_rate=max((float(rec.weight[idx].sum()) for idx in groups),default=0.0)
    if p * max_rate > 1:
        raise ValueError('p makes a physical-location probability exceed 1')
    canon,_,_,_=code_tables(); rng=np.random.default_rng(seed); failures=0
    for start in range(0,shots,batch_size):
        b=min(batch_size,shots-start)
        data=np.zeros(b,dtype=np.int32); sh=np.zeros(b,dtype=np.int64); fh=np.zeros(b,dtype=np.int64)
        for idx in groups:
            probs=p*rec.weight[idx]; cum=np.cumsum(probs)
            draw=np.searchsorted(cum,rng.random(b),side='right')
            data ^= np.append(rec.data[idx],0)[draw]
            sh ^= np.append(rec.syndrome_history[idx],0)[draw]
            fh ^= np.append(rec.flag_history[idx],0)[draw]
        corr=dec.corrections_for(sh,fh)
        failures += int(np.count_nonzero(canon[data ^ corr]))
    lo,hi=_wilson(failures,shots)
    return {
        'rounds':int(rounds),'p':float(p),'shots':int(shots),'seed':int(seed),
        'failures':int(failures),'logical_failure_rate':float(failures/shots),
        'wilson95_low':lo,'wilson95_high':hi,
        'decoder':'order-2 detector-hypergraph decoder',
        'detector_single_fault_conflicts':int(dec.single_fault_conflicts),
        'detector_single_fault_failures':int(dec.single_fault_failures),
        'detector_incoming_failures':int(dec.incoming_failures),
        'detector_primitive_count':int(dec.primitive_count),'detector_map_entries':int(dec.map_entries),
        'native_cx_per_round':int(schedule.total_native_cx),
        'duration_us_per_round':float(schedule.duration_ns/1000.0),
        'max_parallel_cx':int(schedule.max_parallel_cx),
        'total_data_idle_us_per_round':float(sum(schedule.data_idle_ns)/1000.0),
    }

def simulate_parallel_detector_sweep(schedule: ParallelSchedule, context: HardwareContext,
                                     rounds: int, ps, shots: int, seeds,
                                     reference_p: float = 2e-4,
                                     batch_size: int = 5000) -> list[dict]:
    """Evaluate several p values while reusing the repeated-fault catalog/decoder."""
    ps=[float(x) for x in ps]; seeds=[int(x) for x in seeds]
    if len(ps)!=len(seeds):
        raise ValueError('ps and seeds must have same length')
    if shots<=0 or any(p<0 for p in ps):
        raise ValueError('invalid p/shots')
    rec=parallel_repeated_fault_records(schedule,context,rounds)
    meta_plan=build_timed_bridge_plan(schedule.native.labels,schedule.native.hubs,context)
    dec=build_detector_pair_decoder(meta_plan,context,rounds,reference_p=float(reference_p),records=rec)
    locations=np.unique(rec.location); groups=[np.flatnonzero(rec.location==x) for x in locations]
    max_rate=max((float(rec.weight[idx].sum()) for idx in groups),default=0.0)
    canon,_,_,_=code_tables(); out=[]
    for p,seed in zip(ps,seeds):
        if p*max_rate>1:
            raise ValueError('p makes a physical-location probability exceed 1')
        rng=np.random.default_rng(seed); failures=0
        for start in range(0,shots,batch_size):
            b=min(batch_size,shots-start)
            data=np.zeros(b,dtype=np.int32); sh=np.zeros(b,dtype=np.int64); fh=np.zeros(b,dtype=np.int64)
            for idx in groups:
                probs=p*rec.weight[idx]; cum=np.cumsum(probs)
                draw=np.searchsorted(cum,rng.random(b),side='right')
                data ^= np.append(rec.data[idx],0)[draw]
                sh ^= np.append(rec.syndrome_history[idx],0)[draw]
                fh ^= np.append(rec.flag_history[idx],0)[draw]
            corr=dec.corrections_for(sh,fh)
            failures += int(np.count_nonzero(canon[data ^ corr]))
        lo,hi=_wilson(failures,shots)
        out.append({
            'rounds':int(rounds),'p':float(p),'shots':int(shots),'seed':int(seed),
            'failures':int(failures),'logical_failure_rate':float(failures/shots),
            'wilson95_low':lo,'wilson95_high':hi,'decoder':'order-2 detector-hypergraph decoder',
            'detector_single_fault_conflicts':int(dec.single_fault_conflicts),
            'detector_single_fault_failures':int(dec.single_fault_failures),
            'detector_incoming_failures':int(dec.incoming_failures),
            'detector_primitive_count':int(dec.primitive_count),'detector_map_entries':int(dec.map_entries),
            'native_cx_per_round':int(schedule.total_native_cx),
            'duration_us_per_round':float(schedule.duration_ns/1000.0),
            'max_parallel_cx':int(schedule.max_parallel_cx),
            'total_data_idle_us_per_round':float(sum(schedule.data_idle_ns)/1000.0),
        })
    return out
