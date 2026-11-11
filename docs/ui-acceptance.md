# Functional UI acceptance evidence

Date: 2026-11-10. The functional suite renders the actual application components into
jsdom and drives them with Testing Library user events. Every network request is handled
by an isolated, explicit test fixture; the suite never connects to the running Commerce
service, pushes a real price, or uses a runtime model fallback.

## Verification repeat — 2026-11-11

The unchanged frontend passed `npm test` again: source-rendering/eligibility checks and
all 29 DOM interaction tests, with zero failures, skips, or cancellations. The DOM suite
reported 71.88s while the production build ran concurrently. TypeScript/Vite also passed
(Vite reported 15.91s), and whitespace checks passed. These are test/build execution times,
not browser interaction latency measurements. No feature or test behavior was changed.

T38's functional acknowledgment, one-confirmation halt, server loop state/counts, and
disconnected/failure cases remain covered by the tests listed below plus the independent
backend governance/loop suite. T26/T32/T33's actual viewport, painted-theme readability,
and browser-render latency gates remain open.

Exactly one CUA inventory was attempted with an 8,000ms execution timeout. It returned
“js execution timed out; kernel reset” after 12.81s tool wall time and supplied no browser
or app state. No retry or native Chrome fallback followed. The completion summary records
the timeout; no navigation or application action was performed.

## Reproduce

Use the project's supported Node runtime, install `web/package-lock.json` with `npm ci`,
then run from `web/`:

```sh
npm test
npm run build
# Run only DOM interactions:
npm run test:dom
```

`npm test` combines the existing source-rendering/eligibility checks with **29 passing DOM
interaction tests**, zero skipped/canceled tests. The recorded DOM run completed in 15.80s
while a production build ran concurrently. TypeScript/Vite and `git diff --check` passed.
Suite durations include deliberate typing, waits, and fixture responses; they are **not**
measurements of browser action/render latency.

Test dependencies are pinned: jsdom 26.1.0, React Testing Library 16.3.0, DOM Testing Library
10.4.1, and user-event 14.6.1. Source/test modules stay below 400 lines. The runner bundles
repository TSX while sharing one installed React instance and cleans its temporary output.

## Requirement evidence

| Task | Actual component interactions verified | Acceptance limit |
|---|---|---|
| T26 review | Tab reaches a product row, Enter opens its drawer, focus stays in the dialog, Escape closes it and restores focus. Filters cover band/category/disposition/compliance/confidence/delta; sorting covers impact/confidence/delta/band/category. Approve/reject send the expected immutable revision. Override and escalation require a nonblank reason. Veto/no-change states have no approval/revert action. Stale errors do not claim success. Bulk excludes Auto, Escalate, exact-threshold, violating, and terminal rows; missing policy visibly disables bulk. Citation buttons resolve supplied evidence. | This verifies DOM event/focus behavior. Actual 1280px layout and browser-native keyboard/accessibility behavior remain unobserved. |
| T32 simulation | One/many SKU selection, duplicate exclusion/removal, price/horizon/stress/narration payloads, pending/error/retry states, interval labels, margin-risk probability, AI/current/baseline comparisons, retained assumptions, re-evaluation/save/load, and absence of approval routes. Missing intervals/narration remain explicit. | Content remains present under light/dark theme attributes. Painted chart contrast/readability in both themes is not established by jsdom. |
| T33 shell | The same global header survives route navigation. Theme toggling updates the document and persists across remount through the theme-only localStorage entry. Global operational controls remain available across routes. | Actual CSS layout, vector rendering, and <=500ms browser interaction/render latency remain unverified. |
| T38 controls | Mode changes remain pending until acknowledged; failures retain the prior mode. Halt makes no request before its sole confirmation, supports cancel, makes one request after confirmation, then reflects acknowledged Supervised and Loop off. Failed halt retains the current mode and does not claim success. Loop start/stop submits current scope/constraints, reflects server state/counts/run links, and reports failure. Disconnected controls disable mode/halt/start and make no authority-changing request. | These functional requirements are covered with the actual React components and explicit server-response fixtures. Pending-dispatch cancellation, hold timing, and kill fencing are independently covered by the backend governance/loop suite. No real-browser or pixel claim is needed for this functional result. |
| T06/T34 settings | All four aliases apply; transient key clears and is absent from DOM/localStorage. Runtime gateway checking sends no key or request body, waits for the server, distinguishes a verified model listing from unverified structured generation, and shows missing-model/network failures. Policy updates submit only changed fields. TLS bypass stays disabled without the server flag. | Fixture readiness is not live gateway readiness. Actual configured gateway availability still requires a real probe. |

The interaction tests found one actionable UI gap: a missing decision policy disabled
bulk approval but did not explain why. The review page now displays a policy-unavailable
error while continuing to block bulk authority.

## T38 test cases

- `mode changes remain pending until server acknowledgment and rejected changes show no success`
- `halt has exactly one confirmation, supports cancel, and acknowledges Supervised only after the server`
- `failed halt preserves current mode and confirmation without a false acknowledgment`
- `disconnected controls disable price authority and do not claim loop start success`
- `loop setup submits scope and constraints, updates actual counts, and stops after acknowledgment`
- `failed loop start shows an actionable error and leaves scheduling off`
- `global controls survive routes and theme preference persists after remount`

The backend counterpart is in `tests/test_governance_workflow.py`,
`tests/test_governance_execution.py`, and `tests/test_interval_loop.py`: durable decisions,
mode/band policy, pending cancellation, server dispatch fencing, loop failure/boot behavior,
and already-sent receipt reconciliation. The DOM fixture does not substitute for these
backend guarantees.

## Browser access and remaining work

A fresh CUA inventory completed in 5.48s with no browser surfaces and
“The browser access host is unavailable.” The previously hanging native Chrome fallback
was deliberately not retried. No tab was created and the actual local app was left running
unchanged. See [browser-qa.md](browser-qa.md) for the earlier native-access blocker.

Functional T38 acceptance can be assessed from the DOM interactions plus backend tests.
T26/T32/T33 still need actual 1280px/pixel/theme/latency evidence where their acceptance
criteria explicitly require it. Live gateway calls, Windows execution, real human labels,
and business-effectiveness measurements are separate gates recorded in
[task.md](../task.md) and [validation.md](validation.md).

Testing Library documents the [user-event setup and interaction model](https://testing-library.com/docs/user-event/setup/).
jsdom explicitly lists [layout as unimplemented](https://github.com/jsdom/jsdom#unimplemented-parts-of-the-web-platform),
which is why DOM assertions are not presented as visual or browser performance proof.
