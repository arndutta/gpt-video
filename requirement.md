# Requirements Specification

| Field | Value |
|---|---|
| Product | AI-Driven Dynamic Pricing Engine for Retail |
| Status | Draft for review; does not approve or amend the PRD |
| Prepared | 2026-11-08 |
| Source | [prd.md](prd.md), version 1.1, dated 2026-08-07 |
| Related documents | [design.md](design.md), [task.md](task.md) |

## 1. Authority, scope, and priorities

This specification translates the PRD into a build and acceptance reference. The requirement registers below preserve all 127 functional requirements and 40 non-functional requirements, including their original IDs, wording, and priorities. Source section numbers are retained in register subheadings for traceability. **M** means must-have for the demo, **S** should-have, and **C** could-have; the PRD assigns no separate priorities to NFRs. Acceptance checks explain how to verify existing requirements; they do not introduce new product scope. Individual priority rows are retained where the UI subsection introduction says all items are must-have despite FR-070 being S; that inconsistency requires clarification.

Only the PRD was supplied as source material. Its referenced problem statement, master prompt, architecture document, and Phase 1 decision log are unavailable; this document relies on what the PRD records about them. The PRD remains marked awaiting approval. These requested documents are reviewable drafts, and no approval or implementation completion is implied.

Build a single-user desktop web platform that turns SKU-level retail data into deterministic, uncertainty-aware price recommendations, explains them with grounded AI reasoning, applies absolute compliance controls, and sends approved changes to a separate local Commerce Service. Include scenario simulation, banded autonomy, audit, realized-outcome learning, and an explicitly started continuous loop.

### 1.1 Users and needs

| Persona | Need |
|---|---|
| P1 — Priya, Pricing Manager | Set objectives and autonomy policy; review exceptions, push or revert prices, measure business impact. |
| P2 — Marco, Category Merchandiser | Inspect competitor positioning and product-family price ladders. |
| P3 — Aisha, Pricing Analyst | Inspect elasticity assumptions and uncertainty; compare and stress-test scenarios; track forecast improvement. |
| P4 — Ravi, Compliance Officer | Reconstruct rules, evidence, actors, modes, and outcomes for every price decision. |
| P5 — Sam, Platform Engineer | Configure gateway connectivity and observe health, cost, cache, and failures. |

Consumers are not users. Consumer-level data, personal pricing, and PII are excluded.

### 1.2 Required boundaries and invariants

- Commerce Service on port 8001 owns catalog, transactions, inventory, and the live price book in `commerce.db`. The Pricing AI Platform on port 8000 accesses business data exclusively over HTTP; no shared database or direct cross-service imports. The React/Vite UI on port 5173 contacts only the platform.
- Exactly five LangGraph agents: Data & Context; Quantitative; Strategy & Reasoning; Validation & Compliance; Execution. Deterministic edges and SQLite checkpoints support inspectable, resumable runs and a true graph interrupt for human approval.
- The mandatory modelling order is deterministic elasticity regression → Monte Carlo consuming that estimate → constrained optimization over the resulting distributions. An LLM never computes the authoritative price, enforces a rule, or participates in execution.
- Every LLM call uses the sole `GroundedLLM` entry point and LangChain `init_chat_model` through the LiteLLM gateway. Role aliases are configuration-driven and verified at boot: router/narrator use flash-lite, analyst uses flash, strategist uses pro; local `all-MiniLM-L6-v2` supplies embeddings with the PRD's gateway fallback assumption.
- Application-logic model calls use `.with_structured_output(Model, method="json_schema")`, one validation-error repair retry, then a typed failure. Raw `json.loads` of model output is prohibited.
- ChromaDB uses an in-process `PersistentClient` with `pricing_policy`, `market_intel`, `product_kb`, and `user_uploads` collections. Source identifiers and non-empty validated recommendation citations are mandatory. Retrieval breadth may vary by role.
- Compliance veto is absolute. Autonomy changes the approving actor only. Every accepted price follows the same checks and deterministic execution path, including overrides and reversals. Supervised routing sends Auto-approve items to human review without changing their assigned band; Review-only bulk approval does not extend to them.
- Supervised is the default. The loop is off at every boot; resuming a checkpoint must not silently restart the loop or pending automatic work.

## 2. Functional requirement register

### 5.1 Data ingestion and quality

| ID | Requirement | Priority |
|---|---|---|
| FR-001 | Generate a synthetic retail dataset: catalog, sales transaction history, inventory, competitor prices, with realistic seasonality, promotions, and category structure. | M |
| FR-002 | Synthetic sales history must embed **known ground-truth elasticity per SKU**, enabling objective accuracy measurement (Section 9). | M |
| FR-003 | Ingest catalog, sales, inventory, and current prices from the Commerce Service over HTTP. | M |
| FR-004 | Ingest competitor prices through a pluggable `CompetitorFeed` interface; synthetic implementation is the demo path (D14). | M |
| FR-005 | Live competitor scraping available as an optional adapter behind the same interface, disabled by default. | C |
| FR-006 | Preprocessing: normalization, outlier detection, missing-value handling, feature engineering. | M |
| FR-007 | Data quality checks: freshness, completeness, schema conformance, referential integrity, statistical outliers. | M |
| FR-008 | Each check emits a structured verdict with severity and affected record counts. | M |
| FR-009 | Present a data quality report in the UI before run results. | M |
| FR-010 | Data & Context Agent narrates anomalies in business language. | S |
| FR-011 | **A failing quality gate halts the run** with a specific, actionable reason. The system must never price on data it has judged unfit. | M |
| FR-077 | Data & Context Agent executes sales retrieval, competitor fetch, inventory computation, and RAG retrieval as **concurrent** operations within a single node. | M |
| FR-078 | Data & Context Agent produces the grounded competitive-positioning synthesis with citations (absorbing the function of the former Competitive Intelligence agent). | M |
| FR-079 | A failure in any one concurrent ingestion path degrades gracefully: the run continues with reduced inputs and the affected analyses are marked lower-confidence, unless the quality gate fails outright (FR-011). | S |

### 5.2 Analysis, uncertainty, and optimization

| ID | Requirement | Priority |
|---|---|---|
| FR-012 | Estimate price elasticity per SKU from sales history using deterministic regression. | M |
| FR-013 | Report elasticity as a **confidence interval, not a point estimate**, with the underlying sample size. | M |
| FR-014 | Flag SKUs with insufficient history and exclude them from confident recommendation. | M |
| FR-080 | Monte Carlo simulation produces a revenue and margin **distribution** for each candidate price, sampling over the elasticity confidence interval from FR-012/FR-013. | M |
| FR-081 | **The simulation must consume the upstream elasticity estimate.** An implementation that samples only historical sales variance does not satisfy this requirement — see §4.7. | M |
| FR-082 | Sample over at least: elasticity uncertainty, competitor price response, cost drift, and seasonal variation. | M |
| FR-083 | Iteration count is configurable, with a default balancing accuracy against the runtime budget in NFR-006. | M |
| FR-084 | Emit per-candidate-price variance and confidence bands, consumed by the autonomy band assignment (FR-089). | M |
| FR-085 | Report the **probability of falling below the margin floor** for each candidate price. | M |
| FR-086 | Stress-test mode simulates extreme conditions — demand collapse, aggressive competitor undercut, cost spike — and reports downside exposure. | S |
| FR-087 | Simulation is reproducible: a fixed seed yields identical results, so runs are auditable. | M |
| FR-015 | Compute competitive position: price gap vs. each tracked competitor and vs. market index. | M |
| FR-016 | Compute inventory pressure: cover days, sell-through velocity, overstock/stockout flags. | M |
| FR-017 | Deterministic constrained optimizer maximizing the selected objective **over the Monte Carlo distributions**, subject to margin floor, price bounds, and elasticity. | M |
| FR-018 | Support objectives: revenue-weighted, margin-weighted, balanced. | M |
| FR-019 | Optimizer accepts run-scoped constraints (max change %, category floors/ceilings). | M |
| FR-020 | Produce forecast revenue and margin impact per SKU and aggregated per run, **each with a confidence interval**. | M |
| FR-021 | Every recommendation carries a confidence score derived from elasticity confidence, simulation variance, data quality, and competitive data freshness. | M |
| FR-088 | Optimizer respects the damping constraint from FR-091 to prevent oscillation. | M |

### 5.3 Recommendation, explanation, review

| ID | Requirement | Priority |
|---|---|---|
| FR-022 | Each recommendation states: recommended price, current price, delta (absolute and %), forecast impact **with confidence interval**, confidence score, rationale, citations, compliance verdict, and **autonomy band**. | M |
| FR-023 | Rationale must be grounded and cite retrieved sources; ungrounded recommendation text is rejected at validation (D6). | M |
| FR-024 | Review queue supports approve, reject, and override per item; bulk-approve permitted **only** within the Review band, above a confidence threshold, with clean compliance status. | M |
| FR-025 | Override requires a mandatory reason and is **re-validated by the compliance engine** before acceptance. | M |
| FR-026 | Queue sortable and filterable by **band**, impact, confidence, delta, compliance status, category. | M |
| FR-027 | Surface the price-ladder view within a product family, highlighting breaks. | S |
| FR-028 | Recommendation detail view exposes every input the decision used. | S |
| FR-029 | Conversational interface for querying recommendations in natural language. | C |
| FR-096 | Each recommendation displays **the specific reason** for its band assignment — which condition failed, with the threshold and the actual value. | M |
| FR-097 | Auto-approved recommendations remain fully visible and auditable after the fact; automatic approval never means invisible. | M |
| FR-098 | Auto-approved pushes are reversible: the user can revert a SKU to its prior price in one action. | M |

### 5.4 Compliance, stability, and autonomy

| ID | Requirement | Priority |
|---|---|---|
| FR-030 | Deterministic rule engine evaluates every recommendation. **No LLM in the enforcement path** (D7). | M |
| FR-031 | Ship rules: MAP floor, margin floor, maximum change %, price-ladder consistency, category price bounds, round-number policy. | M |
| FR-032 | Rules are configurable without code changes. | S |
| FR-033 | A violation **blocks** the recommendation. It cannot be force-pushed, overridden, or auto-approved — **in any operating mode**. | M |
| FR-034 | LLM generates a human-readable explanation of each violation — explanation only, never enforcement. | M |
| FR-035 | Every rule evaluation is persisted with pass/fail and evaluated values for audit. | M |
| FR-036 | System refuses to produce individual-level or personalized prices (D8). | M |
| FR-037 | Guardrail against sensitive-data leakage into prompts, with automatic redaction. | M |
| FR-090 | Detect oscillation by examining each SKU's price history across runs — direction reversals within a configurable window, and repeated returns to a recent price point. | M |
| FR-091 | Apply **damping** to recommendations for SKUs showing oscillation: constrain the permitted move toward the recommended price rather than allowing the full step. | M |
| FR-092 | Track convergence per SKU and per run: the delta between forecast and realized uplift should narrow across iterations. A widening delta raises a visible warning. | M |
| FR-093 | Detect anomalous recommendations statistically — prices far outside the SKU's own historical distribution or its category peers — independent of whether any compliance rule fired. | M |
| FR-094 | Enforce a per-SKU minimum interval between price changes, configurable, to protect customer-visible price stability. | S |
| FR-095 | Persist stability signals with the recommendation so oscillation and convergence history are auditable. | M |
| FR-089 | Assign every recommendation exactly one band — Auto-approve, Review, or Escalate — per the conditions in §3 W2, evaluated deterministically. | M |
| FR-099 | Escalate is triggered by any of: compliance violation, price within the margin-proximity buffer, Monte Carlo variance beyond the volatility limit, oscillation flag, or market conditions outside historical norms. | M |
| FR-100 | Band thresholds (confidence, delta, variance, margin buffer) are configurable without code changes. | M |
| FR-101 | Global operating mode — Supervised, Assisted, Autonomous — governs which bands may push automatically. **Supervised is the default.** | M |
| FR-102 | A **kill switch** halts the loop, cancels pending automatic pushes, and reverts the mode to Supervised in a single action. | M |
| FR-103 | Mode changes and kill-switch activations are audited with actor, timestamp, and prior state. | M |
| FR-104 | The mode in force at decision time is recorded on every recommendation, so historical decisions remain interpretable after the mode changes. | M |

### 5.5 RAG and grounding

| ID | Requirement | Priority |
|---|---|---|
| FR-038 | Ingest documents into ChromaDB with chunking, local embedding, and metadata. | M |
| FR-039 | UI panel displays per-collection embedding statistics (document count, chunk count, last updated). | M |
| FR-040 | Uploaded documents become mandatory grounding context for subsequent reasoning calls. | M |
| FR-041 | Upload and embed documents at runtime without restart. | M |
| FR-042 | Retrieved context is attributed with source identifiers usable as citations. | M |
| FR-043 | No LLM call may bypass the `GroundedLLM` wrapper; enforced by automated check. | M |
| FR-044 | Retrieval breadth configurable per agent role. | S |

### 5.6 Scenario simulation

| ID | Requirement | Priority |
|---|---|---|
| FR-045 | What-if simulation for arbitrary candidate prices across one or many SKUs. | M |
| FR-046 | Project demand, revenue, margin, and stock cover over a configurable horizon. | M |
| FR-047 | Present results as **distributions with explicit assumptions**, never bare point estimates. | M |
| FR-048 | Save, name, and compare scenarios side by side. | S |
| FR-049 | Compare any scenario against the AI recommendation and the rule-based baseline. | M |
| FR-050 | Narrate scenario outcomes in business language. | S |
| FR-105 | Simulation reuses the **same Monte Carlo engine** as the pricing pipeline (§5.2), so a simulated outcome and a recommendation forecast are directly comparable rather than produced by different code paths. | M |
| FR-106 | Expose stress-test scenarios (FR-086) directly in the simulation UI. | S |

### 5.7 Commerce integration

| ID | Requirement | Priority |
|---|---|---|
| FR-051 | Commerce Service exposes catalog, sales history, inventory, price read, batch price write, and price history endpoints. | M |
| FR-052 | Batch price push is **idempotent** via a batch key; re-push is a no-op (D15). | M |
| FR-053 | Commerce Service **independently re-validates** incoming prices and may reject items; partial success is displayed per SKU with reasons. | M |
| FR-054 | Every push attempt and outcome is recorded in the audit log, including whether the approval was human or automatic. | M |
| FR-055 | Platform reads back realized sales post-push to close the feedback loop. | **M** |
| FR-107 | Realized outcomes are fed back into the elasticity estimates, refining them with each observed price change rather than re-estimating from static history alone. | M |
| FR-108 | Monte Carlo input distributions are refined from observed forecast error, so simulated intervals tighten as evidence accumulates. | M |
| FR-109 | Forecast-vs-realized error is tracked per SKU and feeds the confidence score on subsequent recommendations (FR-021). | M |
| FR-110 | Convergence is measurable across iterations and displayed (FR-092). A system that is not converging must say so. | M |
| FR-111 | Refinement is bounded and inspectable: the magnitude of any adjustment to an elasticity estimate is capped and logged, so the loop cannot silently drift into a bad state. | M |

### 5.8 Dashboards and audit

| ID | Requirement | Priority |
|---|---|---|
| FR-056 | Performance dashboard: revenue and margin impact, forecast vs. realized, recommendation acceptance rate. | M |
| FR-057 | **Baseline comparison dashboard** contrasting AI recommendations against the rule-based baseline pricer on identical data (Section 9.3). | M |
| FR-058 | Per-SKU audit timeline: inputs, agent outputs, simulation distributions, rule evaluations, band and its reason, approver (human or system), mode in force, reason, push result. | M |
| FR-059 | Audit records are append-only. | M |
| FR-060 | Export audit trail. | S |
| FR-061 | Run history with status, duration, token cost, and outcome. | M |
| FR-112 | **Stability dashboard**: oscillation incidents, damping applied, convergence trend, and forecast-error trajectory over time. | M |
| FR-113 | **Autonomy dashboard**: band distribution per run, auto-approve rate, escalation reasons ranked by frequency, and mode-change history. | M |
| FR-114 | Audit view can filter to automatic approvals alone, so a compliance reviewer can inspect exactly what the system decided without human involvement. | M |

### 5.9 Mandated UI elements

| ID | Requirement | Priority |
|---|---|---|
| FR-062 | React + React Router + Vite + Tailwind. Minimal enterprise aesthetic. | M |
| FR-063 | **No emojis anywhere in the UI.** All icons from a vector library (Lucide). | M |
| FR-064 | Explicit light/dark theme toggle via CSS variables and Tailwind semantic tokens; preference persists. | M |
| FR-065 | **Global header LLM monitor**, persistent across all routes, showing active LLM calls, cumulative input/output tokens, and estimated cost (LiteLLM fallback rates when a model is unpriced). | M |
| FR-066 | **Settings gear drawer**, globally accessible, containing gateway URL, port, and API key inputs; an iOS-style toggle for "Disable SSL Verification"; and live cache hit/miss statistics. | M |
| FR-067 | Settings changes apply at runtime without restart. | M |
| FR-068 | **Universal RAG grounding panel** showing embedding stats with runtime document upload (FR-039, FR-041). | M |
| FR-069 | Live run progress streamed to the UI, showing current agent and completed nodes. | M |
| FR-070 | Responsive from 1280px; keyboard-navigable review queue. | S |
| FR-115 | **Operating mode control** — Supervised / Assisted / Autonomous — visible in the global header with the current mode always displayed, never hidden in a submenu. | M |
| FR-116 | **Kill switch** reachable from the global header at all times, visually distinct, with a single confirmation step. | M |
| FR-117 | **Loop control panel**: start/stop, interval and scope selection, iteration count, time to next run, and a live log of what each iteration decided. | M |
| FR-118 | Band indicators use shape or label in addition to colour, so status is not conveyed by colour alone. | M |
| FR-119 | Monte Carlo results render as distribution visualizations — confidence bands, not bare numbers — in both light and dark themes. | M |
| FR-120 | A persistent indicator shows when the loop is running, visible on every route. | M |

### 5.10 Continuous loop mode

| ID | Requirement | Priority |
|---|---|---|
| FR-121 | Interval-triggered pricing loop running inside the application lifespan, started and stopped exclusively from the UI. | M |
| FR-122 | **The loop never auto-starts.** It is off at boot and requires explicit user action every time (NFR-035). | M |
| FR-123 | Each iteration executes the full W1 pipeline and honours the autonomy bands and operating mode in force at that moment. | M |
| FR-124 | A failed iteration **stops the loop** and surfaces a visible error. No silent retry loops (NFR-036). | M |
| FR-125 | Loop state, iteration history, and per-iteration decisions are persisted and auditable. | M |
| FR-126 | The loop stops cleanly on application shutdown, completing or abandoning the in-flight iteration without corrupting run state (NFR-023). | M |
| FR-127 | Configurable maximum iterations per session, as a runaway backstop. | S |

### 5.11 Platform and interoperability

| ID | Requirement | Priority |
|---|---|---|
| FR-071 | A2A agent card and JSON-RPC `message/send` / `tasks/get` (D11). | S |
| FR-072 | Backend-only LLM routing; the client never holds gateway credentials or calls the gateway. | M |
| FR-073 | Two-tier LLM cache — exact-hash and semantic — persisted to SQLite, with hit/miss statistics exposed to the UI. | M |
| FR-074 | Cross-platform startup scripts (`startup.sh`, `startup.bat`) with pre-flight validation. | M |
| FR-075 | Pre-flight verifies venv, Node version, required environment variables, database and Chroma directory permissions, port availability for 8000/8001/5173, and gateway reachability. Fails fast with specific messages. | M |
| FR-076 | Commerce Service must be healthy before the platform accepts pricing runs. | M |

## 3. Non-functional requirement register

### 6.1 Environment and execution

| ID | Requirement |
|---|---|
| NFR-001 | **User-space execution only.** Zero Docker, zero containers, zero root/admin privileges, zero system-wide daemons. |
| NFR-002 | Python 3.x in `venv`; Node.js `>=20.19` with 22.x LTS preferred (resolves source conflict C3). |
| NFR-003 | All network services on unprivileged ports (>1024): 8000, 8001, 5173. |
| NFR-004 | All storage local, file-based, embedded, in-process: ChromaDB and SQLite. No external database server. |
| NFR-005 | `app.db` and `llm_cache.db` are separate files in WAL mode to avoid write contention (D9). |

### 6.2 Performance

| ID | Requirement |
|---|---|
| NFR-006 | Pricing run over a 500-SKU category completes within **5 minutes** on a developer laptop. Revised upward from 3 minutes in v1.0 to accommodate the Monte Carlo layer. |
| NFR-007 | Data & Context ingestion paths execute **concurrently** within the node, not sequentially (FR-077). |
| NFR-008 | Cached LLM responses return in under 100ms. |
| NFR-009 | Interactive UI actions respond within 500ms; long operations stream progress. |
| NFR-010 | Scenario simulation returns within 5 seconds for a single SKU. |
| NFR-037 | Monte Carlo simulation consumes no more than **60 seconds** of the 500-SKU run budget. Iteration count (FR-083) is tuned to hold this, and the trade-off between iterations and interval width is documented. |
| NFR-038 | Monte Carlo is CPU-bound and must not block the event loop; it runs off the async path so UI progress streaming stays responsive. |

### 6.3 Security and privacy

| ID | Requirement |
|---|---|
| NFR-011 | Gateway credentials never reach the client and are never written to disk in plaintext; runtime-supplied keys stay in memory. |
| NFR-012 | Automatic secret and PII redaction in all logs and traces. |
| NFR-013 | No consumer-level or personally identifiable data enters the system (D8, FR-036). |
| NFR-014 | Proprietary sales data never leaves the local environment except as prompt content to the configured gateway. |
| NFR-015 | Append-only audit log for every recommendation, approval, override, and push. |

### 6.4 Corporate TLS handling (D10)

| ID | Requirement |
|---|---|
| NFR-016 | **Preferred path:** trust the corporate root CA via `SSL_CERT_FILE` / `REQUESTS_CA_BUNDLE`. Attempted first. |
| NFR-017 | TLS verification bypass permitted **only** behind an explicit `ALLOW_INSECURE_TLS=true` flag. Never the default. |
| NFR-018 | Bypass logic centralized in a single helper — no scattered `verify=False`. |
| NFR-019 | When bypass is active, log a prominent warning at boot and display a persistent indicator in the UI. |
| NFR-020 | Node-side `NODE_TLS_REJECT_UNAUTHORIZED=0` confined to the Vite dev proxy; never in production build output. |

### 6.5 Reliability

| ID | Requirement |
|---|---|
| NFR-021 | Exponential-backoff retry on transient gateway failures (429, 500, 502, 503, 504). |
| NFR-022 | Boot-time environment validation via Pydantic schemas; fail fast with actionable messages. |
| NFR-023 | Graceful `SIGINT`/`SIGTERM` handling: flush telemetry, checkpoint runs, close SQLite cleanly. |
| NFR-024 | Runs are checkpointed and resumable after interruption. |
| NFR-025 | Telemetry failure never fails a pricing run. |
| NFR-026 | Commerce Service unavailability produces a clear, actionable error — never a silent partial run. |
| NFR-035 | The continuous loop is an **in-process interval task inside the application lifespan** — not a system daemon, not an OS-scheduled job, and it installs nothing. It never auto-starts, and it terminates with the process. This is how §5.10 coexists with NFR-001. |
| NFR-036 | A failed loop iteration **stops the loop** and raises a visible error. The loop must never retry silently into a broken state or continue pricing on stale inputs. |
| NFR-039 | Automatic pushes are reversible. Every auto-approved change records the prior price so a single action restores it (FR-098). |
| NFR-040 | Any recommendation the system approves automatically must satisfy every check a human-approved one does. Autonomy changes who approves, never what is verified. |

### 6.6 Observability

| ID | Requirement |
|---|---|
| NFR-027 | Structured JSON logging (`structlog`) recording latency, token usage, model, and cache hit/miss for every agent action and LLM call. |
| NFR-028 | Langfuse tracing with a local JSONL fallback sink always active (D12). |
| NFR-029 | Token spend and estimated cost attributable per run and per agent. |

### 6.7 Maintainability

| ID | Requirement |
|---|---|
| NFR-030 | **Hard limit 300–400 LOC per file.** |
| NFR-031 | Strict separation of concerns: agents and tools, API routes and A2A, RAG services, prompts and schemas, database and cache, shared utilities. |
| NFR-032 | Framework independence — LLM provider swappable via configuration, not code changes. |
| NFR-033 | Automated tests covering the golden path, compliance veto, idempotency, structured-output repair, and grounding enforcement. |
| NFR-034 | Composition over inheritance; single-responsibility modules. |

## 4. Workflow and acceptance specification

Use controlled synthetic fixtures, fixed simulation seeds, observable API results, and persisted audit records. The checks below complement each individual register row; all M requirements and NFRs remain release obligations, and S/C items retain their stated priority.

### 4.1 Autonomy decisions and modes

Evaluate escalation triggers first, then all Auto-approve conditions, otherwise assign Review. Auto-approve requires confidence above threshold, delta within limit, clean compliance, variance within limit, no oscillation, and sufficient elasticity sample. Escalate applies for any compliance violation, margin proximity, excessive variance, oscillation, or unprecedented market conditions. Show threshold, actual value, and reason.

| Mode | Auto-approve band | Review band | Escalate band |
|---|---|---|---|
| Supervised, default | Human review | Human review | Explicit human decision with written reason; compliance violation remains blocked |
| Assisted | Automatic approval and push | Human review | Same blocked/escalation handling |
| Autonomous | Automatic approval and push | Automatic after configurable hold unless a human intervenes | Same blocked/escalation handling |

An escalation for reasons other than a compliance violation may proceed only after explicit human override with a written reason and fresh validation. A rule-violating price cannot proceed. The kill switch stops the loop and pending automatic pushes and returns to Supervised. UI access has the PRD's single confirmation step; one confirmed action performs all effects.

### 4.2 Acceptance scenarios and traceability

| Check | Workflow / requirements | Observable acceptance evidence |
|---|---|---|
| AC-01 | W1 / US-001; FR-001–005, FR-051, FR-074–076 | Startup scripts validate all stated prerequisites and ports, list invalid model mappings, and refuse runs without healthy Commerce. Synthetic catalog includes seasonality, promotions, categories, and hidden evaluation ground truth; synthetic competitor adapter is active by default. |
| AC-02 | W1; FR-003, FR-006–011, FR-077–079; NFR-007, NFR-026 | Timings demonstrate concurrent retrieval. Quality report includes severity and affected counts before recommendations. A failed gate produces an actionable halted state; a permitted optional-source failure marks affected analysis lower-confidence. Commerce unavailability never yields a silent partial run. |
| AC-03 | W1; FR-012–014 | Known synthetic elasticity can be estimated from history with a coefficient, confidence interval, and sample size. Insufficient history is flagged and cannot produce a confident recommendation. Ground truth is used for evaluation, not as a substitute estimator. |
| AC-04 | W1; FR-080–087; NFR-037–038 | Candidate distributions demonstrably consume upstream elasticity and sample all four required uncertainty sources. Each candidate has variance, confidence bands, and margin-floor breach probability; fixed numerical inputs and seed reproduce simulation results, independently of stochastic LLM narration. CPU work does not stall UI progress. Stress tests retain S priority. |
| AC-05 | W1; FR-015–021, FR-088 | Price gaps and inventory signals are reproducible. Each objective and run constraint changes deterministic optimization as expected; margin floors, price bounds, elasticity, and damping are respected. SKU and run impact include intervals; confidence incorporates all named factors. |
| AC-06 | W1; FR-022–023, FR-078, FR-096 | Every recommendation exposes all required prices, deltas, impact intervals, confidence, rationale, valid citations, compliance result, band, and assignment evidence. Missing or fabricated source IDs prevent acceptance. |
| AC-07 | W2 / US-002, US-003; FR-024–028 | Queue supports all filters, sorting, item decisions, and eligible Review-only bulk approval. Ineligible bands, confidence, and violations are excluded. Override without reason fails; a supplied manual price is revalidated. Price-ladder/input-detail views retain S priority. |
| AC-08 | W2; FR-030–037 | Fixtures exercise every shipped rule at and around its boundary. Every evaluation stores pass/fail and values. Violations cannot be human-approved, force-pushed, overridden, or auto-approved in any mode. Personal-pricing requests are refused and sensitive input is redacted before model access. |
| AC-09 | W2; FR-089–100 | Reversal and repeated-price histories trigger configurable oscillation detection; damping constrains the move. Novel/anomalous prices and all five escalation triggers are tested independently. Every recommendation has exactly one deterministic band and persisted signals. Minimum-change interval retains S priority. |
| AC-10 | W2 / US-010; FR-097, FR-101–104, FR-115–116; NFR-040 | All mode × band combinations behave as the table specifies. Hold-window intervention prevents pending Review auto-push. Audit captures decision-time mode and actor. Kill switch stops pending automatic pushes and loop work, records prior state, and restores Supervised. |
| AC-11 | W3 / US-004; FR-045–050, FR-105–106 | One/many-SKU what-ifs reuse the pricing Monte Carlo engine with configurable horizon, visible assumptions, distributions, margin-risk probability, and comparison with AI and baseline on equivalent inputs. Save/compare, narration, and stress-test UI retain S priority. |
| AC-12 | W4 / US-005; FR-038–044, FR-068 | Runtime upload updates collection document/chunk counts and timestamp without restart. Subsequent reasoning receives relevant uploaded context with valid source IDs. Automated dependency check rejects any LLM entry path outside GroundedLLM; role breadth remains configurable. |
| AC-13 | W5 / US-006; FR-051–054 | A mixed-validity batch returns per-SKU applied/rejected results with reasons after independent Commerce validation. Repeating the same batch key causes zero duplicate changes; every attempt/outcome identifies human or automatic approval. |
| AC-14 | W5; FR-098; NFR-039–040 | Prior price is retained. One revert action uses the same validated execution path and records its outcome. Auto-approved changes remain visible and filterable; reversing a change cannot bypass current compliance rules. |
| AC-15 | W6 / US-007, US-011; FR-055–057, FR-092, FR-107–112 | Realized post-push sales are read over HTTP. Dashboards compare forecast, realized, and cost-plus/category-discount baseline on the same SKU data. Observed error updates subsequent confidence; bounded, logged elasticity/distribution refinements are inspectable. Widening error raises a visible warning. |
| AC-16 | W7 / US-008; FR-035, FR-054, FR-058–061, FR-095, FR-103–104, FR-114; NFR-015 | A SKU timeline reconstructs inputs, outputs, distributions, rules, stability, band reasons, actor, mode, push result, and history. Automatic-only filtering works. Application operations cannot update/delete existing audit events. Export retains S priority. |
| AC-17 | W8 / US-009; FR-062–067, FR-070, FR-072–073; NFR-008–009 | Persistent header and settings function across routes; theme survives reload; vector icons replace emojis. Monitor shows active calls, input/output tokens, cost fallback, and cache stats. Runtime settings apply without restart. Check required credential boundary and flagged ambiguity below. Responsive/keyboard behavior retains S priority. |
| AC-18 | W8; FR-112–120 | Stability/autonomy dashboards expose all named metrics. Mode, kill switch, and loop-running indicator remain visible on every route. Band labels/shapes and distribution bands work in both themes. |
| AC-19 | W9 / US-012; FR-121–127; NFR-023–024, NFR-035–036 | Boot/restart leaves loop off. UI start selects interval and scope; each iteration runs the full current-policy pipeline. A failed iteration stops future iterations and shows an error. State/history survives restart for inspection; graceful shutdown leaves a valid checkpoint. Maximum-iteration backstop retains S priority. |
| AC-20 | FR-071 | Agent card is exposed at `/.well-known/agent-card.json`; JSON-RPC `message/send` and `tasks/get` support the stated limited interoperability surface. Full task lifecycle and autonomous negotiation are excluded; this feature retains S priority. |
| AC-21 | NFR-001–005, NFR-022 | Demonstrate local startup without Docker, root/admin, external DB, or system daemon. Verify Python venv, stated Node version, unprivileged ports, in-process Chroma, separate SQLite files, and WAL on app/cache databases. |
| AC-22 | NFR-011–020 | Browser receives no gateway credentials in responses or bundles; supplied runtime keys remain memory-only and disk/log checks find no plaintext secrets. Corporate CA is attempted first; bypass is unavailable without explicit flag, centralized, visibly indicated, and limited to the intended corporate prototype use. Node override cannot leak into production output. |
| AC-23 | NFR-021–029 | Transient gateway codes trigger exponential backoff; schema failures get exactly one repair retry before typed failure. Interrupt/resume preserves run state. Block Langfuse egress and verify always-on local JSONL, healthy pricing, redaction, and per-run/agent token/cost attribution. Remote telemetry contains operational metadata only; proprietary sales/prompt payloads may leave only through the configured gateway. |
| AC-24 | NFR-030–034; FR-043 | Source checks show no file above 400 LOC, separate concerns, composition, configuration-only model-provider swaps, and sole GroundedLLM access. Required automated suites cover golden path, veto, idempotency, structured repair, and grounding enforcement. |
| AC-25 | NFR-006, NFR-008–010, NFR-037; PRD §9.2 | On documented developer hardware, benchmark 500 SKUs in <5 minutes, Monte Carlo in <60 seconds, cached calls in <100ms, UI actions within 500ms, and a single-SKU simulation within 5 seconds. Record seed, iterations, candidate count, environment, and cache state; document runtime/interval trade-off. |

## 5. Success measures and release evidence

The PRD defines effectiveness targets, not a guarantee that synthetic demonstrations meet them. Report measured values and failures transparently; do not weaken compliance to increase automatic approvals.

| Measure | Required target / comparison |
|---|---|
| Revenue and margin | Forecast revenue uplift ≥5% against identical-data rule-based baseline, with no margin degradation |
| Pricing accuracy | Recommended price within 10% of ground-truth theoretical optimum for high-confidence SKUs |
| Recommendation acceptance | ≥70% approved without override |
| Manual intervention | ≥60% of SKUs auto-approved without human action in Assisted mode |
| Escalation precision | ≥80% of escalations agreed by a human to need escalation |
| Forecast reliability | Realized impact falls within the stated interval ≥80% of the time |
| Stability and convergence | <2% of SKUs oscillate; forecast-versus-realized error narrows over iterations |
| Repeated-run cache | ≥40% hit rate |
| Structured output and grounding | ≥99% valid after repair retry; 100% valid-citation coverage |
| Safety and repeatability | Zero violating prices reaching Commerce in any mode; zero auto-approved human-check failures; zero duplicate changes on re-push; zero loop continuation after failure; 100% fixed-seed reproducibility |
| Maintainability and performance | No source file over 400 LOC; performance thresholds in AC-25 |

Demonstrate better prices against held-out synthetic ground truth, conflicting signals the baseline misses, cited rationale, and honest uncertainty as history degrades. User-story coverage is W1/US-001, W2/US-002/003/010, W3/US-004, W4/US-005, W5/US-006, W6/US-007/011, W7/US-008, W8/US-009, and W9/US-012.

## 6. Assumptions, exclusions, and unresolved decisions

### 6.1 Assumptions inherited from the PRD

| ID | Assumption and fallback |
|---|---|
| A-01 | LiteLLM exposes a working chat model; probe at boot or stop with actionable error. |
| A-02 | Source model aliases may differ from actual gateway aliases; resolve from configuration and list available models on failure. |
| A-03 | Local embedding download or gateway embeddings are available; if neither works, RAG is unavailable and grounding requirements cannot be met. |
| A-04 | Langfuse egress may fail; always-on local telemetry remains available. |
| A-05 | Synthetic retail data is acceptable; no real retailer dataset is supplied. |
| A-06 | Single-user demonstration; production authentication, RBAC, and multitenancy are unnecessary. |

### 6.2 Exclusions and scope control

Exclude personalized pricing; autonomy without compliance/escalation bounds; real Shopify/SAP/Magento integration; production authentication/RBAC/multitenancy; live scraping as the default path; brokers/CDC/per-transaction reactive repricing; LLM execution; deep-learning forecasting; native mobile apps; multiple currencies/regions/tax regimes; cloud deployment, CI/CD, or containers; and autonomous agent negotiation.

Retain M1–M7 release order from PRD §10, elaborated in [task.md](task.md). If the timebox requires cuts, the PRD proposes distribution refinement (FR-107–108, FR-111), then stress tests (FR-086, FR-106), then Autonomous mode. The first and third affect must-have scope and require an explicit scope amendment; this specification does not silently drop them. Monte Carlo and deterministic band assignment must remain.

### 6.3 Decisions and source inconsistencies to resolve

| Item | Required resolution before affected implementation is finalized |
|---|---|
| Approval status | PRD §12 still says awaiting approval. These are requested drafts; PRD approval is not recorded or inferred. |
| Missing source documents | Confirm any Phase 1 details not reproduced in the PRD rather than inventing them. |
| Gateway aliases, embeddings, TLS CA, Langfuse | Use the boot probes and fallbacks from PRD §11; never hardcode presumed external availability. |
| Thresholds and simulation calibration | Select and document compliance thresholds, confidence/delta/variance/margin bands, sample minimum, Monte Carlo iterations/interval level, oscillation window/reversals, damping, hold duration, and loop interval. The PRD supplies no numerical defaults for these. |
| Runtime key input versus client boundary | FR-066 asks for an API-key input; FR-072/NFR-011 say credentials never reach the client. Clarify whether a transient, operator-entered masked field is permitted. At minimum keys must never be returned to the browser, persisted there, or used for browser-to-gateway requests. |
| Reduced inputs versus unavailable Commerce | FR-079 permits graceful optional-path degradation, but NFR-026/FR-076 forbid silent partial runs when Commerce is unavailable. Define mandatory sources and quality-gate failure rules; do not treat an unavailable authoritative service as a usable partial run. |
| Insufficient-history routing | W2 sends unmet Auto-approve conditions to Review absent an escalation trigger; PRD §9.3 describes degraded history reaching Escalate. Define whether degradation also raises variance/novelty enough to trigger Escalate; do not invent a new escalation trigger. |
| Autonomous Review versus broad confidence wording | W2 expressly permits Review auto-push after a hold, while §8 describes confident, stable, low-impact auto-approval. Define eligible Review states consistently, preserving absolute compliance and Escalate blocks. |
| Feedback metrics | Define observation horizon, uplift counterfactual, aggregation, interval coverage, confidence calibration, and convergence warning rule. An observed-sales comparison must not be mislabeled causal realized uplift. Clarify FR-108's tightening language so new evidence may widen intervals when uncertainty increases. |
| Numeric policy | Fix currency precision/rounding, margin definition, candidate grid, objective weighting, shared uncertainty/correlation, cost/competitor response distributions, and model-update caps; keep these inspectable and reproducible. |
| Loop and safety lifecycle | Define no-overlap scheduling, treatment of human-interrupted runs, pending holds on restart, explicit run resumption, and the boundary between cancellation and an already committed Commerce write. A stopped loop must never auto-resume. |
| Cross-reference and limit wording | PRD persona text cites FR-072 for the consumer-data ban; relevant requirements are FR-036/NFR-013. NFR-030 says 300–400 LOC, while §9.2 explicitly uses 400 as the maximum. Full-run/Monte Carlo prose says within/no more than while §9.2 uses strict <; acceptance uses those stricter metrics. UI/single-SKU limits retain their stated within semantics. |
