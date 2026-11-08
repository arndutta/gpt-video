# Retail Pricing Workbench

A local implementation of the [PRD](prd.md), started with the foundation services and a
working quantitative-preview workflow. Browse the synthetic catalog, fit SKU elasticities,
compare candidate-price distributions, inspect saved previews, and run single-SKU what-ifs.

The platform currently produces **non-executable quantitative previews**. Grounded LLM
agents, document ingestion, human approvals, autonomy bands, the kill switch, platform price
execution/revert, learning, and the continuous loop are still pending. Their UI controls
are disabled or explicitly labeled pending. The Commerce batch-write contract exists for
integration and tests; the pricing platform does not expose a price-changing route.

See [requirements](requirement.md), [design](design.md), and the [task plan](task.md).

## Run locally

Requirements: Python 3.11+, a Python virtual environment, and Node 20.19+ or a supported
newer version (22.12+ recommended). No Docker, external database server, or administrator
installation is used. Dependencies are pinned in `requirements.lock` and `web/package-lock.json`.

On this machine, modern Node is already installed under `/opt/homebrew/bin`; the default
shell selects an older Node. Use `export PATH="/opt/homebrew/bin:$PATH"` before npm commands.
The startup helper detects that newer installation automatically.

macOS/Linux:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.lock
cd web
npm ci
cd ..
./startup.sh --seed
```

Windows PowerShell or Command Prompt:

```text
py -3.11 -m venv .venv
.venv\Scripts\python -m pip install -r requirements.lock
cd web
npm ci
cd ..
startup.bat --seed
```

Open **http://127.0.0.1:5173**. `--seed` populates an empty database with 500 synthetic
SKUs and 180 days of history; it preserves an existing catalog. Press Ctrl+C to stop the
three owned processes. A failed service causes the supervisor to stop its remaining children.

The browser calls only the platform through Vite's `/api` proxy. The platform retrieves
Commerce data over HTTP; it never opens the Commerce database or imports Commerce code.

| Process | Port | Storage |
|---|---|---|
| Commerce Service | 8001 | `data/commerce.db` |
| Pricing platform | 8000 | `data/app.db`, separate WAL `data/llm_cache.db` |
| React/Vite UI | 5173 | Browser theme preference only |

Both API services expose interactive documentation at `/docs`. All servers bind to loopback.
`startup.bat` is provided but has not been executed on Windows in this development environment.

## First workflow

1. Open Product catalog to inspect prices, cost, category, and product families.
2. Open Pricing runs, select a scope/objective, and run a preview. Full catalog is 500 SKUs.
3. Inspect a candidate's fitted elasticity, 95% simulation interval, sample size, baseline,
   confidence factors, and assumptions. Data-quality failures halt the preview; sparse
   history or unavailable stock is represented as an explicit skipped item.
4. Select a product in Scenario lab and enter a candidate price. Matching inputs and seed
   reproduce the forecast from the catalog preview through the same numerical engine.
5. Inspect history after a restart. Interrupted previews stay visible; start a new preview
   to obtain fresh inputs. Agent checkpoint/resume is not implemented yet.

No preview approves or applies a price. Confidence is an initial inspectable score, not
an empirically calibrated probability. Synthetic performance does not establish real-world
revenue uplift, causal identification, escalation precision, or forecast coverage.

## Configuration

Startup reads the process environment. `.env.example` lists supported settings but is not
automatically loaded. Export variables in your shell; keep credentials out of files.

| Variable | Default / behavior |
|---|---|
| `DATA_DIR` | `./data`, platform storage and synthetic competitor adapter files |
| `COMMERCE_DB_PATH` | `data/commerce.db` when starting Commerce directly; supervisor sets it from `DATA_DIR` |
| `COMMERCE_URL` | `http://127.0.0.1:8001` |
| `NODE_BINARY` | Optional path to the supported Node executable |
| `GATEWAY_URL`, `GATEWAY_PORT` | Optional backend gateway configuration; no chat calls are made yet |
| `GATEWAY_API_KEY` | Optional process-memory secret; also replaceable through the masked settings form |
| `LLM_MODEL_ANALYST`, `LLM_MODEL_STRATEGIST` | Aliases for the optional initial gateway readiness probe |
| `SSL_CERT_FILE`, `REQUESTS_CA_BUNDLE` | Preferred corporate CA trust; both backend paths use one TLS helper |
| `ALLOW_INSECURE_TLS` | `false`; required before the runtime disable-verification toggle is available |

Runtime gateway settings apply atomically for the session. Keys are write-only, held in
backend memory, omitted from responses/logs/audit, and cleared from the input on submission.
They do not survive a restart. Insecure TLS is never the default; enabling the permitted
prototype toggle emits a warning and a persistent header indicator. The initial browser-entry
transient follows the proposed write-only interpretation documented in `design.md`.

Optional checks:

```sh
.venv/bin/python -m scripts.preflight --skip-ports
./startup.sh --require-gateway
```

`--require-gateway` requires URL/key and analyst/strategist aliases, probes `/models`, and
fails with available aliases when mappings do not match. This probe has not been run
against a real configured gateway. It does not enable agents, grounding, or automatic pricing.
The normal launcher explicitly uses the quantitative-preview path and reports the skipped probe.

## Synthetic data and reproducibility

The seed CLI uses today's UTC date unless `--as-of` is supplied. Record the date and seed
for repeatable fixtures. Normal startup never reseeds existing products.

```sh
.venv/bin/python -m commerce.seed --sku-count 500 --days 180 --seed 42 --as-of 2026-11-08 --data-dir data
```

Use `--category Beverages` for a 500-SKU single-category benchmark. An existing catalog is
rejected by the standalone generator; `--reset` explicitly replaces synthetic Commerce
data and its history/receipts. Preserve any data you need before requesting a reset.

Ground-truth elasticity is isolated in Commerce-owned evaluation storage and
`data/evaluation_truth.json`. It is absent from all ordinary HTTP read payloads and model
inputs. `data/competitor_feed.json` supplies the replaceable synthetic competitor adapter.
The platform stores derived preview evidence and source timestamps, not a live catalog replica.

The initial numerical policy uses USD, decimal monetary strings, gross margin as
`(price - cost) / price`, a 14-day default horizon, 1,000 default draws, 95% intervals,
and at least 30 positive-sales observations with four distinct prices. Monte Carlo samples
fitted elasticity uncertainty, competitor response, cost drift, and seasonality. Shared
shocks retain sample alignment for run-level intervals. Inventory is capped with no replenishment.
Model/engine configuration and all initial uncertainty assumptions appear in preview results.
Stability damping and observed-outcome calibration are future work.

## Validation

```sh
.venv/bin/python -m pytest -q
cd web
npm run build
cd ..
# While ./startup.sh is running:
.venv/bin/python -m scripts.smoke
```

The automated suite covers all six Commerce compliance rules, coupled family rejection,
partial batches, exact/conflicting/concurrent replay, stale versions, private evaluation
data, elasticity recovery, shared-engine simulation, reproducibility, quality gates,
HTTP-only separation, persistence, append-only audit, memory-only secrets, malformed upstream
contracts, atomic settings replacement, and cancellation that retains numerical worker ownership.
Architecture checks enforce a maximum of 400 lines per code file and prevent provider-model
bypasses. These checks do not prove later unimplemented agent/approval paths correct.

The running smoke check exercises the Vite proxy, a full-catalog asynchronous preview,
responsive health during calculation, exact scenario/preview parity, and unchanged catalog
prices. Results are written to ignored `data/smoke_result.json`.

Recorded on 2026-11-08 with Python 3.11.5 and Node 24.4.1: **58 backend tests passed**;
TypeScript and the Vite production build passed; the live 500-SKU preview with 1,000 draws
completed in **8.677 seconds**, with a concurrent health response in **51.39ms**. The
scenario forecast matched exactly and catalog prices were unchanged. These timings cover
the current quantitative-preview path, not the unimplemented grounded agent pipeline.
Startup, restart with retained data, and clean supervisor shutdown were also exercised.

Visual browser QA is unverified because the browser access host was unavailable. The UI
entry point, proxy, backend workflows, TypeScript, and production bundle have been checked.
An upstream FastAPI/Starlette TestClient deprecation warning currently appears for `httpx`;
it does not fail the tests.

## Next implementation work

Continue with Chroma document ingestion, embedding availability checks, `GroundedLLM`, typed
output/repair/citation enforcement, and the five-stage LangGraph state machine (T14–T19).
Then connect independent platform validation, stability/autonomy, actual review interrupts,
and the shared validated dispatcher before enabling any price-changing UI. The complete
M1–M7 release and its product-effectiveness targets remain open.

Implementation reference: [FastAPI lifespan](https://fastapi.tiangolo.com/advanced/events/),
[Pydantic settings](https://docs.pydantic.dev/latest/concepts/pydantic_settings/), and
[Vite setup](https://vite.dev/guide/).
