# Development validation — 2026-11-12 (Asia/Kolkata)

This record separates implemented behavior from measured product effectiveness. The
running application has no configured gateway or mock-model fallback. Model calls in
automated tests and the graph benchmark use an explicit typed provider fixture.
A separate local LiteLLM proxy passes actual grounded startup pre-flight with four
aliases and real MiniLM inference, but its generation probe fails. The
[local integration record](local-gateway.md) distinguishes catalog readiness from working
model generation and corporate-tier acceptance. Browser visual QA and Windows startup
were unavailable. The native
Chrome follow-up also returned no screenshot or accessibility state; see the exact
[browser verification limits](browser-qa.md).

## Reproduce

```sh
.venv/bin/python -m pytest -q
PATH=/opt/homebrew/bin:$PATH npm --prefix web run build
.venv/bin/python -m scripts.benchmark --as-of 2026-11-09 --iterations 1000 \
  --output data/benchmark_selection_result.json
.venv/bin/python -m scripts.benchmark --as-of 2026-11-09 --iterations 100 \
  --output data/benchmark_100_result.json
```

The benchmark creates temporary Commerce and platform databases, reads business inputs
through the HTTP adapter, and removes the temporary databases on completion. It does not
change the running application's catalog, price book, approvals, knowledge, or loop.
The current selection-confidence report is the local ignored artifact
`data/benchmark_selection_result.json`; the earlier 100-iteration comparison remains in
`data/benchmark_100_result.json`. Model preparation must already have completed for real
local retrieval; the report clearly identifies retrieval fixtures if the model is missing.
The full graph measurement is skipped when real local grounding is unavailable.

Final November 12 integration verification passes **451 backend tests in 49.55s**,
source/rendering checks, **29 DOM interaction tests**, and the strict TypeScript/Vite
production build. The isolated W1–W9 demonstration passes **56 cases in 19.984s** with
an unchanged source hash. These declarations retain the explicit fixture and browser
limits in [UI acceptance](ui-acceptance.md) and [acceptance demo](acceptance-demo.md).
The earlier live HTTP smoke
checks cover constrained previews, matched scenarios, monitor/audit, A2A discovery and
unchanged Commerce prices/versions. After restarting the final application, the running
500-SKU preview took **8.736s** with an **18.01ms** concurrent health response;
idempotent real-model upload/retrieval took **0.646s**, preserving corpus revision 2.
Reproduce with `scripts.operations_smoke`,
`scripts.smoke`, and `scripts.grounding_smoke` using the project interpreter.

Hardware: Apple M1, 8 logical CPUs, 8 GiB RAM; macOS 15.6.1 arm64. Python 3.11.5,
Node v24.4.1, NumPy 2.4.6, SciPy 1.17.1. CPU and RAM were verified separately with
read-only `sysctl` probes because those probes are unavailable inside the benchmark
sandbox. Timings are one development-machine observation, not a production SLA.

## Performance observations

Fixture: **500 SKUs in one Beverages category**, 180 historical days, seed 42,
as-of 2026-11-09, balanced objective, 14-day horizon, initial model/policy versions.
The optimizer starts with a 21-point grid plus the current price and feasible floor;
the generated products have 20–21 distinct feasible candidates after rounding.
All 500 products were eligible. The same SKU set and inventory caps are used for
the proposed, current-price, and conventional-baseline forecasts.

| Measurement | 1,000 iterations, November 11 | 100 iterations, earlier implementation | Acceptance interpretation |
|---|---:|---:|---|
| Full numerical pipeline | 14.818 s | 2.975 s | Below 300 s; excludes live model calls |
| Monte Carlo compute, all candidate/final draws | 2.437 s | 0.305 s | Below 60 s |
| Single-SKU scenario | 55.9 ms | 20.5 ms | Below 5 s; identical matched forecast |
| Five-agent LangGraph to first human interrupt | 16.719 s | Not repeated after final role routing | Actual graph/checkpoints and real MiniLM; typed model fixture |
| Health response maximum during numerical work | 310.3 ms | 98.5 ms | Async backend stayed responsive; not a browser action measurement |
| Maximum event-loop heartbeat gap | 322.1 ms | 270.2 ms | Measured during CPU work and HTTP health reads |
| Cached grounded call median / p95 / maximum | 14.98 / 25.40 / **124.92 ms** | 6.13 / 12.69 / 62.71 ms | p95 passes; strict all-hits <100ms target fails on the latest observation |
| Exact + semantic hits / total calls | 20 / 21 = 95.24% | 20 / 21 = 95.24% | Repeated equivalent-context fixture; not an operational hit-rate estimate |

The graph benchmark runs all five actual nodes, including deterministic validation and
Execution's real per-item interrupt. It produced **500/500 cited recommendations** in
Supervised mode using 24 typed model-fixture calls, created approximately 87.9 MB of
checkpoint files, and made **zero Commerce price-history writes**. Its clock ends at
human review. Live gateway latency, human response time and applied-price outcomes are
outside that timing, so the full live-agent five-minute target remains unverified.

Cached-call measurements include current Chroma retrieval and real MiniLM processing,
with only the model generation replaced by the explicit fixture. Each request re-reads
the active source manifest; an upload changes the corpus namespace and invalidates
response eligibility. Local embedding vectors are memoized in a bounded memory cache,
and file integrity is reused only while inode, size, mtime and ctime remain unchanged.
Corruption/replacement and token limits are still checked before a cached vector is used.

The current November 11 run included the selection-uncertainty calculation and concurrent
test/proof workloads. Its timing must not be treated as a paired iteration-count comparison
against the earlier implementation. The November 9 study measured 3.887s versus 2.975s
of numerical work at 1,000 versus 100 iterations, with Monte Carlo compute 0.898s versus
0.305s. Forecast uplift was -7.052% versus -7.023%, with 466 versus 467 of all 500 prices
within 10% of the theoretical optimum. This does not establish interval calibration or
justify narrowing uncertainty; 1,000 remains the default. The final November 10 graph
adds a separate concurrent anomaly narrator: Data & Context uses analyst and narrator,
Quantitative uses analyst, Strategy uses strategist, and Validation uses strategist.
Execution is deterministic and makes no model calls. The numerical comparison uses
unchanged default constraints and the identical November 9 synthetic fixture.

## Effectiveness observations and failed targets

The held-out evaluator alone reads generator elasticity and baseline demand. Production
estimators, agents, model prompts and caches never receive those values. The evaluator
uses the same feasible candidate set, stock cap, latest seasonal level, joint family
ladder, objective weights and explicit +0.06 competitor follow-through. It computes
deterministic expected outcomes; these are not observed future sales or causal uplift.

| Product target | Measured at 1,000 iterations | Result |
|---|---|---|
| Forecast revenue uplift versus conventional baseline ≥5% | **-7.052%** | Fails on this balanced-objective fixture |
| No gross-profit degradation versus baseline | +$1,282,492 forecast gross profit | Passes for this forecast comparison |
| No margin-rate degradation versus baseline | +17.351 percentage points | Passes for this forecast comparison |
| All modeled prices within 10% of theoretical optimum | 466/500 = **93.2%**, unchanged by confidence correction | Retains the full denominator |
| High-confidence prices within 10% of theoretical optimum | **405/414** on November 11, with 9 errors still over 10% | Fails the unchanged all-high-confidence interpretation |
| Valid source citations | 500/500 in graph fixture | Tested fixture evidence; no live model reliability claim |

The original confidence model labeled all 500 recommendations above 0.8. The corrected
`confidence-v2-selection` acknowledges uncertainty in the selected price: coverage is
414/500 in seed 42 and 405/500 in seed 43 on November 11. The latter has 396/405 prices
within 10%, also leaving 9 high-confidence errors. All 500 remain modeled; overall accuracy
is still 466/500 in both seeds. Source fixtures are dated November 9 and competitor freshness
decays against the actual UTC evaluation date, so confidence coverage changes on later
reruns; prices, forecasts and the feasibility bounds remain identical for the recorded
fixed inputs. The conventional baseline can forecast higher revenue at lower margins.
No threshold, confidence score, compliance rule, or baseline was weakened to make a
target pass. Further fixture diversity, confidence calibration and objective evaluation
are required before product effectiveness can be accepted.

The [feasibility proof and decision-uncertainty review](effectiveness-feasibility.md)
show that +5% revenue uplift is impossible under the recorded legal price sets against
the unchanged baseline. Even an explicitly analytical legal-baseline projection permits
only 2.494% / 2.195% maximum family-constrained grid revenue uplift on seeds 42 / 43.
This unresolved acceptance gate requires an owner decision; it is not marked achieved.

The separate [threshold study](calibration.md) evaluates 72 policy combinations across
two independent 500-SKU fixture seeds. It records coverage and predicted band tradeoffs
without selecting a new default or updating system policy; higher confidence cutoffs
do not establish target achievement by excluding almost every SKU.

Human acceptance ≥70%, Assisted automatic share ≥60%, escalation precision ≥80%, realized
interval coverage ≥80%, longitudinal oscillation <2%, and narrowing realized forecast error
remain **unobserved**. The seeded history does not include mature post-push outcomes.
Feedback correctly remains pending until a complete disjoint observation window exists.
Tests exercise feedback and learning with explicit synthetic outcome fixtures, which do
not establish these product metrics. Post-repair model validity ≥99% also requires an
actual gateway evaluation; passing typed fixtures is not that evaluation.

## Correctness and recovery evidence

Automated suites cover the following material paths:

- `test_grounded_llm.py` and `test_llm_gateway_and_telemetry.py`: actual LangChain HTTP
  envelopes, structured schema enforcement, one repair, typed failure, current required
  grounding, citation validity, exact/semantic cache eligibility, transient retries,
  cancellation counters, ambient tracing disabled, metadata-only tracing failure isolation,
  and prompt/output/credential/contact redaction.
- `test_workflow_integration.py`: actual five-node LangGraph, immutable computed prices,
  resolved citations, mixed per-item approve/reject, Commerce receipts, reconnectable
  progress, SQLite checkpoint restart, explicit recovery, and no model calls in Execution.
- `test_discovery_integration.py`: successful A2A initiation, durable same-message replay,
  conflicting input rejection, input-required task polling and restart, cited read-only
  chat despite execution requests, and current-memory credential redaction in audit export.
- `test_llm_pricing_and_repair.py`: sanitized actual schema error locations/types and
  static citation repair diagnostics, attributed LiteLLM rates, explicit role pricing,
  long-context rates, unknown-model fallback and metadata cost-source persistence.
- `test_feedback_learning.py`: mature/disjoint windows, explicit zero versus missing data,
  duplicate and intervening-price exclusion, missing cost evidence, immutable versions,
  capped updates, widening uncertainty and minimum evidence before learned calibration.
- `test_scenarios_extended.py`: one shared engine, corresponding-sample aggregation,
  fixed-seed parity, stress assumptions, learned-state parity, invalid inputs and no writes.
- `test_interval_loop.py`: explicit start, nonoverlap, cap, first-failure stop, human-review
  disposition, timer cancellation and scheduling off after restart. Operator stop ends
  scheduling; an admitted analysis may finish. Kill additionally cancels active graph work.
- `test_local_model_readiness.py`: integrity checks detect edits despite restored mtime,
  missing files, bounded vector reuse, returned-vector isolation and token-limit enforcement.
- Commerce, governance, grounding and boundary suites independently exercise rule veto,
  version/idempotency/partial receipt handling, mode/hold/kill fences, compliant revert,
  immutable audit/evidence, upload recovery, HTTP/database ownership and the 400-line cap.

The full backend suite and frontend build must be run after integration; their latest
results are recorded in the task plan and operator README. Browser keyboard behavior,
layout in both themes, ordinary action latency, Windows process cleanup, real gateway
aliases/structured support and metadata tracing egress remain environment validation work.

## Cost estimate provenance

The packaged `platform_app/llm/model_prices.json` is a small attributed subset of the
[official LiteLLM model cost map](https://docs.litellm.ai/docs/proxy/model_cost_map), copied
from its linked GitHub catalog. It records the retrieval timestamp and SHA-256 of the
complete source catalog. It covers standard text-token Gemini 2.5 Flash Lite, Flash,
Pro and two optional OpenAI models; it is a dated snapshot with no automatic network refresh.
Gemini Pro's recorded long-context tier and available cached-input rates are retained.

The resolver uses an explicit `LLM_PRICING_MODEL_<ROLE>` identifier when configured,
otherwise the provider-reported model and then the gateway alias. Unknown identifiers
use the configured input/output fallback rates. The monitor records `litellm_snapshot`,
`configured_fallback_rates` or mixed sources rather than claiming invoice accuracy.
Provider fees, gateway markup, specialized service tiers and unmodeled modalities are
not guaranteed by this standard-text estimate.

An isolated wheel build was inspected: `platform_app/llm/model_prices.json` is included
and exactly matches the source file (SHA-256
`104307258c76e8e3365d66d949c61a58eb3ea7045ba6f43eef17a4a1c9c1eddf`).

## Initial policy and learning choices

Current initial defaults are inspectable via `/api/policy`: confidence >0.8, automatic
delta ≤5%, revenue coefficient of variation ≤0.35, margin headroom >0.03, sample ≥60,
oscillation window 8, reversal trigger 2, damping fraction 0.35, hold 60 seconds and
minimum-change interval 0 seconds. Runtime edits are versioned and audited. These are
development defaults, not empirically approved or guaranteed thresholds. The loop defaults
to 60 seconds and never overlaps an active analysis; it starts only through an explicit
operator action and remains off at every boot.

Learned refinements require at least three disjoint outcome windows and 30 observed days.
An elasticity adjustment is capped at 0.1 per update and 0.5 cumulatively, with at least
a 2% price change for that adjustment. The uncertainty multiplier remains within
0.75–2.0; poor residual evidence widens it. Learning versions retain before/after evidence
and never update from duplicate, overlapping, incomplete, unchanged-price or intervening-price
windows. This observational mechanism does not prove a causal elasticity change.
