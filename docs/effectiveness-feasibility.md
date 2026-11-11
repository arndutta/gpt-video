# Effectiveness feasibility and decision uncertainty — 2026-11-11

The unchanged revenue target cannot be achieved on either recorded 500-SKU fixture
at the recorded **14-day horizon** under its existing legal price bounds. This is an upper-bound result, not an excuse
to weaken rules or substitute a more convenient denominator. No PRD requirement,
baseline, band threshold, fixture seed or evaluator-truth assumption was changed.

```sh
.venv/bin/python -m scripts.effectiveness_feasibility --as-of 2026-11-09
.venv/bin/python -m scripts.calibrate --as-of 2026-11-09 \
  --output data/calibration_selection_result.json
```

These evaluation-only scripts generate temporary Commerce databases for independent
seeds 42 and 43, each with 500 Beverages SKUs and 180 historical days. Inputs are read
over HTTP; only the evaluator reads hidden generator truth. The 14-day forecasts use
1,000 samples and the unchanged balanced objective. They never write to the running
application or apply an analytical counterfactual to production.

## Revenue ceilings

For a SKU with current price `p0`, known evaluator elasticity `e0`, baseline demand
`q0`, latest seasonal index `s`, horizon `H`, stock `I`, and candidate price `p`, the
existing evaluator's expected revenue is:

`r(p) = p × min(q0 × s × H × (p / p0)^(e0 + 0.06), I)`.

The +0.06 term preserves the existing explicit competitor follow-through assumption.
The legal continuous interval retains MAP, category bounds, margin floor and maximum
change limits. The bound relaxes price ticks, the candidate grid, family ordering and
the requirement to preserve aggregate margin relative to the baseline.

Below the stock cap, revenue is a power of price; at the cap it is linear. On each
side of the stock crossing it is monotone or constant, so the maximum lies at a legal
endpoint or at the crossing. The script evaluates those points. Summing independent
SKU maxima bounds every family-constrained legal policy because it relaxes constraints.
Dense exhaustive-grid tests check the endpoint/crossing algorithm for positive,
negative and zero effective demand exponents and different stock levels.

A separate forecast bound uses the actual fitted Monte Carlo draws: maximize expected
revenue over each SKU's existing legal candidate grid, then sum. This likewise relaxes
family constraints and ignores any additional aggregate-profit-preservation requirement.
It is an upper bound for the implemented grid and fixed recorded sample realization.

| Upper-bound uplift against the **unchanged raw cost-plus baseline** | Seed 42 | Seed 43 |
|---|---:|---:|
| Fitted Monte Carlo grid, family relaxed | **-2.951%** | **-3.269%** |
| Evaluator truth, continuous prices, family/ticks relaxed | **-2.626%** | **-3.339%** |
| Required revenue uplift | +5% | +5% |

Even the relaxed maxima fall below the baseline. Requiring no margin degradation,
restoring family ordering or enforcing ticks cannot increase these ceilings. Increasing
Monte Carlo iterations, changing confidence eligibility or choosing a better optimizer
cannot bridge this structural gap on these fixtures.

The raw conventional baseline remains a disclosed forecast comparison, not an approved
price. Its independent platform rule failures are:

| Rule | Seed 42 violating SKUs | Seed 43 violating SKUs |
|---|---:|---:|
| MAP floor | 307 | 316 |
| Maximum price change | 423 | 421 |
| Category lower bound | 197 | 197 |

Counts overlap. Those baseline violations are **not** violations by proposed prices.
The optimizer and execution paths continue to enforce all existing rules.

## Legal-baseline counterfactual does not solve the target

For diagnosis only, the script projects each raw cost-plus price onto the existing
feasible grid while preserving the joint family ladder. It minimizes summed squared
relative distance from the raw baseline. This projection has zero rule violations.
It is labeled an analytical counterfactual and does not replace the production baseline.

The script then maximizes **pure aggregate forecast revenue** on that same grid with
the real family constraints. This is more permissive than the balanced objective.

| Against projected legal cost-plus counterfactual | Seed 42 | Seed 43 |
|---|---:|---:|
| Maximum family-constrained grid revenue uplift | **2.494%** | **2.195%** |
| Margin-rate difference at that maximum | +3.246 pp | +3.207 pp |

A fair-baseline projection alone therefore still cannot meet +5%. No baseline amendment
has been requested or silently applied. Satisfying the current acceptance gate requires
an explicit product-owner decision about the target, feasible operating envelope or
evaluation evidence; code cannot honestly mark it achieved using these fixtures.

## Price-error diagnosis

| Measurement over all 500 SKUs | Seed 42 | Seed 43 |
|---|---:|---:|
| Fitted elasticity RMSE versus held-out truth | 0.108 | 0.104 |
| Coverage of nominal 95% elasticity interval | 95.6% | 96.0% |
| Demand mean absolute percentage error | 0.780% | 0.787% |
| Original Monte Carlo prices over 10% from theoretical optimum | 34 / 500 | 34 / 500 |
| Plug-in point optimizer prices over 10% from optimum | 35 / 500 | 34 / 500 |
| Monte Carlo versus plug-in price differences over 10% | 0 / 500 | 0 / 500 |

The measurements do not demonstrate an OLS or Monte Carlo arithmetic defect. Small
elasticity estimation errors can move the argmax substantially when the weighted
objective is flat. For families containing a price error above 10%, the median loss
of the exact evaluator's normalized balanced objective is only 0.358% / 0.521%; the
maximum is 1.029% / 1.811%. This explains sensitivity, but does not redefine the
price-accuracy target or declare the errors acceptable.

The demonstrated implementation gap was confidence: the old score used elasticity
precision and forecast variance but ignored how uncertain the **selected price** was.

## Corrected decision-precision evidence

`joint-price-selection-v1` re-optimizes each existing simulated sample column using
the same objective normalization and family constraints, including unchanged siblings.
It emits the selected price's simulated probability, a 95% argmax price range and its
relative width. The expected-objective selected price remains unchanged.

`confidence-v2-selection` caps the former heuristic score at
`1 / (1 + argmax_interval_width / selected_price)`. This dimensionless precision cap
does not use held-out truth, the 10% target, a changed confidence threshold or a price
accuracy label. It is explicitly not a probability of true price accuracy or an
empirically calibrated coverage guarantee. Arbitrary what-if candidates retain their
forecast score and explicitly state that optimizer decision precision was not evaluated.

| Result after the correction | Seed 42 | Seed 43 |
|---|---:|---:|
| **All modeled prices within 10%** | **466 / 500** | **466 / 500** |
| Confidence >0.8 coverage, November 11 | 414 / 500 | 405 / 500 |
| Within 10% among that high-confidence set | 405 / 414 | 396 / 405 |
| High-confidence errors still over 10% | **9 / 414** | **9 / 405** |
| Predicted Auto-eligible SKUs in the earlier November 10 study | 10 / 500 | 7 / 500 |
| Predicted Auto prices within 10% in that earlier study | 10 / 10 | 7 / 7 |

No SKU was dropped and no proposed price, revenue forecast or baseline changed. The
all-SKU denominator remains 500. The all-high-confidence price target still fails,
and a better conditional percentage is not presented as target achievement. Smaller
automatic eligibility is the consequence of acknowledging uncertainty, not an observed
Assisted execution rate or a new automatic-share achievement.

This November 11 proof reran the unchanged November 9 fixtures. Source age is part
of confidence: competitor freshness decays against the actual UTC evaluation date.
The earlier November 10 confidence coverage was 416/500 and 412/500, with the same
nine errors in each high-confidence set. No clock was frozen and no freshness check
was bypassed to recover a preferred score. Both reports retain the actual evaluation
timestamp; all-SKU price errors, forecasts and upper bounds are unchanged.

The remaining price errors include ordinary finite-sample uncertainty: a nominal 95%
parameter interval does not contain every true value in 500 independent products.
Additional evidence and an explicit acceptance decision remain necessary. Realized
coverage, convergence, human acceptance and escalation precision are still unobserved.
