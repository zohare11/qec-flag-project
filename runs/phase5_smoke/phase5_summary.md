# Phase 5 summary

Scope: hardware-aware proposal search for one noisy six-check Steane extraction round on a fixed synthetic 12-node nearest-neighbour graph.

Hardware routing and timing are represented by schedule-dependent effective logical fault weights. Inserted native routing gates are counted and timed, but not individually fault-enumerated. Lower hardware-aware C2 is better.

- Hardware actions/check: 96 = 48 certified local templates x 2 syndrome-hub placements
- Full schedule space: 96^6 = 782,757,789,696
- Exact hardware-aware C2 evaluation budget for random/coordinate/policy-beam: 4 complete schedules/context

## Topology

```json
{
  "graph": "3x4 nearest-neighbour grid (synthetic, not a named device)",
  "physical_qubits": 12,
  "edges": [
    [
      0,
      1
    ],
    [
      0,
      4
    ],
    [
      1,
      2
    ],
    [
      1,
      5
    ],
    [
      2,
      3
    ],
    [
      2,
      6
    ],
    [
      3,
      7
    ],
    [
      4,
      5
    ],
    [
      4,
      8
    ],
    [
      5,
      6
    ],
    [
      5,
      9
    ],
    [
      6,
      7
    ],
    [
      6,
      10
    ],
    [
      7,
      11
    ],
    [
      8,
      9
    ],
    [
      9,
      10
    ],
    [
      10,
      11
    ]
  ],
  "data_nodes": [
    0,
    3,
    8,
    11,
    1,
    10,
    9
  ],
  "hub_nodes": [
    5,
    6
  ],
  "flag_nodes": {
    "A": 4,
    "B": 7
  },
  "routing_model": "SWAP-forward / native-CX / SWAP-back; mapping restored",
  "native_cx_count_for_distance_d": "6*(d-1)+1",
  "idle_model": "persistent-data idle exposure smeared onto existing logical data-CNOT Pauli categories"
}
```

## hw_id

| Method | Mean C2 | Median C2 | Mean native CX | Mean duration (us) | Hub-0 use | Two-flag use |
|---|---:|---:|---:|---:|---:|---:|
| reference | 19750.104316 | 19750.104316 | 180.0 | 45.606 | 100.0% | 0.0% |
| proxy_fixed | 7450.143417 | 7450.143417 | 180.0 | 45.706 | 33.3% | 0.0% |
| routing_heuristic | 7978.360358 | 7978.360358 | 180.0 | 44.883 | 83.3% | 0.0% |
| local_greedy | 5217.888315 | 5217.888315 | 192.0 | 48.772 | 75.0% | 0.0% |
| random_search | 22304.393050 | 22304.393050 | 250.0 | 63.481 | 50.0% | 33.3% |
| coordinate_search | 5155.209628 | 5155.209628 | 192.0 | 48.772 | 75.0% | 0.0% |
| policy_greedy_seed_mean | 7850.891785 | 7850.891785 | 193.0 | 49.299 | 91.7% | 8.3% |
| policy_beam_seed_mean | 7595.577628 | 7595.577628 | 193.0 | 49.299 | 91.7% | 8.3% |

- Policy-beam vs random: win fraction 100.0%; mean C2 change -65.95%.
- Policy-beam vs coordinate: win fraction 0.0%; mean C2 change 47.34%.
- Policy-beam vs one-evaluation hardware local-greedy: win fraction 0.0%.

## ood_hub0_bad

| Method | Mean C2 | Median C2 | Mean native CX | Mean duration (us) | Hub-0 use | Two-flag use |
|---|---:|---:|---:|---:|---:|---:|
| reference | 3611295.933559 | 3611295.933559 | 228.0 | 77.910 | 100.0% | 0.0% |
| proxy_fixed | 84610.043985 | 84610.043985 | 186.0 | 51.022 | 33.3% | 0.0% |
| routing_heuristic | 106360.003526 | 106360.003526 | 186.0 | 51.022 | 33.3% | 0.0% |
| local_greedy | 32826.402928 | 32826.402928 | 246.0 | 60.020 | 0.0% | 0.0% |
| random_search | 5249626.879001 | 5249626.879001 | 387.0 | 111.674 | 58.3% | 25.0% |
| coordinate_search | 32826.402928 | 32826.402928 | 246.0 | 60.020 | 0.0% | 0.0% |
| policy_greedy_seed_mean | 124043.951831 | 124043.951831 | 216.0 | 60.566 | 41.7% | 0.0% |
| policy_beam_seed_mean | 123580.003585 | 123580.003585 | 216.0 | 60.566 | 41.7% | 0.0% |

- Policy-beam vs random: win fraction 100.0%; mean C2 change -97.65%.
- Policy-beam vs coordinate: win fraction 0.0%; mean C2 change 276.47%.
- Policy-beam vs one-evaluation hardware local-greedy: win fraction 0.0%.

## ood_hub1_bad

| Method | Mean C2 | Median C2 | Mean native CX | Mean duration (us) | Hub-0 use | Two-flag use |
|---|---:|---:|---:|---:|---:|---:|
| reference | 14786.673878 | 14786.673878 | 180.0 | 47.205 | 100.0% | 0.0% |
| proxy_fixed | 972381.829923 | 972381.829923 | 192.0 | 63.636 | 33.3% | 0.0% |
| routing_heuristic | 16733.467533 | 16733.467533 | 180.0 | 47.205 | 100.0% | 0.0% |
| local_greedy | 13936.650133 | 13936.650133 | 180.0 | 47.205 | 100.0% | 0.0% |
| random_search | 1001294.485789 | 1001294.485789 | 310.0 | 92.714 | 50.0% | 33.3% |
| coordinate_search | 13599.251516 | 13599.251516 | 180.0 | 47.205 | 100.0% | 0.0% |
| policy_greedy_seed_mean | 30300.029325 | 30300.029325 | 198.0 | 51.830 | 100.0% | 0.0% |
| policy_beam_seed_mean | 31795.515098 | 31795.515098 | 216.0 | 56.593 | 100.0% | 0.0% |

- Policy-beam vs random: win fraction 100.0%; mean C2 change -96.82%.
- Policy-beam vs coordinate: win fraction 0.0%; mean C2 change 133.80%.
- Policy-beam vs one-evaluation hardware local-greedy: win fraction 0.0%.

## ood_edge_hotspot

| Method | Mean C2 | Median C2 | Mean native CX | Mean duration (us) | Hub-0 use | Two-flag use |
|---|---:|---:|---:|---:|---:|---:|
| reference | 36701.646581 | 36701.646581 | 180.0 | 45.718 | 100.0% | 0.0% |
| proxy_fixed | 22811.398366 | 22811.398366 | 180.0 | 44.959 | 33.3% | 0.0% |
| routing_heuristic | 25032.520922 | 25032.520922 | 180.0 | 44.909 | 41.7% | 0.0% |
| local_greedy | 20834.572948 | 20834.572948 | 180.0 | 45.462 | 50.0% | 0.0% |
| random_search | 45746.722517 | 45746.722517 | 268.0 | 68.036 | 25.0% | 33.3% |
| coordinate_search | 19730.986440 | 19730.986440 | 180.0 | 45.462 | 50.0% | 0.0% |
| policy_greedy_seed_mean | 36281.562891 | 36281.562891 | 180.0 | 45.718 | 100.0% | 0.0% |
| policy_beam_seed_mean | 34898.960181 | 34898.960181 | 180.0 | 45.718 | 100.0% | 0.0% |

- Policy-beam vs random: win fraction 50.0%; mean C2 change -23.71%.
- Policy-beam vs coordinate: win fraction 0.0%; mean C2 change 76.87%.
- Policy-beam vs one-evaluation hardware local-greedy: win fraction 0.0%.

## Finite-p reduced hardware diagnostics

These use one predeclared `hw_id` context. The schedule is first converted to effective logical fault weights; the reduced logical Monte Carlo is then run.

| Method | p | failures/shots | logical failure rate | 95% interval | native CX | duration (us) |
|---|---:|---:|---:|---:|---:|---:|
| reference | 0.0002 | 1/3000 | 0.0003333 | [0.0000588, 0.0018858] | 180 | 47.855 |
| reference | 0.0005 | 3/3000 | 0.0010000 | [0.0003401, 0.0029361] | 180 | 47.855 |
| routing_heuristic | 0.0002 | 1/3000 | 0.0003333 | [0.0000588, 0.0018858] | 180 | 46.409 |
| routing_heuristic | 0.0005 | 4/3000 | 0.0013333 | [0.0005186, 0.0034235] | 180 | 46.409 |
| local_greedy | 0.0002 | 2/3000 | 0.0006667 | [0.0001828, 0.0024276] | 180 | 47.317 |
| local_greedy | 0.0005 | 0/3000 | 0.0000000 | [0.0000000, 0.0012788] | 180 | 47.317 |
| random_search | 0.0002 | 4/3000 | 0.0013333 | [0.0005186, 0.0034235] | 280 | 74.433 |
| random_search | 0.0005 | 21/3000 | 0.0070000 | [0.0045831, 0.0106779] | 280 | 74.433 |
| coordinate_search | 0.0002 | 0/3000 | 0.0000000 | [0.0000000, 0.0012788] | 180 | 47.317 |
| coordinate_search | 0.0005 | 3/3000 | 0.0010000 | [0.0003401, 0.0029361] | 180 | 47.317 |
| policy_beam | 0.0002 | 1/3000 | 0.0003333 | [0.0000588, 0.0018858] | 180 | 47.855 |
| policy_beam | 0.0005 | 7/3000 | 0.0023333 | [0.0011307, 0.0048088] | 180 | 47.855 |

## Interpretation constraints

- The 12-node graph and calibration families are synthetic controlled stress tests, not a named processor or measured backend.
- Remote logical CNOTs use a SWAP-forward / CNOT / SWAP-back count-and-duration model. Routing-gate faults are collapsed into effective logical-location weights rather than explicitly propagated gate by gate.
- Persistent data-qubit idle exposure is modeled approximately and folded into logical data-CNOT Pauli weights.
- Checks remain serialized in X0,X1,X2,Z0,Z1,Z2 order; Phase 5 adds placement/routing/timing context but not parallel scheduling.
- The decoder and ideal boundaries are inherited from Phase 4; this is still a one-round experiment, not repeated fault-tolerant memory.
- A positive learned-search result would motivate explicit native-circuit fault simulation and repeated rounds; it would not establish hardware advantage.

