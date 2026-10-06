from pathlib import Path

from qecflag.phase5_actions import ensure_hardware_action_table
from qecflag.phase5_noise import sample_hardware_contexts
from qecflag.phase7_catalog import ensure_catalog
from qecflag.phase7_routing import bridge_native_risk
from qecflag.phase10_scheduler import schedule_parallel, certify_parallel_schedule

from ftrepair.routing_repair import logical_round_is_single_fault_ft, repair_routing
from ftrepair.schedule_repair import repair_parallel_schedule, schedule_with_precedence

ROOT = Path(__file__).resolve().parents[1]


def _injected_case():
    ctx = sample_hardware_contexts(1, 11101, 'hw_id').context(0)
    cat = ensure_catalog(ROOT)
    table = ensure_hardware_action_table(ROOT)
    labels, hubs = cat.labels_hubs(0)
    for action in range(table.n_actions):
        nl = list(labels); nh = list(hubs)
        nl[0] = table.template_label(action); nh[0] = table.hub(action)
        if not logical_round_is_single_fault_ft(nl):
            continue
        risk = bridge_native_risk(nl, nh, ctx, compute_c2=False)
        passed = (
            risk.c1 == 0.0 and risk.decoder.single_fault_conflicts == 0
            and risk.decoder.single_fault_failures == 0 and risk.decoder.incoming_failures == 0
        )
        if not passed:
            return ctx, tuple(nl), tuple(nh)
    raise AssertionError('no injected case found')


def test_repair_input_remains_logically_ft_but_physical_lowering_fails():
    ctx, labels, hubs = _injected_case()
    assert logical_round_is_single_fault_ft(labels)
    risk = bridge_native_risk(labels, hubs, ctx, compute_c2=False)
    assert risk.c1 > 0 or risk.decoder.single_fault_failures > 0 or risk.decoder.single_fault_conflicts > 0


def test_counterexample_guided_routing_repair_recovers_ft_locally():
    ctx, labels, hubs = _injected_case()
    r = repair_routing(ROOT, labels, hubs, ctx, max_edits=2, max_verifier_calls=24, witness_check_limit=2)
    assert r.success
    assert r.final_bridge is not None and r.final_bridge.passed
    assert r.final_bridge.c1 == 0.0
    assert 0 in r.changed_checks
    assert len(r.changed_checks) <= 2
    assert r.verifier_calls <= 24


def test_constrained_scheduler_is_resource_valid_and_deterministic():
    ctx = sample_hardware_contexts(1, 11101, 'hw_id').context(0)
    labels, hubs = ensure_catalog(ROOT).labels_hubs(0)
    a = schedule_with_precedence(labels, hubs, ctx, 'shortest_greedy', forbidden_pairs={(0, 1), (2, 3)})
    b = schedule_with_precedence(labels, hubs, ctx, 'shortest_greedy', forbidden_pairs={(2, 3), (0, 1)})
    assert a.duration_ns == b.duration_ns
    assert [(x.event.uid, x.start_ns) for x in a.events] == [(x.event.uid, x.start_ns) for x in b.events]


def test_schedule_repair_turns_unsafe_parallel_compile_safe():
    ctx = sample_hardware_contexts(1, 11101, 'hw_id').context(0)
    labels, hubs = ensure_catalog(ROOT).labels_hubs(0)
    start = schedule_parallel(labels, hubs, ctx, 'shortest_greedy')
    assert not certify_parallel_schedule(start, ctx).passed
    r = repair_parallel_schedule(labels, hubs, ctx, 'shortest_greedy', max_constraints=15)
    assert r.success
    assert r.final_c1 == 0.0
    assert r.final_failures == 0
    assert len(r.constraints) > 0


def test_schedule_repair_can_preserve_true_cx_parallelism_reference_case():
    ctx = sample_hardware_contexts(1, 11101, 'hw_id').context(0)
    labels, hubs = ensure_catalog(ROOT).labels_hubs(0)
    r = repair_parallel_schedule(labels, hubs, ctx, 'shortest_greedy', max_constraints=15)
    assert r.success
    assert r.final_max_parallel_cx is not None and r.final_max_parallel_cx >= 2
    assert r.final_duration_ns < schedule_parallel(labels, hubs, ctx, 'serialized').duration_ns
