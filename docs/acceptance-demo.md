# Isolated W1–W9 acceptance demonstration

Run the backend implementation demonstration without contacting or changing the
running application:

```sh
.venv/bin/python -m scripts.acceptance_demo
```

The script launches one selected pytest suite in a temporary directory, removes
inherited gateway/tracing/proxy configuration from that child, and deletes its fixture
storage afterward. It writes `data/acceptance_demo_result.json`, a JUnit XML file, and
a pytest log. A workflow passes only when every selected assertion actually ran and
passed. Missing, skipped, failed, or uncollected cases fail the report. Changes to the
Python source tree during execution also fail the report so its source hash remains
meaningful. The report includes individual test names, measured durations, source hash,
platform, exit status, and limitations; the nine workflow counts can share evidence.

| Workflow | Demonstrated evidence |
|---|---|
| W1 | Actual five-node LangGraph, computed price integrity, valid citations, Supervised review, persisted checkpoints and item-scoped resume |
| W2 | All operating modes and bands, every compliance rule in every mode, written escalation decisions, kill fencing |
| W3 | Saved multi-SKU what-ifs, shared-engine uncertainty bands, stress cases and baseline comparison without price changes |
| W4 | Runtime upload replacement consumed by a subsequent grounded graph in the same application; historical citations retained |
| W5 | Per-item partial Commerce outcomes, original-key ambiguous-commit recovery, exact replay and independently validated compensating revert |
| W6 | Three nonoverlapping ten-day observation windows read through the real Commerce HTTP adapter; duplicate exclusion and bounded versioned learning |
| W7 | Append-only audit evidence, per-SKU reconstruction, decisions and HTTP attempts, redacted export |
| W8 | Runtime gateway settings, memory-only credentials, TLS opt-in boundary, metered structured SDK requests |
| W9 | Explicit start, iteration cap, timer stop, full-graph failure halt and scheduling off after restart |

This demonstration uses an explicit typed model fixture and lightweight embedding
fixture. It is not a normal-runtime fallback. W6 uses an explicit isolated Commerce
clock and synthetic aggregated sales, not mature real business observations. Gateway
requests in the SDK contract test use a mock HTTP transport. Passing demonstrates the
backend behavior under those declared fixtures; it does not establish real model
reliability/latency, product effectiveness, human review metrics, native browser
interaction, Windows execution, or production release readiness.

The final isolated execution on 2026-11-12 (Asia/Kolkata) passed all nine workflows
with 56 cases in 19.984s and subprocess exit code 0. The report confirms that the Python source hash
did not change during the run. Its JSON, JUnit XML, and pytest log are retained under
`data/acceptance_demo_result.*`; the JSON includes the exact source hash and every
asserted test case. Separately, 38 startup, gateway-readiness, acceptance-runner,
upload/readback, and architecture checks passed in 19.83s. These are measured fixture
suite durations. After the stale optimizer-interval correction, 34 focused override,
revert, workflow and architecture checks passed in 6.81s. Fresh human candidates clear
the previous optimizer's interval, while immutable earlier revisions retain it. These
checks are not live pricing-run or model latency results. Regenerate this report
after implementation changes instead of substituting these historical measurements.

Verified Python-source SHA-256:
`56dc51887cae7a6c199109194923a413e7b871e9dbebe4ad33bcea7e3c546efa`
(137 Python files across Commerce, platform, scripts, and tests).

## Mode-specific startup

```sh
./startup.sh --mode preview --seed
./startup.sh --mode grounded
.venv/bin/python -m scripts.preflight --skip-ports --mode preview --require-embeddings
.venv/bin/python -m scripts.preflight --skip-ports --mode grounded
```

Preview is the default unless `PRICING_STARTUP_MODE=grounded` is set. Grounded mode
requires gateway URL/key, all four role aliases advertised by `/models`, and an actual
embedding readiness check before the launcher starts any child. The existing
`--require-gateway` flag also selects grounded startup. Published grounding documents
are still required before a run; model-catalog verification does not claim structured
generation has succeeded. The platform repeats gateway verification in its own lifespan
when grounded startup is selected, so its public health reflects the child process's
current configuration.

The launcher checks Commerce health before starting the platform and checks platform
readiness before starting Vite. A degraded platform fails startup. It owns direct Python
and Node children, stops them in reverse order, and escalates termination only after a
bounded wait. It invokes the Vite JavaScript entrypoint directly rather than leaving an
npm shell between the supervisor and UI process.

On this macOS workspace, `./startup.sh --help` succeeded, and preview pre-flight with
real local embeddings verified Python 3.11.5, Node v24.4.1, writable storage, and a
384-dimensional model. An unconfigured grounded pre-flight fails with an actionable
missing-gateway message. A subsequent real local LiteLLM grounded pre-flight passes
in 6.589s with all four aliases and real MiniLM inference. Port checks were skipped
for that probe because the existing services were running; the separately exercised
Unix startup checked ports and actual readiness ordering. All local aliases map to
one installed model. Its generation probe fails, so this does not establish a working
chat model or corporate model-tier acceptance; see [local gateway evidence](local-gateway.md).

`startup.bat` uses the Windows virtual-environment interpreter and forwards the same
arguments. Tests exercise Windows-style `node.exe` plus `node_modules/npm/bin/npm-cli.js`
discovery, argument/environment propagation, readiness ordering, and cleanup through
portable process seams. No Windows machine or `cmd.exe` is available here, so native
Windows execution remains explicitly unverified rather than being inferred from those
tests. Corporate CA handling uses the shared TLS helper; insecure TLS remains opt-in.
