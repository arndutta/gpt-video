import { cleanup } from '@testing-library/react';

export const forecast = { revenue: { mean: 110, median: 108, lower: 90, upper: 130, variance: 9 },
  gross_profit: { mean: 40, median: 39, lower: 30, upper: 50 },
  units: { mean: 11, median: 11, lower: 9, upper: 13 },
  margin_rate: { mean: 0.35, median: 0.35, lower: 0.3, upper: 0.4 },
  below_margin_floor_probability: 0.03 };

export function recommendation(id = 'review-1', patch = {}) {
  return { id, run_id: 'run-fixture', revision: 2, sku: id.toUpperCase(), name: `Product ${id}`,
    category: 'Beverages', currency: 'USD', family_id: 'family-1', current_price: '10.00',
    proposed_price: '10.50', delta_pct: 5, confidence: 0.9, band: 'review', band_reasons: [],
    compliance: { status: 'passed', rules: [{ rule: 'margin_floor', passed: true, actual: 0.35, threshold: 0.2 }] },
    compliance_status: 'passed', stability: {}, status: 'pending_review', mode_at_decision: 'supervised',
    mode_version: 1, executable: false, forecast, current_forecast: forecast,
    baseline: { price: '10.20', forecast }, ai_forecast: forecast,
    rationale: 'Synthetic fixture reasoning.', citations: ['rag:fixture:policy:0'],
    product_evidence: { size: 1 }, assumptions: ['Synthetic fixture; fixed stock cap'], ...patch };
}

export const products = ['BEV-1', 'SNACK-1'].map((sku, index) => ({ sku, name: index ? 'Oat snack' : 'Tea pack',
  category: index ? 'Snacks' : 'Beverages', family_id: `f-${index}`, size: 1, currency: 'USD',
  cost: '6.00', current_price: '10.00', map_price: '8.00', min_price: '8.00', max_price: '15.00', price_version: 1 }));

export const initialPolicy = { confidence_threshold: 0.8, bulk_confidence_threshold: 0.8, auto_delta_pct: 5,
  volatility_limit: 0.35, margin_proximity_buffer: 0.03, minimum_sample: 60, oscillation_window: 8,
  reversals_threshold: 2, damping_fraction: 0.35, anomaly_z_threshold: 4, market_gap_limit_pct: 30,
  minimum_change_seconds: 0, hold_seconds: 60 };

export function reply(data, status = 200) {
  return new Response(JSON.stringify(data), { status, headers: { 'Content-Type': 'application/json' } });
}

export function deferred() {
  let resolve, reject;
  const promise = new Promise((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
}

export function installApi(patch = {}) {
  const state = { items: [], mode: 'supervised', runs: [], saved: [],
    loop: { running: false, status: 'off', iteration_count: 0, iterations: [], interval_seconds: 60 },
    settings: { gateway_url: '', gateway_port: null, key_configured: false, verify_tls: true,
      allow_insecure_tls: false, models: { router: '', narrator: '', analyst: '', strategist: '' },
      cache: { hits: 0, misses: 0, available: true }, mode: 'supervised' }, ...patch };
  const calls = [], routes = new Map();
  globalThis.fetch = async (input, init = {}) => {
    const url = new URL(String(input), 'http://127.0.0.1:5173');
    const path = url.pathname, method = init.method || 'GET';
    const body = typeof init.body === 'string' ? JSON.parse(init.body) : init.body;
    calls.push({ path, method, body });
    const custom = routes.get(`${method} ${path}`);
    if (custom) return custom({ body, init, state, calls, url });
    if (method === 'GET' && path === '/api/control') return reply({ mode: state.mode, version: 1, generation: 1, hold_seconds: 60, loop: state.loop });
    if (path === '/api/monitor') return reply({ active_calls: 0, input_tokens: 120, output_tokens: 30, estimated_cost_usd: 0.001, cache: { hits: 2, misses: 1, available: true } });
    if (path === '/api/health') return reply({ status: 'ok', mode: state.mode, commerce: { status: 'ok' }, gateway: { configured: false }, capabilities: { quantitative_preview: true, grounded_recommendations: false }, loop: state.loop });
    if (method === 'GET' && path === '/api/recommendations') return reply({ items: state.items });
    if (method === 'GET' && path === '/api/policy') return reply({ version: 1, thresholds: initialPolicy });
    if (method === 'PATCH' && path === '/api/policy') return reply({ version: 2, thresholds: { ...initialPolicy, ...body } });
    if (path === '/api/catalog/summary') return reply({ sku_count: 2, categories: [{ name: 'Beverages', sku_count: 1 }, { name: 'Snacks', sku_count: 1 }], inventory_units: 200 });
    if (path === '/api/catalog') return reply({ items: products, total: products.length });
    if (method === 'GET' && path === '/api/runs') return reply({ items: state.runs });
    if (method === 'POST' && path === '/api/runs') {
      const run = { id: 'run-created', status: 'completed', stage: 'completed', created_at: '2026-11-10T00:00:00Z', request: body, result: { type: 'quantitative_preview', recommendations: [] } };
      state.runs.push(run); return reply(run, 202);
    }
    if (method === 'GET' && path.startsWith('/api/runs/')) return reply(state.runs.find(run => path.endsWith(run.id)) || {}, 200);
    if (path === '/api/dashboard') return reply({ recommendations: 0, decisions: { total: 0 }, forecast: {}, realized: { status: 'pending', revenue: null }, bands: {}, stability: {}, mode_history: [] });
    if (method === 'GET' && path === '/api/settings') return reply(state.settings);
    if (method === 'PATCH' && path === '/api/settings') {
      const { api_key, ...safe } = body; state.settings = { ...state.settings, ...safe, key_configured: !!api_key || state.settings.key_configured }; return reply(state.settings);
    }
    if (method === 'POST' && path === '/api/gateway/check') return reply({ status: 'verified', verified: true, checked_at: '2026-11-10T00:00:00Z', detail: 'Configured aliases are available.', structured_output_verified: false });
    if (path === '/api/grounding/uploads') return reply({ items: [] });
    if (path === '/api/grounding/collections') return reply({ items: [], corpus_version: 0, status: 'unavailable', embedding: { available: false, provider: 'local', detail: 'Synthetic fixture not indexed' } });
    if (path.startsWith('/api/grounding/citations/')) return reply({ citation_id: 'rag:fixture:policy:0', title: 'Synthetic policy', source_id: 'policy', version: 'v1', text: 'Synthetic policy requires compliance.' });
    if (method === 'PATCH' && path === '/api/control/mode') { state.mode = body.mode; return reply({ mode: state.mode }); }
    if (method === 'POST' && path === '/api/control/kill') { state.mode = 'supervised'; state.loop = { ...state.loop, running: false, status: 'stopped' }; return reply({ mode: state.mode, loop: state.loop }); }
    if (method === 'POST' && path === '/api/loop') { state.loop = { ...state.loop, running: true, status: 'running', request: body.request, interval_seconds: body.interval_seconds, max_iterations: body.max_iterations }; return reply(state.loop, 202); }
    if (method === 'POST' && path === '/api/loop/stop') { state.loop = { ...state.loop, running: false, status: 'stopped' }; return reply(state.loop); }
    if (method === 'GET' && path === '/api/scenarios/saved') return reply({ items: state.saved });
    if (method === 'POST' && path === '/api/scenarios/batch') return reply({ items: body.items.map(item => recommendation(item.sku, { sku: item.sku, proposed_price: item.candidate_price })), configuration: body });
    if (method === 'POST' && path === '/api/scenarios/saved') { const saved = { id: 'saved-1', name: body.name, request: body.request, created_at: '2026-11-10T00:00:00Z', result: { items: [recommendation('saved-result', { proposed_price: '11.00' })] } }; state.saved.push(saved); return reply(saved, 201); }
    if (method === 'POST' && path === '/api/recommendations/bulk') {
      state.items = state.items.map(item => body.ids.includes(item.id) ? { ...item, status: 'approved' } : item); return reply({ items: state.items });
    }
    if (method === 'POST' && /\/api\/recommendations\/[^/]+\/(decision|revert)$/.test(path)) return reply({ status: 'approved' });
    return reply({ detail: `No fixture response for ${method} ${path}` }, 500);
  };
  return { state, calls, on: (method, path, handler) => routes.set(`${method} ${path}`, handler),
    sent: path => calls.filter(call => call.path === path && call.method !== 'GET') };
}

export function resetUi() {
  cleanup(); localStorage.clear(); document.documentElement.removeAttribute('data-theme');
}
