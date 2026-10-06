from itertools import combinations
import numpy as np
import pytest
from qecflag.physics import (GENERATORS, N, SYN, FLAG, code_tables, commutes, weight, local_pauli,
    candidate_schedules, schedule_from_label, labels, fault_records, decoder_and_certificate,
    quadratic_risk_matrix, cx_frame, propagate, data_part)
from qecflag.dense_check import (ideal_measurement_valid, crosscheck_records, cx, pauli,
                                compact_frame, equivalent_up_to_phase)
from qecflag.noise import sample_contexts
from qecflag.simulation import failure_mask


def test_stabilizers_commute_and_are_independent():
    assert all(commutes(a, b) for a in GENERATORS for b in GENERATORS)
    canon, _, syndromes, _ = code_tables()
    assert np.count_nonzero(canon == 0) == 64
    assert len(set(syndromes)) == 64


def test_code_distance_is_three():
    canon, _, syndromes, _ = code_tables()
    nontrivial_logicals = np.flatnonzero((syndromes == 0) & (canon != 0))
    assert min(weight(int(p)) for p in nontrivial_logicals) == 3


def test_logical_x_is_not_mistaken_for_no_error():
    canon, _, syndromes, _ = code_tables()
    logical_x = 127
    assert syndromes[logical_x] == 0
    assert canon[logical_x] != 0


def test_canonical_stabilizer_identity_matches_dense_encoded_logical_map():
    # Independent Steane |0_L>, |1_L> construction from the X-generator span.
    words = [0]
    for g in GENERATORS[:3]:
        words += [w ^ g for w in words.copy()]
    logical = np.zeros((128, 2), dtype=complex)
    logical[words, 0] = 1 / np.sqrt(8)
    logical[np.array(words) ^ 127, 1] = 1 / np.sqrt(8)
    canon, _, syndromes, _ = code_tables()
    for error in np.flatnonzero(syndromes == 0):
        x, z = int(error) & 127, int(error) >> 7
        indices = np.arange(128) ^ x
        signs = np.array([(-1) ** ((int(i) & z).bit_count()) for i in indices])
        acted = logical[indices] * signs[:, None]
        assert equivalent_up_to_phase(acted, logical) == (canon[error] == 0)


def test_candidate_count_and_label_roundtrip():
    schedules = candidate_schedules()
    assert len(schedules) == 360
    assert len(set(schedules)) == 360
    assert all(schedule_from_label(labels(s)) == s for s in schedules)


@pytest.mark.parametrize('text', ['', '00123FF', '01234FF', '0123F', '0F1F23F'])
def test_invalid_schedule_labels_rejected(text):
    with pytest.raises(ValueError):
        schedule_from_label(text)


@pytest.mark.parametrize('schedule', candidate_schedules(), ids=labels)
def test_ideal_instrument_and_independent_fault_propagation(schedule):
    assert ideal_measurement_valid(schedule)
    assert crosscheck_records(schedule, fault_records(schedule)) == 94


def test_cnot_pauli_propagation_all_sixteen_local_operators():
    rng = np.random.default_rng(51)
    state = rng.normal(size=(64, 2)) + 1j * rng.normal(size=(64, 2))
    for a in range(4):
        for b in range(4):
            frame = local_pauli(a, 0) ^ local_pauli(b, SYN)
            x, z = compact_frame(frame)
            direct = cx(pauli(state, x, z), 0, 4)
            predicted_frame = cx_frame(frame, 0, SYN)
            x, z = compact_frame(predicted_frame)
            predicted = pauli(cx(state, 0, 4), x, z)
            assert equivalent_up_to_phase(direct, predicted)


def test_incoming_single_data_errors_do_not_spread_to_other_data():
    for schedule in candidate_schedules():
        for q in range(7):
            for p in (1, 2, 3):
                full = propagate(schedule, local_pauli(p, q))
                assert data_part(full) == local_pauli(p, q, n=7)
                assert (full >> (N + FLAG)) & 1 == 0


def test_exactly_96_schedules_are_certified(catalog):
    assert len(catalog.labels) == 96
    assert catalog.reports[candidate_schedules().index(schedule_from_label('0F12F3'))]['certified']


def test_all_certified_schedules_recover_every_single_fault(catalog):
    for label, decoder in zip(catalog.labels, catalog.decoders):
        records = fault_records(schedule_from_label(label))
        assert not failure_mask(records.data, records.flag, decoder).any()
        assert len(records.data) == 94


def test_negative_bare_ancilla_detected():
    _, report = decoder_and_certificate(schedule_from_label('0123'))
    assert not report['certified']
    assert report['unflagged_hook_faults'] > 0
    assert report['decoder_conflicts'] > 0


def test_negative_misplaced_flag_detected():
    _, report = decoder_and_certificate(schedule_from_label('0F1F23'))
    assert not report['certified']
    assert report['unflagged_hook_faults'] > 0


def test_negative_missing_data_coupling_detected():
    assert not ideal_measurement_valid((0, FLAG, 1, 2, FLAG))


def test_negative_ignoring_flag_breaks_recovery():
    schedule = schedule_from_label('0F12F3')
    decoder, _ = decoder_and_certificate(schedule)
    records = fault_records(schedule)
    assert failure_mask(records.data, np.zeros_like(records.flag), decoder).any()


def test_common_phase_checker_rejects_relative_phase():
    a = np.eye(2, dtype=complex)
    b = np.diag([1, -1])
    assert not equivalent_up_to_phase(a, b)
    assert equivalent_up_to_phase(a, 1j * a)


def test_quadratic_coefficient_matches_explicit_different_location_pairs(catalog):
    context = sample_contexts(1, 941)[0]
    chosen = catalog.reference
    schedule = schedule_from_label(catalog.labels[chosen])
    rec = fault_records(schedule)
    total = 0.0
    for i, j in combinations(range(len(rec.data)), 2):
        if rec.location[i] == rec.location[j]:
            continue
        bad = failure_mask(np.array([rec.data[i] ^ rec.data[j]]),
                           np.array([rec.flag[i] ^ rec.flag[j]]), catalog.decoders[chosen])[0]
        if bad:
            total += context[rec.category[i]] * context[rec.category[j]]
    actual = context @ catalog.matrices[chosen] @ context
    assert actual == pytest.approx(total, abs=1e-11)


def test_perfect_recovery_decoder_always_matches_its_syndrome(catalog):
    _, _, syndromes, _ = code_tables()
    for decoder in catalog.decoders:
        assert np.array_equal(syndromes[decoder], np.tile(np.arange(64), 2))
