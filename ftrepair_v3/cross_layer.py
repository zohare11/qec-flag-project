"""Cross-layer routing + scheduling repair portfolios for FT repair v3."""
from __future__ import annotations
from dataclasses import dataclass, asdict
from pathlib import Path

from qecflag.phase5_hardware import HardwareContext

from .model import RoutingState, edit_atoms
from .cache import RoutingVerifierCache, GenericVerifierCache
from .routing_cegis import enumerate_safe_routing_repairs, repair_routing_v3
from .op_scheduler import repair_operation_schedule_portfolio


@dataclass
class CrossLayerRepairResult:
    success: bool
    routing_success: bool
    scheduling_success: bool
    routing_candidates_found: int
    routing_verifier_calls: int
    routing_cache_hits: int
    scheduling_verifier_calls: int
    scheduling_cache_hits: int
    total_verifier_calls: int
    selected_routing_edits: int
    selected_schedule_constraints: int
    total_compiler_edits: int
    final_duration_ns: float | None
    final_max_parallel_cx: int | None
    speedup_vs_serial_percent: float | None
    selected_state: RoutingState | None
    selected_constraints: tuple[tuple[int,int,int,int], ...]
    candidate_summaries: list[dict]

    def to_dict(self): return asdict(self)


def repair_staged_v3(project_root:Path,state:RoutingState,context:HardwareContext,
                     schedule_method='shortest_greedy',routing_max_calls=48,
                     scheduling_max_calls=32):
    rr=repair_routing_v3(project_root,state,None,context,max_verifier_calls=routing_max_calls,
                         max_solutions=1)
    if not rr.success or rr.repaired_state is None:
        return CrossLayerRepairResult(False,False,False,0,rr.verifier_calls,rr.cache_hits,0,0,rr.verifier_calls,
            0,0,0,None,None,None,None,tuple(),[])
    sr=repair_operation_schedule_portfolio(rr.repaired_state,context,schedule_method,
                                           max_verifier_calls=scheduling_max_calls)
    success=bool(sr.success)
    return CrossLayerRepairResult(success,True,success,1,rr.verifier_calls,rr.cache_hits,
        sr.verifier_calls,sr.cache_hits,rr.verifier_calls+sr.verifier_calls,rr.edit_count,
        len(sr.constraints) if success else 0,rr.edit_count+(len(sr.constraints) if success else 0),
        float(sr.final_duration_ns) if success else None,int(sr.final_max_parallel_cx) if success else None,
        sr.speedup_vs_serial_percent if success else None,rr.repaired_state if success else None,
        tuple(sr.constraints) if success else tuple(),
        [{'routing_edits':rr.edit_count,'schedule_success':success,'duration_ns':sr.final_duration_ns,
          'schedule_constraints':len(sr.constraints),'speedup_vs_serial_percent':sr.speedup_vs_serial_percent}])


def repair_cross_layer_portfolio(project_root:Path,state:RoutingState,context:HardwareContext,
                                 schedule_method='shortest_greedy',routing_max_calls=72,
                                 scheduling_calls_per_candidate=28,max_routing_solutions=4,
                                 objective='minimal_edits') -> CrossLayerRepairResult:
    """Enumerate several serial-safe lowerings, then select using downstream schedulability.

    This is a genuine cross-layer *portfolio* rather than a monolithic joint SAT
    solver: routing candidates are not accepted solely on serial quality.  Each
    candidate is passed through the operation-level scheduler, and the final
    choice uses exact safety plus combined compiler-edit/timing objectives.
    """
    rcache=RoutingVerifierCache()
    sols,meta=enumerate_safe_routing_repairs(project_root,state,None,context,
        max_verifier_calls=routing_max_calls,max_solutions=max_routing_solutions,cache=rcache)
    if not sols:
        return CrossLayerRepairResult(False,False,False,0,int(meta['calls']),int(meta['hits']),0,0,
            int(meta['calls']),0,0,0,None,None,None,None,tuple(),[])
    candidates=[];sched_calls=0;sched_hits=0
    for i,st in enumerate(sols):
        scache=GenericVerifierCache()
        sr=repair_operation_schedule_portfolio(st,context,schedule_method,
            max_verifier_calls=scheduling_calls_per_candidate,cache=scache)
        sched_calls+=sr.verifier_calls;sched_hits+=sr.cache_hits
        redits=len(edit_atoms(state,st));sedits=len(sr.constraints) if sr.success else 10**6
        total=redits+sedits
        candidates.append({'index':i,'state':st,'schedule':sr,'success':bool(sr.success),
                           'routing_edits':redits,'schedule_constraints':len(sr.constraints),
                           'total_edits':total,'duration_ns':float(sr.final_duration_ns),
                           'speedup_vs_serial_percent':sr.speedup_vs_serial_percent,
                           'max_parallel_cx':int(sr.final_max_parallel_cx)})
    safe=[x for x in candidates if x['success']]
    if not safe:
        return CrossLayerRepairResult(False,True,False,len(sols),int(meta['calls']),int(meta['hits']),sched_calls,
            sched_hits,int(meta['calls'])+sched_calls,0,0,0,None,None,None,None,tuple(),
            [{k:v for k,v in x.items() if k not in ('state','schedule')} for x in candidates])
    if objective=='performance':
        best=min(safe,key=lambda x:(x['duration_ns'],x['total_edits'],x['routing_edits'],x['index']))
    elif objective=='minimal_edits':
        best=min(safe,key=lambda x:(x['total_edits'],x['duration_ns'],x['routing_edits'],x['index']))
    else:
        raise ValueError('objective must be minimal_edits or performance')
    sr=best['schedule'];st=best['state']
    summaries=[{k:v for k,v in x.items() if k not in ('state','schedule')} for x in candidates]
    return CrossLayerRepairResult(True,True,True,len(sols),int(meta['calls']),int(meta['hits']),sched_calls,sched_hits,
        int(meta['calls'])+sched_calls,best['routing_edits'],best['schedule_constraints'],best['total_edits'],
        best['duration_ns'],best['max_parallel_cx'],best['speedup_vs_serial_percent'],st,tuple(sr.constraints),summaries)
