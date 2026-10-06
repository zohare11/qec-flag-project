"""End-to-end mixed compiler repair: unsafe lowering followed by unsafe scheduling."""
from __future__ import annotations
from dataclasses import dataclass, asdict
from pathlib import Path
from qecflag.phase5_hardware import HardwareContext
from .routing_cegis import repair_routing_multidefect
from .schedule_cegis import repair_parallel_schedule_portfolio


@dataclass
class MixedRepairResult:
    success: bool
    routing_success: bool
    scheduling_success: bool
    routing_verifier_calls: int
    scheduling_verifier_calls: int
    total_verifier_calls: int
    changed_checks: tuple[int, ...]
    precedence_constraints: tuple[tuple[int,int], ...]
    final_max_parallel_cx: int | None
    speedup_vs_serial_percent: float | None

    def to_dict(self): return asdict(self)


def repair_mixed(project_root: Path, labels, hubs, context: HardwareContext,
                 schedule_method='shortest_greedy', routing_max_edits=4,
                 routing_max_calls=64, schedule_max_constraints=15,
                 schedule_max_calls=20):
    rr=repair_routing_multidefect(project_root,labels,hubs,context,
        max_edits=routing_max_edits,max_verifier_calls=routing_max_calls)
    if not rr.success:
        return MixedRepairResult(False,False,False,rr.verifier_calls,0,rr.verifier_calls,
            tuple(),tuple(),None,None)
    sr=repair_parallel_schedule_portfolio(rr.repaired_labels,rr.repaired_hubs,context,
        method=schedule_method,max_constraints=schedule_max_constraints,max_verifier_calls=schedule_max_calls)
    return MixedRepairResult(bool(sr.success),True,bool(sr.success),rr.verifier_calls,sr.verifier_calls,
        rr.verifier_calls+sr.verifier_calls,rr.changed_checks,sr.constraints,
        int(sr.final_max_parallel_cx) if sr.final_max_parallel_cx is not None else None,
        sr.retained_speedup_vs_serial_percent)
