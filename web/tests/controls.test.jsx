import assert from 'node:assert/strict';
import { afterEach, test } from 'node:test';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { GlobalControls } from '../src/features/GlobalControls';
import { LoopDrawer } from '../src/features/LoopDrawer';
import { App } from '../src/app/App';
import { deferred, installApi, reply, resetUi } from './fixtures.mjs';

afterEach(resetUi);

test('mode changes remain pending until server acknowledgment and rejected changes show no success', async () => {
  const api = installApi(); const pending = deferred(); const user = userEvent.setup();
  api.on('PATCH', '/api/control/mode', async ({ body, state }) => { await pending.promise; state.mode = body.mode; return reply({ mode: state.mode }); });
  render(<MemoryRouter><GlobalControls /></MemoryRouter>);
  const mode = screen.getByRole('combobox', { name: 'Operating mode' });
  await waitFor(() => assert.equal(mode.disabled, false));
  await user.selectOptions(mode, 'assisted'); assert.equal(mode.value, 'supervised'); assert.equal(mode.disabled, true);
  assert.equal(screen.queryByText(/Mode changed/), null);
  pending.resolve(); await screen.findByText('Mode changed to assisted.');
  await waitFor(() => assert.equal(mode.value, 'assisted'));
  api.on('PATCH', '/api/control/mode', () => reply({ detail: 'Mode update unavailable.' }, 503));
  await user.selectOptions(mode, 'autonomous');
  assert.match((await screen.findByRole('alert')).textContent, /Mode update unavailable/);
  assert.equal(mode.value, 'assisted'); assert.equal(screen.queryByText(/Mode changed to autonomous/), null);
});

test('halt has exactly one confirmation, supports cancel, and acknowledges Supervised only after the server', async () => {
  const api = installApi({ mode: 'autonomous', loop: { running: true, status: 'waiting', iteration_count: 1, iterations: [] } });
  const pending = deferred(); const user = userEvent.setup();
  api.on('POST', '/api/control/kill', async ({ state }) => { await pending.promise; state.mode = 'supervised'; state.loop.running = false; return reply({ mode: state.mode }); });
  render(<MemoryRouter><GlobalControls /></MemoryRouter>);
  await waitFor(() => assert.equal(screen.getByRole('button', { name: 'Halt' }).disabled, false));
  await user.click(screen.getByRole('button', { name: 'Halt' }));
  assert.equal(screen.getAllByRole('dialog').length, 1); assert.equal(api.sent('/api/control/kill').length, 0);
  await user.click(screen.getByRole('button', { name: 'Keep current activity' }));
  assert.equal(api.sent('/api/control/kill').length, 0);
  await user.click(screen.getByRole('button', { name: 'Halt' }));
  await user.click(screen.getByRole('button', { name: 'Confirm halt' }));
  assert.equal(api.sent('/api/control/kill').length, 1);
  assert.equal(screen.getByRole('button', { name: 'Halting…' }).disabled, true);
  assert.equal(screen.getByRole('combobox', { name: 'Operating mode' }).value, 'autonomous');
  assert.equal(screen.queryByText(/Halt acknowledged/), null);
  pending.resolve(); await screen.findByText(/Halt acknowledged/);
  assert.equal(screen.queryByRole('dialog'), null);
  await waitFor(() => assert.equal(screen.getByRole('combobox', { name: 'Operating mode' }).value, 'supervised'));
  await screen.findByRole('button', { name: 'Loop off' });
  assert.equal(api.sent('/api/control/kill').length, 1);
});

test('disconnected controls disable price authority and do not claim loop start success', async () => {
  const api = installApi(); api.on('GET', '/api/control', () => reply({ detail: 'Service offline.' }, 503));
  const user = userEvent.setup(); render(<MemoryRouter><GlobalControls /></MemoryRouter>);
  await screen.findByText('Controls disconnected');
  assert.equal(screen.getByRole('button', { name: 'Halt' }).disabled, true);
  assert.equal(screen.getByRole('combobox', { name: 'Operating mode' }).disabled, true);
  await user.click(screen.getByRole('button', { name: 'Loop unavailable' }));
  assert.equal(screen.getByRole('button', { name: 'Start loop' }).disabled, true);
  assert.match(screen.getByRole('alert').textContent, /disconnected/);
  assert.equal(api.calls.some(call => call.method === 'POST'), false);
});

test('loop setup submits scope and constraints, updates actual counts, and stops after acknowledgment', async () => {
  const api = installApi(); const user = userEvent.setup();
  api.on('POST', '/api/loop', ({ body, state }) => { state.loop = { running: true, status: 'waiting', request: body.request, iteration_count: 1, iterations: [{ iteration: 1, run_id: 'loop-run', status: 'awaiting_review', decisions: { total: 7, auto_approved: 2, queued: 3, applied: 1, unchanged: 2, unknown: 1, blocked: 0 } }] }; return reply(state.loop, 202); });
  render(<MemoryRouter><GlobalControls /></MemoryRouter>);
  await screen.findByRole('button', { name: 'Loop off' });
  await user.click(screen.getByRole('button', { name: 'Loop off' }));
  await screen.findByRole('option', { name: 'Beverages' });
  await user.selectOptions(screen.getByLabelText('Scope'), 'Beverages');
  await user.type(screen.getByLabelText(/Maximum iterations/), '2');
  await user.click(screen.getByText(/Advanced price constraints/));
  await user.type(screen.getByLabelText('Maximum price change (%)'), '4');
  await user.type(screen.getByLabelText('Price floor'), '8.50');
  await user.click(screen.getByRole('button', { name: 'Start loop' }));
  await screen.findByText(/Loop start acknowledged/);
  const request = api.sent('/api/loop')[0].body;
  assert.equal(request.request.kind, 'grounded'); assert.equal(request.request.category, 'Beverages'); assert.equal(request.max_iterations, 2);
  assert.deepEqual(request.request.constraints, { max_change_pct: 0.04, category_floors: { Beverages: '8.50' } });
  await screen.findByRole('link', { name: '#1 · loop-run' });
  assert.equal(screen.getByRole('columnheader', { name: 'No change' }).textContent, 'No change');
  assert.match(screen.getByRole('row', { name: /loop-run/ }).textContent, /7 recommendations/);
  await user.click(screen.getByRole('button', { name: 'Stop scheduling' }));
  await screen.findByText(/Loop stop acknowledged/);
  await waitFor(() => assert.equal(screen.getByRole('button', { name: 'Start loop' }).disabled, false));
  assert.equal(api.sent('/api/loop/stop').length, 1);
});

test('failed loop start shows an actionable error and leaves scheduling off', async () => {
  const api = installApi(); api.on('POST', '/api/loop', () => reply({ detail: 'Configure all gateway aliases.' }, 409));
  const user = userEvent.setup();
  render(<MemoryRouter><LoopDrawer state={api.state.loop} connected onClose={() => {}} onChanged={() => {}} /></MemoryRouter>);
  await user.click(screen.getByRole('button', { name: 'Start loop' }));
  assert.match((await screen.findByRole('alert')).textContent, /gateway aliases/);
  assert.equal(screen.getByText('Scheduling is off').textContent, 'Scheduling is off');
  assert.equal(screen.queryByText(/Loop start acknowledged/), null);
});

test('failed halt preserves current mode and confirmation without a false acknowledgment', async () => {
  const api = installApi({ mode: 'autonomous' }); const user = userEvent.setup();
  api.on('POST', '/api/control/kill', () => reply({ detail: 'Halt could not be acknowledged.' }, 503));
  render(<MemoryRouter><GlobalControls /></MemoryRouter>);
  await waitFor(() => assert.equal(screen.getByRole('button', { name: 'Halt' }).disabled, false));
  await user.click(screen.getByRole('button', { name: 'Halt' }));
  await user.click(screen.getByRole('button', { name: 'Confirm halt' }));
  assert.match((await screen.findByRole('alert')).textContent, /could not be acknowledged/);
  assert.equal(screen.getByRole('combobox', { name: 'Operating mode' }).value, 'autonomous');
  assert.equal(screen.getAllByRole('dialog').length, 1); assert.equal(screen.queryByText(/Halt acknowledged\./), null);
  assert.equal(api.sent('/api/control/kill').length, 1);
});

test('global controls survive routes and theme preference persists after remount', async () => {
  installApi(); const user = userEvent.setup();
  const first = render(<MemoryRouter initialEntries={['/review']}><App /></MemoryRouter>);
  await screen.findByRole('heading', { name: 'Review queue' });
  const header = document.querySelector('header');
  assert.ok(within(header).getByRole('button', { name: 'Halt' }));
  await user.click(screen.getByRole('button', { name: 'Switch to dark theme' }));
  assert.equal(document.documentElement.dataset.theme, 'dark'); assert.equal(localStorage.getItem('pricing-theme'), 'dark');
  await user.click(screen.getByRole('link', { name: 'Scenario lab' }));
  await screen.findByRole('heading', { name: 'Scenario lab' });
  assert.equal(document.querySelector('header'), header); assert.equal(document.documentElement.dataset.theme, 'dark');
  first.unmount(); render(<MemoryRouter><App /></MemoryRouter>);
  assert.ok(screen.getByRole('button', { name: 'Switch to light theme' }));
  await user.click(screen.getByRole('button', { name: 'Switch to light theme' }));
  assert.equal(document.documentElement.dataset.theme, 'light'); assert.equal(localStorage.getItem('pricing-theme'), 'light');
  assert.deepEqual(Object.keys(localStorage), ['pricing-theme']);
});
