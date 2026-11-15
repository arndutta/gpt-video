# Optional local model integration

## Working five-stage functional path — 2026-11-15 (Asia/Kolkata)

The concise-narration functional diagnostic now **passes**: all five actual graph
stages reach a persisted Supervised human-review interrupt for one SKU in **284.447s**.
It uses real MiniLM, LiteLLM/Ollama and the complete original facts/schema. The one
recommendation has a validated citation, its computed numerical artifact is unchanged,
and Commerce prices/versions remain unchanged with zero price writes.

This is a separately labelled **480-second functional observation window**; the default
diagnostic deadline remains 240 seconds. It does not establish the unchanged requirement
for 500 SKUs in under 300 seconds. The earlier failed 240-second attempts remain below.
The safe artifact is `data/local_graph_functional_20261115.json`.

Seven real provider calls include two ordinary single repairs. All observed token
budgets fit context 4096 with batch 64/output limit 800; native input/context loss stays
disabled. No input-truncation or runner-kill marker appears. All owned listeners and
forwarders stop, no model remains loaded and temporary storage is removed. A single
successful workflow is not statistical 99% post-repair validity or four distinct
corporate model tiers.

To reproduce this explicit functional diagnostic:

```sh
.venv/bin/python -m scripts.local_graph_probe --model phi3:mini --deadline-seconds 480 \
  --output data/local_graph_functional_result.json
```

## Full graph verification — reconciled 2026-11-15 (Asia/Kolkata)

The real 1-SKU graph still does not pass. After the output-length repair and sibling-task
ownership fixes, both Data & Context responses recover with their normal one repair;
that stage completes in **175.712s**. The **240.031s** overall deadline then interrupts
Quantitative narration, before any recommendation reaches review. No larger real-model
graph run or further generation retry followed. The report is
`data/local_graph_probe_after_repair_20261114.json`.

The reproducible diagnostic is:

```sh
.venv/bin/python -m scripts.local_graph_probe --model phi3:mini \
  --output data/local_graph_probe_result.json
```

It uses real MiniLM, a real local model, fresh temporary Commerce data through the HTTP
adapter and Supervised mode. An owned loopback forwarding guard preserves messages,
schema and options while adding native `truncate=false` and `shift=false`; these fields
are version-pinned to the verified Ollama 0.40.16 API contract. Oversized or uncertain
requests cannot receive a passing context-budget claim. Normal citation validation,
schema and numeric authority remain unchanged. It is a diagnostic, not an application
fallback or a replacement for the corporate models.

All five observed native request budgets fit 4096 tokens, without input truncation or
runner-kill markers. The ordinary SDK usage is **5,308 input / 2,967 output tokens**;
native metadata totals **8,335 / 3,767**, including a canceled inference that finishes
during cleanup. The SDK snapshot must not be presented as total native consumption.
Both owned listeners stop, all forwarders finish, no model remains loaded, and there
are zero price writes. A November 15 read-only check independently reconfirms cleanup.
Full workflow reliability, 500-SKU latency and release acceptance remain open.

## Successful bounded probe — 2026-11-14 (Asia/Kolkata)

A read-only check found the installed Ollama runtime had changed from the historical
0.32.1 failure logs to **0.40.16**. This changed condition justified one isolated retry
of the existing helper, preserving the full schema/evidence, 4096-token context,
batch 64 and 800-token output limit. No model download or daemon configuration change
was made. The earlier runner kill's cause remains unconfirmed.

The real `GroundedLLM` request passes in **11.677s**, with one provider call, zero repair
attempts, 419 input tokens, 109 output tokens, and one validated local-RAG citation.
Proxy port 4002 is free after cleanup and Ollama reports no loaded model. The safe
artifacts are `data/local_gateway_readiness_20261114.json` and
`data/local_gateway_probe_20261114.json`.

This establishes one working local structured generation. It does not establish a 99%
validity rate, a 500-SKU live pipeline, four distinct corporate model tiers, or release
readiness. The earlier failure records below remain historical evidence.

## Helper and historical observations

This explicit probe uses an **already installed** Ollama model through a separate
LiteLLM proxy. It does not configure the running workbench, change prices, download
models, change the Ollama service, or enable a fallback in the application.
All four aliases route to the model selected on the command line; these names do
not certify the corporate Flash/Pro model tiers or the full release acceptance criteria.

Install the optional proxy outside the application's virtual environment:

```sh
.venv/bin/python -m venv .cache/local-gateway-env
uv pip install --python .cache/local-gateway-env/bin/python 'litellm[proxy]==1.109.0' --cache-dir .cache/uv
```

With the existing Ollama service listening on `127.0.0.1:11434`, select an exact
identifier from its installed model catalog. For example, this machine has
`phi3:mini` installed:

```sh
.venv/bin/python -m scripts.local_gateway --model phi3:mini --output data/local_gateway_probe.json
```

An explicit `--batch-tokens 64` reduces the per-request prompt processing batch
from its default 512 tokens. It preserves the full input, strict response schema,
4096-token context, 800-token output limit and citation checks. It does not change
the Ollama daemon's configuration. The report records the selected request limits.
Smaller batches may reduce temporary compute allocations; a previous signal kill
does not establish that a smaller batch will make inference succeed.

```sh
.venv/bin/python -m scripts.local_gateway --model phi3:mini --batch-tokens 64 --output data/local_gateway_batch64_probe_20261112.json
```

The helper checks that port 4002 is free, starts a loopback-only proxy, verifies
`local-router`, `local-narrator`, `local-analyst` and `local-strategist` via the real
model catalog, and makes one `GroundedLLM` structured `CitedNarrative` request.
It uses real cached MiniLM embeddings and temporary Chroma evidence containing
only a small public synthetic policy. The ordinary wrapper validates citations and
permits its usual single repair; each model attempt is bounded at 120 seconds.
No provider factory or scripted model response is injected.

The JSON report contains safe metadata: catalog status, structured-call status,
citations if successful, timing, token/cache metrics, and the unchanged-price fact.
Usage prices for unknown local aliases are explicitly fallback estimates rather
than a measurement of local electricity or hardware cost. A successful catalog
check alone does not establish structured output support. A failed call exits with
status 1 and retains a safe error code.

The proxy key is random, exists only in helper memory and the proxy child
environment, and is never printed or written to the temporary configuration. The
child receives a minimal environment without inherited cloud credentials, tracing
destinations, database settings or external proxy variables. The helper suppresses
proxy stdout/stderr, disables callbacks, telemetry and prompt/spend/error logs,
uses bundled offline cost/tokenizer data, and has no database or remote provider.
It preserves the existing Ollama daemon's own configuration and logging policy.

The CLI cleans up the proxy and temporary RAG files on completion, failure, Ctrl+C
or SIGTERM, and restores its caller's previous SIGTERM handler afterward;
the existing Ollama service and workbench services stay running. The model context
is capped at 4096 tokens, output at 800 tokens, and `keep_alive=0` requests unloading
after each inference. This is a small integration check, not a 500-SKU performance
test. The helper does not start a permanent daemon.

`LocalGateway.running()` is also an explicit Python context manager for isolated
integration checks. Its `settings(directory)` method returns memory-only
credentials for that context. Do not persist or print those credentials. Callers
embedding this context manager retain responsibility for their process signal policy.

Observed on this machine: the actual `scripts.preflight.check(mode="grounded",
skip_ports=True)` passed in **6.589 seconds** using a temporary proxy and a fresh
real MiniLM embedding operation. It verified the venv, Node runtime, dependencies,
writable storage, four real gateway aliases and local 384-dimensional embeddings.
Ports were skipped because the existing workbench services were already running.
The memory-only environment fields were restored afterward, the temporary proxy
stopped, and there were zero model generations and price writes during this check.
The metadata report is `data/local_grounded_preflight.json` (ignored runtime data).

Generation was blocked during the November 12 probes. Tiny requests failed with HTTP 400, reported safely
as `gateway_call_failed`; no validated response or citations were produced. In the
final bounded diagnostic, the native Ollama runner logged termination with
**`signal: killed`** at `2026-11-12T00:26:01.108+05:30`, from `llama_server.go:976`.
The corresponding native HTTP400 entry has the same second (`00:26:01`), tying
that request failure to runner termination. The reason for the kill was not
established; out-of-memory is not a verified diagnosis. Static adapter inspection
confirmed that the JSON schema, context limit, token limit and keep-alive settings
are forwarded correctly, and each alias has a registered deployment. No schema
relaxation, remote fallback, new model or server configuration change was applied.

The helper stopped every proxy, retained no provider response text and performed
zero price writes. A larger graph run was not attempted, and the running workbench
was left unconfigured. `data/local_gateway_probe.json` and
`data/local_gateway_diagnostic.json` retain safe failure metadata. Startup readiness
does not complete the live-generation or corporate-model acceptance tasks.

On November 12, a single additional request tested the explicit batch64 override
after reading current system and runner resource metadata. The exact initial
synthetic request, including the full strict schema and serialized JSON overhead,
measured 2,196 UTF-8 bytes. Adding a conservative 171-token template reserve,
64-token special-token reserve and the unchanged 800-token output cap gave a
3,231-token initial budget within the retained 4096-token context. This initial
budget does not certify an arbitrary repair request. The independent budget is
recorded in `data/local_gateway_batch64_budget_20261112.json`.

The request still failed safely after **6.777 seconds**, with one provider call,
no repair and zero returned tokens or citations. Native metadata confirms the
selected limits reached the runner: `n_ctx=4096`, `n_seq_max=1`,
`n_batch=n_ubatch=64`. The KV allocation was 1536 MiB; compute allocations were
39.02 MiB and 2.00 MiB. At `2026-11-12T20:48:38.314+05:30`, the runner again
reported `signal: killed`, matching the HTTP400 entry at the same second. This
does not establish the reason for the kill. No input-truncation marker appeared,
no model remained loaded afterward, and port4002 was free after cleanup. There
were zero price writes and no changes to main application settings or data.
The safe result is `data/local_gateway_batch64_probe_20261112.json`. No larger
graph run or further generation retry followed this failed bounded probe.

Implementation references: [LiteLLM Ollama provider](https://docs.litellm.ai/docs/providers/ollama),
[offline mode and outbound requests](https://docs.litellm.ai/docs/proxy/outbound_requests),
[usage telemetry](https://docs.litellm.ai/docs/proxy/telemetry),
and [log storage settings](https://docs.litellm.ai/docs/proxy/ui_logs).
Ollama documents per-request `num_ctx` and `num_batch` in its
[API reference](https://github.com/ollama/ollama/blob/main/docs/api.md).
