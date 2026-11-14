import assert from 'node:assert/strict';
import { afterEach, test } from 'node:test';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { App } from '../src/app/App';
import { CatalogPage } from '../src/features/CatalogPage';
import { Dashboard } from '../src/features/Dashboard';
import { DistributionBand } from '../src/components/Forecast';
import { installApi, products, reply, resetUi } from './fixtures.mjs';

afterEach(resetUi);

test('command search navigates with the keyboard, restores focus, and sends no mutation', async () => {
  const api = installApi(); const user = userEvent.setup();
  render(<MemoryRouter initialEntries={['/review']}><App /></MemoryRouter>);
  await screen.findByRole('heading', { name: 'Review queue' });
  const trigger = screen.getByRole('button', { name: 'Open workspace search' });
  await user.click(trigger);
  const search = screen.getByRole('combobox', { name: 'Search workspace' });
  assert.equal(document.activeElement, search);
  const dialog = screen.getByRole('dialog', { name: 'Find your next move' });
  assert.equal(dialog.parentElement.parentElement, document.body, 'Modal is outside header stacking and layout contexts.');
  await user.type(search, 'scenario');
  assert.equal(within(dialog).getAllByRole('option').length, 1);
  await user.keyboard('{Enter}');
  await screen.findByRole('heading', { name: 'Scenario lab' });
  assert.equal(screen.queryByRole('dialog'), null);
  assert.equal(document.activeElement, trigger);
  assert.equal(api.calls.some(call => call.method !== 'GET'), false);
});

test('Ctrl+K searches settings, handles no matches, and does not interrupt another modal', async () => {
  const api = installApi(); const user = userEvent.setup();
  render(<MemoryRouter initialEntries={['/review']}><App /></MemoryRouter>);
  await screen.findByRole('heading', { name: 'Review queue' });
  await user.keyboard('{Control>}k{/Control}');
  const search = screen.getByRole('combobox', { name: 'Search workspace' });
  await user.type(search, 'no-such-workspace-action');
  await screen.findByText(/No matching pages/);
  await user.keyboard('{Enter}'); assert.ok(screen.getByRole('dialog'));
  await user.clear(search); await user.type(search, 'Workspace settings'); await user.keyboard('{Enter}');
  await screen.findByRole('dialog', { name: 'Workspace settings' });
  await user.keyboard('{Control>}k{/Control}');
  assert.equal(screen.getAllByRole('dialog').length, 1);
  assert.equal(screen.queryByRole('combobox', { name: 'Search workspace' }), null);
  await user.keyboard('{Escape}');
  assert.equal(api.calls.some(call => call.method !== 'GET'), false);
});

test('collapsed navigation retains accessible route links and persistent global controls', async () => {
  installApi(); const user = userEvent.setup();
  render(<MemoryRouter initialEntries={['/review']}><App /></MemoryRouter>);
  await screen.findByRole('heading', { name: 'Review queue' });
  await user.click(screen.getByRole('button', { name: 'Collapse navigation' }));
  assert.equal(screen.getByRole('button', { name: 'Expand navigation' }).getAttribute('aria-expanded'), 'false');
  const header = document.querySelector('header');
  await user.click(screen.getByRole('link', { name: 'Product catalog' }));
  await screen.findByRole('heading', { name: 'Product catalog' });
  assert.equal(document.querySelector('header'), header);
  assert.ok(within(header).getByRole('button', { name: 'Halt' }));
  assert.equal(document.title, 'Product catalog · Retail pricing');
  await user.click(screen.getByRole('button', { name: 'Expand navigation' }));
  assert.equal(screen.getByRole('button', { name: 'Collapse navigation' }).getAttribute('aria-expanded'), 'true');
  assert.deepEqual(Object.keys(localStorage), ['pricing-theme']);
});

test('catalog grid and current-page sorting use supplied products and inspection remains read-only', async () => {
  const api = installApi(); const user = userEvent.setup();
  api.on('GET', '/api/catalog', () => reply({ items: [{ ...products[0], current_price: '20.00' }, { ...products[1], current_price: '5.00' }], total: 2 }));
  render(<MemoryRouter><CatalogPage /></MemoryRouter>);
  await screen.findByRole('button', { name: 'Inspect Tea pack' });
  await user.selectOptions(screen.getByRole('combobox', { name: 'Sort current page' }), 'price-high');
  assert.equal(screen.getAllByRole('button', { name: /Inspect / })[0].getAttribute('aria-label'), 'Inspect Tea pack');
  await user.click(screen.getByRole('button', { name: 'Grid view' }));
  assert.equal(screen.getByRole('button', { name: 'Grid view' }).getAttribute('aria-pressed'), 'true');
  assert.equal(screen.getAllByRole('article').length, 2);
  await user.selectOptions(screen.getByRole('combobox', { name: 'Sort current page' }), 'price-low');
  assert.equal(screen.getAllByRole('article')[0].querySelector('h2').textContent, 'Oat snack');
  const inspect = screen.getByRole('button', { name: 'Inspect Oat snack' });
  await user.click(inspect);
  const dialog = screen.getByRole('dialog', { name: 'Oat snack' });
  assert.match(dialog.textContent, /\$5\.00/); assert.match(dialog.textContent, /Price version 1/);
  assert.equal(within(dialog).queryByRole('button', { name: /Apply|Approve/ }), null);
  await user.keyboard('{Escape}'); assert.equal(document.activeElement, inspect);
  assert.equal(api.calls.some(call => call.method !== 'GET'), false);
});

test('catalog search and category retain server filtering and pagination parameters', async () => {
  const api = installApi(); const user = userEvent.setup(); const requests = [];
  api.on('GET', '/api/catalog', ({ url }) => { requests.push(new URLSearchParams(url.search)); return reply({ items: products, total: 50 }); });
  render(<MemoryRouter><CatalogPage /></MemoryRouter>);
  await screen.findByRole('button', { name: 'Inspect Tea pack' });
  await user.click(screen.getByRole('button', { name: 'Next' }));
  await waitFor(() => assert.equal(requests.at(-1).get('offset'), '25'));
  await user.selectOptions(screen.getByRole('combobox', { name: 'Filter by category' }), 'Beverages');
  await waitFor(() => assert.equal(requests.at(-1).get('category'), 'Beverages'));
  assert.equal(requests.at(-1).get('offset'), '0');
  await user.type(screen.getByRole('textbox', { name: 'Search products' }), 'Tea');
  await waitFor(() => assert.equal(requests.at(-1).get('q'), 'Tea'));
  assert.equal(requests.at(-1).get('limit'), '25');
  await user.click(screen.getByRole('button', { name: 'Clear filters' }));
  await waitFor(() => assert.equal(requests.at(-1).has('category'), false));
  assert.equal(requests.at(-1).has('q'), false);
  assert.equal(api.calls.some(call => call.method !== 'GET'), false);
});

test('interval controls expose exact supplied bounds by keyboard without inventing samples', async () => {
  const user = userEvent.setup();
  render(<DistributionBand label="Revenue" distribution={{ lower: 80, median: 105, upper: 140 }} />);
  assert.match(screen.getByRole('img').getAttribute('aria-label'), /median \$105\.00, 95 percent interval \$80\.00 to \$140\.00/);
  const lower = screen.getByRole('button', { name: 'Revenue lower bound' });
  await user.tab(); assert.equal(document.activeElement, lower); await user.keyboard('{Enter}');
  assert.equal(lower.getAttribute('aria-pressed'), 'true');
  assert.ok(screen.getByText('Lower bound: $80.00'));
  await user.click(screen.getByRole('button', { name: 'Revenue upper bound' }));
  assert.ok(screen.getByText('Upper bound: $140.00'));
  assert.ok(screen.getByText('95% simulation interval'));
});

test('reversed intervals stay unavailable and a supplied mean is labeled as a mean', () => {
  const first = render(<DistributionBand label="Revenue" distribution={{ lower: 140, median: 105, upper: 80 }} />);
  assert.ok(screen.getByText('Interval unavailable')); assert.equal(screen.queryByRole('img'), null);
  first.unmount();
  const mean = render(<DistributionBand label="Units" distribution={{ lower: 8, mean: 10, upper: 12 }} format={value => String(value)} />);
  assert.match(screen.getByRole('img').getAttribute('aria-label'), /mean 10/);
  assert.ok(screen.getByRole('button', { name: 'Units mean' }));
  mean.unmount();
  render(<DistributionBand label="Units" distribution={{ lower: 8, mean: 20, upper: 12 }} format={value => String(value)} />);
  assert.match(screen.getByRole('img').getAttribute('aria-label'), /mean 20, 95 percent interval 8 to 12/);
  assert.equal(screen.queryByText('Interval unavailable'), null, 'A skewed mean may legitimately be outside a central interval.');
});

test('dashboard insight tabs work by keyboard and preserve the observed outcome denominator', async () => {
  const api = installApi(); const user = userEvent.setup();
  api.on('GET', '/api/dashboard', () => reply({ recommendations: 10, decisions: { total: 4, approved: 3, automatic: 2 }, forecast: {}, realized: { status: 'pending', revenue: null, observed_skus: 2, pending_skus: 8 }, bands: { auto_approve: 2, review: 5, escalate: 3 }, stability: { error_trend: 'widening' } }));
  render(<Dashboard />);
  await screen.findByText('3 approved / 4 recorded decisions');
  assert.ok(screen.getByText('Observed: 2 SKUs · Pending: 8 SKUs. Missing sales are never treated as zero.'));
  assert.equal(screen.queryByRole('heading', { name: 'Stability and learning' }), null);
  const forecast = screen.getByRole('tab', { name: 'Forecast & outcomes' });
  forecast.focus(); await user.keyboard('{ArrowRight}');
  assert.equal(screen.getByRole('tab', { name: 'Decisions & stability' }).getAttribute('aria-selected'), 'true');
  assert.ok(screen.getByRole('heading', { name: 'Stability and learning' }));
  assert.ok(screen.getByText(/Forecast error is widening/));
  assert.match(screen.getByRole('img').getAttribute('aria-label'), /2 Auto-approve, 5 Review, 3 Escalate/);
  await user.keyboard('{Home}');
  assert.equal(forecast.getAttribute('aria-selected'), 'true');
  assert.equal(api.calls.some(call => call.method !== 'GET'), false);
});

test('overview workflow explorer describes stages without starting a pricing run', async () => {
  const api = installApi(); const user = userEvent.setup();
  render(<MemoryRouter><App /></MemoryRouter>);
  await screen.findByRole('heading', { name: 'Pricing overview' });
  await user.click(screen.getByRole('button', { name: 'Explore Execute stage' }));
  assert.ok(screen.getByRole('heading', { name: 'Keep execution accountable.' }));
  assert.equal(screen.getByRole('button', { name: 'Explore Execute stage' }).getAttribute('aria-pressed'), 'true');
  assert.ok(screen.getByText('Configure the gateway and index required evidence'));
  assert.equal(api.calls.some(call => call.method !== 'GET'), false);
});
