# Implementation Tasks: AI-Driven Dynamic Pricing Engine for Retail

Status: The implemented SQLite/RAG engineering demonstration has owner scope approval.
Desktop Chromium acceptance is complete. Windows acceptance is being rerun after a
native test-loader fix; full real-model scale and business-effectiveness gates remain open.
Prepared: 2026-11-08. Source: [prd.md](prd.md), version 1.1, dated 2026-08-07.
Companion documents: [requirement.md](requirement.md) and [design.md](design.md).

The PRD controls scope and acceptance. This plan decomposes its seven milestones into
work that can be implemented and verified. Creating these documents does not approve the
PRD, change its priorities, or authorize its suggested scope cuts. The source documents
linked from the PRD are absent from this repository; only decisions described in the PRD
are used here. Checkboxes remain open until the entire stated task and its acceptance
criteria are met; implemented subsets are tracked below and in [README.md](README.md).

### SQLite engineering acceptance — 2026-11-17 (Asia/Kolkata)

- SQLite business/reference data, explicit DDL/DML, migration cleanup, exact SQL exports,
  and SQLite document/vector/citation retrieval are installed and verified. The static
  business JSON copies are removed. The committed database migration is `ff89acd`.
- **562 backend tests**, **67 DOM tests**, and the production TypeScript/Vite build pass.
  **Six actual Chromium tests** pass at 1280×900 in both themes, with 20 screenshots,
  clean checked WCAG A/AA scans and 34.2ms maximum sampled interaction latency.
  [Browser evidence](docs/browser-qa.md) closes T26/T32/T33's desktop gates.
- Fresh [SQLite benchmarks](docs/sqlite-benchmarks.md) pass numerical/cache/scenario
  timing, native macOS service/cleanup checks and all **56 W1–W9 fixture cases**.
  Numerical 500-SKU analysis is 1.494s; Monte Carlo compute 0.245s; warmed cache maximum
  2.856ms. The 6.390s five-node 500-SKU result uses an explicitly typed model fixture.
- Windows CI has been pushed and exercised. Native Node exposed a test-loader file-URL
  defect, fixed in `befd7fc`; the [Windows record](docs/windows-acceptance.md) tracks
  rerun evidence. A queued/in-progress run is not a passing native result.
- The project owner/user explicitly approved **a limited engineering demo while keeping
  business KPI gates open**. [Release readiness](docs/release-readiness.md) records that
  scope and the fresh 216-row calibration/feasibility study. No PRD target, default,
  compliance rule or baseline changed. T46's full real-model/observational targets and
  the full-PRD portion of T47 remain unchecked; synthetic data does not supply real labels
  or mature future sales.

### Follow-up development — 2026-11-10

- Remaining FR-019 run-scoped constraint controls now cover run creation and loop setup:
  optional maximum change is entered as a percentage and submitted as a fraction;
  selected-scope category floors/ceilings retain decimal monetary strings. Blank fields
  add no bound, inverted/invalid bounds fail clearly, and current Commerce compliance
  remains authoritative. Backend parity across preview/grounded/override/revert paths
  is verified in the integrated suite.
- Settings exposes the trial market-gap escalation threshold (initial 30%). Explicit
  **No change** terminal outcomes remain distinct from applied writes; loop iteration
  summaries expose the separate count. Realized comparisons now retain the mature
  observed SKU denominator rather than comparing partial observations with all-run forecasts.
- UI serialization/safety/rendering checks and the TypeScript/Vite production build pass.
  The latest full backend suite passes 457 tests. This follow-up does not claim unavailable
  live gateway or business-effectiveness targets; remaining gates stay unchecked.

### Current development status — 2026-11-12 (Asia/Kolkata)

- The local foundation and deterministic preview remain available without a gateway. The
  implementation now also contains the sole grounded model wrapper, five-node LangGraph
  workflow with persisted per-item review interrupts, independent platform compliance,
  stability/damping, deterministic bands, three modes, versioned human decisions, fenced
  execution/revert, durable Commerce recovery, and append-only evidence.
- Realized readback and bounded learning use complete, mature Commerce HTTP observations;
  static seed history does not invent future post-push sales. Missing outcomes remain
  pending. One/many-SKU scenarios, stress presets, saving, and optional grounded narration
  reuse the numerical engine.
- The React workspace includes the review queue/details/ladder, real global mode/halt/loop
  controls, settings and configurable initial policy, token/cost/cache monitoring, impact/
  stability/autonomy views, audit filtering/export, and read-only grounded discovery.
- Lifespan-owned continuous scheduling is explicitly started, never restored at boot,
  and stops on a failed iteration. Exact/equivalent-context caching, safe local telemetry,
  optional metadata-only Langfuse, and bounded A2A methods are implemented. The optional
  remote competitor adapter accepts JSON behind an explicit opt-in; no scraper is claimed.
- T14/T15 real local-model ingestion/retrieval evidence remains valid. Actual grounded
  startup pre-flight passes against an isolated local LiteLLM proxy and real embeddings.
  Its generation probe fails; the running workbench still has no gateway/key/aliases.
  Runtime model generation has no fabricated fallback. See [local integration](docs/local-gateway.md).
- A later real probe with the new explicit helper batch-64 option preserves the entire
  input/schema, 4096-token context and normal citation validation. It still fails after
  6.777s with the runner killed and no generated tokens. The kill's cause is unconfirmed;
  the proxy was cleaned up and the running app remains unconfigured. No further blind
  generation retries or larger graph run followed. Live-generation acceptance stays open.
- The integrated suite passes 457 backend tests (40.55s). Source/rendering checks,
  54 frontend DOM tests, and the strict TypeScript/production build
  pass. The current benchmark artifact is `data/benchmark_selection_result.json`;
  [validation notes](docs/validation.md) distinguish real
  local compute/retrieval from an explicitly injected model fixture. Full live-gateway
  timing and effectiveness are not inferred from fixture timing.
- Live HTTP checks pass: constrained preview, matched scenario, monitoring/audit and A2A
  discovery preserve Commerce prices/versions. After restarting the final application,
  the 500-SKU preview takes 8.736s with an 18.01ms concurrent health response;
  idempotent real-model upload/retrieval takes 0.646s
  without restart or a new corpus revision. Evidence is in the ignored `data/*smoke_result.json`
  artifacts. Historical queues and audit chains remain reachable after newer records;
  valid audit UUIDs survive redaction while known credentials remain hidden.
- An evaluation-only [calibration study](docs/calibration.md) measures 72 threshold
  combinations across two independent 500-SKU seeds. It preserves compliance and selects
  no new defaults. Revenue uplift and high-confidence price-accuracy targets fail on these
  fixtures; operational/human outcome targets remain unobserved.
- Confidence now includes simulated uncertainty of the joint selected-price optimum.
  Prices, forecasts and baseline remain unchanged; arbitrary overrides/reverts clear the
  prior optimizer range and retain it only in the immutable earlier revision.
  [Feasibility evidence](docs/effectiveness-feasibility.md) proves the +5% revenue target
  unreachable on both recorded fixtures under the existing price bounds, even when
  relaxing family/tick constraints. No PRD target, baseline or rule was weakened.
- The isolated [W1–W9 demonstration](docs/acceptance-demo.md) passes 56 cases with
  stable source hashes. It explicitly uses typed model/embedding and observation-clock
  fixtures; it does not claim real gateway reliability or mature business outcomes.
- [Operator runbook](docs/operator-runbook.md) provides reproducible W1–W9 steps;
  [implementation decisions](docs/decisions.md) records assumptions, policy defaults,
  lifecycle semantics, and unresolved acceptance. Checkboxes below remain acceptance
  gates, not a claim that every shipped code path has been verified externally.
- Browser visual/interaction QA, Windows execution, live gateway/Langfuse/remote-feed
  access, human labels, mature business effectiveness, and full live-pipeline performance
  remain unverified. Initial thresholds are not empirically calibrated guarantees.
  [Browser QA](docs/browser-qa.md) records the service blocker and confirms no browser
  action or populated fixture was performed.
- Build authorization comes from the user's explicit development/completion instructions.
  The original PRD remains unchanged and no formal approval status is inferred.

### UI redesign — 2026-11-12 (Asia/Kolkata)

The user's selected modern blue/mint dashboard is implemented across the local workspace:
new navigation/header, command search, overview/workflow explorer, dashboard tabs,
catalog grid/table and product inspection, interactive forecast intervals, shared
light/dark surfaces, and reduced-motion-aware animation. Follow-up adds native workflow/
stress cards, loaded run-history filters, review-band shortcuts and hidden-selection
warnings, recorded audit metadata, and editable evidence-question starters.
Follow-up polish adds accurate settings-draft feedback, disabled in-flight settings,
explicit service retry, loading placeholders, IME handling and native modal Tab stops.
All 54 DOM cases
and the TypeScript/Vite build pass; four architecture/boundary checks also pass.
See [redesign details and verification limits](docs/ui-redesign.md). After the earlier
tool usage limit, a permitted inventory still reports the browser access host unavailable. Actual
viewport, painted contrast, and browser latency remain unverified; T26/T32/T33 and the
live-model/effectiveness/release gates remain open. No backend or pricing policy changed.

### UI reliability follow-up — 2026-11-14 (Asia/Kolkata)

- Pending scenario simulation/save operations now disable competing requests, saved-result
  loading, and input editing so earlier responses cannot overwrite a different scenario.
- Canceled resource responses cannot replace a newer query after JSON parsing finishes.
  Polling hides data from a previous URL/filter scope immediately; same-scope refreshes
  retain the last response and keep connection errors visible until successful recovery.
- Catalog refresh reloads summary counts/categories, reports summary failures, and moves
  to the last valid page when refreshed product totals shrink. Missing forecast centers
  remain explicitly unavailable, including percentage-formatted margin forecasts.
- Drawers recapture Tab after a focused control disappears. New close callbacks no longer
  reset focus during editing, and Escape uses the latest callback.
- Verification passes: **457 backend tests** (23.61s), **63 DOM tests** (11.980s), UI
  source/rendering checks, strict TypeScript/Vite production build, and four final
  architecture/boundary checks. Nine new regression cases cover these failures.
- One bounded browser inventory still returns no browsers and reports the access host
  unavailable. No browser action occurred. T26/T32/T33 visual/latency acceptance and
  existing live-generation/effectiveness/release gates remain open.

### Operational hardening continuation — 2026-11-14 (Asia/Kolkata)

- Grounded checkpoint resume reserves the shared analysis slot before checkpoint I/O,
  releases it on failed/canceled/no-op inspection, and cannot launch delayed graph work
  after halt or shutdown. Automatic decision notifications defer while analysis is busy.
- A failed JSONL emission no longer suppresses independent SQLite model usage history
  or exporter submission. Malformed token metadata is ignored without failing an otherwise
  valid cited answer or leaving an active-call count stuck.
- Gateway model-list verification now has a total 10-second deadline in addition to
  HTTP operation timeouts; slow streaming cannot prolong readiness indefinitely.
- Policy inputs remain disabled during an update, retaining the submitted draft after
  failure. Document upload history/statistics discard responses begun before a relevant
  accepted upload or publication, then fetch current state after the old read settles.
- Final verification passes **471 backend tests in 21.20s**, **67 DOM tests in 12.998s**,
  source/rendering checks, strict TypeScript/Vite production build (Vite 1.44s), and
  whitespace checks. Fourteen backend and four UI regression cases were added.
- A fresh isolated W1–W9 demonstration passes **56 cases in 8.217s**, with an unchanged
  139-file Python source digest. Evidence is `data/acceptance_demo_20261114_result.*`.
  Model/embedding and mature-sales-clock fixtures remain explicit. Browser, native Windows,
  live-generation, effectiveness and final release acceptance remain open.

### Local acceptance follow-up — 2026-11-14 (Asia/Kolkata)

- After the installed Ollama runtime changed from the historical 0.32.1 failure runtime
  to 0.40.16, one unchanged local structured-generation probe passes in 11.677s with a
  valid real-RAG citation, 419 input / 109 output tokens and no repair. Cleanup verifies
  the temporary proxy stopped and no model remained loaded. No external gateway exists.
- An actual 1-SKU graph attempt then fails at Data & Context after 48.205s; a native
  response reaches its 800-token output limit and an outstanding sibling exposes a
  cleanup gap. Both concurrent phases now cancel and await peers before propagating
  the original failure. SDK length-limit errors now receive the ordinary single safe
  structured repair and retain token usage, without changing schema, facts or limits.
- The new portable `scripts.local_acceptance` uses real temporary 500-SKU services,
  prepared local embeddings, HTTP previews/controls/upload and before/after price/history
  snapshots. Its macOS run passes in **9.732s**: preview **3.147s**, concurrent health
  **38.96ms**, upload-to-retrieval **0.255s**; zero price writes, unchanged prices/versions,
  all owned children stopped, ports free and temporary data removed. It does not certify
  browser behavior, native Windows, or shell/batch startup wrappers.
- Cache-stage profiling preserves current retrieval/citation checks on all 200 warmed
  hits (100 exact, 100 semantic). Final total median/p95/max is **2.133/2.307/2.924ms**;
  this sampled maximum passes <100ms without replacing the earlier contended failure
  or claiming a universal guarantee. Cache SQLite connections now close after transactions.
- A fresh six-case objective study covers both seeds and all three objectives, 500/500
  modeled SKUs per case and 216 threshold rows, with zero compliance violations. All
  cases fail the unchanged revenue and high-confidence price-accuracy targets. No policy,
  baseline, denominator or target changed; human labels and mature outcomes remain absent.
- Final checks pass **492 backend tests in 22.01s**, **67 DOM tests in 13.069s**, strict
  TypeScript/Vite build (Vite 1.43s), and the isolated W1–W9 **56-case demonstration in
  8.178s**. Native acceptance and demonstration record the same stable 146-file Python
  source digest. The browser host is still unavailable and this machine has no native
  Windows shell. T26/T32/T33/T46/T47 stay open where their acceptance is unverified.

### Acceptance reconciliation — 2026-11-15 (Asia/Kolkata)

- The final real-model 1-SKU graph remains failed acceptance: repaired Data & Context
  completes in 175.712s, then the 240.031s overall deadline interrupts Quantitative
  narration before recommendation/review. There are zero price writes, unchanged
  Commerce prices/versions, no input truncation or runner kill, and verified owned
  listener/forwarder/model cleanup. No larger real-model run or further retry followed.
- SDK-observed usage is 5,308 input / 2,967 output tokens. Native metadata totals
  8,335 / 3,767 because an already-sent canceled inference finishes during cleanup.
  The SDK snapshot is not total native consumption; full live reliability remains open.
- A fresh read-only cleanup check confirms ports 8001/8000/5173/4002 free and no loaded
  model. The implementation source still matches the stable 146-file digest verified
  by the 492-test backend suite and 56-case isolated demo. Frontend code is unchanged
  from its passing 67 tests/build. A new browser inventory again finds the host unavailable.
- T26/T32/T33/T46/T47 remain open for real browser acceptance, native Windows, full
  live workflow/performance/statistical validity, human labels/mature outcomes and owner
  release readiness. No external gateway is available; optional integrations are
  unconfigured. `data/acceptance_reconciliation_20261115.json` consolidates evidence.

### Bounded workflows and native Windows preparation — 2026-11-15 (Asia/Kolkata)

- Concise initial narration retains all material warnings/uncertainty without echoing
  input tables. Explicit strategy/validation batches (default 25, range 1–25) retain
  complete per-SKU facts and verdicts. Validation checks policy versions around every
  batch and does not activate partial results. Optional complete-envelope byte caps
  reject intact oversized initial/repair inputs; they are not token-capacity guarantees.
- The real five-stage **one-SKU functional workflow passes in 284.447s**, reaches a
  persisted Supervised human-review interrupt, validates its citation and unchanged
  numerical artifact, and makes zero price writes. Seven real calls include two ordinary
  repairs. The explicit functional window is 480s; default diagnostic 240s and the PRD's
  500-SKU/300s target remain unchanged. All native context budgets and cleanup checks pass.
- The updated 500-SKU typed-model-fixture graph covers all recommendations/citations
  through 43 bounded model calls in 6.089s. It is not real 500-SKU model latency evidence.
- Fixed Windows-only dependency installation (`uvloop` marker), SIGBREAK handling and
  startup metadata SQLite handle closure. The batch-wrapper harness atomically creates
  its root inside an owned Job Object; descendant cleanup survives wrapper exit and
  forced cleanup fails acceptance. CI uses pinned official actions and one native
  command per PowerShell step. The dedicated CI branch is prepared, not published/run.
- Final checks: **529 backend tests (22.49s)**, **67 DOM cases (13.015s)**, TypeScript/Vite
  build (1.92s), and **56 isolated W1–W9 cases (10.022s)** pass. Actual macOS service
  acceptance passes in 11.264s, with 500-SKU preview 3.361s, concurrent health 38.6ms,
  upload/retrieval 0.465s, unchanged prices and complete cleanup. The stable Python
  digest covers 157 files. Native Windows, browser QA, real 500-SKU model performance,
  statistical validity, human/mature-outcome measures and owner release acceptance stay open.

## How to use this plan

- **M**: must-have for the demo; **S**: should-have; **C**: could-have, following the
  individual PRD requirement rows. NFRs remain mandatory acceptance constraints.
- Dependencies are task IDs, not a requirement to finish every earlier milestone first.
  Independent backend, numeric, and UI tasks may proceed in parallel after their inputs exist.
- A task is done when its implementation, stated acceptance evidence, and applicable
  regression checks are complete. A document describing behavior is not implementation evidence.
- Preserve FR/NFR identifiers in code reviews and verification records. Each task below
  explicitly names its source requirements; a requirement can be shared across tasks.
- Use synthetic, aggregated SKU-level data. No consumer data, production integration,
  production authentication, cloud deployment, containers, or system daemons are planned.

## Before implementation

### T00 — Record approval, resolve contract decisions, and establish calibration fixtures

- [x] Record the PRD approval state and review the proposed choices in `design.md` before
  product implementation. Resolve the decision register in `requirement.md`; retain unresolved
  items explicitly rather than treating draft designs as approved policy.
- [x] Specify currency precision, margin formula, forecast horizon, interval coverage,
  objective weighting, minimum sample rules, quality severity, candidate price grid, and
  deterministic random-seed handling. Select and record development hardware for benchmarks.
- [x] Resolve API-key input versus the ban on client-held credentials; evidence snapshots
  versus business-data ownership; optional ingestion failure versus Commerce outage; and
  insufficient-history Review versus the Escalate example in PRD §9.3.
- [x] Define the Autonomous hold window, mode-change behavior for pending work, the
  boundary between pending and already-sent pushes, and revert behavior if the prior price
  violates current rules. Preserve compliance veto throughout.
- [x] Preserve FR-070's S priority while flagging §5.9's broader must-have statement.
  Keep FR-107, FR-108, and FR-111 as M unless a PRD amendment authorizes their removal.
- **Done when:** choices, remaining open questions, approved scope, and reproducible fixture
  definitions are recorded. Tune numeric thresholds in T46 rather than inventing approved values.
- **Depends on:** none. **Source:** PRD §§4, 7, 10–12; all later acceptance gates.

## M1 — Foundation

### T01 — Establish application structure and runtime boundaries [M]

- [x] Create separate Commerce, pricing-platform, and React/Vite workspaces; use Python
  `venv`, Node >=20.19 (PRD preference: 22.x LTS), and local embedded storage only.
- **Done when:** services start on 8001/8000/5173; the browser accesses only the platform;
  architecture checks reject platform access to Commerce SQLite or Commerce implementation
  imports; modules use composition and stay under 400 LOC, targeting 300 or fewer.
- **Depends on:** T00. **Requirements:** FR-062; NFR-001, NFR-002, NFR-003, NFR-004,
  NFR-030, NFR-031, NFR-034.

### T02 — Define typed configuration, contracts, and safe runtime settings [M]

- [x] Add Pydantic environment validation, typed API/agent schemas, configuration-driven
  gateway role aliases, in-memory runtime secrets, and one corporate-CA/TLS helper.
- **Done when:** invalid settings fail with actionable errors; keys never enter persistent
  files, responses, logs, traces, or caches; insecure TLS is disabled by default, requires
  `ALLOW_INSECURE_TLS=true`, and emits boot/UI indicators. Any Node bypass is confined to
  the development proxy and absent from build output. All model traffic remains backend-only.
- **Depends on:** T01, T00 credential decision. **Requirements:** FR-072; NFR-011,
  NFR-016, NFR-017, NFR-018, NFR-019, NFR-020, NFR-022, NFR-032.

### T03 — Implement local persistence and migrations [M]

- [x] Add Commerce-owned catalog, sales, inventory, price book/history, and batch receipts;
  platform-owned run checkpoints, recommendation evidence, decisions, audit, scenarios,
  policy versions, learning state, and loop history; and a separate cache database.
- **Done when:** `commerce.db` is accessible only to Commerce; `app.db` and `llm_cache.db`
  are distinct WAL databases; transactions and schema migrations survive restart; evidence
  snapshots do not become a second authoritative catalog or sales store.
- **Depends on:** T01, T02, T00 ownership decision. **Requirements:** NFR-004, NFR-005,
  NFR-015, NFR-024; PRD §4.1.

### T04 — Generate seeded synthetic retail fixtures [M]

- [x] Generate at least a 500-SKU category with catalog families, historical transactions,
  inventory, competitor prices, seasonality, promotions, and known per-SKU elasticity.
- **Done when:** the same seed reproduces fixtures; sparse, stale, anomalous, conflicting,
  oscillating, and high-volatility cases are available; ground-truth elasticity is reserved
  for evaluation and does not leak into fitted-model inputs or recommendation prompts.
- **Depends on:** T03, T00 fixture definitions. **Requirements:** FR-001, FR-002.

### T05 — Expose Commerce HTTP endpoints and independent validation [M]

- [x] Implement health, catalog, sales, inventory, current prices, batch price writes,
  and price history. Define versioned records and per-item batch outcomes.
- **Done when:** endpoint contracts run against `commerce.db`; Commerce independently
  rejects invalid prices; every accepted write stores prior/new prices and a receipt;
  conflicting reuse of a batch key is rejected and exact replay applies no duplicate change.
- **Depends on:** T02, T03, T04; rule semantics from T00. **Requirements:** FR-051,
  FR-052, FR-053; NFR-026.

### T06 — Add cross-platform pre-flight and ordered startup [M]

- [x] Create `startup.sh` and `startup.bat` with venv, Node, environment, storage permissions,
  port, gateway-model/embedding availability, and Commerce health checks.
- **Done when:** Unix and Windows startup paths are exercised or any unavailable platform
  verification is recorded; failures name a remedy; Commerce starts before platform runs
  are accepted; model aliases are checked against actual gateway availability; corporate
  CA trust is attempted before an explicitly enabled bypass.
- **Depends on:** T01–T05. **Requirements:** FR-074, FR-075, FR-076; NFR-001, NFR-002,
  NFR-003, NFR-016, NFR-022, NFR-026; PRD §11 model/embedding/TLS checks.

- **Implementation evidence (2026-11-09):** Code and mocked gateway/pre-flight checks are implemented. Windows execution is recorded as unavailable; actual gateway alias availability remains unverified.
- **Follow-up evidence (2026-11-11):** Preview/grounded startup modes, readiness ordering,
  child environment and bounded cleanup are tested, including portable Windows-layout
  seams. Grounded startup checks advertised aliases and real local embeddings and repeats
  gateway verification inside the platform lifespan. Settings provides runtime model-list
  verification, invalidated on credential/alias changes. Live positive verification still
  requires the missing URL, key and four aliases; native Windows unavailability is recorded
  under this task's permitted unavailable-platform alternative.
- **Acceptance evidence (2026-11-12, Asia/Kolkata):** Actual
  `scripts.preflight.check(mode="grounded", skip_ports=True)` passes in 6.589s against
  an explicit loopback LiteLLM proxy, all four local role aliases, and fresh real MiniLM
  inference. Dependencies, Node, virtual environment and writable storage also pass.
  Existing services required skipping ports for this probe; the separate Unix startup
  already exercised port checks and Commerce → platform → Vite ordering. Native Windows
  remains unavailable, as permitted above. `data/local_grounded_preflight.json` records
  zero generations/writes, proxy cleanup and environment restoration. All four aliases
  map to one installed local model; corporate tiers are not certified. T06's catalog/
  startup gate is complete, while the failed generation probe leaves PRD A-01's working
  chat-model acceptance and the live release gates open.

## M2 — Analysis core

### T07 — Implement preprocessing and the data-quality gate [M]

- [x] Normalize and engineer features; handle missing values and outliers; check freshness,
  completeness, schema, referential integrity, and statistical anomalies.
- **Done when:** structured reports contain severity/counts and a blocking reason; failed
  data never reaches the numeric pipeline; degraded optional inputs are explicitly marked.
- **Depends on:** T04, T05, T00 quality policy. **Requirements:** FR-006, FR-007,
  FR-008, FR-011.

### T08 — Fit elasticity with intervals and sample eligibility [M]

- [x] Implement deterministic regression per SKU with sample count, confidence interval,
  fit diagnostics, and explicit insufficient-history outcomes.
- **Done when:** seeded synthetic cases recover price-response behavior within documented
  tolerances; missing price variation and sparse history cannot yield a confident estimate;
  ground truth is used only by the evaluation harness.
- **Depends on:** T07. **Requirements:** FR-012, FR-013, FR-014.

### T09 — Implement competitor and inventory analysis [M; optional scraper C]

- [x] Add `CompetitorFeed` with the synthetic adapter; compute competitor/market gaps,
  cover days, velocity, and stock flags. Keep live scraping disabled by default.
- **Done when:** feed replacement does not change callers; zero demand/stock and stale
  competitor data have typed outcomes; competitor freshness is available to confidence scoring.
- **Depends on:** T05, T07. **Requirements:** FR-004, FR-005, FR-015, FR-016.

### T10 — Build the shared Monte Carlo engine [M; stress tests S]

- [x] Sample upstream elasticity uncertainty, competitor response, cost drift, and seasonal
  variation for each candidate price. Emit demand/revenue/margin/cover distributions,
  variance, confidence bands, and probability of breaching the margin floor.
- [x] Add configurable iterations and demand-collapse, undercut, and cost-spike stress cases.
- **Done when:** fixed seed plus identical input/model/configuration reproduces numeric
  results, including parallel execution; changing the fitted elasticity changes forecasts;
  simulation runs off the async event loop. Record interval semantics and assumptions.
- **Depends on:** T08, T09, T00 simulation choices. **Requirements:** FR-080, FR-081,
  FR-082, FR-083, FR-084, FR-085, FR-086, FR-087; NFR-037, NFR-038.

### T11 — Optimize candidate distributions and aggregate impacts [M]

- [x] Optimize revenue-weighted, margin-weighted, or balanced objectives under price bounds,
  margin floors, elasticity, run constraints, and a damping limit supplied by T21.
- **Done when:** constraints are enforced deterministically; infeasible SKUs produce a
  reason instead of a fabricated price; SKU and run impact intervals are computed from
  samples with documented aggregation assumptions, not by summing interval endpoints.
- **Depends on:** T10, T21, T00 objective definitions.
- **Requirements:** FR-017, FR-018, FR-019, FR-020, FR-088.

### T12 — Implement the conventional baseline and evaluation harness [M]

- [x] Add cost-plus/category-discount pricing and a ground-truth optimum evaluator.
- **Done when:** baseline and AI evaluations use identical SKU sets, horizons, inputs,
  and outcome assumptions; metrics distinguish forecast comparisons from realized results;
  the baseline uses no AI reasoning or hidden elasticity ground truth.
- **Depends on:** T04, T10, T11. **Requirements:** FR-057; PRD §9.1 and §9.3.

### T13 — Compute inspectable confidence [M]

- [x] Derive scores from elasticity confidence/sample eligibility, simulation variance,
  quality, competitor freshness, and available forecast-error history.
- **Done when:** component contributions and confidence-model version are retained;
  sparse/stale/noisy input lowers eligibility rather than claiming certainty; banding
  consumes computed values and does not allow an LLM to raise eligibility.
- **Depends on:** T07–T10. Live error-history integration is completed in T29. **Requirements:** FR-021,
  FR-014, FR-109.

## M3 — Agent orchestration and grounding

### T14 — Build persistent retrieval and document ingestion [M; role breadth S]

- [x] Add local Chroma `PersistentClient`, local `all-MiniLM-L6-v2` embeddings, chunking,
  metadata, and the `pricing_policy`, `market_intel`, `product_kb`, `user_uploads` collections.
- **Done when:** chunks retain source IDs/version metadata; retrieval returns citable
  evidence; local embedding availability and any gateway fallback are explicitly checked;
  role breadth can be configured without allowing a bypass of mandatory grounding.
- **Depends on:** T02, T03, T06. **Requirements:** FR-038, FR-042, FR-044; NFR-004;
  PRD §4.4 and assumption A-03.
- **Evidence (2026-11-09):** all 123 backend tests pass; real local model download/checksum, 384-dimensional inference,
  synthetic-policy ingestion/retrieval, and `--require-embeddings` pre-flight pass. Automated
  tests cover all four collections, persistence across processes, immutable citations,
  idempotency, partial-index failure/retry, role limits, token budgets, model separation,
  and embedding contracts. Gateway availability is checked only when explicitly selected
  and opted in; its tests use a mock, and no live gateway access is claimed. No T15 browser
  upload feature or T16 grounded generation is included in this completion.

### T15 — Support runtime uploads and collection statistics [M]

- [x] Expose document ingestion status and document/chunk counts with last-updated time.
- **Done when:** uploads become retrievable without restart; failed/partial ingestion is
  visible; subsequent reasoning uses current uploaded context and its knowledge version.
- **Depends on:** T14. **Requirements:** FR-039, FR-040, FR-041.
- **Evidence (2026-11-09):** 167 backend tests and the TypeScript/production build pass.
  Runtime upload → ready status → updated corpus statistics → retrieval → citation lookup
  passed against the real local model in the same running app (2.489s). Tests cover version
  replacement/replay, historical citations, failed/partial publication, multipart body
  limits and truncation, temporary-file cleanup, safe errors, restart recovery, and owned
  workers. The global panel refreshes status/counts without restart. The retrieval path
  includes uploaded context and its current corpus version; actual grounded reasoning
  consumption remains T16. Browser visual QA was unavailable; build and targeted rendering
  checks passed. Source PRD and its approval status remain unchanged.

### T16 — Implement the sole grounded model entry point [M]

- [x] Route all chat-model use through `GroundedLLM`, LangChain `init_chat_model`, and
  configured LiteLLM aliases. Inject attributed retrieval; redact prompts; enforce typed
  `.with_structured_output(..., method="json_schema")`, one repair-retry, then typed failure.
- **Done when:** application-logic calls cannot parse raw model JSON; citations must resolve
  to supplied sources; automated import/call checks find no model bypass; missing required
  grounding never becomes uncited reasoning. Execution makes no LLM calls.
- **Depends on:** T02, T14, T15. **Requirements:** FR-023, FR-037, FR-040, FR-042,
  FR-043, FR-072; NFR-012, NFR-013, NFR-014, NFR-032, NFR-033; PRD §4.3.

### T17 — Implement Data & Context with concurrent ingestion [M; narration/degradation S]

- [x] Fetch Commerce data over HTTP and run sales, competitor, inventory, and retrieval
  paths concurrently; apply T07 and produce cited competitive synthesis.
- **Done when:** concurrency is observable; optional failure lowers confidence with a
  reason; required Commerce outage, unusable data, or mandatory-grounding failure halts
  clearly; quality reporting precedes results. Add business-language anomaly narration.
- **Depends on:** T05, T07, T09, T14, T16. **Requirements:** FR-003, FR-009, FR-010,
  FR-011, FR-077, FR-078, FR-079; NFR-007, NFR-026.

### T18 — Implement Quantitative and Strategy & Reasoning agents [M]

- [x] Connect regression → Monte Carlo → constrained optimization; generate grounded
  interpretation, assumptions, and rationale from deterministic results.
- **Done when:** recommendations contain current/proposed price, absolute/percent delta,
  impact intervals, confidence, and valid citations; model output cannot replace computed
  prices/intervals/scores. Compliance/band fields are finalized by T22.
- **Depends on:** T08, T10, T11, T13, T16, T17. **Requirements:** FR-020, FR-021,
  FR-022, FR-023; PRD §4.2 and §4.7.

### T19 — Orchestrate five nodes, checkpoints, and progress [M]

- [x] Add deterministic LangGraph edges, typed errors, SQLite checkpoints, progress
  streaming, and true per-item human approval interrupts before Execution.
- **Done when:** typed gate/execution fixtures demonstrate mixed-item interrupts,
  checkpoint/resume, inspectable node/terminal states, and stream reconnection. Real
  Validation, review, and Execution integration is accepted in T22, T24, and T28.
- **Depends on:** T03, T17, T18. **Requirements:**
  FR-061, FR-069; NFR-024, NFR-031; PRD §4.2.

## M4 — Compliance, stability, autonomy, and review

### T20 — Implement deterministic compliance and redaction gates [M; rule configuration S]

- [x] Add MAP, margin, maximum change, price-ladder, category-bound, and rounding rules;
  evaluated values and pass/fail records; configurable policies; personal-pricing rejection.
- **Done when:** violations block all approval/push routes in every mode; LLM violation
  explanations cannot change enforcement; manual candidates are checked identically;
  prompt/log/trace redaction covers sensitive data and secrets.
- **Depends on:** T02, T03, T16; T00 final rule definitions. **Requirements:** FR-030,
  FR-031, FR-032, FR-033, FR-034, FR-035, FR-036, FR-037; NFR-012, NFR-013, NFR-040.

### T21 — Detect instability, apply damping, and expose convergence [M; cooldown S]

- [x] Detect directional reversals, recent-price returns, historical/category anomalies,
  forecast-error trends, and configurable per-SKU minimum change intervals. Supply damping
  bounds before final optimization and validate the final price again.
- **Done when:** ping-pong fixtures produce a retained oscillation flag for band assignment;
  damping constrains the selected move without clearing the incident; widening error is
  visible; signals and parameters are persisted. Missing realized data is shown as pending.
- **Depends on:** T05, T10. Validate convergence calculations with fixture error series;
  live outcome integration is completed in T29. **Requirements:**
  FR-088, FR-090, FR-091, FR-092, FR-093, FR-094, FR-095, FR-110.

### T22 — Assign bands with threshold evidence [M]

- [x] Implement Escalate-first deterministic banding, then all Auto-approve eligibility
  checks, otherwise Review; support runtime threshold configuration.
- **Done when:** exactly one band and all relevant reasons/actual values/thresholds are
  persisted; each of the five escalation triggers independently prevents automatic approval;
  compliance violations have no override path. Band and execution disposition remain distinct.
- **Depends on:** T13, T18, T20, T21. **Requirements:** FR-022, FR-089, FR-096,
  FR-099, FR-100; NFR-040.

### T23 — Implement operating modes, hold windows, and kill switch [M]

- [x] Default to Supervised; implement Assisted automatic eligibility and Autonomous Review
  hold/release; audit transitions. Kill stops the loop, cancels pending automatic pushes,
  and resets mode to Supervised atomically with respect to dispatch authorization.
- **Done when:** the three-mode/three-band policy matrix and dispatch-fence contract checks
  pass; Escalate always needs human intervention; stale automatic intents are canceled.
  Actual HTTP dispatch and loop integration are accepted in T28 and T39, including visible
  reconciliation of requests already sent when kill occurs.
- **Depends on:** T03, T22. **Requirements:**
  FR-101, FR-102, FR-103, FR-104; NFR-039, NFR-040; PRD W2.

### T24 — Implement human decisions and server-side review validation [M]

- [x] Add approve/reject, price override with mandatory reason, and written human override
  for an escalation with a clean compliance verdict; retain immutable recommendation
  revisions and revalidate final prices.
- [x] Enforce bulk approval only for actual Review-band items above the confidence threshold
  with clean compliance. An Auto-approve-band item queued by Supervised mode keeps its band.
- **Done when:** stale/conflicting decisions fail explicitly; no UI/API route bypasses
  compliance; human approvals resume graph interrupts; human/system actors are distinguishable.
- **Depends on:** T19, T20, T22, T23. **Requirements:** FR-024, FR-025, FR-026,
  FR-033, FR-096, FR-097; NFR-040; PRD W2.

### T25 — Implement append-only audit evidence [M; export S]

- [x] Record inputs/evidence versions, all five agents, distributions, rule evaluations,
  stability, band reasons, approvals/overrides, actor/mode, push attempts, and results.
- **Done when:** records cannot be edited/deleted through application routes; per-SKU chains
  reconstruct decisions; system-only filtering and export work without exposing secrets;
  evidence never substitutes for authoritative Commerce data.
- **Depends on:** T03, T19, T20, T22, T23, T24. **Requirements:** FR-035, FR-054,
  FR-058, FR-059, FR-060, FR-095, FR-097, FR-103, FR-104, FR-114; NFR-015.

### T26 — Build review queue, recommendation details, and family ladder [M; details/ladder S]

- [x] Implement filters/sorts by band, impact, confidence, delta, compliance, and category;
  approve/reject/override and eligible bulk actions; expose thresholds and evaluated values.
- **Done when:** keyboard navigation works at 1280px; bands have labels/shapes; auto-approved
  items remain visible; details expose inputs and citations; product-family ladders show breaks.
- **Depends on:** T01 UI scaffold, T19, T24, T25. **Requirements:** FR-009, FR-022,
  FR-024, FR-025, FR-026, FR-027, FR-028, FR-070, FR-096, FR-097, FR-118.

- **Implementation evidence (2026-11-09):** Review filters/actions, revision checks, evidence/ladder views, and native keyboard controls are implemented. SSR/safety checks and build pass; actual 1280px keyboard/browser interaction verification was completed by the November 17 Chromium suite; see docs/browser-qa.md.

## M5 — Commerce execution, feedback, and simulation

### T27 — Integrate idempotent batch pushes and ambiguous-result recovery [M]

- [x] Implement the HTTP Commerce adapter with persisted batch keys, item receipts,
  independent rejection reasons, bounded transport recovery, and current-price/version checks.
- **Done when:** exact replay is a no-op; partial success is first-class; timeouts after
  possible commit reconcile using the original key; retries do not create a second price change.
- **Depends on:** T05, T20, T24, T25. **Requirements:** FR-051, FR-052, FR-053,
  FR-054; NFR-026, NFR-040.

### T28 — Complete deterministic Execution and compliant revert [M]

- [x] Route human and automatic approvals through one dispatch path, rechecking approval,
  compliance, mode/cancellation state, cooldown, and source-price validity before push.
- [x] Add one-action revert from pushed prices using stored prior price and a new linked,
  idempotent change; surface any current compliance failure instead of bypassing it.
- **Done when:** no Execution LLM call exists; applied/rejected/unknown outcomes are visible
  per SKU; auto changes retain prior prices; retries, kill, manual intervention, and restart
  cannot produce unauthorized pushes. Exercise the graph end to end.
- **Depends on:** T19, T23, T24, T25, T27; T00 revert decision. **Requirements:**
  FR-033, FR-053, FR-054, FR-097, FR-098, FR-102; NFR-039, NFR-040.

### T29 — Read realized outcomes and compute forecast error [M]

- [x] Fetch post-push aggregate sales over HTTP; align observation windows with forecasts
  and the baseline; persist provenance, completeness, per-SKU error, and convergence series.
- **Done when:** missing/immature outcomes are pending rather than zero; repeated readback
  does not double-count observations; both SKU and run forecasts compare to actuals; later
  confidence scores consume available error history.
- **Depends on:** T12, T13, T21, T28. **Requirements:** FR-055, FR-056, FR-092,
  FR-109, FR-110.

### T30 — Refine elasticity and uncertainty with bounded learning [M]

- [x] Update estimates using new post-price-change evidence; calibrate Monte Carlo inputs
  from forecast residuals; cap and log estimate changes with before/after model versions.
- **Done when:** subsequent runs consume learned state; stale/duplicate data cannot update
  twice; good evidence can tighten calibrated intervals without forcing unjustified narrowing;
  widening error triggers a warning; updates remain inspectable and reproducible.
- **Depends on:** T08, T10, T13, T29; T00 update-cap decision. **Requirements:**
  FR-107, FR-108, FR-109, FR-110, FR-111.

### T31 — Expose shared-engine what-if scenarios [M; saving/narration/stress S]

- [x] Support arbitrary one/many-SKU prices and configurable horizons through T10; return
  demand/revenue/margin/cover distributions, explicit assumptions, and margin-breach probability.
- [x] Add saved/named scenarios, side-by-side AI/baseline comparisons, grounded narration,
  and stress presets without mutating the live price book.
- **Done when:** matched scenario/recommendation inputs and seed yield matched numeric
  forecasts; inputs, assumptions, and versions are retained; no scenario becomes an approval.
- **Depends on:** T10, T12, T16, T18, T20. **Requirements:** FR-045, FR-046, FR-047,
  FR-048, FR-049, FR-050, FR-085, FR-105, FR-106.

### T32 — Build simulation distribution and comparison views [M; S capabilities follow T31]

- [x] Add candidate/horizon controls, uncertainty plots, margin-risk display, assumptions,
  AI/baseline comparisons, saved-scenario controls, and stress-mode controls.
- **Done when:** confidence bands are readable in both themes; empty/failed scenarios have
  explicit states; results never appear as unexplained point estimates; single-SKU latency
  is verified in T46.
- **Depends on:** T31, T33 theme tokens. **Requirements:** FR-045, FR-046, FR-047,
  FR-048, FR-049, FR-050, FR-106, FR-119; NFR-010.

- **Implementation evidence (2026-11-09):** One/many-SKU simulation, comparisons, saving, stress, and narrative controls are implemented. Numerical scenario latency is measured; both-theme browser visual verification was completed by the November 17 Chromium suite; see docs/browser-qa.md.

## M6 — UI completion

### T33 — Complete the application shell and persistent global controls [M]

- [x] Add React Router, Tailwind semantic tokens/CSS variables, Lucide icons, and persisted
  light/dark preference. Provide a global header and common pending/error/progress states.
- **Done when:** there are no UI emojis; header survives route changes; charts and bands
  work in both themes; ordinary interactions target <500ms with progress for long work.
- **Depends on:** T01, T02. **Requirements:** FR-062, FR-063, FR-064, FR-118,
  FR-119; NFR-009.

- **Implementation evidence (2026-11-09):** The persistent shell, Router, vector icons, theme tokens/preference, and common states are implemented. Browser-rendered contrast and sampled <=500ms UI interaction measurement passed in the November 17 Chromium suite; see docs/browser-qa.md.

### T34 — Add runtime gateway settings and LLM monitor [M]

- [x] Add the global gear drawer with URL/port/key inputs, iOS-style disable-verification
  toggle, and live cache stats; show active calls, input/output tokens, and estimated cost
  in the header, with LiteLLM fallback rates for unpriced models.
- **Done when:** changes apply without restart through validated server settings; browser
  handling follows the resolved credential decision; secrets never return from settings APIs;
  TLS indicators persist when bypass is active; monitor survives failed calls.
- **Depends on:** T02, T16, T33, T40, T41. **Requirements:**
  FR-065, FR-066, FR-067, FR-073; NFR-011, NFR-019, NFR-029.

### T35 — Build the universal grounding panel [M]

- [x] Add runtime document upload, ingestion status, per-collection counts/update time,
  and source inspection through platform APIs.
- **Done when:** the panel is globally available; newly uploaded context affects a subsequent
  grounded recommendation without restart; ingestion failures are actionable.
- **Depends on:** T15, T33. **Requirements:** FR-039, FR-040, FR-041, FR-068.

### T36 — Build impact, baseline, stability, and autonomy dashboards [M]

- [x] Show forecast/realized revenue and margin, acceptance, AI/baseline comparisons,
  oscillation/damping/error trends, bands, auto-approve share, escalation causes, and mode history.
- **Done when:** metrics identify scope, horizon, denominator, and forecast/realized status;
  missing feedback is visible; widening error warns; auto decisions remain inspectable.
- **Depends on:** T12, T21, T22, T25, T29, T30, T33. **Requirements:** FR-056,
  FR-057, FR-092, FR-097, FR-110, FR-112, FR-113; PRD §9.

### T37 — Build run history and the audit timeline [M; export S]

- [x] Show run status, duration, token cost, outcome, live nodes, complete SKU evidence,
  rules, approvals, and push results; add automatic-only filter and audit export.
- **Done when:** a reviewer can reconstruct a human or automatic price change from cited
  inputs to Commerce receipt, including partial failures; exporting cannot change history.
- **Depends on:** T19, T25, T28, T33, T41. **Requirements:** FR-058, FR-059,
  FR-060, FR-061, FR-069, FR-114.

### T38 — Add persistent mode, kill, and loop controls [M]

- [x] Put current mode and its switch in the global header; provide a distinct kill
  switch with exactly one confirmation; add loop start/stop, interval/scope, count,
  countdown, decisions, and a running indicator across every route.
- **Done when:** backend acknowledgement updates state; kill clears pending automatic work
  and shows Supervised; unavailable/disconnected controls do not claim success; loop
  indicators reflect server state. Verify full loop behavior after T39.
- **Depends on:** T23, T33, T39. **Requirements:**
  FR-101, FR-102, FR-115, FR-116, FR-117, FR-120.

- **Acceptance evidence (2026-11-11):** [Actual React DOM interactions](docs/ui-acceptance.md)
  verify pending/acknowledged mode changes, exactly one halt confirmation, cancel/error paths,
  acknowledged Supervised/Loop off, scope/constraints, iteration counts, stop acknowledgement,
  and disconnected controls. Backend governance/loop tests verify actual cancellation and
  dispatch fencing. These satisfy this task's functional criteria without claiming browser
  pixels, viewport layout or render latency; those remain T26/T32/T33/T46 gates.

## M7 — Continuous loop and hardening

### T39 — Implement the lifespan-managed interval loop [M; iteration cap S]

- [x] Add UI-triggered loop start/stop and persisted sessions/iterations/decisions. Run the
  full pipeline per iteration using current policy/mode; prohibit overlapping iterations.
- [x] Keep scheduling off at every boot, stop on any failed iteration with visible error,
  support a configurable session cap, and stop/checkpoint cleanly on shutdown or kill.
- **Done when:** restart never restarts scheduling or timers automatically; queued review
  items are distinguished from a failed iteration; failure cannot silently schedule another
  iteration; stale/manual/loop runs cannot race prices; explicit stopped/failed states are audited.
- **Depends on:** T19, T23, T28, T29. UI integration is accepted in T38. **Requirements:** FR-102, FR-117, FR-120,
  FR-121, FR-122, FR-123, FR-124, FR-125, FR-126, FR-127; NFR-023, NFR-035, NFR-036.

### T40 — Add persistent exact and semantic LLM caching [M]

- [x] Implement two-tier caching in `llm_cache.db` with hit/miss statistics and validated
  response reuse. Include model, schema/prompt, role, evidence/knowledge, numeric input,
  and relevant policy versions in cache eligibility; never store API keys.
- **Done when:** changed price/policy/upload inputs cannot reuse stale decisions or citations;
  semantic reuse is limited to equivalent verified contexts; exact/semantic hits remain typed
  and grounded; stats reach settings; cached responses meet <100ms in T46.
- **Depends on:** T03, T15, T16. **Requirements:** FR-073; NFR-005, NFR-008, NFR-011.

### T41 — Add redacted tracing and nonblocking cost telemetry [M]

- [x] Emit structured `structlog` events, Langfuse callbacks, and an always-on local JSONL
  sink for node/tool/model latency, tokens, model, cache outcome, and run/agent cost.
- **Done when:** local traces survive Langfuse egress failure; sales data/prompts are not
  sent to an external telemetry sink contrary to NFR-014; secrets/PII are redacted;
  broken telemetry never fails pricing or blocks dispatch/progress.
- **Depends on:** T02, T16, T19, T40. **Requirements:** FR-061, FR-065; NFR-012,
  NFR-014, NFR-025, NFR-027, NFR-028, NFR-029.

### T42 — Harden retries, cancellation, and recovery [M]

- [x] Add bounded exponential backoff for gateway 429/500/502/503/504; handle SIGINT/SIGTERM
  by stopping new work, checkpointing runs, flushing telemetry, and closing SQLite.
- **Done when:** interruption at analysis, review, and ambiguous Commerce commit recovers
  without lost audit or duplicate writes; resumed automatic work requires fresh execution
  authorization; gateway call retries do not turn a failed loop iteration into a silent retry.
- **Depends on:** T19, T27, T28, T39, T41. **Requirements:** NFR-021, NFR-023,
  NFR-024, NFR-025, NFR-026, NFR-035, NFR-036.

### T43 — Expose bounded A2A interoperability [S]

- [x] Add `/.well-known/agent-card.json` and JSON-RPC `message/send` / `tasks/get`.
- **Done when:** advertised capabilities match implementation; external calls share the
  same grounding, compliance, review, and idempotency paths; no unrequested full task
  lifecycle or agent negotiation is introduced.
- **Depends on:** T19, T24, T28, T42. **Requirements:** FR-071; PRD §4.6.

### T44 — Implement optional discovery interfaces [C]

- [x] Add natural-language recommendation queries using the grounded router/model path;
  implement the optional live competitor adapter behind an explicit disabled-by-default flag.
- **Done when:** chat cannot approve or push via an alternate route; the synthetic demo
  remains reliable when live scraping is unavailable; shared feed contracts remain unchanged.
- **Depends on:** T09, T16, T26; any required optional-source availability. **Requirements:**
  FR-005, FR-029. These are C features and do not block must-have acceptance.

### T45 — Run the release correctness and safety suite [M]

- [x] Automate the golden path; failed quality/grounding; structured-output repair and typed
  failure; every compliance rule in every mode; all band boundaries; bulk/override rules;
  partial success; idempotent replay; single-engine simulation; numeric seed reproducibility;
  kill versus dispatch/hold timers; loop failure/boot behavior; and interruption/recovery.
- [x] Enforce HTTP/DB ownership boundaries, the sole model wrapper, secret redaction,
  no Execution LLM, module separation, and the 400-LOC source-file ceiling.
- **Done when:** acceptance fixtures demonstrate zero violating Commerce writes, zero
  duplicate writes, zero automatic-path verification omissions, zero continuing loop
  iterations after failure, and complete valid citations for generated recommendations.
  Record results rather than assuming success from document coverage.
- **Depends on:** T20–T30, T39–T42; T43/T44 only when included. **Requirements:**
  FR-011, FR-023, FR-033, FR-043, FR-052, FR-087, FR-102, FR-124;
  NFR-030, NFR-031, NFR-033, NFR-034, NFR-036, NFR-039, NFR-040; PRD §9.2.

### T46 — Benchmark, calibrate, and report product effectiveness [M]

- [ ] Measure a 500-SKU run <5 minutes, Monte Carlo <60 seconds, cached responses <100ms,
  ordinary UI actions <=500ms, and a single-SKU
  scenario <=5 seconds on recorded hardware. Observe progress responsiveness under CPU load.
- [ ] Tune iterations, oscillation window/reversal threshold, damping, confidence/delta/
  volatility/margin bands, hold window, and nonoverlapping loop interval. Record every
  value/version and the simulation accuracy/runtime trade-off.
- [ ] Evaluate forecast uplift >=5%, no margin degradation, high-confidence price error
  <=10% against ground truth, acceptance >=70%, Assisted auto-approval >=60%, escalation
  precision >=80% with human labels, forecast interval coverage >=80%, oscillation <2%,
  and narrowing forecast error. Document denominators and observation sufficiency.
- [ ] Measure repeated-run cache hits >=40% and post-repair structured-output validity
  >=99%. Demonstrate conflicting signals and degraded-history behavior alongside the baseline.
- **Done when:** reproducible results, failures/limitations, and resolved threshold decisions
  are recorded; no metric is achieved by weakening compliance or forcing narrow intervals.
  Product targets requiring repeated outcomes/human labels remain unverified until observed.
- **Depends on:** T12, T13, T30, T32, T36, T39, T40, T41, T45.
- **Requirements:** FR-021, FR-057, FR-083, FR-087, FR-100, FR-110;
  NFR-006, NFR-007, NFR-008, NFR-009, NFR-010, NFR-037, NFR-038; PRD §9 and §11.
- **Evidence (2026-11-10):** [validation](docs/validation.md) records numerical, real-local-RAG
  cache, scenario and five-node model-fixture timings. [Calibration](docs/calibration.md)
  records independent-seed threshold tradeoffs and failed targets without changing policy.
  Live gateway validity/latency, Windows/browser acceptance and mature human/realized
  metrics remain open; no fixture result is substituted for those observations.
- **Follow-up (2026-11-11):** The original revenue target is infeasible for the recorded
  fixtures: relaxed legal forecast-grid maxima remain 2.951% / 3.269% below the raw
  baseline; even a projected compliant-baseline counterfactual permits at most 2.494% /
  2.195% pure-revenue uplift. Selection-confidence correction reduces overconfidence but
  nine high-confidence price errors remain per seed. Latest cache p95 is 25.40ms but its
  124.92ms maximum under concurrent load misses a strict all-hits <100ms interpretation.
  See [the proof and preserved denominators](docs/effectiveness-feasibility.md). Product-owner
  evaluation decisions and actual human/realized data are required; this gate stays open.

### T47 — Complete operator documentation and demonstrate release scope [M]

- [x] Document startup on supported platforms, configuration/model aliases, CA trust and
  bypass controls, secret lifecycle, data generation, thresholds, checkpoints/resume,
  loop start/stop/failure, kill/revert semantics, telemetry fallback, and recovery.
- [x] Record owner approval for the explicitly scoped engineering demonstration, retaining
  failed and unobserved business targets. User approval is recorded in the November 17 release packet.
- [ ] Demonstrate full-PRD W1–W9 acceptance: generated run, banded review, what-if, upload grounding, partial
  push/replay/revert, realized feedback/learning, audit reconstruction, runtime settings,
  and explicit-start continuous loop with failure stop. Show Supervised by default.
- **Local demonstration evidence (2026-11-11):** The isolated runner covers all nine
  workflows with 56 passing cases, real HTTP/graph/storage paths, declared model/embedding
  fixtures and a simulated mature-outcome clock. Source hash and JUnit cases are retained.
  The full release demonstration remains open because real gateway generation, native UI
  checks and effectiveness acceptance are not supplied by those fixtures.
- **Done when:** every included M/S/C requirement has implementation and validation evidence;
  unmet targets and deferred S/C features are listed; the owner records release readiness.
  If time compresses, any cut to M feedback or Autonomous mode is a PRD amendment, not an
  unchecked task silently relabeled optional. Preserve Monte Carlo, banding, and compliance.
- **Depends on:** T06, T26, T28, T30, T32, T34–T42, T45, T46; T43/T44 if selected.
- **Requirements:** FR-074, FR-075, FR-076; all included requirements; PRD §§3, 8–12.

## Milestone acceptance and scheduling

| Milestone | Exit evidence | Main dependency |
|---|---|---|
| M1 | Both services and UI start; synthetic data and pre-flight work; service boundary holds. | T00–T06 |
| M2 | Elasticity → Monte Carlo → optimizer executes deterministically; baseline is comparable. | T07–T13; damping finalized in M4 |
| M3 | Five-node graph, concurrent ingestion, mandatory grounding, typed outputs, and checkpoints work. | T14–T19; gates/execution finalized in M4/M5 |
| M4 | Compliance veto, stability signals, correct bands/modes, review interrupts, and audit evidence work. | T20–T26 |
| M5 | Unified human/automatic push, partial failures, replay/revert, realized feedback, and shared-engine scenarios work. | T27–T32 |
| M6 | Required global controls, settings, RAG panel, themes, dashboards, and run/audit views are usable. | T33–T38; live backend data from M7 |
| M7 | Explicit-start loop, cache, telemetry, recovery, tests, performance, and demo evidence are complete. | T39–T47 |

Milestones are integration checkpoints. Their original PRD order does not imply all
implementation must be serial: build the UI shell early, start numeric benchmarking once
T10 exists, and implement telemetry/cache before final UI integration. Where the PRD places
a dashboard or control before its backing data is ready, complete the contract first and
accept the end-to-end feature only after its dependencies land. No duration estimates are
asserted because team capacity, gateway latency, and the hackathon deadline are unspecified.
