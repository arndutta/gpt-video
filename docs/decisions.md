# Implementation decisions and acceptance boundaries

Recorded 2026-11-09. These choices make the requested local implementation concrete.
Updated 2026-11-10 for run constraints, market-gap escalation and matched outcome scope.
They do not amend the source PRD, imply formal approval, or establish calibrated business
guarantees. The user explicitly authorized development and completion of remaining work.
The source documents linked from the PRD were not supplied; no missing decisions were reconstructed.

## Ownership, credentials, and grounding

| Decision | Implemented interpretation | Remaining acceptance |
|---|---|---|
| PRD approval | Development authorization follows the user's instructions; the original approval text is preserved. | Owner records formal release readiness. |
| Commerce ownership | Commerce owns catalog, sales, inventory, current prices, history, and receipts. Platform reads/writes over HTTP. Platform retains derived decision evidence/checkpoints, not an authoritative business mirror. | Validate any future retention policy against actual retailer data. |
| Key input versus client boundary | Operator-entered masked field is transient and write-only. It clears on submit; the server retains the key in memory and never returns/persists it. Environment secrets remain in the launching process. Browser stores theme only. | This resolves implementation behavior; no formal requirement amendment is inferred. |
| Mandatory versus optional sources | Required Commerce failure, failed quality, empty required grounding, or missing gateway stops the affected grounded run. Optional competitor failure is explicit and lowers numerical confidence/increases uncertainty. | Real gateway and optional remote feed availability are unverified. |
| Uploaded evidence | Every populated collection participates in retrieval. Current corpus/evidence versions bind each model call/cache. Role breadth is bounded per collection; retrieval is relevant top-k context, not all-document injection. | Retrieval distance does not itself prove business relevance or complete document coverage. |
| Embedding egress | Local MiniLM is preferred. Gateway embeddings require explicit provider selection, model/dimensions, and an opt-in flag. | No automatic fallback or real gateway embedding verification is claimed. |
| Model authority | GroundedLLM is the sole chat entry point. Structured output receives one repair attempt; citation IDs must come from supplied published evidence. Models explain deterministic values and cannot replace prices, intervals, or scores. Execution has no model call. | Actual aliases must support the configured JSON Schema contract. |
| Personal pricing | Requests for personal/consumer-specific pricing are rejected; prompts/log metadata are redacted. | No production identity or consumer data integration is included. |

## Numerical policy

Currency is USD in the supplied fixtures. Monetary API values are decimal strings with
two decimal places and half-up rounding; a candidate must align exactly to its SKU tick.
Gross margin is `(price - cost) / price`. Commerce SKU evidence supplies MAP, minimum
margin, maximum change, category price bounds, tick, family, and size constraints.
Platform policy can tighten applicable rules; Commerce independently evaluates writes.
Optional run constraints further tighten the maximum price-change fraction and category
floors/ceilings. They are retained in immutable evidence and enforced for human edits,
bulk approval, automatic execution and compensating reverts. A prior price that violates
the originating run's constraints or current policy cannot be forced through a revert.

The market-gap norm defaults to 30% absolute proposed-price versus competitor-median gap.
Crossing it escalates with the actual value and configured threshold. It is an explicit
trial norm, not a claim of empirically learned market history.

Run outcome comparisons include only the same complete, disjoint observed SKU windows
on both sides. Baseline comparisons remain counterfactual forecasts; missing observations
are pending. Use the supplied startup script: one platform worker owns the lifecycle,
continuous scheduler and dispatch fence.

| Parameter | Initial implementation |
|---|---|
| Forecast horizon | 14 days by default; browser/API range 1–90 |
| Monte Carlo draws | 1,000 by default; browser/API range 100–5,000 |
| Interval | Empirical 2.5th/97.5th draw quantiles, with mean/median/variance retained |
| Elasticity eligibility | At least 30 positive-sales observations and four distinct prices with sufficient variation |
| Regression | Deterministic log-price response with promotion, season, and weekly controls; Student-t coefficient intervals |
| Candidate grid | 21 evenly spaced feasible points, tick-rounded, plus current price and smallest feasible tick |
| Revenue objective | 0.8 normalized expected revenue + 0.2 normalized expected gross profit |
| Margin objective | 0.2 revenue + 0.8 gross profit |
| Balanced objective | 0.5 revenue + 0.5 gross profit |
| Family selection | Joint monotone-size dynamic program; unchanged/skipped siblings remain constraints |
| Seed | Default 42; SHA-derived SKU/run streams and recorded engine version, not Python's randomized hash |
| Inventory | Fixed on-hand cap with no replenishment |
| Shared uncertainty | Fitted elasticity uncertainty, competitor response, cost drift, seasonal/residual variation; shared cost/season shocks retain aligned sample columns |
| Aggregate intervals | Sum aligned draws, then calculate quantiles; never sum interval endpoints |
| Baseline | Cost × (1 + category markup) × (1 − category discount), half-up to SKU tick; Beverages 40%/0%, Snacks 45%/5%, Household 35%/3% |
| Ground truth | Hidden evaluation fixture only; never a fit input, model prompt, or ordinary Commerce HTTP field |

The default cost drift sigma is 0.02, competitor sigma is 0.035 with quotes / 0.12 without,
and shared-shock correlation is 0.36. These are inspectable assumptions, not empirically
fitted retailer distributions. Stress cases multiply demand by 0.5, transmit a 20% competitor
undercut with exponent 0.4, or multiply costs by 1.2. Identical scenario/recommendation inputs
and seed share the numerical engine. Scenarios never create approval authority.

## Initial governance thresholds

Read `/api/policy` for the current persisted version and values. Settings exposes the
autonomy/stability thresholds; API updates also support the optional rule-tightening fields.
Changing mode or policy cancels prior pending approval intents rather than migrating them
silently. Existing evidence remains immutable and inspectable.

| Field | Initial value | Meaning |
|---|---|---|
| `confidence_threshold` | 0.8 | Auto confidence must be strictly greater |
| `bulk_confidence_threshold` | 0.8 | Bulk Review confidence must be strictly greater |
| `auto_delta_pct` | 5.0 | Maximum absolute percent change for Auto eligibility |
| `volatility_limit` | 0.35 | Revenue standard deviation / max(abs(mean), 1) |
| `margin_proximity_buffer` | 0.03 | Margin headroom must exceed this fraction |
| `minimum_sample` | 60 | Auto sample minimum; does not relax fit eligibility |
| `oscillation_window` | 8 | Recent changes inspected |
| `reversals_threshold` | 2 | Direction reversals trigger an incident; a recent-price return also triggers |
| `damping_fraction` | 0.35 | Fraction of normal allowed move used when damping is active |
| `anomaly_z_threshold` | 4.0 | Historical/category price anomaly threshold |
| `minimum_change_seconds` | 0 | Optional per-SKU cooldown; initial demo imposes none |
| `hold_seconds` | 60 | Autonomous Review hold |
| Optional tighter margin/change/tick | SKU rules plus configured tightening | Rules cannot be weakened at Commerce dispatch |

Escalate is evaluated first: compliance failure, margin proximity, excessive volatility,
oscillation, or novel market/price signals. All Auto conditions must pass; remaining items
are Review. Low confidence alone is Review, preserving W2. A degraded-history demonstration
reaches Escalate only when a named trigger actually fires; no extra trigger is invented.
Damping bounds apply before final optimization, and the incident remains visible after damping.
Insufficient eligible history produces an explicit skipped/error outcome instead of a confident price.

## Authorization and lifecycle

| Mode | Auto-approve band | Review band | Escalate band |
|---|---|---|---|
| Supervised | Human decision | Human decision | Written human intervention |
| Assisted | Automatic | Human decision | Written human intervention |
| Autonomous | Automatic | Automatic after hold unless human intervenes | Written human intervention |

Compliance violations have an absolute veto in all modes, manual overrides, and reverts.
Bulk approval applies only to actual Review-band items with clean compliance and confidence
above threshold. Auto-band items queued by Supervised retain their band. Manual price
overrides create immutable revisions, require a written reason, and receive a fresh
deterministic forecast/rule evaluation. Expected revision and Commerce price version prevent stale decisions.

The dispatch fence serializes final authorization with mode/policy changes and kill.
After halt acknowledgment, pending unsent work cannot use stale authority. Requests already
sent may have committed; an unknown result stays visible and is reconciled by the original
persisted batch key. Reconciliation must not use a replacement key. A revert is a new linked
compensating change, not deletion of history; a newly illegal prior price is refused.

Each grounded run uses a SQLite LangGraph thread and per-item human interrupts. Recording
a decision resumes the appropriate active run. Restart requires explicit checkpoint resume
and fresh execution authorization. Continuous scheduling is lifespan-owned, starts only from
the UI/API, runs without overlapping analysis, and remains off at every boot. Review waits
are distinct from failed iterations. A failed iteration stops scheduling; retry is explicit.
The default loop interval is a fixed 60-second delay between iterations, configurable 5–86,400,
with an optional 1–1,000 iteration cap. These choices are not throughput guarantees.

## Feedback and effectiveness

The observation window starts on the UTC day after confirmed application and spans the
run's forecast horizon. It must be mature and contain complete daily Commerce rows at the
approved price. Missing rows stay pending; intervening prices and previously counted days
are excluded. Cost is the decision-time evidence because no realized cost feed is supplied.
Forecast-versus-realized comparisons are observational and are never labeled causal uplift.

Learning versions retain provenance and before/after state. Elasticity adjustment begins
after at least three windows / 30 observed days and a price move of at least 2%; per-update
offset is capped at 0.1 and cumulative offset at 0.5. Residual uncertainty multipliers stay
between 0.75 and 2.0. Bad evidence can widen uncertainty; running again never forces it to
narrow. Widening recent error is visible. Static seed data does not manufacture future
post-push transactions, so real maturity and human acceptance/precision targets remain open.

FR-070 retains its stated **S** priority despite the broader UI introduction. FR-107,
FR-108, FR-111, full banding, Monte Carlo, and Autonomous mode retain their required scope.
No proposed PRD scope cut is treated as approved. Browser interaction/visual QA, Windows,
live gateway/Langfuse access, and product-effectiveness thresholds require additional evidence.
