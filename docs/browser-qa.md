# Browser verification record

Date: 2026-11-10. Local application: `http://127.0.0.1:5173`.

## Bounded retry — 2026-11-11

One read-only `cua.getState()` inventory was attempted with an 8,000ms execution timeout.
The tool returned “js execution timed out; kernel reset” after 12.81s wall time, with no
accessibility tree, screenshot, or browser/app inventory. This attempt does not establish
current browser availability. No retry, native `getApp` fallback, tab creation, navigation,
or application action followed. Its CUA completion summary was recorded once.

The unchanged frontend passed its source-rendering checks, all 29 DOM interaction tests,
and strict TypeScript/Vite build again on November 11. These provide the functional evidence
in [ui-acceptance.md](ui-acceptance.md), including T38 controls; they do not establish actual
1280px layout, painted theme contrast, or browser action/render latency. Those gates below
remain unverified. The actual local services were not touched by the fixture-driven tests.

## Observed computer-use result

The CUA inventory reported Google Chrome running and available as a native application.
Its browser inventory was empty and reported **“The browser access host is unavailable.”**

The fallback call `cua.getApp('Google Chrome')` returned no accessibility tree or screenshot.
It remained pending for 1,814 seconds and was canceled during verification. Native inspection did
not succeed. No tab was created, no URL was opened, and no form, theme, operating-mode,
approval, or price action was performed through CUA. No isolated browser test fixture was
started. The CUA completion summary records this blocker. The running local application
was left unchanged.

## Checks completed without a browser

`npm test` passed using the actual React components with server rendering and decision
helpers. Coverage includes disconnected global controls, compliance veto, strict Review
bulk eligibility, terminal no-change behavior, citation extraction, family ladder sizes,
distribution intervals/risk/baseline, loop counts and links, and run-constraint validation
and serialization. These are automated rendering/contract checks, not browser interaction
or visual acceptance.

The strict TypeScript and Vite production build also passed after the November 10 UI
changes. Run-scoped maximum-change/category-bound controls and market-gap settings compile
against the API contract. Final backend and running-service checks are recorded separately
in [validation.md](validation.md) and [task.md](../task.md).

## Unverified browser gates

- Actual Overview, Catalog, Runs, Review, Simulation, Settings, Knowledge, and Loop screens.
- Layout, clipping, contrast, and distribution readability at a measured 1280px viewport.
- Light/dark appearance and persisted theme behavior in a browser.
- Keyboard Tab/focus behavior, populated review rows, bulk selection, and drawer actions.
- Browser acknowledgment of mode, halt confirmation, loop start/stop, and disconnected state.
- Ordinary UI action/render latency of at most 500ms.
- Actual gateway-generated recommendations and real human review effectiveness.

No visual, keyboard, viewport, or UI-latency requirement is marked passed from the CUA
attempt. Re-run these checks when either the browser host or native application access
can return an observable UI state.
