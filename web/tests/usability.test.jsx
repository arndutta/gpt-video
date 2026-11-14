import assert from 'node:assert/strict';
import { afterEach, test } from 'node:test';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { SettingsDrawer } from '../src/features/SettingsDrawer';
import { App } from '../src/app/App';
import { deferred, installApi, reply, resetUi } from './fixtures.mjs';

afterEach(resetUi);

test('editing any gateway field invalidates old saved/verified feedback until the draft is applied', async () => {
  const api = installApi({ settings: { gateway_url: 'https://gateway.example.test/v1', gateway_port: null, key_configured: true, verify_tls: true, allow_insecure_tls: true, models: {}, cache: { hits: 0, misses: 0 }, mode: 'supervised' } });
  const user = userEvent.setup(); render(<SettingsDrawer onClose={() => {}} onSaved={() => {}} />);
  const verify = await screen.findByRole('button', { name: 'Verify current gateway settings' });
  const edits = [
    async () => user.type(screen.getByLabelText('Port (optional)'), '4000'),
    async () => user.type(screen.getByLabelText('Analyst model alias'), 'new-analyst'),
    async () => user.click(screen.getByRole('switch', { name: 'Disable SSL verification' })),
    async () => user.type(screen.getByLabelText(/API key/), 'synthetic-draft-key'),
  ];
  for (const edit of edits) {
    await user.click(verify); await screen.findByText('Model listing verified');
    await edit();
    assert.equal(screen.queryByText('Model listing verified'), null);
    assert.equal(screen.queryByText('Settings applied for this session.'), null);
    assert.equal(verify.disabled, true);
    assert.ok(screen.getByText(/unapplied gateway changes/));
    await user.click(screen.getByRole('button', { name: 'Apply settings' }));
    await screen.findByText('Settings applied for this session.');
    assert.equal(verify.disabled, false);
    assert.equal(screen.queryByText(/unapplied gateway changes/), null);
  }
  assert.equal(screen.getByLabelText(/API key/).value, '');
  assert.equal(document.body.textContent.includes('synthetic-draft-key'), false);
  assert.equal(localStorage.length, 0);
  assert.equal(api.sent('/api/settings').length, 4);
});

test('pending settings save and verification prevent newer draft edits from being mislabeled as saved', async () => {
  const api = installApi(); const save = deferred(); const check = deferred(); const user = userEvent.setup();
  api.on('PATCH', '/api/settings', async ({ body, state }) => { await save.promise; state.settings = { ...state.settings, gateway_url: body.gateway_url }; return reply(state.settings); });
  api.on('POST', '/api/gateway/check', async () => { await check.promise; return reply({ status: 'verified', verified: true, detail: 'Listed aliases.', structured_output_verified: false }); });
  render(<SettingsDrawer onClose={() => {}} onSaved={() => {}} />);
  const url = await screen.findByLabelText('Gateway URL');
  await user.type(url, 'https://gateway.example.test/v1');
  await user.click(screen.getByRole('button', { name: 'Apply settings' }));
  assert.equal(url.matches(':disabled'), true);
  await user.type(url, '/must-not-edit');
  assert.equal(url.value, 'https://gateway.example.test/v1');
  assert.equal(screen.queryByText('Settings applied for this session.'), null);
  save.resolve(); await screen.findByText('Settings applied for this session.');
  assert.equal(url.matches(':disabled'), false);
  await user.click(screen.getByRole('button', { name: 'Verify current gateway settings' }));
  assert.equal(url.matches(':disabled'), true);
  check.resolve(); await screen.findByText('Model listing verified');
  assert.equal(url.matches(':disabled'), false);
});

test('failed service status is explicit and retry recovers using read-only requests', async () => {
  const api = installApi(); let online = false;
  api.on('GET', '/api/health', () => online ? reply({ status: 'ok', commerce: { status: 'ok' }, mode: 'supervised', capabilities: { quantitative_preview: true }, loop: { running: false } }) : reply({ detail: 'Status probe unavailable.' }, 503));
  const user = userEvent.setup(); render(<MemoryRouter initialEntries={['/review']}><App /></MemoryRouter>);
  await screen.findByText('Status unavailable');
  assert.equal(screen.queryByText('Connecting to services'), null);
  online = true;
  await user.click(screen.getByRole('button', { name: 'Retry service check' }));
  await screen.findByText('Commerce connected');
  assert.equal(screen.queryByRole('button', { name: 'Retry service check' }), null);
  assert.equal(api.calls.some(call => call.method !== 'GET'), false);
});

test('IME composition does not select a destination or close the command dialog', async () => {
  const api = installApi(); const user = userEvent.setup();
  render(<MemoryRouter initialEntries={['/review']}><App /></MemoryRouter>);
  await user.click(screen.getByRole('button', { name: 'Open workspace search' }));
  const input = screen.getByRole('combobox', { name: 'Search workspace' });
  await user.type(input, 'scenario');
  fireEvent.keyDown(input, { key: 'Enter', isComposing: true });
  fireEvent.keyDown(input, { key: 'Escape', isComposing: true });
  assert.ok(screen.getByRole('dialog', { name: 'Find your next move' }));
  assert.equal(screen.queryByRole('heading', { name: 'Scenario lab' }), null);
  fireEvent.keyDown(input, { key: 'k', ctrlKey: true, repeat: true });
  assert.ok(screen.getByRole('dialog'));
  await user.keyboard('{Enter}');
  await screen.findByRole('heading', { name: 'Scenario lab' });
  await waitFor(() => assert.equal(screen.queryByRole('dialog'), null));
  assert.equal(api.calls.some(call => call.method !== 'GET'), false);
});
