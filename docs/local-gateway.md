# Optional local model integration

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

Generation remains blocked. Tiny requests failed with HTTP 400, reported safely
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
