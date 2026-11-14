import assert from 'node:assert/strict';
import { afterEach, test } from 'node:test';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { ScenarioPage } from '../src/features/ScenarioPage';
import { RunsPage } from '../src/features/RunsPage';
import { deferred, forecast, installApi, recommendation, reply, resetUi } from './fixtures.mjs';

afterEach(resetUi);

test('scenario controls submit stress/horizon and show pending state, bands, risk and comparisons', async () => {
  const api = installApi(); const pending = deferred(); const user = userEvent.setup();
  api.on('POST', '/api/scenarios/batch', async ({ body }) => { await pending.promise; return reply({ items: [recommendation('BEV-1')], configuration: body }); });
  render(<ScenarioPage />);
  await screen.findByRole('option', { name: 'Tea pack · BEV-1' });
  await user.selectOptions(screen.getByLabelText('Product'), 'BEV-1');
  assert.equal(screen.getByLabelText('Candidate price').value, '10.00');
  await user.clear(screen.getByLabelText('Candidate price')); await user.type(screen.getByLabelText('Candidate price'), '10.50');
  await user.clear(screen.getByLabelText('Horizon (days)')); await user.type(screen.getByLabelText('Horizon (days)'), '7');
  await user.click(screen.getByRole('radio', { name: 'Cost spike' }));
  await user.click(screen.getByRole('checkbox', { name: 'Add grounded interpretation' }));
  await user.click(screen.getByRole('button', { name: 'Simulate scenario' }));
  await screen.findByText('Sampling possible outcomes with shared assumptions…');
  assert.equal(screen.getByRole('button', { name: 'Simulating…' }).disabled, true);
  assert.equal(screen.queryByRole('button', { name: /Approve|Submit decision/ }), null);
  const request = api.sent('/api/scenarios/batch')[0].body;
  assert.equal(request.horizon_days, 7); assert.equal(request.stress, 'cost_spike'); assert.equal(request.narrate, true);
  assert.equal(request.items[0].sku, 'BEV-1'); assert.equal(typeof request.items[0].candidate_price, 'string');
  assert.equal(Number(request.items[0].candidate_price), 10.5);
  pending.resolve();
  assert.match((await screen.findByRole('img', { name: /Revenue: median.*95 percent interval/ })).getAttribute('aria-label'), /90.*130/);
  assert.ok(screen.getByText('3%')); assert.ok(screen.getByRole('columnheader', { name: 'AI recommendation' }));
  assert.ok(screen.getByRole('columnheader', { name: 'Baseline' }));
  assert.ok(screen.getByText('Synthetic fixture; fixed stock cap'));
});

test('multi-SKU setup rejects duplicate selection and supports removing a row', async () => {
  const api = installApi(); const user = userEvent.setup(); render(<ScenarioPage />);
  await screen.findByRole('option', { name: 'Tea pack · BEV-1' });
  await user.selectOptions(screen.getByLabelText('Product'), 'BEV-1');
  await user.click(screen.getByRole('button', { name: 'Add another SKU' }));
  await user.selectOptions(screen.getByLabelText('Product 2'), 'BEV-1');
  assert.equal(screen.getByRole('button', { name: 'Simulate scenario' }).disabled, true);
  assert.ok(screen.getByRole('alert', { name: '' }).textContent.includes('Choose each SKU once.'));
  await user.selectOptions(screen.getByLabelText('Product 2'), 'SNACK-1');
  await user.click(screen.getByRole('button', { name: 'Simulate scenario' }));
  await screen.findByRole('button', { name: 'Reevaluate & save' });
  assert.equal(api.sent('/api/scenarios/batch')[0].body.items.length, 2);
  await user.click(screen.getByRole('button', { name: 'Remove product 2' }));
  assert.ok(screen.getByLabelText('Product')); assert.equal(screen.queryByLabelText('Product 2'), null);
});

test('failed scenario shows the server error instead of fabricated distributions and permits retry', async () => {
  const api = installApi(); api.on('POST', '/api/scenarios/batch', () => reply({ detail: 'Insufficient eligible price history.' }, 422));
  const user = userEvent.setup(); render(<ScenarioPage />);
  await screen.findByRole('option', { name: 'Tea pack · BEV-1' });
  await user.selectOptions(screen.getByLabelText('Product'), 'BEV-1');
  await user.click(screen.getByRole('button', { name: 'Simulate scenario' }));
  assert.match((await screen.findByRole('alert')).textContent, /Insufficient eligible/);
  assert.equal(screen.queryByRole('img', { name: /Revenue/ }), null);
  assert.equal(screen.getByRole('button', { name: 'Simulate scenario' }).disabled, false);
  api.on('POST', '/api/scenarios/batch', () => reply({ items: [recommendation('retry')] }));
  await user.click(screen.getByRole('button', { name: 'Simulate scenario' }));
  await screen.findByRole('img', { name: /Revenue/ });
  assert.equal(screen.queryByRole('alert'), null);
});

test('catalog failure leaves an explicit error and cannot start a scenario with fabricated inputs', async () => {
  const api = installApi(); api.on('GET', '/api/catalog', () => reply({ detail: 'Commerce unavailable.' }, 503));
  render(<ScenarioPage />);
  assert.match((await screen.findByRole('alert')).textContent, /Commerce unavailable/);
  assert.equal(screen.getByRole('button', { name: 'Simulate scenario' }).disabled, true);
  assert.equal(screen.queryByRole('img', { name: /Revenue/ }), null);
  assert.equal(api.sent('/api/scenarios/batch').length, 0);
});

test('saving reevaluates the retained request and loading restores saved inputs/results without approval', async () => {
  const api = installApi(); const user = userEvent.setup(); render(<ScenarioPage />);
  await screen.findByRole('option', { name: 'Tea pack · BEV-1' });
  await user.selectOptions(screen.getByLabelText('Product'), 'BEV-1');
  await user.click(screen.getByRole('radio', { name: 'Demand collapse' }));
  await user.click(screen.getByRole('button', { name: 'Simulate scenario' }));
  const save = await screen.findByRole('button', { name: 'Reevaluate & save' }); assert.equal(save.disabled, true);
  await user.type(screen.getByLabelText('Scenario name'), 'Stock review');
  await user.click(save); await screen.findByText(/Scenario reevaluated against current Commerce data/);
  assert.deepEqual(api.sent('/api/scenarios/saved')[0].body.request, api.sent('/api/scenarios/batch')[0].body);
  assert.ok(screen.getByText('$11.00'));
  const saved = await screen.findByRole('button', { name: /Stock review/ });
  await user.click(screen.getByRole('radio', { name: 'Normal assumptions' }));
  await user.click(saved);
  assert.equal(screen.getByRole('radio', { name: 'Demand collapse' }).checked, true);
  assert.equal(api.calls.some(call => /recommendations.*decision|prices/.test(call.path)), false);
});

test('pending scenario operations prevent loading or editing another request until the response settles', async () => {
  const request = { items: [{ sku: 'SNACK-1', candidate_price: '12.00' }], horizon_days: 7, iterations: 1000, seed: 42, stress: 'cost_spike', narrate: false };
  const saved = { id: 'saved-other', name: 'Other scenario', created_at: '2026-11-10T00:00:00Z', request,
    result: { items: [recommendation('other-result', { sku: 'SNACK-1', proposed_price: '12.00' })] } };
  const api = installApi({ saved: [saved] }); const simulation = deferred(); const saving = deferred();
  api.on('POST', '/api/scenarios/batch', async ({ body }) => { await simulation.promise; return reply({ items: [recommendation('BEV-1')], configuration: body }); });
  api.on('POST', '/api/scenarios/saved', async ({ body }) => { await saving.promise; return reply({ ...saved, name: body.name, request: body.request }); });
  const user = userEvent.setup(); render(<ScenarioPage />);
  await screen.findByRole('option', { name: 'Tea pack · BEV-1' });
  await user.selectOptions(screen.getByLabelText('Product'), 'BEV-1');
  await user.click(screen.getByRole('button', { name: 'Simulate scenario' }));
  const other = screen.getByRole('button', { name: /Other scenario/ });
  assert.equal(other.disabled, true);
  assert.equal(screen.getByLabelText('Product').disabled, true);
  assert.equal(screen.getByLabelText('Candidate price').disabled, true);
  assert.equal(screen.getByLabelText('Horizon (days)').disabled, true);
  assert.equal(screen.getByRole('button', { name: 'Add another SKU' }).disabled, true);
  assert.equal(screen.getByRole('checkbox', { name: 'Add grounded interpretation' }).disabled, true);
  await user.click(other);
  assert.equal(screen.getByLabelText('Product').value, 'BEV-1');
  simulation.resolve();
  await screen.findByRole('button', { name: 'Reevaluate & save' });
  await user.type(screen.getByLabelText('Scenario name'), 'Current scenario');
  await user.click(screen.getByRole('button', { name: 'Reevaluate & save' }));
  assert.equal(screen.getByRole('button', { name: 'Simulate scenario' }).disabled, true);
  assert.equal(other.disabled, true);
  assert.equal(screen.getByLabelText('Scenario name').disabled, true);
  assert.equal(screen.getByRole('radio', { name: 'Cost spike' }).matches(':disabled'), true);
  await user.click(other);
  await user.click(screen.getByRole('button', { name: 'Simulate scenario' }));
  assert.equal(api.sent('/api/scenarios/batch').length, 1);
  assert.deepEqual(api.sent('/api/scenarios/saved')[0].body.request, api.sent('/api/scenarios/batch')[0].body);
  saving.resolve();
  await screen.findByText(/Scenario reevaluated against current Commerce data/);
  assert.equal(screen.getByLabelText('Product').disabled, false);
  assert.equal(other.disabled, false);
  await user.click(other);
  assert.equal(screen.getByLabelText('Product').value, 'SNACK-1');
  assert.equal(screen.getByRole('radio', { name: 'Cost spike' }).checked, true);
});

test('missing intervals and unavailable optional narration have explicit DOM states in either theme', async () => {
  const api = installApi(); api.on('POST', '/api/scenarios/batch', () => reply({ items: [recommendation('sparse', { forecast: { ...forecast, revenue: { mean: 100 } } })], narrative_status: 'gateway_unavailable' }));
  const user = userEvent.setup(); document.documentElement.dataset.theme = 'dark'; render(<ScenarioPage />);
  await screen.findByRole('option', { name: 'Tea pack · BEV-1' });
  await user.selectOptions(screen.getByLabelText('Product'), 'BEV-1');
  await user.click(screen.getByRole('button', { name: 'Simulate scenario' }));
  await screen.findByText(/Grounded interpretation unavailable: gateway unavailable/);
  assert.ok(screen.getByText('Interval unavailable'));
  assert.equal(screen.queryByRole('img', { name: /Revenue/ }), null);
  document.documentElement.dataset.theme = 'light';
  assert.ok(screen.getByText('Interval unavailable')); assert.ok(screen.getByText('3%'));
});

test('run form sends advanced scope constraints and shows validation errors before network submission', async () => {
  const api = installApi(); const user = userEvent.setup(); render(<MemoryRouter><RunsPage /></MemoryRouter>);
  await screen.findByRole('option', { name: 'Beverages' });
  await user.selectOptions(screen.getByLabelText('Scope'), 'Beverages');
  await user.click(screen.getByRole('radio', { name: 'Grounded pricing workflow' }));
  await user.click(screen.getByText(/Advanced price constraints/));
  await user.type(screen.getByLabelText('Maximum price change (%)'), '5');
  await user.type(screen.getByLabelText('Price floor'), '12');
  await user.type(screen.getByLabelText('Price ceiling'), '11');
  await user.click(screen.getByRole('button', { name: 'Start run' }));
  assert.match((await screen.findByRole('alert')).textContent, /floor cannot exceed/);
  assert.equal(api.sent('/api/runs').length, 0);
  await user.clear(screen.getByLabelText('Price ceiling')); await user.type(screen.getByLabelText('Price ceiling'), '13');
  await user.click(screen.getByRole('button', { name: 'Start run' }));
  await waitFor(() => assert.equal(api.sent('/api/runs').length, 1));
  assert.deepEqual(api.sent('/api/runs')[0].body.constraints, { max_change_pct: 0.05, category_floors: { Beverages: '12.00' }, category_ceilings: { Beverages: '13.00' } });
  assert.equal(api.sent('/api/runs')[0].body.kind, 'grounded');
});
