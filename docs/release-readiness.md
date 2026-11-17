# Release readiness decision packet — 2026-11-17

**Current decision: the owner approved a limited engineering demonstration on
2026-11-17 (Asia/Kolkata); business KPI gates remain open. Full PRD acceptance is
not established.** Desktop Chromium acceptance now passes; native Windows technical
checks are being rerun after a portable test-loader fix.

This packet records measured results and the owner's explicit scope decision. It
does not approve a full PRD release, amend the PRD, change the baseline or select new
policy defaults. The original [success measures](../requirement.md#5-success-measures-and-release-evidence)
and [T46/T47 gates](../task.md#t46--benchmark-calibrate-and-report-product-effectiveness-m)
remain authoritative. Browser and Windows evidence is maintained separately; later
results there cannot supply missing human labels or post-push sales.

## Recorded owner decision

| Option | Concrete meaning | Consequence for acceptance |
|---|---|---|
| A — Retain the current full-release requirements | Keep the existing targets and collect the missing observations; investigate the failed effectiveness results within the existing rules. | Full release remains pending. The +5% revenue gate cannot pass on the two current fixtures, even with a better legal optimizer. |
| **B — Limited engineering demonstration: selected** | Authorize a demonstration of implemented behavior with the exact measured failures and unobserved metrics below disclosed. | Approval applies to the limited demonstration only. It does not complete T46, establish business effectiveness, or satisfy a full PRD release. Any cut to a must-have requirement requires an explicit PRD amendment. |
| C — Authorize an evaluation change request | Review the revenue baseline's legality, target feasibility and intended operating envelope, then approve an explicit written amendment before changing acceptance. Predeclare any revised metric, fixture envelope, denominator, holdout and observation plan. | No automatic pass follows. The unchanged results remain historical evidence; an amended evaluation needs new independent measurements. A projected legal baseline by itself still cannot reach +5% on these fixtures. |

Owner-selected option: **B — limited engineering demonstration**. Decision owner:
**project owner/user in this session**. Decision date: **2026-11-17, Asia/Kolkata**.
The explicit instruction was: **“Approve a limited engineering demo; keep business
KPI gates open”.** Approval covers the engineering demonstration with the measured
failures, fixture limitations and missing observations in this packet disclosed.
Browser and native Windows technical checks remain in progress at this update;
approval does not substitute for their results. No baseline/target amendment or
price-write authorization is inferred from this scope approval.

## Fresh isolated effectiveness measurements

Both commands completed on November 17 using temporary Commerce databases, with no
model calls, running-application writes, approvals or price pushes:

```sh
.venv/bin/python -m scripts.calibrate --as-of 2026-11-17 \
  --objectives balanced revenue margin \
  --output data/calibration_objectives_20261117_result.json
.venv/bin/python -m scripts.effectiveness_feasibility --as-of 2026-11-17 \
  --output data/effectiveness_feasibility_20261117_result.json
```

The calibration study covers seeds 42 and 43, each with 500 Beverages SKUs and 180
historical days, three objectives, 1,000 Monte Carlo draws and a 14-day horizon.
All six cases model **500/500 SKUs**, with no skips. Four confidence thresholds,
three delta thresholds and three volatility thresholds give **216 rows**. Every
row retains zero compliance violations among recommendations and predicted Auto
items. Seed 43 is an independent same-generator comparison, not real-market evidence.

| Objective | Forecast revenue uplift vs unchanged baseline, seed 42 / 43 | High-confidence prices within 10%, seed 42 / 43 | Default predicted Auto count, seed 42 / 43 |
|---|---:|---:|---:|
| Balanced | **−6.909% / −7.544%** | **410/419 / 402/412** | 11/500 / 9/500 |
| Revenue | **−3.412% / −3.642%** | **389/393 / 389/391** | 6/500 / 5/500 |
| Margin | **−12.803% / −13.167%** | **453/463 / 435/450** | 39/500 / 27/500 |

The high-confidence definition remains strictly **confidence >0.8**. The requirement
is that each high-confidence price be within 10% of the evaluator's optimum; it is
not satisfied by reporting a favorable average or removing the errors. All six
cases fail that requirement and the ≥5% forecast revenue-uplift requirement. All
six improve forecast gross profit and margin rate against the unchanged baseline.
Those improvements satisfy only the measured no-degradation comparison, not the
combined revenue-and-margin target.

Default margin-objective predicted Auto subsets include **3/39** and **1/27** price
errors over 10%. The largest predicted Auto share anywhere in the 216 rows is
**95/500 = 19%**. Snapshot band eligibility does not measure actual Assisted automatic
execution, human approval or escalation precision. Raising eligibility would not
prove those measures and no threshold was changed.

Recorded hardware: Apple M1, 8 logical CPUs, 8 GiB RAM, macOS 15.6.1 arm64,
Python 3.11.5, Node v24.4.1, NumPy 2.4.6 and SciPy 1.17.1. Numerical analysis takes
**1.443–1.617 seconds per case** in this study; this is not full grounded workflow
latency. Competitor freshness uses the actual UTC evaluation date. The as-of date
controls freshly generated history; no evaluation clock is frozen.

### The revenue failure has a demonstrated feasibility limit

The existing [bound derivation](effectiveness-feasibility.md#revenue-ceilings) is
rerun on the fresh November 17 fixtures. The fitted-grid bound independently
maximizes revenue for each SKU and relaxes family constraints; the truth-based
continuous bound additionally relaxes tick/grid constraints. Both retain legal
per-SKU price bounds. Relaxation can only raise the achievable maximum.

| Revenue uplift ceiling vs original raw baseline | Seed 42 | Seed 43 |
|---|---:|---:|
| Fitted Monte Carlo candidate-grid maximum, family relaxed | **−2.803%** | **−3.122%** |
| Held-out truth, continuous legal prices, family/ticks relaxed | **−2.447%** | **−3.183%** |
| Unchanged target | +5% | +5% |

Restoring family order, tick rounding or no-margin-degradation requirements cannot
increase these upper bounds. More draws, higher confidence thresholds or a better
optimizer cannot close this structural gap on these recorded fixtures and horizon.

The raw baseline is a comparison forecast, not an approved executable price. It
violates MAP on **307/500 and 316/500** SKUs, maximum change on **423/500 and 421/500**,
and category bounds on **197/500 in each seed**; these overlapping counts are baseline
failures, not recommendation failures. An analytical projection onto the existing
legal grid and joint family ladder has zero rule failures. Even maximizing pure
revenue against that projected counterfactual permits only **+2.559% / +2.240%**.
It remains an analytical counterfactual and has not replaced the product baseline.

All-SKU balanced price accuracy is **464/500 and 465/500** within 10% of held-out
truth. Elasticity RMSE is **0.1084 / 0.1047**, nominal 95% elasticity interval coverage
is **95.4% / 95.6%**, and demand MAPE is **0.725% / 0.698%**. These are synthetic
parameter/decision diagnostics, not mature forecast-interval coverage. They do not
resolve the high-confidence errors or establish future market accuracy.

### Policy remains unchanged

The studied default policy is confidence/bulk confidence 0.8, absolute Auto delta
5%, revenue coefficient of variation 0.35, margin buffer 0.03, market gap 30%, sample
minimum 60, oscillation window 8, reversal threshold 2, damping fraction 0.35,
minimum-change interval 0s, anomaly z threshold 4 and hold 60s. Product-level MAP,
margin, bounds, family ladder and tick constraints retain veto. No new defaults,
iteration count, fixture, hidden truth, objective definition or baseline was selected
to obtain a passing result. Longitudinal tuning still needs longitudinal evidence.

## Installed SQLite observation audit

The read-only audit at **2026-11-17 01:54:39 UTC** uses `mode=ro`,
`PRAGMA query_only=ON` and an explicit read transaction for each database. The result
is `data/effectiveness_sqlite_audit_20261117_result.json`. Quick integrity checks are
`ok` for Commerce, app, market, cache and RAG. Their individual transactions are
consistent snapshots; this is not a cross-database atomic snapshot.

| Installed evidence | Observed count | What it establishes |
|---|---:|---|
| Commerce products / price rows | 500 / 500 | A populated synthetic catalog exists. |
| Commerce sales rows / historical dates | 90,000 / 180 | Seed history spans May 13–November 8; it does not contain confirmed post-push outcomes. |
| Commerce price history / batches | **0 / 0** | There are no installed applied-price observations to evaluate. |
| App recommendation revisions / state rows / outbox rows | **0 / 0 / 0** | No installed review or dispatch cohort exists. |
| Human approve/reject/override/bulk decision events | **0** | Approval-without-override acceptance has denominator zero. |
| Explicit human judgments that an escalation was necessary | **0** | Escalation precision has denominator zero. |
| Realized outcome rows / observed SKU-days / learning versions | **0 / 0 / 0** | Mature coverage, error convergence and learned calibration remain unobserved. |
| Loop sessions / iterations | **0 / 0** | No installed consecutive-run stability cohort exists. |
| LLM usage / saved responses / cache hits / cache misses | **0 / 0 / 0 / 0** | Installed operational validity and cache rate cannot be inferred. |
| Completed runs | 10 | All are preview requests; they create no recommendation/review cohort. |
| RAG chunks / versions / active documents | 4 / 2 / 2 | Grounding content is retained in SQLite. |

The installed global mode is **Supervised**, policy version 1. Human audit events
that do exist are 10 preview requests and four queued grounding uploads; these
must not be counted as pricing approvals or escalation labels. Existing export and
migration checks are described in [SQLite storage](sqlite.md); successful storage
does not manufacture observation denominators.

## What observations can close each effectiveness gate

| Gate | Available result | Evidence still required |
|---|---|---|
| ≥5% forecast uplift, no margin degradation | Revenue fails all six fresh objective cases; profit and margin improve. Legal upper bounds prove +5% infeasible on both recorded fixtures. | Owner decision on the current evaluation conflict, followed by evidence against the unchanged requirements or an explicit approved amendment. |
| Every high-confidence price within 10% of truth optimum | Fails all six cases, with all denominators retained. | A defensible improvement validated against independent hidden truth; no threshold selected from this study can be claimed empirically calibrated. |
| ≥70% approved without override | Unobserved, **0 human pricing decisions**. | Genuine human approve/reject/override decisions on a predeclared review cohort, linked to immutable item/revision evidence; report numerator, denominator and unresolved items. |
| ≥60% automatically handled in Assisted mode | Unobserved operational rate; maximum studied eligibility is 19%. | Actual Assisted decision/execution audit on a declared SKU cohort, including rejected, pending, no-change and human-intervened items. No developer impersonation of a reviewer. |
| ≥80% escalation precision | Unobserved, **0 necessity judgments**. | Humans must explicitly judge whether each escalation needed escalation, linked to the original item/revision and risk evidence. Approving or rejecting its price is not that judgment. The current schema has no dedicated necessity-label field; an owner-reviewed linked label register/import is needed before measurement. |
| ≥80% realized interval coverage | Unobserved, **0 mature outcomes**. | Complete daily aggregate Commerce sales over each applied revision's full horizon at its applied price; no missing-day-as-zero or fixture-clock substitution. |
| <2% oscillating SKUs | Unobserved, **0 applied price histories / consecutive run cohort**. | Actual consecutive-run/applied-price history with a declared eligible SKU denominator and the unchanged configured detector/window. Zero history is insufficient evidence of stability. |
| Narrowing forecast error | Unobserved, **0 learned observations**. | Multiple complete disjoint outcome windows per SKU; show the actual error series, observation counts and trend rather than assuming every update improves performance. |
| ≥40% repeated-run cache rate | November 17 SQLite benchmark gives 20/21 = 95.24% including one cold miss; the separate warmed sample gives 200/200 hits. Installed operational denominator is zero. | Representative repeated real workflow requests with the same invalidation rules and explicit hits/misses, workload and coverage. Deliberately warmed equivalent contexts establish cache mechanics only. |
| ≥99% valid structured outputs after repair; valid citations | A real one-SKU workflow reaches review with a valid citation, seven native requests and two repair events. | A predeclared sufficiently sized real request series including final failures and retries; report per-logical-request validity separately from provider-call success. A single completed workflow does not establish a population rate. |

The [feedback collector](../platform_app/feedback.py) starts observation on the UTC
day after application and requires one row per day for the whole horizon, at the
applied price. An intervening price excludes the window; missing sales leave it
pending; overlapping SKU-days are not counted twice. For an actual November 17
push at a 14-day horizon, the earliest first mature window is November 18 through
December 1, observable on December 2, provided all required sales exist. No such
push is authorized or performed by this audit.

Learning calibration requires at least **three disjoint observations and 30 observed
days**; at the 14-day horizon that is at least 42 observed days. Stability convergence
classification requires **six error observations**, comparing the latest three with
the preceding three. These are implementation minimums, not a statistical guarantee
of coverage or business improvement. A demo with a simulated observation clock
verifies the software path, not elapsed real observations.

## Performance and demonstration evidence remain scoped

Fresh [SQLite benchmark evidence](sqlite-benchmarks.md) records real macOS HTTP
service acceptance in **8.886s**, a 500-SKU numerical preview in **3.285s**, a concurrent
health response in **118.77ms** and real upload-to-retrieval in **0.253s**, with zero price
writes and complete owned cleanup. The isolated numerical benchmark records **1.494s**
for 500-SKU analysis, **0.245s** Monte Carlo compute and a **5.509ms** matched single-SKU
scenario. The 500-SKU five-node graph with an explicit typed model fixture takes
**6.390s**; it is not real model latency. These measurements precede later UI changes;
their source scope and digests are retained in the linked record.

The real local one-SKU grounded workflow reaches Supervised human review in
**284.447s**, within an explicitly selected 480s functional observation window, with
one cited recommendation and unchanged numerical artifact. Its scope is **1 SKU**;
the unchanged requirement is **500 SKUs in <300s**. That full real-model target
remains unmeasured. Earlier failed/timeout probes remain in the evidence record.

The November 17 SQLite cache benchmark's 200 warmed hits have total median/p95/max
**2.314/2.527/2.856ms**, using real local MiniLM and SQLite RAG with a typed model fixture.
The separate 20-hit check has a **25.890ms maximum**. An earlier contended **124.92ms
maximum** remains a historical failure of a strict all-hit interpretation, not erased
by the fresh warmed sample. This workload does not establish an operational hit rate.

The fresh SQLite 56-case W1–W9 fixture demonstration passes in **8.910s** and verifies
HTTP, graph, persistence, controls,
push/replay/revert, feedback and learning paths, with declared model/embedding and
mature-observation fixtures. It cannot itself supply human necessity judgments, a
real business acceptance cohort, actual future sales or owner release signoff; the
limited demonstration scope approval is recorded separately above.

See [validation](validation.md), [browser QA](browser-qa.md),
[native platform preparation](windows-acceptance.md), [operator runbook](operator-runbook.md)
and [acceptance demonstration](acceptance-demo.md) for independently maintained
evidence. A later browser/Windows pass can close those individual gates while full
release remains contingent on the failures and absent observations above.

## Signoff record

- Owner option and approved scope: **B — limited engineering demonstration approved**;
  project owner/user in this session, **2026-11-17 (Asia/Kolkata)**. Exact instruction:
  **“Approve a limited engineering demo; keep business KPI gates open”.**
- Browser technical checks: **six actual Chromium tests passed**, both themes at 1280px,
  checked WCAG A/AA scans clean, maximum sampled action latency 34.2ms. Windows checks:
  **rerun in progress after the native ESM loader fix**;
  outcomes belong in [browser QA](browser-qa.md) and
  [native Windows acceptance](windows-acceptance.md).
- Baseline/target/envelope amendment, if any: **none approved here**.
- Human reviewer cohort and necessity-label protocol: **pending**.
- Mature daily-sales source and observation schedule: **pending**.
- Real 500-SKU model performance and request-series validity: **pending**.
- Full PRD release readiness: **not established; limited demonstration approval
  does not close T46, the full T47 gate, or business KPI requirements**.

Machine-readable fresh reports live in ignored `data/`; the measured summaries and
decisions above are retained in this tracked document. No production policy, price,
target, baseline or acceptance checkbox was changed by this review.
