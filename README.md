# TROPE

Reference implementation for **TROPE: Typed Representations and Operators for
Problem Editing in LLM Reasoning** (EMNLP 2026).

Inference-time methods vary the *output*. TROPE parses each problem into a typed
structural representation `R = (E, Rel, T, A, G, F)` and edits *that* before
generating: eleven operators across three levels (token noise, conceptual
mutation, conceptual crossover), with edit size drawn from a calibrated
heavy-tailed law, candidates scored by compression gain over an evidence corpus,
and survivors kept in a MAP-Elites archive. Every candidate is verified against
the **original** problem; the edited representation is a search hypothesis, never
a replacement task.

```
Problem ──► Parser Φ ──► R ──► operator o at radicality ρ ──► R′ ──► LLM ──► s
                                    ▲                                        │
                       π_θ, γ ──────┘            Nov(s|C), V_P(s) ──► archive
                                    └──────────── advantage ◄──────────┘
```

## Install

```bash
pip install -e .
```

The core runs on numpy and scipy alone, so the whole pipeline and the full test
suite work on a laptop with no GPU. Models are extras:

```bash
pip install -e ".[hf,encoder,analysis]"
```

## Run it offline

```bash
bash scripts/smoke.sh
```

That runs the test suite, then TROPE and five baselines on a synthetic dataset
through the deterministic mock backend, then calibration, the novelty null check
and the table builders. Two minutes, no downloads, no GPU.

The mock backend is a control-flow simulator, not a model: it is given the answer
key and decides whether a candidate solves the problem from a hidden condition on
the representation. It exists so that every branch of Algorithm 1 — parser
retries, well-formedness failures, novelty rejections, budget exhaustion — is
exercised in CI. Accuracy numbers produced against it mean nothing.

Individual commands:

```bash
python -m trope.cli run       --config configs/smoke.yaml --seeds 1,2,3,4,5
python -m trope.cli baseline  --config configs/smoke.yaml --name self_consistency
python -m trope.cli calibrate --config configs/smoke.yaml --n 1000
python -m trope.cli nullcheck --config configs/smoke.yaml --samples 200
python -m trope.cli tables    --runs runs/smoke --out runs/smoke/tables
python -m trope.cli info
```

## Run it on the paper's setup

`configs/paper.yaml` is the configuration of the paper: **Qwen2.5-7B-Instruct**
as the backbone, **Qwen2.5-3B-Instruct** as the reference LM,
`sentence-transformers/all-MiniLM-L6-v2` as the typed-feature encoder,
`K = 64`, five seeds. The cross-family reference LMs are
`meta-llama/Llama-3.2-3B-Instruct` and `mistralai/Mistral-7B-Instruct-v0.3`; the
backbone sweep is over size *classes*, so `scripts/run_sensitivity.sh` takes its
checkpoints from `BACKBONES_SMALL` and `BACKBONES_LARGE`. The `hf` backend writes
the resolved id, revision hash and parameter count into every run's
`manifest.json`.

The ten benchmarks are not redistributed here. Put them under `data/<benchmark>/`
or set `TROPE_DATA_DIR`; each loader names its upstream source and expected
filename when the data is missing. The full suite is roughly 480 A100-hours.

Each launch script writes run artifacts under `runs/`, and each builder reads
them:

| Paper object | Script | Builder |
| --- | --- | --- |
| main results (`tab:main`) | `scripts/run_main.sh` | `trope tables --which main` |
| full mean±SE and Wilcoxon (`tab:fullse`) | `scripts/run_main.sh` | `trope tables --which fullse` |
| operator-subset decomposition (`tab:decomp`) | `scripts/run_ablations.sh` | `trope tables --which decomposition` |
| consolidated ablation (`tab:ablation`) | `scripts/run_ablations.sh` | `trope tables --which ablation` |
| equal-total-compute control (`tab:equalcompute`) | `scripts/run_equalcompute.sh` | `trope tables --which equalcompute` |
| search trace (`tab:trace`) | any TROPE run (`trace.jsonl`) | `trope tables --which trace` |
| per-benchmark component ablation (`tab:componentfull`) | `scripts/run_ablations.sh` | `trope tables --which component` |
| leave-one-operator-out (`tab:loo`) | `scripts/run_ablations.sh` | `trope tables --which loo` |
| pair diagnostic (`tab:pairdiag`) | `scripts/run_ablations.sh` | `trope tables --which pairdiag` |
| operator commutativity (`tab:commute`) | `scripts/run_commutativity.sh` | `trope tables --which commute` |
| tail-index sweep (`tab:alphasweep`) | `scripts/run_sensitivity.sh` | `trope tables --which alpha` |
| reference-LM choice (`tab:lmrefsize`) | `scripts/run_sensitivity.sh` | `trope tables --which lmref` |
| sample-budget scaling (`tab:budget`) | `scripts/run_sensitivity.sh` | `trope tables --which budget` |
| novelty null check (`tab:nullcheck`) | `scripts/run_calibration.sh` | `trope nullcheck` |
| PI-controller band occupancy (`tab:band`) | any TROPE run | `trope tables --which band` |
| cost and overhead (`tab:cost`, `tab:overhead`) | `scripts/run_main.sh` | `trope tables --which cost` |
| operator usage by family (`tab:usage`) | `scripts/run_main.sh` | `trope tables --which usage` |
| §4.4 calibration figures | `scripts/run_calibration.sh` | `trope figures` |

The human audits — the semantic audit of 240 parser–edit pairs, the retrieval
audit of 320 passages and the novelty examples — are annotations, not
computations. `analysis/audit.py` draws the samples in the stratification the
paper reports and writes annotation sheets with blank columns, plus
`cohens_kappa` so the reported agreement is computed rather than asserted.

## What is where

| Paper | Code |
| --- | --- |
| Parser Φ, retry rule, fallback (§2.2, App. F) | `parser.py`, `validation.py`, `schemas/representation.json`, `prompts/parser.txt` |
| Eleven operators (§2.3, App. G) | `operators/{token,mutation,crossover}.py`, `prompts/operators/*.txt` |
| α-stable radicality, rejection (§2.4–2.5) | `sampling/{stable,rejection}.py` |
| Operator policy π_θ (Eq. 7) | `sampling/bandit.py` |
| PI controller, λ̂_struct (§2.6) | `control/{pi,divergence}.py` |
| Compression novelty (§2.7) | `novelty.py`, `corpus.py` |
| Archive, coverage (§2.8, Eq. 2) | `archive.py`, `descriptors.py` |
| Structural distance d_struct (Eq. 4) | `features.py`, `sinkhorn.py`, `distance.py` |
| Algorithm 1 | `search.py`, `pipeline.py` |
| Hill, KS, LR, Wilcoxon (App. J) | `stats/{hill,stablefit,gof,tests}.py` |
| Baselines (§4.1) | `baselines/`, `configs/decoding.yaml` |
| Tables and figures | `analysis/{tables,figures}.py` |
| Disciplinary similarity map (App. N) | `assets/frames.json`, `assets/disciplinary_similarity.json`, `scripts/build_assets.py` |

`config.py` holds the defaults, which are the paper's hyperparameter table;
`configs/default.yaml` mirrors them and a test holds the two together.
`pipeline.py` is the only place that turns configuration into constructor
arguments — every other module takes what it needs and reads no config of its
own.

## How the loop fits together

`search.run_search` is Algorithm 1 and nothing else: it owns the order the parts
fire in and the bookkeeping that makes a run auditable. One iteration is

1. draw an operator from `π_θ` over the catalog available to the run;
2. draw a radicality and apply the operator — the rejection loop of §2.5 works on
   *proposals*, so it applies the operator, measures `d_struct(R, o(R, ρ))` and
   tests that against the rolling window. An operator is a pure function of
   representations, so a rejected proposal costs no backbone call;
3. check well-formedness; a malformed `R_new` is discarded and does not consume
   one of the `K` samples;
4. generate from `R_new`, score `Nov(s|C)` against the evidence corpus and run
   the verifier against the **original** problem;
5. insert into the archive and the buffer on Algorithm 1's two gates,
   `Nov ≥ τ_Nov` and `V_P(s) > 0`;
6. update `π_θ` by Eq. (7), and every eight iterations re-estimate `λ̂_struct`
   from two parallel branches and feed the PI controller of Eq. (9).

Every step writes one JSONL record to `trace.jsonl`. Analysis code reads only
the documented fields, so new fields can be added but none may be renamed.

## Budget accounting

The paper's comparison is at *matched generator-backbone-call budget*, and the
code enforces it:

* only calls tagged `generator` count against `K`;
* parser calls, reference-LM scoring, the descriptor tagger and judge calls are
  metered under their own roles and reported separately, which is what the cost
  table shows;
* the divergence probe applies operators to representations only and never
  generates, so it costs nothing against `K`;
* the loop terminates on generator calls, because Algorithm 1's `continue` on a
  malformed `R_new` produces no sample and §4.1 defines `K` as generator calls;
* every run writes `ledger.json`, and the table builders refuse to put two arms
  in one comparison table when their generator totals disagree.

## Determinism

Every stochastic component draws from a named stream derived from the run seed by
a hash of its label, so streams are independent of call order and a loop whose
length varies — parser retries, rejection sampling — cannot shift any other
component's draws. Module-level `np.random`, the stdlib `random` module and
`hash()` are banned in `src/trope`, and `tests/test_determinism.py` greps for
them.

Bit-reproducible on the `mock` backend for a fixed platform and numpy version. On
`hf`, reproducible given the same GPU, driver and dtype — BLAS reduction order
varies across builds, so the claim is statistical rather than bit reproducibility.
On `vllm`, continuous batching means seeds do not determine the output at all.

## Baselines

Sixteen arms, registered in `baselines/registry.py` and reachable as
`trope baseline --name <arm>`: greedy; temperature at 0.7, 1.0 and 1.2; top-*p*;
min-*p*; top-*H*; η-sampling; self-consistency; Tree of Thoughts; Verbalized
Sampling; FunSearch; PromptBreeder; EvoPrompt; Eureka; Universe of Thoughts.
Decoding settings are in `configs/decoding.yaml`, and each arm's docstring states
what is faithful to its original paper, what is adapted and what is simplified.

Every backbone call an arm makes counts against `K`, including Tree-of-Thoughts
value estimates and the Verbalized Sampling and Universe of Thoughts judges;
verifier and judge calls made by `V_P` stay outside `K`, as they do for TROPE.
Two arms are task-restricted, matching the paper's "--" cells: FunSearch needs a
programmatic verifier, and Eureka needs an execution loop.

## Implementation notes

A few places where the code makes a choice the paper leaves open, worth knowing
before reading the source:

* **`Entity` carries `type` and `sort`.** `type` is the closed six-role
  vocabulary the parser schema validates; `sort` is the open domain label it
  cannot. The feature map of Eq. (4) embeds both, which is what makes the single
  node-name resampling that starts the two divergence branches visible to
  `d_struct`.
* **`Relation` carries an optional third argument.** The parser schema is binary;
  reification writes the ternary `relates(e_p, e_i, e_j)`. Everything that walks
  the graph reads `Relation.endpoints`, so the third argument counts toward
  degree, is pruned when it dangles and is matched by `isomorphism.py`.
* **The rolling window holds one entry per operator application.** An edit
  confined to `A`, `G` or `F` leaves `mu_R` fixed, so `d_struct` is exactly zero
  and no distance was produced; `R_new = R` still reaches the generator, because
  Algorithm 1 branches on well-formedness. Window entries are mapped through the
  folded stable CDF at the scale in force when they were recorded, because the
  controller moves `γ` between draws.
* **`d_struct` orders its arguments by fingerprint before solving.** A
  fixed-iteration Sinkhorn leaves the marginal updated last exact and the other
  approximate, so the value depends on argument order; ordering makes the
  distance a function of the unordered pair, which the pair cache and the pooled
  calibration sample both require.
* **`γ` is clamped to `[gamma_min, gamma_max]`.** `Stable(α, 0, γ, 0)` is
  undefined at `γ ≤ 0` and an unbounded `γ` runs away; `ControlStep.saturated`
  records every pinned step.
* **`NoveltyResult.value` is the per-token gain, `.gain` is Eq. (5) itself.**
  Eq. (5) is a difference of summed log-probabilities over the whole corpus,
  which `.gain` reports; `.value` divides it by the corpus token count, which is
  the scale the per-family `τ_Nov` thresholds of 0.3 to 0.6 live on and the scale
  the worked trace's `Nov = 1.84` is on. `novelty.normalise` also offers `total`
  and `compression`; the null check scores `total`, because the bound it tests is
  on the compression in nats and a clipped reading cannot falsify it.
* **`isomorphism.compare` answers True only when a bijection has been
  exhibited.** Colour refinement prunes the search but never decides it; a
  comparison that exhausts the assignment budget is reported `undecided` and
  counted against the commutativity rate rather than for it.
* **The composite creativity metrics are stand-ins.** NoveltyBench cumulative
  utility, CreativityPrism Q-N-D, UoT F-U-N and ResearchBench F1 are defined by
  their own benchmark implementations, so `verify/oracle.py` ships rubric-based
  stand-ins that return `meta["stand_in"] = True` and must be replaced with each
  benchmark's own scorer before any number is reported. LLM-SRBench symbolic
  accuracy is computed for real.

## Tests

```bash
python -m pytest -q
```

Everything runs offline. Tests that need an optional dependency are marked
`extras` and skip cleanly. Beyond unit tests, the suite pins the things that go
wrong quietly: the prompt files cannot drift from the schema or the operator
catalog, `configs/default.yaml` cannot drift from the dataclass defaults, the
budget is spent exactly, no-ops and well-formedness failures actually occur, and
verification never sees the edited representation.

## Citing

```bibtex
@inproceedings{bikbulatov2026trope,
  title     = {{TROPE}: Typed Representations and Operators for Problem Editing in {LLM} Reasoning},
  author    = {Bikbulatov, Vadim and Petrosian, Ovanes},
  booktitle = {Proceedings of the 2026 Conference on Empirical Methods in Natural Language Processing},
  year      = {2026},
}
```

## Licence

Apache-2.0. Benchmarks and model weights are not redistributed here; each is used
under its own licence.
