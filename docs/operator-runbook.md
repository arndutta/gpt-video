# Local operator runbook

This runbook covers the implemented W1–W9 paths and recovery contracts. Steps requiring
a real configured gateway or future observed sales are demonstrations to perform, not
claims that they were performed in this development session. The PRD remains unchanged.

## Startup and readiness

1. Install `requirements.lock` in `.venv` and run `npm ci` inside `web` with supported Node.
2. Start `./startup.sh --seed` on macOS/Linux or `startup.bat --seed` on Windows.
   `--seed` only fills empty Commerce storage. The launcher's process group owns services
   on 8001/8000/5173; Ctrl+C shuts them down. Windows execution is not verified here.
3. Open `http://127.0.0.1:5173`. Platform OpenAPI is
   `http://127.0.0.1:8000/docs`; Commerce OpenAPI is `http://127.0.0.1:8001/docs`.
4. Verify Commerce connected, the operating mode, and **Loop off**. Fresh installations
   default to Supervised. Boot never restores interval scheduling or stale automatic intents.
5. For local retrieval, explicitly prepare the model and check it:

```sh
.venv/bin/python -m scripts.rag prepare
.venv/bin/python -m scripts.rag check
.venv/bin/python -m scripts.preflight --skip-ports --require-embeddings
```

No implicit model download occurs during application startup/inference. The official model
archive is checksum-verified; model files and the SQLite RAG database remain under ignored `data/`.
An unavailable/corrupt cache produces an actionable error. A different
`RAG_MODEL_CACHE_DIR` can be prepared separately without discarding existing evidence.

To create a repeatable isolated fixture, stop its services first and use a separate directory:

```sh
.venv/bin/python -m commerce.seed --sku-count 500 --days 180 --seed 42 --as-of 2026-11-08 --data-dir data/fixture-demo --category Beverages
```

The generator refuses a populated database unless explicitly given `--reset`. Resetting
synthetic Commerce removes its prior history/receipts; normal startup never performs it.
Use fresh dated data for freshness-gated demos. The fixed date above is for reproducible
testing and will eventually be stale. Do not reset the user's working data for a demonstration.

## Native acceptance checks

For a repeatable native-host acceptance check, first stop any workbench services on
8001/8000/5173, prepare the local embedding model, and run:

```sh
.venv/bin/python -m scripts.local_acceptance --output data/native_acceptance_result.json
# Windows, from the repository root:
.venv\Scripts\python -m scripts.local_acceptance --output data\native_windows_acceptance_result.json
```

The runner refuses occupied ports, uses fresh temporary 500-SKU storage, starts direct
Commerce/platform/Vite children, exercises the HTTP preview/controls/upload paths, and
checks unchanged prices/versions, zero price-history writes and owned-process cleanup.
It removes its fixture storage and retains only the metadata report. It does not use
the working Commerce database or require a gateway. It requires the existing prepared
embedding cache and installed Python/Node dependencies; it never downloads models.
The report applies only to the host where it ran. Verify `startup.bat` separately on
Windows; the direct-child runner does not claim batch-wrapper or browser acceptance.

The dedicated native Windows batch-wrapper check is:

```sh
.venv\Scripts\python -m scripts.windows_startup_check --output data\windows_batch_acceptance.json
```

It launches the real `startup.bat` suspended and atomically assigned to an owned Windows
Job Object, then resumes it in its own process group with fresh temporary data. It
requests graceful shutdown with CTRL_BREAK; job ownership survives wrapper exit.
Handle-based forced cleanup prevents leftover owned processes and fails graceful-
shutdown acceptance. The launcher
handles SIGBREAK on Windows; the dependency lock excludes unsupported `uvloop` there.

`.github/workflows/windows-acceptance.yml` prepares a Windows runner, installs locked
dependencies, explicitly prepares real embeddings, runs backend/frontend checks, then
both native acceptance commands. It runs manually or on a push to the dedicated
`codex/windows-acceptance` branch only. A prepared workflow is not Windows evidence:
retain its completed reports before closing the native Windows gate.
The dedicated branch push is the initial execution path. GitHub manual dispatch also
requires the workflow definition to be available on the repository's default branch;
see [GitHub's manual-run requirements](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/manually-run-a-workflow).

## Gateway, TLS, and secret lifecycle

Open Settings from the global gear. Configure URL (including the gateway's API prefix),
optional port, write-only key, and router/narrator/analyst/strategist aliases. The gateway
must support the structured JSON Schema calls used by LangChain. These settings take
effect without restart. Keys are cleared from the field on submission and never read back;
the browser does not retain them. Restart requires re-entry or a secret already supplied
to the launching process. `.env.example` is documentation and is not automatically loaded.
After saving, choose **Verify gateway**. The backend checks the current four aliases
against the gateway's model list and displays the result. This makes no model-generation
call, and explicitly does not certify structured generation or reasoning quality. Changing
the URL, credential, aliases or TLS setting invalidates the earlier readiness result.
Verification has a total 10-second deadline, including streamed response reads. A timeout
uses the normal unavailable error; fix access before trying again.

For a strict startup probe, provide `GATEWAY_URL`, `GATEWAY_API_KEY`, and all four
`LLM_MODEL_*` aliases in process environment, then use:

```sh
./startup.sh --mode grounded
```

The gateway probe lists actual available model IDs when aliases mismatch. Listing models
does not verify chat schema support or quality; perform W1 against the real gateway.
No key or real endpoint is included in repository examples or test fixtures.

For gateways with smaller supported requests, export `LLM_STRATEGY_BATCH_SIZE` and
`LLM_VALIDATION_BATCH_SIZE` (each 1–25, default 25) before startup. Strategy and validation
retain every full per-SKU input; validation cannot activate items until all batches
succeed and policy versions remain unchanged. Single-batch validation keeps the existing
narrative shape; multi-batch reports retain each complete response and its SKU IDs.

`LLM_MAX_ENVELOPE_BYTES` optionally rejects a complete application messages/schema
envelope above the configured UTF-8 byte count, including added repair feedback.
It never truncates facts or evidence. This is not an SDK wire-size limit or an estimate
of model token capacity. A rejection requires a smaller scope/batch or a capacity-backed
configuration change; merely raising the byte cap does not prove a request fits.

Use `SSL_CERT_FILE` or `REQUESTS_CA_BUNDLE` for a corporate CA bundle. Verification is on
by default. `ALLOW_INSECURE_TLS=true` is required before Settings permits a bypass; enabling
it emits a server warning and persistent header indicator. Re-enable verification after
correcting trust. No blanket Node TLS bypass is needed by the client bundle.

## W1 — Generate a pricing run

1. Open **Pricing runs** and select a category, full catalog, or API-supplied SKU set;
   choose objective, horizon, draws, and seed.
2. Choose **Quantitative preview** for read-only numbers without an LLM. Preview output
   includes the fit, uncertainty, baseline, quality checks, and skipped SKU reasons.
3. Choose **Grounded pricing workflow** after configuring all aliases and indexing policy
   evidence. Watch the five fixed node stages. Required Commerce/grounding/quality failure
   stops the run; optional competitor degradation is visible and reduces confidence.
4. Open candidate evidence. Check current/proposed price, deltas, 95% impact/forecast
   bands, sample size, confidence contributions, assumptions, citations, rules, and band reasons.
   Source buttons resolve published citations through the platform.
5. Open **Review queue** to view current states. A saved run report is retained evidence;
   later revisions/decisions appear in the queue and audit trail.

The model cannot replace tool-computed numbers. Grounding is fetched again on each model
call; cached results must validate against current sources. A missing/unresolvable citation
or invalid structured output gets one repair attempt, then a typed failure. Execution makes
no model call. Quantitative previews do not create approval authority.

## W2 — Review bands and choose operating mode

Supervised queues all bands for a human. Assisted automatically approves only Auto-approve.
Autonomous also releases clean Review items after the configured hold unless a human
intervenes. Escalate always requires a written human intervention; compliance failure is an
absolute veto in every mode. A band is independent of disposition: Supervised does not
rename queued Auto-approve items to Review.

1. Filter/sort the queue by band, category, compliance, confidence, absolute delta, impact,
   or disposition. Product buttons/checkboxes and drawer actions support native keyboard
   navigation; actual 1280px/browser visual and interaction acceptance remains to be exercised.
2. Open a recommendation. Inspect all evaluated rules/thresholds, source context, family
   ladder, stability, hold release time, and approval/receipt evidence.
3. Approve/reject the expected revision, or select Override and supply price plus a written
   reason. The server independently revalidates overrides and recomputes their forecasts.
4. Bulk selection includes only actual Review-band items with clean compliance and confidence
   **strictly above** the current bulk threshold. Server validation remains authoritative.
5. Change global mode in the header. Mode/policy changes increment authorization generations
   and cancel pending intents from the previous generation. Create a fresh run as needed.
6. Edit initial policy thresholds in Settings or inspect `/api/policy`; record the resulting
   version. These are development defaults, not proven calibration values.

The global **Halt** opens exactly one confirmation. Confirming fences dispatch, stops the
loop/active work, cancels pending authority, and acknowledges Supervised. A disconnected
control does not claim success. Already-sent requests may have committed and are reconciled;
halt does not pretend to recall an external write. Inspect unknown outcomes and receipts.

## W3 — Simulate one or many candidate prices

1. Open **Scenario lab**, choose one or more distinct SKUs, and enter positive tick-aligned
   prices. Choose horizon, draws, and seed. Numerical API supports up to 500 items; the
   interactive form bounds manual entry to 50.
2. Select normal assumptions or demand-collapse/competitor-undercut/cost-spike stress.
3. Optionally request grounded interpretation. If unavailable, its explicit status is shown
   while numerical results remain inspectable.
4. Simulate. Inspect medians and 95% intervals, margin-floor breach probability, current
   and conventional baseline comparisons, aggregate distributions, and assumptions.
5. Name the request and choose **Reevaluate & save**. This performs a fresh evaluation
   against current Commerce data and retains that request/result. Loading a saved item shows
   the saved evidence; simulate again to use current data. No scenario can approve a price.

Matched numerical inputs/seed use the same engine as recommendations. Differences in
learning version, stress, stock, costs, evidence date, or horizon invalidate a direct parity claim.

## W4 — Upload company knowledge without restart

Use the global **Knowledge & grounding** panel. Upload UTF-8 `.txt`/`.md` up to 2MB into
`pricing_policy`, `market_intel`, `product_kb`, or `user_uploads`. Wait for **ready**;
queued/indexing/failed/interrupted jobs and safe errors remain visible. Collection counts,
last update, and corpus revision reflect only active published versions.

Optional source ID/title/version identify immutable versions. With no explicit ID, filename
determines the logical source. Same version replay is a no-op; changed text or metadata must
use a new version. A metadata-only update needs an explicit new version. A failed replacement
preserves the prior active document, and historical published citation IDs remain resolvable.

```sh
.venv/bin/python -m scripts.rag ingest examples/pricing-policy.md --source-id demo-pricing-policy --collection pricing_policy --version demo-v1
.venv/bin/python -m scripts.rag query "What margin and change rules apply?" --role analyst
.venv/bin/python -m scripts.rag collections
.venv/bin/python -m scripts.grounding_smoke
```

Copy a complete returned citation ID to `.venv/bin/python -m scripts.rag citation 'ID'`.
The smoke script uploads the synthetic example, waits for publication, retrieves it, and
resolves its citation through the running Vite proxy. It writes ignored local evidence.
Then run W1 again to demonstrate that current uploaded evidence reaches actual model calls.
That last live gateway demonstration remains unverified without configured access.

RAG settings are `RAG_EMBEDDING_PROVIDER`, `RAG_MODEL_CACHE_DIR`, `RAG_CHUNK_SIZE`,
`RAG_CHUNK_OVERLAP`, and `RAG_{ROUTER,NARRATOR,ANALYST,STRATEGIST}_TOP_K`.
Defaults are local, 700/100-character token-aware chunks, and breadth 1/2/3/4 per populated
collection. Every role breadth is 1–10. Overlong queries fail rather than silently truncate.
Gateway embedding additionally requires `ALLOW_GATEWAY_EMBEDDINGS=true`,
`RAG_GATEWAY_EMBEDDING_MODEL`, and matching `RAG_GATEWAY_EMBEDDING_DIMENSIONS`.
Changing embedding identity requires a separate knowledge store; live gateway embeddings
are not verified. No automatic gateway fallback occurs.

## W5 — Inspect push, replay, partial results, and revert

Approved human and automatic items use the same dispatcher. Final checks include durable
approval revision, policy/mode generation, current Commerce price/version, cooldown, all
rules, and automatic band eligibility. Commerce independently checks rules again.

Inspect each queue item's receipt: applied, execution-rejected, stale, or unknown is explicit.
Partial results are first-class. The durable batch key binds its payload. A timeout after a
possible commit is reconciled using receipt lookup and bounded same-key replay; changed
payload under the same key is rejected. **Do not generate a replacement key for an unknown result.**

For a confirmed applied item, choose **Revert this change**. A new linked idempotent batch
restores the retained prior price only if current price/version, rules, and cooldown permit.
It does not delete original history or force a newly illegal price. The resulting item/receipt
and audit evidence stay visible. Repeated revert requests do not duplicate the restoration.

Use isolated automated fixtures for partial rejection/ambiguous commit; deliberately causing
transport faults in the user's running application is unnecessary:

```sh
.venv/bin/python -m pytest -q tests/test_commerce.py tests/test_governance_execution.py
```

## W6 — Read outcomes and inspect bounded learning

Use the refresh button on **Realized performance**, or `POST /api/feedback/refresh`.
Readback fetches aggregate sales over Commerce HTTP. The window starts on the UTC day after
confirmed application and spans the forecast horizon. A complete, mature daily window at
the approved price is required. Incomplete/immature windows remain pending; absence is not
zero sales. Intervening price treatment or overlapping days is excluded from learning.

The overview distinguishes forecast/baseline from observed revenue/profit, coverage/error,
and pending counts. Cost uses decision-time evidence because a realized cost feed is absent.
`GET /api/feedback` exposes provenance and immutable learning versions. Subsequent numerical
runs consume bounded elasticity/residual updates. Widening errors warn; intervals are never
forced narrower simply because more runs occurred.

The seeded history stops at its as-of date and does not generate future transactions after
a new push. Pending is therefore expected in a fresh live demo. Mature feedback/learning is
verified with isolated dated fixtures, not by changing the machine clock or fabricating sales:

```sh
.venv/bin/python -m pytest -q tests/test_feedback_learning.py
```

Forecast uplift is not causal realized uplift. Human acceptance, escalation precision,
longitudinal interval coverage, and convergence require sufficient observations/labels.

## W7 — Reconstruct a decision in audit

Open **Audit trail**. Filter by run ID/SKU/system-only, inspect event details, and export
JSON. Evidence includes source hashes/versions, node events, numeric distributions, rule
values, stability/band reasons, actors/mode versions, approval revisions, batch attempts,
and Commerce receipts. Export applies server filters and reports its 10,000-event bound.
Audit records cannot be edited/deleted through application routes; SQLite append-only
triggers protect existing audit rows. Retained evidence never replaces Commerce authority.

`GET /api/recommendations/{id}` includes immutable revision history. Saved run reports can
precede current decisions, so correlate the item ID/revision with the queue and receipt.

## W8 — Operate settings, monitor, and integrations

The global header survives navigation: mode, loop state, halt, token/cost monitor, settings,
theme, and TLS bypass indicator remain available. Theme preference alone is stored locally.
Settings shows live cache values returned by the server and configurable decision policy.
Monitor totals include failures; cost is an estimate using configured fallback USD rates,
not a bill. Cache namespace changes with model, facts, policy, corpus, and evidence.

Local `data/telemetry.jsonl` always receives a best-effort, fixed metadata allowlist for
HTTP/tool/model activity. Prompt text, HTTP bodies, sales rows, and keys are excluded.
`LANGFUSE_ENABLED=true` plus host/public/secret keys permits metadata-only export. A bounded
background queue isolates tracing failures from pricing; unavailable telemetry is reported.
No real remote Langfuse egress has been verified. Ambient prompt tracing is disabled.

**Ask the evidence** calls the grounded router and cannot approve, push, or start tasks.
`/.well-known/agent-card.json` advertises a bounded A2A **0.3** JSON-RPC subset at `/a2a`:
`message/send` starts the normal grounded run, `tasks/get` polls it, and human decisions
stay in the local review flow. No full protocol lifecycle/negotiation is claimed.

Competitors use the synthetic adapter by default. `LIVE_COMPETITOR_ENABLED=true` and
`LIVE_COMPETITOR_URL` explicitly select a bounded remote JSON feed using the same contract
and TLS helper. This is not a website scraper. Remote availability and data quality remain
unverified; unavailable optional feed data is visibly degraded.

## W9 — Start, stop, and recover continuous scheduling

1. Open **Loop** in the header. Confirm scheduling is off and choose scope, objective,
   horizon, interval (5–86,400 seconds), and optional iteration cap (1–1,000).
2. Choose **Start loop**. Acknowledged server state shows session ID, iteration count,
   next-run countdown, and last run. Each iteration uses the full current-policy pipeline.
3. Review waits remain visible item interrupts. Numerical/required grounding/gateway or
   execution failures stop future scheduling and show an error; a new session is explicit.
4. Choose **Stop scheduling** to stop the timer. Existing decisions remain inspectable.
   Use global **Halt** when pending automatic authority must also be canceled.
5. Stop/restart the application. Loop sessions/history persist, but scheduling stays off.
   Resume an interrupted grounded run explicitly from Pricing runs after resolving its
   item decision. Starting a new loop is separate from checkpoint resume.

```sh
.venv/bin/python -m pytest -q tests/test_interval_loop.py tests/test_workflow_integration.py
```

## Recovery and release evidence

| Condition | Action |
|---|---|
| Local model missing | Run explicit prepare/check; retain failed upload metadata, then resubmit. |
| Gateway/schema failure | Check URL, key, all four actual aliases and CA trust; correct Settings, then explicitly retry/resume. |
| Commerce unavailable or malformed | Restore the required service/data; never treat it as an optional partial run. |
| Stale recommendation/revision | Refresh evidence and create a new run; do not force old versions. |
| Unknown Commerce result | Reconcile original durable key/receipt; no new payload/key for the same attempt. |
| Halt during send | Inspect reconciliation and confirmed receipts; use a compliant compensating revert if needed. |
| Failed loop | Inspect last run and fix its cause; restart scheduling explicitly. |
| Restarted uploads | Active finite work drains on graceful shutdown; interrupted jobs can be safely resubmitted. |
| Restarted graph | Resume explicitly; stale automatic authority is canceled and loop remains off. |
| Telemetry failure | Continue business safely, inspect monitor availability/dropped counts, restore writable storage/optional tracing. |

Run `.venv/bin/python -m pytest -q`, `npm test`, and `npm run build` before release.
The 2026-11-15 local verification passes 529 backend tests, 67 DOM tests and the
UI build. `scripts.acceptance_demo` also passes all 56 isolated W1–W9 cases.
Against running services, `scripts.operations_smoke`, `scripts.smoke`, and
`scripts.grounding_smoke` verify read-only previews/scenarios and local knowledge without
changing Commerce prices. Use the project interpreter, for example
`.venv/bin/python -m scripts.operations_smoke`.
Running-service `scripts.smoke` checks a 500-SKU preview, responsiveness, scenario parity,
and unchanged prices; `scripts.grounding_smoke` checks real-model runtime upload/retrieval.
One real local five-stage, one-SKU workflow reaches Supervised review in 284.447s with
validated citations and no price writes. Real 500-SKU model timing/statistical reliability,
browser visual/interaction behavior, native Windows, human labels and mature business
effectiveness remain acceptance gates until directly observed.
Use [task.md](../task.md) for the dated verification record; do not mark unavailable targets
passed because a deterministic test fixture or document describes the desired behavior.
