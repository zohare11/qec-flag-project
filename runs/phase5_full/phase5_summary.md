# Phase 5 summary

Scope: hardware-aware proposal search for one noisy six-check Steane extraction round on a fixed synthetic 12-node nearest-neighbour graph.

Hardware routing and timing are represented by schedule-dependent effective logical fault weights. Inserted native routing gates are counted and timed, but not individually fault-enumerated. Lower hardware-aware C2 is better.

- Hardware actions/check: 96 = 48 certified local templates x 2 syndrome-hub placements
- Full schedule space: 96^6 = 782,757,789,696
- Exact hardware-aware C2 evaluation budget for random/coordinate/policy-beam: 8 complete schedules/context

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
| reference | 19190.964784 | 17229.280279 | 180.0 | 45.283 | 100.0% | 0.0% |
| proxy_fixed | 15004.116047 | 14656.587228 | 180.0 | 44.980 | 66.7% | 0.0% |
| routing_heuristic | 17237.243626 | 16690.742904 | 180.0 | 44.266 | 61.7% | 0.0% |
| local_greedy | 12609.293058 | 11270.471912 | 186.0 | 46.355 | 65.0% | 0.0% |
| random_search | 30671.322739 | 17637.682691 | 238.6 | 59.200 | 58.3% | 38.3% |
| coordinate_search | 11835.260498 | 11186.989133 | 186.0 | 46.355 | 65.0% | 0.0% |
| policy_greedy_seed_mean | 14016.525968 | 12472.914646 | 180.0 | 44.793 | 71.1% | 0.0% |
| policy_beam_seed_mean | 13187.388162 | 11432.856857 | 180.0 | 44.759 | 72.8% | 0.0% |

- Policy-beam vs random: win fraction 100.0%; mean C2 change -57.00%.
- Policy-beam vs coordinate: win fraction 40.0%; mean C2 change 11.42%.
- Policy-beam vs one-evaluation hardware local-greedy: win fraction 50.0%.

## ood_hub0_bad

| Method | Mean C2 | Median C2 | Mean native CX | Mean duration (us) | Hub-0 use | Two-flag use |
|---|---:|---:|---:|---:|---:|---:|
| reference | 5811915.374290 | 1130914.060117 | 217.2 | 70.512 | 100.0% | 0.0% |
| proxy_fixed | 350821.932317 | 129289.950754 | 207.6 | 62.384 | 66.7% | 0.0% |
| routing_heuristic | 60114.542491 | 36848.861160 | 190.8 | 50.297 | 28.3% | 0.0% |
| local_greedy | 28988.275315 | 16112.762524 | 229.2 | 56.144 | 1.7% | 0.0% |
| random_search | 285805.242723 | 130175.977892 | 328.8 | 87.225 | 38.3% | 30.0% |
| coordinate_search | 28164.964012 | 15704.838544 | 229.2 | 56.144 | 1.7% | 0.0% |
| policy_greedy_seed_mean | 101647.338239 | 38229.150438 | 204.8 | 53.644 | 31.1% | 0.0% |
| policy_beam_seed_mean | 76607.656500 | 24390.395873 | 210.8 | 53.795 | 23.9% | 0.0% |

- Policy-beam vs random: win fraction 100.0%; mean C2 change -73.20%.
- Policy-beam vs coordinate: win fraction 0.0%; mean C2 change 172.00%.
- Policy-beam vs one-evaluation hardware local-greedy: win fraction 0.0%.

## ood_hub1_bad

| Method | Mean C2 | Median C2 | Mean native CX | Mean duration (us) | Hub-0 use | Two-flag use |
|---|---:|---:|---:|---:|---:|---:|
| reference | 24714.597530 | 15547.266440 | 180.0 | 46.131 | 100.0% | 0.0% |
| proxy_fixed | 137799.738121 | 68876.139748 | 183.6 | 53.549 | 66.7% | 0.0% |
| routing_heuristic | 19593.914808 | 15667.926849 | 180.0 | 46.131 | 100.0% | 0.0% |
| local_greedy | 18904.518394 | 14257.190280 | 180.0 | 46.131 | 100.0% | 0.0% |
| random_search | 261678.903651 | 132672.754952 | 298.2 | 82.098 | 58.3% | 35.0% |
| coordinate_search | 18280.086697 | 13405.855118 | 180.0 | 46.131 | 100.0% | 0.0% |
| policy_greedy_seed_mean | 19774.801896 | 13545.491338 | 180.0 | 46.397 | 97.8% | 0.0% |
| policy_beam_seed_mean | 18588.056373 | 13133.884310 | 180.0 | 46.156 | 99.4% | 0.0% |

- Policy-beam vs random: win fraction 100.0%; mean C2 change -92.90%.
- Policy-beam vs coordinate: win fraction 50.0%; mean C2 change 1.68%.
- Policy-beam vs one-evaluation hardware local-greedy: win fraction 50.0%.

## ood_edge_hotspot

| Method | Mean C2 | Median C2 | Mean native CX | Mean duration (us) | Hub-0 use | Two-flag use |
|---|---:|---:|---:|---:|---:|---:|
| reference | 23983.361789 | 19711.342447 | 189.6 | 46.811 | 100.0% | 0.0% |
| proxy_fixed | 15790.951220 | 14686.198213 | 189.6 | 46.939 | 66.7% | 0.0% |
| routing_heuristic | 18649.569358 | 12988.911170 | 187.2 | 46.049 | 66.7% | 0.0% |
| local_greedy | 13395.524934 | 10477.248543 | 190.8 | 47.264 | 61.7% | 0.0% |
| random_search | 33132.098950 | 23602.118727 | 248.4 | 61.863 | 50.0% | 30.0% |
| coordinate_search | 13124.373529 | 10246.917690 | 189.6 | 46.976 | 61.7% | 0.0% |
| policy_greedy_seed_mean | 15352.400339 | 12604.288157 | 189.2 | 46.984 | 56.1% | 0.0% |
| policy_beam_seed_mean | 12173.043317 | 10692.689392 | 188.0 | 46.683 | 57.2% | 0.0% |

- Policy-beam vs random: win fraction 100.0%; mean C2 change -63.26%.
- Policy-beam vs coordinate: win fraction 60.0%; mean C2 change -7.25%.
- Policy-beam vs one-evaluation hardware local-greedy: win fraction 60.0%.

## ood_slow_link

| Method | Mean C2 | Median C2 | Mean native CX | Mean duration (us) | Hub-0 use | Two-flag use |
|---|---:|---:|---:|---:|---:|---:|
| reference | 16788.061931 | 13195.611034 | 180.0 | 53.688 | 100.0% | 0.0% |
| proxy_fixed | 14555.346303 | 9590.495333 | 180.0 | 52.258 | 66.7% | 0.0% |
| routing_heuristic | 20659.642230 | 11007.759901 | 180.0 | 50.189 | 65.0% | 0.0% |
| local_greedy | 11617.965337 | 7559.950817 | 187.2 | 53.400 | 61.7% | 0.0% |
| random_search | 31879.437477 | 34578.270622 | 247.0 | 75.055 | 55.0% | 38.3% |
| coordinate_search | 11288.730856 | 7249.189432 | 186.0 | 52.868 | 60.0% | 0.0% |
| policy_greedy_seed_mean | 12765.013018 | 8826.187286 | 180.0 | 52.619 | 68.9% | 0.0% |
| policy_beam_seed_mean | 11586.980468 | 8063.353813 | 180.0 | 52.297 | 70.6% | 0.0% |

- Policy-beam vs random: win fraction 100.0%; mean C2 change -63.65%.
- Policy-beam vs coordinate: win fraction 20.0%; mean C2 change 2.64%.
- Policy-beam vs one-evaluation hardware local-greedy: win fraction 30.0%.

## ood_idle_hotspot

| Method | Mean C2 | Median C2 | Mean native CX | Mean duration (us) | Hub-0 use | Two-flag use |
|---|---:|---:|---:|---:|---:|---:|
| reference | 15532.132677 | 13599.775137 | 180.0 | 44.802 | 100.0% | 0.0% |
| proxy_fixed | 12325.629187 | 11964.153471 | 180.0 | 44.443 | 66.7% | 0.0% |
| routing_heuristic | 17331.248647 | 15960.789271 | 180.0 | 43.705 | 66.7% | 0.0% |
| local_greedy | 9477.773796 | 8953.476365 | 184.8 | 45.853 | 65.0% | 0.0% |
| random_search | 20093.916788 | 18682.180262 | 233.8 | 58.674 | 56.7% | 28.3% |
| coordinate_search | 9340.278682 | 8920.573481 | 184.8 | 45.853 | 65.0% | 0.0% |
| policy_greedy_seed_mean | 10787.052834 | 9628.494383 | 180.8 | 44.634 | 57.8% | 0.0% |
| policy_beam_seed_mean | 9574.996187 | 8516.011730 | 180.0 | 44.553 | 62.2% | 0.0% |

- Policy-beam vs random: win fraction 90.0%; mean C2 change -52.35%.
- Policy-beam vs coordinate: win fraction 30.0%; mean C2 change 2.51%.
- Policy-beam vs one-evaluation hardware local-greedy: win fraction 30.0%.

## ood_logical_shift

| Method | Mean C2 | Median C2 | Mean native CX | Mean duration (us) | Hub-0 use | Two-flag use |
|---|---:|---:|---:|---:|---:|---:|
| reference | 7291.948026 | 5146.823648 | 180.0 | 44.953 | 100.0% | 0.0% |
| proxy_fixed | 6385.688039 | 5346.873539 | 180.0 | 44.982 | 66.7% | 0.0% |
| routing_heuristic | 8549.980309 | 7882.086586 | 180.0 | 44.389 | 71.7% | 0.0% |
| local_greedy | 9999.735658 | 8210.442529 | 182.4 | 45.503 | 70.0% | 0.0% |
| random_search | 13537.861584 | 12332.809978 | 239.4 | 60.237 | 63.3% | 25.0% |
| coordinate_search | 7926.699583 | 6630.281121 | 181.2 | 45.275 | 71.7% | 0.0% |
| policy_greedy_seed_mean | 6845.228146 | 5701.168450 | 180.0 | 45.087 | 57.8% | 0.0% |
| policy_beam_seed_mean | 6179.561529 | 5449.150232 | 180.0 | 45.145 | 59.4% | 0.0% |

- Policy-beam vs random: win fraction 100.0%; mean C2 change -54.35%.
- Policy-beam vs coordinate: win fraction 60.0%; mean C2 change -22.04%.
- Policy-beam vs one-evaluation hardware local-greedy: win fraction 90.0%.

## ood_mixed

| Method | Mean C2 | Median C2 | Mean native CX | Mean duration (us) | Hub-0 use | Two-flag use |
|---|---:|---:|---:|---:|---:|---:|
| reference | 773331.151882 | 31128.289965 | 193.2 | 49.928 | 100.0% | 0.0% |
| proxy_fixed | 39012.406066 | 39575.038086 | 190.8 | 51.879 | 66.7% | 0.0% |
| routing_heuristic | 45520.071293 | 31403.074873 | 183.6 | 48.387 | 73.3% | 0.0% |
| local_greedy | 19738.738265 | 19808.088183 | 202.8 | 51.711 | 80.0% | 0.0% |
| random_search | 112144.355640 | 129931.804323 | 299.6 | 80.454 | 66.7% | 26.7% |
| coordinate_search | 19137.907897 | 19436.560340 | 202.8 | 51.711 | 80.0% | 0.0% |
| policy_greedy_seed_mean | 29116.156570 | 29297.224323 | 191.6 | 50.671 | 70.0% | 0.0% |
| policy_beam_seed_mean | 24420.949958 | 27070.604156 | 194.8 | 50.675 | 73.3% | 0.0% |

- Policy-beam vs random: win fraction 100.0%; mean C2 change -78.22%.
- Policy-beam vs coordinate: win fraction 40.0%; mean C2 change 27.61%.
- Policy-beam vs one-evaluation hardware local-greedy: win fraction 40.0%.

## Finite-p reduced hardware diagnostics

These use one predeclared `hw_id` context. The schedule is first converted to effective logical fault weights; the reduced logical Monte Carlo is then run.

| Method | p | failures/shots | logical failure rate | 95% interval | native CX | duration (us) |
|---|---:|---:|---:|---:|---:|---:|
| reference | 0.0002 | 18/40000 | 0.0004500 | [0.0002847, 0.0007113] | 180 | 44.570 |
| reference | 0.0005 | 99/40000 | 0.0024750 | [0.0020335, 0.0030120] | 180 | 44.570 |
| reference | 0.001 | 413/40000 | 0.0103250 | [0.0093803, 0.0113637] | 180 | 44.570 |
| routing_heuristic | 0.0002 | 19/40000 | 0.0004750 | [0.0003041, 0.0007418] | 180 | 43.767 |
| routing_heuristic | 0.0005 | 101/40000 | 0.0025250 | [0.0020787, 0.0030669] | 180 | 43.767 |
| routing_heuristic | 0.001 | 291/40000 | 0.0072750 | [0.0064882, 0.0081564] | 180 | 43.767 |
| local_greedy | 0.0002 | 4/40000 | 0.0001000 | [0.0000389, 0.0002571] | 192 | 46.390 |
| local_greedy | 0.0005 | 55/40000 | 0.0013750 | [0.0010566, 0.0017891] | 192 | 46.390 |
| local_greedy | 0.001 | 201/40000 | 0.0050250 | [0.0043780, 0.0057671] | 192 | 46.390 |
| random_search | 0.0002 | 24/40000 | 0.0006000 | [0.0004032, 0.0008927] | 220 | 52.891 |
| random_search | 0.0005 | 108/40000 | 0.0027000 | [0.0022370, 0.0032585] | 220 | 52.891 |
| random_search | 0.001 | 360/40000 | 0.0090000 | [0.0081205, 0.0099738] | 220 | 52.891 |
| coordinate_search | 0.0002 | 9/40000 | 0.0002250 | [0.0001184, 0.0004276] | 192 | 46.390 |
| coordinate_search | 0.0005 | 59/40000 | 0.0014750 | [0.0011438, 0.0019020] | 192 | 46.390 |
| coordinate_search | 0.001 | 214/40000 | 0.0053500 | [0.0046811, 0.0061139] | 192 | 46.390 |
| policy_beam | 0.0002 | 9/40000 | 0.0002250 | [0.0001184, 0.0004276] | 180 | 44.147 |
| policy_beam | 0.0005 | 51/40000 | 0.0012750 | [0.0009699, 0.0016758] | 180 | 44.147 |
| policy_beam | 0.001 | 227/40000 | 0.0056750 | [0.0049848, 0.0064601] | 180 | 44.147 |

## Interpretation constraints

- The 12-node graph and calibration families are synthetic controlled stress tests, not a named processor or measured backend.
- Remote logical CNOTs use a SWAP-forward / CNOT / SWAP-back count-and-duration model. Routing-gate faults are collapsed into effective logical-location weights rather than explicitly propagated gate by gate.
- Persistent data-qubit idle exposure is modeled approximately and folded into logical data-CNOT Pauli weights.
- Checks remain serialized in X0,X1,X2,Z0,Z1,Z2 order; Phase 5 adds placement/routing/timing context but not parallel scheduling.
- The decoder and ideal boundaries are inherited from Phase 4; this is still a one-round experiment, not repeated fault-tolerant memory.
- A positive learned-search result would motivate explicit native-circuit fault simulation and repeated rounds; it would not establish hardware advantage.

