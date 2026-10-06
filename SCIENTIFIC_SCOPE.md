# Scientific contract and derivation

## 1. Purpose

This is a complete runnable *component-level* pilot in the QEC/circuit-design direction: train a contextual RL policy to select a gate order for one fault-checked flag measurement under known synthetic calibration information. It is deliberately not labeled a complete fault-tolerant quantum memory, logical-state-preparation protocol, or hardware experiment.

## 2. Code and qubit conventions

Data qubits are 0..6. Syndrome qubit s=7 and flag qubit f=8 are auxiliary. The Steane X generator supports are {0,1,2,3}, {0,1,4,5}, {0,2,4,6}; the three Z generators have identical supports. Logical X and Z act on all seven data qubits.

Pauli errors are stored in the integer x | (z << n). Bit q of x/z refers to qubit q. Local encodings are 0=I, 1=X, 2=Z, 3=Y. Global Pauli phases do not affect the error syndrome or logical-frame classification, so the binary propagation model ignores them. Independent ideal-instrument tests retain complex amplitudes. They do not forgive relative phases between logical inputs.

For a CNOT c->t, propagation obeys x_t <- x_t XOR x_c and z_c <- z_c XOR z_t. The test suite independently checks this with dense vectors and then cross-checks all enumerated fault records.

The stabilizer group has 64 elements. Two Pauli errors are equivalent on the code when their product is in that stabilizer group, up to global phase. Merely having the same syndrome is NOT sufficient: they may differ by a logical operation. The classifier checks the full stabilizer coset. Logical X with zero syndrome is a negative example in the tests.

## 3. Desired measurement

The measured check is S = Z0 Z1 Z2 Z3. For arbitrary states of the four active data qubits, the ideal instrument has

K[m,flag=0] = (I + (-1)^m S)/2,
K[m,flag=1] = 0.

The dense test checks each complete 16-column operator. Since the other three data qubits are untouched, this also applies when the active subsystem is entangled with them or an external reference.

Prepare s in |0>, f in |+>. Apply four data->s CNOTs and two f->s CNOTs. Measure s in Z and f in X. All CNOTs share a target and commute in the absence of faults, so all 360 arrangements implement the same ideal instrument. Errors inserted *between* gates can propagate differently despite that ideal equivalence.

## 4. Fault locations

For every six-CNOT candidate, enumerate 94 single-fault cases:

- one effective preparation error on |0>_s (X);
- one effective preparation error on |+>_f (Z);
- 15 nonidentity two-qubit Pauli alternatives after each of six CNOTs;
- one syndrome-readout bit flip and one flag-readout bit flip.

A Pauli preparation error that leaves the prepared state unchanged is physically irrelevant; the listed error represents the orthogonal erroneous preparation. Single-qubit basis rotations are treated as part of preparation/readout, not separately scheduled gates.

The suite also checks each of the 21 incoming single-qubit Pauli data errors with a fault-free gadget. It does not claim correction of an incoming error *plus* a circuit fault as a single-fault condition; that is a two-error event.

Idle errors, leakage, correlated faults between distinct locations, amplitude damping, and crosstalk are not included. The interaction graph is a directed star into s. No SWAP routing or hardware duration is modeled.

## 5. Acceptance conditions

Every candidate must implement the ideal instrument. For every enumerated single fault producing data error E, an unraised flag is allowed only when min(weight(E), weight(E*S)) <= 1. This is the measured-stabilizer-modulo version of a one-flag condition.

A second condition checks correction using the flag and a *hypothetical perfect final full syndrome*. A deterministic recovery table is built from no error, all incoming single data errors, and every candidate's single circuit-fault outcome. Two outcomes with the same observation (flag, final syndrome) must not demand incompatible stabilizer cosets. Conflicts reject the candidate.

Unobserved syndrome/flag entries fall back to a deterministic minimum-weight Pauli decoder; ties use the smallest Pauli integer. This decoder is fixed before noise contexts are drawn. It is not retuned to test outcomes or to the two-fault distribution.

Exactly 96 of the 360 candidates satisfy these tests. The reference 0F12F3 passes. A bare measurement and the misplaced schedule 0F1F23 fail. These statements are exhaustive for this specified candidate/fault family, not universal fault-tolerance theorems.

## 6. Why a perfect final recovery is included

After the noisy check, the diagnostic is given an exact six-bit Steane syndrome and applies a noiseless flag-conditioned Pauli correction. The corrected residual always has zero syndrome. A nontrivial stabilizer coset then means a logical Pauli failure on an arbitrary unknown encoded logical state.

This oracle is an analysis device. Its measurements and corrections have no gate cost and no faults in this experiment. The noisy syndrome bit produced by the gadget is not used by it. Therefore the experiment does NOT implement or certify an adaptive noisy full-QEC protocol. Building such a protocol requires specifying repeated syndrome extraction, decoder behavior, control flow, and faults in all additional operations.

The flag is not a discard signal in this diagnostic. All shots are retained and recovered; there is no postselection advantage.

## 7. Noise contexts and C2

A calibration context is a nonnegative vector of 79 category weights:

- two preparation weights;
- five directed edges (data0..3->s and f->s), each with 15 Pauli weights;
- two readout weights.

For base scale p, a physical location has error probability p times the sum of its category weights. If faulty, it chooses one of its Pauli alternatives accordingly. Alternatives at a single location are mutually exclusive. The two appearances of the flag CNOT use the same calibration weights but independent fault draws.

Rates and Pauli probabilities are synthetic. Training rates use clipped log-normal variation and Pauli mixtures use a Dirichlet distribution. Shifted tests broaden both. No parameters are claimed to be measured device calibrations.

For certified circuits, every single-location fault is corrected in the diagnostic. Let M be the set of pairs of fault alternatives at *different* locations that yield a logical failure. Then

C2(w) = sum_(i,j in M, i<j) w_i w_j,
p_L(p,w) = C2(w)*p^2 + O(p^3).

The implementation sums all relevant pairs exactly and stores the quadratic form. A same-location pair is excluded because a gate cannot simultaneously draw two different alternatives in this model. This distinction has a dedicated test.

C2 is dimensionless but is NOT a probability. For finite p, the O(p^3) terms and the no-fault probabilities of other locations matter. The noisy sampler tests the full specified independent-location model, including any number of faulty locations. `low_order_bounds` computes the exact <=2-location failure contribution and bounds all remaining failures by the probability of >=3 faulty locations.

## 8. Learning contract

The observation is calibration information only. The action is one certified schedule. The return is based on its C2 relative to a fixed reference schedule. This is a one-step contextual bandit trained with REINFORCE, not PPO or a sequential circuit-construction policy.

The network has 79 log-transformed, train-standardized features, one tanh hidden layer, and 96 softmax outputs. Adam and gradient clipping are implemented directly in NumPy. Gradient tests use finite differences. A reference-circuit control variate requires a second reward evaluation per training context; both evaluation counts are recorded.

Training gets sampled-action rewards and the reference value, not argmin labels. Validation minima are used only for checkpoint selection. The scaler and best-constant baseline use only training data. Test and shifted-test sets are not used to select checkpoints.

## 9. Fair comparisons and limits

The same certified library and risk model are available to every method. Best-fixed is a strong constant baseline fitted offline. Greedy and random search each have a 16-candidate budget. Exhaustive selection evaluates all 96 and is the exact finite-library bound. Model training and library construction are not free, even when a policy chooses one circuit at deployment.

This candidate library is small enough for exact search to be cheap. A learned policy can show conditional decision learning and a quality-versus-online-search-budget tradeoff; that alone is not a practical advantage, novel circuit discovery, or fault-tolerant hardware result. Future claims require a larger independent benchmark and full cost accounting.
