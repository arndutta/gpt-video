# Evaluation-only threshold study — 2026-11-10

## Fresh objective comparison — 2026-11-14 (Asia/Kolkata)

The expanded study now covers balanced, revenue-weighted and margin-weighted objectives
on fresh November 14 fixtures, seeds 42 and 43, 500 SKUs each, 180 historical days,
1,000 draws and a 14-day horizon. All six cases model 500/500 SKUs without skips.
The 36 threshold combinations per case produce **216 rows**, with zero compliance
violations. The report is `data/calibration_objectives_20261114_result.json`.

```sh
.venv/bin/python -m scripts.calibrate --as-of 2026-11-14 \
  --objectives balanced revenue margin --output data/calibration_objectives_20261114_result.json
```

| Objective | Forecast revenue vs baseline, seeds 42 / 43 | High-confidence prices within 10%, seeds 42 / 43 | Default predicted Auto counts, seeds 42 / 43 |
|---|---:|---:|---:|
| Balanced | -6.309% / -6.986% | 411/420 / 400/409 | 14 / 10 |
| Revenue-weighted | -2.845% / -3.119% | 392/396 / 391/393 | 11 / 8 |
| Margin-weighted | -12.136% / -12.553% | 451/461 / 436/452 | 42 / 27 |

All six cases improve forecast gross profit and margin rate over their baseline. All
six fail the unchanged +5% revenue and all-high-confidence-prices-within-10% targets.
The largest predicted Auto share across the study is 19%; snapshot eligibility is not
an observed Assisted execution rate. Even the default margin-objective Auto subsets
contain two price errors out of 42 and one out of 27, respectively.

No default, production policy, price constraint, baseline, target or confidence denominator
was changed. This adds objective sensitivity evidence; it does not close calibration
or business-effectiveness acceptance. Human approval/escalation labels, complete mature
daily aggregate sales at applied prices, multiple disjoint outcome windows, and an owner
decision about the revenue evaluation envelope remain necessary.

## Historical balanced-objective study

This is the historical study before `confidence-v2-selection`. Its observations are
retained rather than rewritten. The current [decision-uncertainty and feasibility
review](effectiveness-feasibility.md) records the corrected model and explicitly dated
coverage; rerunning this script now uses that current implementation and actual
freshness clock.

No new default is selected. This study does not update the running application's
policy, approvals, recommendations, Commerce prices or data. It evaluates a fixed
set of computed recommendations against held-out synthetic truth and varies only
the eligibility thresholds used to predict bands. No LLM is called.

```sh
.venv/bin/python -m scripts.calibrate --as-of 2026-11-09
```

The measured default study uses independent seeds **42 and 43**, each with 500 SKUs
in one Beverages category, 180 historical days, 1,000 Monte Carlo iterations, a
14-day horizon and the balanced objective. Seed 42 is the development fixture;
seed 43 is an independent comparison from the same generator, not a real-market
holdout. Each fixture is generated in a temporary Commerce database and read over
the HTTP adapter. Only the evaluator reads hidden generator truth.

The full local report is `data/calibration_result.json`: 36 threshold combinations
per seed, 72 rows total, with explicit denominators, price-error counts, predicted
band shares, compliance counts and escalation causes. The script also supports
`--objectives balanced revenue margin` for a broader objective study; that expanded
study was not part of this bounded measurement. `--objectives revenue` or `margin`
runs one alternative without changing production defaults.

The confidence grid is 0.8/0.85/0.9/0.95 (strictly greater than the threshold), the
absolute-delta grid is 3%/5%/10%, and the revenue coefficient-of-variation grid is
0.2/0.35/0.5. MAP, margin, maximum-change and ladder constraints remain enforced.
The margin headroom buffer 0.03, sample minimum 60, market-gap norm 30%, damping
fraction 0.35, oscillation window 8 and reversal threshold 2 remain unchanged.
Proposed prices are not re-optimized when band thresholds change.

## Default snapshot results

| Measurement | Seed 42 | Seed 43 |
|---|---:|---:|
| Modeled / input SKUs | 500 / 500 | 500 / 500 |
| Numerical analysis time | 3.246 s | 3.067 s |
| Forecast revenue versus conventional baseline | **-7.052%** | **-7.683%** |
| Forecast gross-profit gain versus baseline | $1,282,492 | $1,328,834 |
| Forecast margin-rate gain versus baseline | 17.351 pp | 17.930 pp |
| High-confidence prices within 10% of held-out optimum | **466 / 500** | **466 / 500** |
| Mean / maximum price error | 2.070% / 22.923% | 2.221% / 37.197% |
| Predicted Auto / Review / Escalate counts | 43 / 443 / 14 | 36 / 456 / 8 |
| Predicted Auto share | 8.6% | 7.2% |
| Predicted Auto prices within 10% of optimum | 28 / 43 | 26 / 36 |
| Compliance-violating recommendations | 0 | 0 |

The ≥5% revenue-uplift target fails on both balanced-objective fixtures. Gross profit
and margin rate improve. The all-high-confidence-prices-within-10% interpretation
also fails: 34 eligible SKUs exceed the error bound in each seed. All denominators
include those errors. Clean compliance does not imply a calibrated confidence score
or a price close to the evaluator's optimum.

Predicted Auto eligibility is a snapshot of deterministic band logic. It is not a
measurement of Assisted execution, human acceptance or future realized outcomes.
In Supervised mode every clean eligible item still requires human review.

## Confidence and coverage tradeoff

At the default 5% delta and 0.35 volatility limits:

| Confidence threshold | Seed 42 eligible / modeled | Seed 43 eligible / modeled | Price errors over 10% in eligible set |
|---|---:|---:|---|
| >0.80 | 500 / 500 | 500 / 500 | 34 / 500 and 34 / 500 |
| >0.85 | 1 / 500 | 0 / 500 | 0 / 1 and unobserved |
| >0.90 | 0 / 500 | 0 / 500 | Unobserved for both |
| >0.95 | 0 / 500 | 0 / 500 | Unobserved for both |

The single qualifying seed-42 item above 0.85 has zero theoretical price error,
but only 0.2% coverage and no qualifying counterpart in seed 43. This does not
establish a successful product threshold. Empty sets have null accuracy rather
than a fabricated 100% score. Predicted Auto eligibility falls to zero in both
seeds for all three higher confidence cutoffs.

## Delta and volatility tradeoffs

At confidence >0.8 and volatility ≤0.35:

| Maximum absolute delta | Seed 42 predicted Auto | Seed 43 predicted Auto | Predicted Auto within 10% of optimum, seed 42 / seed 43 |
|---|---:|---:|---|
| 3% | 25 / 500 = 5.0% | 23 / 500 = 4.6% | 14 / 25 and 15 / 23 |
| 5% | 43 / 500 = 8.6% | 36 / 500 = 7.2% | 28 / 43 and 26 / 36 |
| 10% | 103 / 500 = 20.6% | 90 / 500 = 18.0% | 82 / 103 and 71 / 90 |

A larger automatic delta limit admits more proposals. It neither repairs the
underlying confidence/price-error relationship nor demonstrates the operational
60% Assisted automatic-share target. The predicted Auto subsets still contain
theoretical price errors above 10% at every studied delta limit.

Changing the volatility threshold between 0.2, 0.35 and 0.5 did not change bands in
these two fixtures. All observed escalations were driven by the configured market-gap
norm: 14 SKUs in seed 42 and 8 in seed 43. That norm remains an initial trial
threshold, not a measured distribution of unprecedented market conditions.
No human labels exist to assess escalation precision.

Across all 72 rows, there were zero compliance-violating recommendations and zero
compliance violations among predicted Auto items. This is evidence for these
snapshots, alongside the separate adversarial rule tests; it is not a guarantee
about unobserved data. The empty price history cannot measure longitudinal
oscillation, damping efficacy or error convergence.

The result supports keeping calibration acceptance open. Broader category and
outcome fixtures, labeled escalations, and evidence that confidence predicts price
error are still needed. No compliance gate was weakened, uncertainty interval
forced narrower, confidence denominator hidden, or default silently changed.
