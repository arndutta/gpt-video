# Retail Pricing Workbench

A local SKU-level pricing application with separate Commerce and platform services, a
React workspace, deterministic elasticity/Monte Carlo optimization, and a five-agent
grounded workflow. Recommendations retain citations, rule evidence, stability signals,
approval decisions, and per-item Commerce outcomes.

The quantitative preview works without a model gateway. A grounded pricing run requires
a configured gateway, all four model aliases, and published retrieval evidence. Missing
grounding or gateway access stops that workflow; there is no fabricated model fallback.
The app includes Supervised, Assisted, and Autonomous modes, human review, a global halt,
validated execution/revert, saved scenarios, feedback calibration, and an explicit-start
interval loop. These are local demonstration capabilities, not production authorization
or evidence of measured business uplift.

Latest verification: **562 backend tests**, **67 DOM tests**, **6 actual Chromium tests**, the UI build,
and the isolated **56-case W1–W9 demonstration** pass. T06 startup checks and T38
functional acceptance are complete. An isolated local gateway passes real alias and
embedding pre-flight checks and a real five-stage, one-SKU workflow reaching human review;
see [local gateway evidence](docs/local-gateway.md). Live 500-SKU performance, statistical
reliability and product-effectiveness gates remain open; [browser acceptance](docs/browser-qa.md)
now verifies 1280px layout, both themes and keyboard/decision behavior. [The feasibility proof](docs/effectiveness-feasibility.md)
shows why the unchanged +5% revenue target cannot be met on the current fixtures.

See the [task plan](task.md), [requirements](requirement.md), [design](design.md),
[implementation decisions](docs/decisions.md), and [operator runbook](docs/operator-runbook.md).
The source [PRD](prd.md) is unchanged; its formal approval state remains unrecorded.
The project owner explicitly approved a **limited engineering demo with business KPI
gates open**; [release readiness](docs/release-readiness.md) records the approved scope,
failed targets and missing observations. Fresh [SQLite benchmarks](docs/sqlite-benchmarks.md)
and [native Windows CI evidence](docs/windows-acceptance.md) are tracked separately.

The [modern dashboard redesign](docs/ui-redesign.md) adds a blue/mint visual system,
collapsible navigation, Ctrl/Cmd+K workspace search, interactive overview stages,
dashboard tabs, catalog grid/table views, product drawers, and explorable forecast
intervals. Motion respects reduced-motion preferences; light/dark themes remain available.
The November 14 reliability follow-up prevents stale query/scenario responses, keeps
modal focus stable through updates, and repairs catalog refresh/pagination recovery.
Further hardening fences checkpoint resumes during halt, isolates telemetry sinks,
bounds gateway verification, and preserves policy drafts and upload status during requests.
The native macOS acceptance runner verifies fresh 500-SKU HTTP previews, real upload/
retrieval and owned service cleanup. Cache connections now close explicitly; failed
concurrent workflow phases drain their peers, and truncated SDK output receives one
safe structured repair without changing facts or schema.
The real one-SKU functional run reaches Supervised review in 284.447s with unchanged
computed numbers and zero price writes. Earlier 240-second failures remain recorded;
the 500-SKU timing target is unchanged. A dedicated Windows CI branch/workflow and
owned Job Object batch-wrapper harness are prepared but require an actual Windows run.

Reproduce browser acceptance with `npm --prefix web run test:browser` after
`cd web && npx playwright install chromium`. It starts the production UI against
disposable SQLite data and preserves screenshots, accessibility results and timings
under ignored `data/browser-qa/`. The normal installed data and gateway are untouched.

## Run locally

Use Python 3.11+ in a virtual environment and Node >=20.19 (or supported 22.12+).
Dependencies are pinned in `requirements.lock` and `web/package-lock.json`. No Docker,
external database, cloud deployment, or administrator installation is required.

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.lock
cd web
npm ci
cd ..
./startup.sh --seed
```

On this Mac, use `export PATH="/opt/homebrew/bin:$PATH"` before npm commands; the normal
shell selects an older Node. The launcher detects the supported installation automatically.
On Windows use `py -3.11 -m venv .venv`, `.venv\Scripts\python`, and `startup.bat --seed`.
The Windows entry point is provided; execution on Windows is unverified here.

Open **http://127.0.0.1:5173**. `--seed` creates 500 synthetic SKUs and 180 days of sales
only when Commerce is empty. Existing data is preserved. Ctrl+C stops the three owned
processes. Startup order is Commerce → platform → Vite. All listeners bind to loopback.

| Service | URL | Owned storage |
|---|---|---|
| UI | `http://127.0.0.1:5173` | Browser theme preference |
| Platform | `http://127.0.0.1:8000/docs` | `data/app.db`, `checkpoints.db`, `llm_cache.db`, `rag.db`, telemetry |
| Commerce | `http://127.0.0.1:8001/docs` | `data/commerce.db`, price book, receipts/history |

To install all SQLite tables and initial data explicitly, run
`.venv/bin/python -m scripts.database`. Existing data is preserved; an empty catalog
receives the demo dataset. Competitor quotes now live in `data/market.db`, and model
pricing rates live in `data/app.db`. Grounding documents, vectors, and manifests live
in `data/rag.db`. The runtime uses packaged DDL/DML scripts and database reads instead
of JSON data files. After installation, `.venv/bin/python -m scripts.database cleanup-legacy`
removes the two verified legacy data sidecars. See [SQLite setup and SQL exports](docs/sqlite.md).

The browser uses Vite's `/api` proxy. Platform business reads/writes go through Commerce
HTTP; the platform never opens Commerce SQLite or imports Commerce implementation code.
Platform snapshots are immutable decision evidence, not an authoritative second catalog.

## First workflow

1. Inspect **Product catalog**. In **Pricing runs**, choose **Quantitative preview** to
   fit elasticity, compare price distributions, and inspect confidence, baseline, and quality.
2. Prepare local embeddings once with `.venv/bin/python -m scripts.rag prepare`.
   Open **Knowledge & grounding** and upload `examples/pricing-policy.md` into
   `pricing_policy`. Wait for **ready** and inspect collection counts.
   Use **Advanced price constraints** to set a run-only maximum change (%) and optional
   price floors/ceilings for categories in the chosen scope. Blank fields add no bound;
   the request cannot relax Commerce compliance rules. The same controls are available
   when starting a loop.
3. Open the settings gear. Enter the gateway URL, optional port, a write-only API key,
   and router/narrator/analyst/strategist aliases that exist at your gateway. Apply settings.
4. Select **Grounded pricing workflow** in Pricing runs. The fixed graph runs Data &
   Context → Quantitative → Strategy & Reasoning → Validation & Compliance → Execution.
   Numerical prices/scores remain tool-computed; generated reasoning must cite supplied sources.
5. Open **Review queue**. Inspect rule values, thresholds, rationale/citations, stability,
   family ladders, and forecast bands. Supervised requires human approval for every band.
   An escalation needs a written human reason; a compliance violation cannot be approved.
6. Approved changes use the shared deterministic dispatcher. Inspect applied, rejected,
   stale, or unknown outcomes. An applied change offers **Revert this change**, which
   creates a fresh, linked change and must pass current rules and Commerce versions.
7. Explore **Scenario lab**, **Audit trail**, and the overview dashboards. Start the
   **Loop** only when intended. Scheduling is off after every application restart.

Read [W1–W9 operator steps](docs/operator-runbook.md#w1--generate-a-pricing-run) for
recovery, partial results, feedback maturity, and explicit demonstrations.

## Configuration and secrets

Startup reads the process environment. `.env.example` documents values; it is **not
automatically loaded**. Runtime gateway settings are session-only. The masked key field
clears on submission, keys remain in backend memory, and saved keys never return to the
browser or enter local storage, audit, telemetry, or LLM cache. Credentials must be supplied
again after restart unless the launching process already has them.

| Variable | Behavior |
|---|---|
| `DATA_DIR`, `COMMERCE_URL` | Defaults `./data`, `http://127.0.0.1:8001` |
| `COMMERCE_DB_PATH` | Direct Commerce path; supervisor derives it from `DATA_DIR` |
| `NODE_BINARY` | Optional supported Node executable |
| `GATEWAY_URL`, `GATEWAY_PORT`, `GATEWAY_API_KEY` | Backend gateway configuration; URL commonly includes `/v1` |
| `LLM_MODEL_ROUTER`, `LLM_MODEL_NARRATOR`, `LLM_MODEL_ANALYST`, `LLM_MODEL_STRATEGIST` | Required configured chat aliases for grounded runs |
| `LLM_TIMEOUT_SECONDS`, `LLM_TRANSPORT_RETRIES` | Defaults 60 seconds / 2 bounded transient retries |
| `LLM_STRATEGY_BATCH_SIZE`, `LLM_VALIDATION_BATCH_SIZE` | Defaults 25 / 25; explicit 1–25 SKU batches retain every complete input verdict/reasoning fact |
| `LLM_MAX_ENVELOPE_BYTES` | Optional complete application messages/schema UTF-8 byte cap; rejects intact initial/repair inputs, not a wire-size or token-context guarantee |
| `LLM_INPUT_COST_PER_MILLION`, `LLM_OUTPUT_COST_PER_MILLION` | Configured fallback USD estimates; defaults 0.10 / 0.40 |
| `SSL_CERT_FILE`, `REQUESTS_CA_BUNDLE` | Preferred corporate CA trust through one backend TLS helper |
| `ALLOW_INSECURE_TLS` | Default false; gates the runtime disable-verification toggle |
| `LANGFUSE_ENABLED`, `LANGFUSE_HOST`, `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY` | Optional metadata-only tracing; disabled by default |
| `LIVE_COMPETITOR_ENABLED`, `LIVE_COMPETITOR_URL` | Explicit opt-in remote JSON adapter; synthetic feed is the default |

Prefer corporate CA trust. A permitted TLS bypass emits a boot warning and a persistent
UI indicator. No browser-to-gateway model traffic or production identity/RBAC system is included.

```sh
.venv/bin/python -m scripts.preflight --skip-ports
.venv/bin/python -m scripts.preflight --skip-ports --require-embeddings
# Requires actual URL, key and all four aliases in the launching environment:
./startup.sh --require-gateway --require-embeddings
```

Gateway pre-flight checks `/models`. A successful model listing does not prove a model
supports JSON Schema generation; a grounded run exercises that contract. One isolated
local Ollama generation now passes. Corporate model tiers, statistical structured-output
reliability and remote Langfuse remain unverified.

## Knowledge and caching

Local MiniLM ONNX inference uses a checksum-verified, explicitly prepared model in
`data/models`. Inference/startup never downloads it implicitly. SQLite persists grounding
documents, embedding vectors, and manifests in `data/rag.db`; active versions publish
atomically only after successful indexing. The database installer migrates an existing
`data/chroma` store before initializing the SQLite index.
Historical citations remain resolvable. Runtime UTF-8 `.txt`/`.md` uploads are bounded to
2MB, with durable queued/indexing/ready/failed/interrupted jobs and collection statistics.

```sh
.venv/bin/python -m scripts.rag check
.venv/bin/python -m scripts.rag ingest examples/pricing-policy.md --source-id demo-pricing-policy --collection pricing_policy --version demo-v1
.venv/bin/python -m scripts.rag query "What margin and change rules apply?" --role analyst
.venv/bin/python -m scripts.rag collections
```

Retrieval searches every populated `pricing_policy`, `market_intel`, `product_kb`, and
`user_uploads` collection, with default per-collection breadth 1/2/3/4 for the four roles.
GroundedLLM obtains current retrieval for every call and validates citations on generated
and cached responses. The separate SQLite cache includes model/schema/prompt, numeric
facts, policy, evidence, and corpus versions in eligibility. Semantic reuse is deliberately
restricted to normalized equivalent prompts in the same verified context.

Gateway embeddings require both explicit provider selection and
`ALLOW_GATEWAY_EMBEDDINGS=true`; they are never an automatic fallback. Their live behavior
is unverified. See the runbook for all RAG variables and safe version replacement.

## Decisions, outcomes, and operation

Initial policy values are visible and configurable in Settings and `/api/policy`.
The market-gap escalation limit is configurable in percent (initial trial value 30%);
it complements retained price-history/category anomaly signals.
They are development calibration choices, not approved or empirically proven thresholds.
The full mode/band matrix, numeric assumptions, hold semantics, and learning caps are
recorded in [decisions](docs/decisions.md).

The global **Halt** has one confirmation: it fences pending dispatch, stops scheduling,
and resets Supervised. An already-sent request cannot be recalled; durable batch keys and
Commerce receipt lookup reconcile ambiguous outcomes. Never create a new key to retry an
unknown result. Restart cancels stale automatic authorizations and never restarts loop timers.

Feedback reads aggregate post-push Commerce sales over HTTP. Immature/incomplete windows
stay pending. Intervening prices and overlapping observations are excluded. Learning is
bounded, versioned residual calibration; poor evidence may widen uncertainty. The static
seed does not invent future transactions after a price push, so new changes usually remain
pending until suitable observations exist. Forecast comparisons are not causal realized uplift.

The header monitor exposes tokens, estimated cost, and exact/semantic cache activity.
Local JSONL telemetry is always attempted without prompt/body logging. Optional Langfuse
receives metadata only; tracing failure does not fail pricing. The bounded A2A 0.3 subset
advertises `message/send` and `tasks/get` at `/a2a`; local human review remains in the UI.
**Ask the evidence** is read-only. The optional remote competitor adapter consumes JSON;
no website scraper or production competitor integration is claimed.

## Validation and remaining acceptance

```sh
.venv/bin/python -m pytest -q
cd web
npm test
npm run build
cd ..
# Against the running local services:
.venv/bin/python -m scripts.smoke
.venv/bin/python -m scripts.operations_smoke
.venv/bin/python -m scripts.grounding_smoke
.venv/bin/python -m scripts.acceptance_demo
# Isolated native service startup/HTTP/upload/shutdown; requires prepared embeddings:
.venv/bin/python -m scripts.local_acceptance --output data/native_acceptance_result.json
# Real local retrieval/cache stages, explicit model fixture:
.venv/bin/python -m scripts.cache_benchmark --samples 200 --output data/cache_stage_benchmark_result.json
```

The suite includes service boundaries, deterministic numerics, compliance/mode decisions,
idempotency and recovery, graph/loop behavior, grounding/structured-output/cache contracts,
and redaction. UI checks render the real components and verify decision eligibility,
disconnected controls, compliance veto, and simulation evidence. These checks supplement
the strict TypeScript and production build; browser visual and interaction QA remains unverified
because the browser service could not provide a screenshot or accessibility tree; the
exact follow-up is recorded in [browser QA](docs/browser-qa.md). No Windows, live gateway, human effectiveness,
or mature real-world feedback acceptance is inferred from mocked tests.

Historical measurements: the 500-SKU quantitative preview with 1,000 draws completed in
8.854 seconds with a 51.18ms concurrent health response; real-model runtime upload to
retrieval completed in 2.489 seconds. These measurements cover the earlier local preview
and ingestion paths, not the complete live grounded pipeline. Consult [task.md](task.md)
and [validation notes](docs/validation.md) for current verification evidence and remaining release gates. Acceptance, escalation
precision, interval coverage, real uplift, and convergence targets require adequate observed
outcomes and human labels; no target is claimed solely from synthetic code coverage.


Latest reproducible local benchmark (`data/benchmark_result.json`, 2026-11-10, Apple M1,
8GiB RAM, eight logical CPUs): 500-SKU numeric analysis 3.879s, Monte Carlo compute 0.932s,
one-SKU scenario 22.5ms, and cache p95 12.03ms with real MiniLM retrieval. The actual five-node
500-SKU graph reached Supervised review in 15.129s with **an explicit typed model fixture**,
500 cited recommendations and zero price writes; this excludes live model/human latency.
The balanced fixture missed the >=5% revenue-uplift target against baseline (-7.05%) while
improving forecast profit/margin; 466/500 high-confidence prices were within 10% of the
held-out optimum, so the all-prices target also failed. These results are recorded honestly;
T46 calibration and the external acceptance gates remain open.

The latest confidence model also evaluates uncertainty of the jointly selected price.
This lowers eligibility when plausible simulated optima differ widely; it does not change
the selected price, forecasts, baseline or rule thresholds. Scenario candidates explicitly
carry no optimizer-selection verdict, and human edits clear the prior price's range.

The evaluation-only [threshold study](docs/calibration.md) compares 72 configurations
across two 500-SKU seeds. It preserves compliance, records coverage and accuracy limits,
and makes no automatic policy changes. Run it with `.venv/bin/python -m scripts.calibrate`.

Local HTTP smoke checks cover the running 500-SKU preview, run constraints, matching
scenarios, monitor/audit, and real local grounding. Commerce prices and versions remain
unchanged by these checks. The latest full-suite count is recorded in [task.md](task.md).


Follow-up implementation on 2026-11-10 adds run-scoped maximum-change/category-bound
controls to both run creation and continuous-loop setup, market-gap threshold settings,
explicit **No change** outcomes, and observed-window forecast comparisons that preserve
the mature feedback SKU scope. UI safety/serialization checks and the production build
pass; final backend integration counts are recorded in the task/validation report. Live
gateway access, browser verification, Windows execution, and business-effectiveness gates
remain separate acceptance work.
