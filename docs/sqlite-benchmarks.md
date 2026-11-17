# SQLite benchmark and acceptance evidence

Measured on **2026-11-17** from commit
`ff89acd543cb90c3524df2c72b7ec70f02be8549`, before later UI changes. These
three isolated commands below ran sequentially in temporary storage, without
listeners or changes to running application data/prices. Commerce reads used the
ASGI HTTP adapter. Local retrieval used the prepared MiniLM model and SQLite RAG;
generation used an explicit deterministic typed model fixture.

```sh
.venv/bin/python -m scripts.benchmark --skus 500 --iterations 1000 --as-of 2026-11-17 --output data/benchmark_sqlite_20261117.json
.venv/bin/python -m scripts.cache_benchmark --samples 200 --output data/cache_sqlite_20261117.json
.venv/bin/python -m scripts.acceptance_demo --output data/acceptance_demo_sqlite_20261117.json
```

Hardware/software: Apple M1, 8 logical CPUs, 8,589,934,592 bytes RAM, macOS 15.6.1
arm64, Python 3.11.5, Node v24.4.1, NumPy 2.4.6, SciPy 1.17.1. The fresh Beverages
fixture contains 500 SKUs and 180 sales days, seed 42, 1,000 draws, a 14-day horizon,
the balanced objective, and a 21-point candidate grid (20–21 feasible prices per SKU).
Raw JSON retains unrounded measurements; the tables round seconds to six decimals.

| Measurement | Result | Target and outcome |
|---|---:|---|
| 500-SKU quantitative analysis | 1.493533s | <300s: passed for this numeric workload |
| Monte Carlo compute | 0.244869s | <60s: passed |
| One-SKU scenario | 0.005509s | <5s: passed; forecast equals the matching recommendation |
| Actual five-node graph to first human review | 6.390342s | <300s: passed **with the model fixture** |
| Concurrent health response, maximum of 100 samples | 56.979666ms | Responsiveness evidence during numeric compute |
| Concurrent event-loop gap, maximum | 90.037875ms | ASGI/backend evidence; does not measure browser actions |

The graph finished `awaiting_review` in Supervised mode with 500 queued SKUs, 500
cited SKUs, 43 model-fixture calls, and **zero price-history rows**. Its checkpoint
files occupied 88,001,600 bytes. Timing stops at the first real human interrupt and
excludes human review and live model generation. See
[`benchmark_sqlite_20261117.json`](../data/benchmark_sqlite_20261117.json).

## Warmed cache stages

Two warmup calls preceded 200 alternating equivalent-context requests. Every
measured request retrieved current evidence using real local MiniLM and SQLite RAG.
The runner imposed no concurrent workload; other system load was uncontrolled.

| Stage | Samples | Median | p95 | Maximum |
|---|---:|---:|---:|---:|
| Retrieval | 200 | 1.407ms | 1.565ms | 1.987ms |
| SQLite cache lookup | 200 | 0.618ms | 0.729ms | 0.864ms |
| Total grounded response | 200 | 2.314ms | 2.527ms | 2.856ms |

All 200 sampled responses met <100ms. There were 100 exact hits, 100 semantic hits,
and zero measured misses: a 100% hit rate on this warmed repeated-context fixture.
This exceeds 40% for this workload but does not establish the operational repeated-run
hit rate or guarantee every future cache hit will be below 100ms. The benchmark's
separate 20-sample cache check recorded p95 5.198746ms and maximum 25.889667ms;
its 20 hits/21 total calls (95.2381%) include one cold miss.

The cache runner's scoped source SHA-256 was unchanged during execution:
`9d87617a1a27736c03d52a603b4c5900edcdc52e837ade86f86673a7a65e34dc`.
Its five-file scope is declared in `scripts/cache_benchmark.py`. See
[`cache_sqlite_20261117.json`](../data/cache_sqlite_20261117.json).

## Effectiveness targets

These are synthetic forecast and held-out generator comparisons. They are not
observed sales outcomes or causal business uplift.

| Target | Measured result | Outcome |
|---|---:|---|
| Forecast revenue uplift versus baseline ≥5% | −6.908511% | Failed |
| No forecast gross-profit degradation | +1,313,678.820627 forecast currency units | Passed on fixture |
| No forecast margin-rate degradation | +0.173951 absolute rate (+17.395103 percentage points) | Passed on fixture |
| Every high-confidence price within 10% of held-out optimum | 410/419 (97.8520%); 9 outside | Failed |

High confidence means score >0.8; 419 of 500 SKUs qualified. Their mean absolute
price error was 1.177665% and maximum error was 22.923497%. The held-out optimum
uses generator demand/elasticity, stock-capped expected demand, the same feasible
grid and family ladder, and the balanced objective. These results retain the
original targets; they do not change policy thresholds or resolve T46.

## W1–W9 implementation acceptance

The isolated acceptance demonstration passed **all nine workflows and 56 cases in
8.910s**, subprocess exit code 0, with no skipped/missing evidence and no source
change during execution. Its temporary fixture storage was removed, live services
were not contacted, and inherited gateway/tracing/proxy configuration was removed
from the child process. The report, JUnit file, and pytest log are retained as
[`acceptance_demo_sqlite_20261117.json`](../data/acceptance_demo_sqlite_20261117.json),
[`acceptance_demo_sqlite_20261117.junit.xml`](../data/acceptance_demo_sqlite_20261117.junit.xml),
and [`acceptance_demo_sqlite_20261117.pytest.log`](../data/acceptance_demo_sqlite_20261117.pytest.log).

The unchanged SHA-256 covers 171 Python files under `commerce`, `platform_app`,
`scripts`, and `tests`, including uncommitted content:
`9f79514194ed04ee8e753920f1f073bb6b8d04f8944a5cf06ec8c3c1d42192b6`.
See [the workflow descriptions and fixture limits](acceptance-demo.md).

## Native macOS service acceptance

After the isolated measurements, this separate runner started three owned native
service children against another fresh temporary 500-SKU/180-day SQLite fixture:

```sh
.venv/bin/python -m scripts.local_acceptance --as-of 2026-11-17 --output data/native_sqlite_acceptance_20261117.json
```

It passed in **8.886s**. The HTTP 500-SKU/1,000-draw preview took **3.285s**;
the concurrent HTTP health request took **118.77ms**. Scenarios matched preview
forecasts. Run constraints, zero-change caps, monitor/audit availability, Supervised
mode, and an inactive loop passed. Real local runtime upload through citable retrieval
took **0.253s**, published corpus version 1, and resolved the uploaded citation without
restart. Commerce prices and versions remained unchanged with **zero price writes**.

All three owned children stopped, temporary storage was removed, and ports 8000,
8001, and 5173 were free before and after execution; a separate listener check also
confirmed cleanup. The same 171-file Python source digest above remained unchanged.
This checks native macOS direct processes and HTTP behavior; it does not exercise
the `startup.sh`/`startup.bat` wrappers or render the browser. See
[`native_sqlite_acceptance_20261117.json`](../data/native_sqlite_acceptance_20261117.json).

The W1–W9 suite uses typed model and lightweight embedding fixtures; its mature-sales
windows use an isolated simulated observation clock. No ≥99% live post-repair model
validity, full live 500-SKU latency, native Windows execution, browser render/action
latency, human acceptance/escalation precision, operational Assisted share, realized
interval coverage, oscillation, or error-convergence target is established here.
Any later implementation or UI changes require the corresponding checks again;
these measurements do not certify a later source revision or production readiness.
