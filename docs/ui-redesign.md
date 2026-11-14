# Modern pricing workspace

Updated 2026-11-14 (Asia/Kolkata). The user selected a modern blue/mint dashboard
with spacious cards and subtle animation. The redesign is implemented in the
existing local React app at `http://127.0.0.1:5173`.

## Experience

- Deep navy navigation with grouped destinations, accessible collapsed labels,
  a collapse/expand control, and horizontal navigation on small screens.
- Persistent two-level header: navigation/search/theme/settings above service
  status, model monitoring, operating mode, loop state, and the existing halt action.
- Search pages and settings with the search button or Ctrl/Cmd+K. Arrow keys select,
  Enter opens, and Escape closes. The command menu offers navigation and settings;
  it cannot approve recommendations, start runs, or change prices.
- Overview hero with an interactive five-stage workflow explainer, real catalog
  metrics, recent runs, readiness, and quick links. The explainer is explicitly a
  workflow illustration rather than live run progress.
- Forecast/outcome and decision/stability dashboard tabs support arrow keys and
  Home/End. Actual denominators, pending observations, limitations, baseline
  comparisons, and learning evidence are retained.
- Catalog table/grid switch, explicit current-page sorting, server-side search,
  category filtering and pagination, and read-only product-detail drawers.
- Forecast interval graphics expose the supplied lower bound, median or mean,
  and upper bound through pointer/focus/keyboard controls. No density, histogram,
  or historical trend is fabricated. Missing/reversed intervals remain unavailable.
- Shared blue primary and mint success tokens, readable form/table/card styling,
  and matching drawers, settings, grounding, review, audit and scenario surfaces
  in light and dark themes. Theme preference remains the only persisted UI setting.
- Subtle card entrances, chart-line reveals, route fades, drawer motion and hover/
  focus transitions. `prefers-reduced-motion` disables these effects.
- Native keyboard-selectable cards for preview/grounded workflows and scenario
  stress cases. Selecting a card configures inputs; Enter in a card does not
  submit the form. Run/scenario summaries reflect the current draft inputs.
- Loaded run-history filters, review-band shortcuts with loaded-response counts,
  and a warning when selected review items are hidden by filters. Bulk eligibility
  and the exact-revision submission contract are retained.
- Audit timeline metadata shows the recorded actor, run and SKU. Reset clears
  both server-side and loaded-event text filters; records remain read-only.
- Evidence question starters populate an editable draft without calling a model.
  After a response, its submitted question stays visible while another draft is edited.
- Gateway edits clear old saved/verified feedback and require applying the draft
  before verification. During save/check requests, native disabled fields prevent
  newer edits from being mislabeled by an earlier response. Keys still clear on submit.
- Service-check failure has an explicit unavailable state and a read-only retry.
  Loading placeholders are decorative, announced once, and respect reduced motion.
- Modal Tab boundaries account for hidden fields, disabled fieldsets, closed details,
  radio-group stops, and explicit Tab order. IME composition does not navigate the
  command menu or dismiss its dialog; held shortcuts do not repeatedly toggle it.

Drawers render in the document body, outside header/filter/stacking contexts, retain
focus trapping and Escape/backdrop close, and restore the initiating focus. Each
dialog has its own accessible title ID. Existing mode/halt/loop acknowledgment,
review eligibility, approval confirmation and credential boundaries are retained.

## Source organization

`web/src/redesign.css` supplies the shared visual system after the existing base
styles. `web/src/app/shell.css` owns the shell and command menu. Overview, catalog,
and forecast components have scoped styles alongside their implementation. The
navigation registry and command component are separate from the persistent app.
`WorkflowChoices.tsx`, `ReviewBands.tsx`, and `DiscoveryStarters.tsx` supply the
workflow controls; `features/workflow-pages.css` styles their page-specific surfaces.
No dependencies, remote fonts, model calls, or backend changes were introduced.

## Verification and limits

The subsequent policy/upload follow-up passes **67/67 DOM cases in 12.998s**, UI
source/rendering checks and strict TypeScript/Vite build (Vite 1.44s). Pending policy
updates freeze their draft; failed updates retain it for retry. Accepted uploads and
completion transitions invalidate earlier in-flight history/collection reads and
schedule current reads once those settle. Four new cases cover these races and the
multipart upload/failure UI. Backend verification now passes 471 tests; actual browser
and live-generation acceptance remain open.

The November 14 reliability follow-up passes **63/63 DOM cases in 11.980s**, UI
source/rendering checks, strict TypeScript/Vite build (Vite 1.33s), and four final
architecture checks. The full backend suite passes **457 tests in 23.61s**. Nine new
cases cover scenario operation locking, canceled-response parsing, polling scope and
retry behavior, catalog summary/pagination recovery, missing margin forecast centers,
and stable modal focus through content/callback updates. Requests use explicit fixtures;
no real price writes or model generations are performed by these UI tests. A fresh
bounded browser inventory still reports the access host unavailable, so the visual
acceptance limits below remain unchanged.

The November 12 verification record follows for comparison.

Run `npm --prefix web test` and `npm --prefix web run build` with the supported Node
runtime. The final DOM run passes **54/54 cases in 25.700s**, and the strict
TypeScript/Vite production build passes. The original 29 interaction
cases are retained; nine dashboard cases cover
commands, navigation, catalog controls, interval honesty, dashboard tabs, and the
workflow explorer. Six further workflow-page cases cover native radio keyboard
selection/non-submission, retained history, review selection warnings, unique-SKU
scenario summaries, editable question starters, and audit metadata/filter reset.
Six further focus cases cover native Tab stops and actual Drawer wrapping; four
usability cases cover settings draft invalidation, pending-request immutability,
service retry, and IME command behavior. The final build reports Vite 3.60s.
Existing request, constraint, saved-scenario and decision assertions are retained.
Tests use explicit network fixtures and make no real price writes. The jsdom harness
supplies the missing CSS.escape identifier-serialization API needed by user-event's
native radio traversal; browser behavior is not replaced by a custom keyboard handler.
The boundary suite verifies ownership, the model wrapper, and the 400-line limit.
Solid text/surface theme-token checks meet a 4.5:1 contrast ratio in both themes;
the lowest checked pair is light muted text on the blue-tinted surface at 4.55:1.
This calculation does not verify painted gradients, clipping, or complete accessibility.

The local dev server returns HTTP 200 and serves the new command component; platform
and Commerce health both return `ok`. These are service checks, not rendered visual QA.

An earlier inventory was prevented by automatic approval review after the tool usage
limit was reached. A later permitted inventory on November 12 around 20:17 Asia/Kolkata
returned **"The browser access host is unavailable"**, no browser surfaces, and no
workbench screenshot or accessibility tree. Its completion summary was recorded; no
alternate browser-control path was used. Actual screenshots, 1280px layout/keyboard
verification, painted contrast, and browser interaction latency remain outstanding
under T26/T32/T33. Existing live-model and effectiveness gates remain unchanged.
This redesign does not mark those tasks complete.

## Manual preview

1. Open Overview at 1280px and check both themes, the header, and workflow explorer.
2. Use Ctrl/Cmd+K, arrows and Enter to navigate; check Escape and returned focus.
3. In Catalog, switch views, filter, sort the current page, and inspect a product.
4. In Pricing runs, choose Quantitative preview, create a read-only analysis, and
   inspect its progress, candidates, and forecast bounds. Filter its retained history.
5. In Scenario lab, choose a product and stress preset, simulate, and inspect the
   comparison and interval controls. Verify unique-SKU counting and duplicate rejection.
6. Open Settings and check Tab/Shift+Tab/Escape. Unsaved edits should be labeled as
   drafts; only apply configuration values intended for the running session.
7. Expand audit timeline entries, search, and reset filters. Populated review and
   model-generated discovery checks still require a working gateway and real evidence.
