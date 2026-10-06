import numpy as np
import pytest
from qecflag.noise import sample_contexts
from qecflag.physics import schedule_from_label, fault_records
from qecflag.simulation import simulate, low_order_bounds, wilson_interval, failure_mask


def test_zero_noise_is_exactly_zero(catalog):
    i = catalog.reference
    schedule = schedule_from_label(catalog.labels[i])
    w = sample_contexts(1, 710)[0]
    result = simulate(schedule, catalog.decoders[i], w, 0, 200, 99)
    assert result['logical_failures'] == 0
    assert result['flag_rate'] == 0
    bounds = low_order_bounds(schedule, catalog.decoders[i], w, 0)
    assert bounds['rigorous_model_upper_bound'] == 0


def test_sampler_is_reproducible(catalog):
    i = catalog.reference
    args = (schedule_from_label(catalog.labels[i]), catalog.decoders[i], sample_contexts(1, 70)[0], .02, 1000, 99)
    assert simulate(*args) == simulate(*args)


def test_low_p_limit_matches_exact_second_order(catalog):
    i = catalog.reference
    schedule = schedule_from_label(catalog.labels[i])
    w = sample_contexts(1, 19)[0]
    p = 1e-7
    lower = low_order_bounds(schedule, catalog.decoders[i], w, p)['rigorous_model_lower_bound']
    coefficient = w @ catalog.matrices[i] @ w
    assert lower / p**2 == pytest.approx(coefficient, rel=2e-5)


def test_known_two_location_model_agrees_with_monte_carlo(catalog):
    i = catalog.reference
    schedule = schedule_from_label(catalog.labels[i])
    rec = fault_records(schedule)
    pair = None
    for a in range(len(rec.data)):
        for b in range(a+1, len(rec.data)):
            ca, cb = rec.category[a], rec.category[b]
            # Only unique data-CNOT edges: no repeated flag-edge location.
            if not (2 <= ca < 62 and 2 <= cb < 62 and (ca-2)//15 != (cb-2)//15):
                continue
            if failure_mask(np.array([rec.data[a] ^ rec.data[b]]),
                            np.array([rec.flag[a] ^ rec.flag[b]]), catalog.decoders[i])[0]:
                pair = (ca, cb)
                break
        if pair:
            break
    assert pair is not None
    w = np.zeros(79)
    w[list(pair)] = 1
    p = .2
    bounds = low_order_bounds(schedule, catalog.decoders[i], w, p)
    assert bounds['probability_three_or_more_faulty_locations'] == 0
    assert bounds['rigorous_model_lower_bound'] == pytest.approx(p*p)
    result = simulate(schedule, catalog.decoders[i], w, p, 100000, 177)
    sigma = np.sqrt(p*p * (1-p*p) / 100000)
    assert abs(result['logical_failure_rate_with_perfect_final_recovery'] - p*p) < 6 * sigma


def test_wilson_interval_for_zero_events_has_nonzero_upper_bound():
    low, high = wilson_interval(0, 1000)
    assert low == pytest.approx(0, abs=1e-16)
    assert high > 0
    assert high < 0.004


def test_noise_past_probability_one_is_rejected(catalog):
    i = catalog.reference
    with pytest.raises(ValueError):
        simulate(schedule_from_label(catalog.labels[i]), catalog.decoders[i], np.ones(79), 1, 100, 4)
