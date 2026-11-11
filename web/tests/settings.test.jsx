import assert from 'node:assert/strict';
import { afterEach, test } from 'node:test';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { SettingsDrawer } from '../src/features/SettingsDrawer';
import { deferred, installApi, reply, resetUi } from './fixtures.mjs';

afterEach(resetUi);

test('settings clear the transient key and apply all four aliases without persisting credentials', async () => {
  const api = installApi(); const user = userEvent.setup(); let saved = 0;
  render(<SettingsDrawer onClose={() => {}} onSaved={() => saved++} />);
  await screen.findByLabelText('Gateway URL');
  await user.type(screen.getByLabelText('Gateway URL'), 'https://gateway.example.test/v1');
  await user.type(screen.getByLabelText(/API key/), 'synthetic-ui-memory-key');
  for (const role of ['Router', 'Narrator', 'Analyst', 'Strategist']) await user.type(screen.getByLabelText(`${role} model alias`), `fixture-${role.toLowerCase()}`);
  await user.click(screen.getByRole('button', { name: 'Apply settings' }));
  await screen.findByText('Settings applied for this session.');
  assert.equal(screen.getByLabelText(/API key/).value, ''); assert.equal(saved, 1);
  const payload = api.sent('/api/settings')[0].body;
  assert.equal(payload.api_key, 'synthetic-ui-memory-key');
  for (const role of ['router', 'narrator', 'analyst', 'strategist']) assert.equal(payload[`model_${role}`], `fixture-${role}`);
  assert.equal(localStorage.length, 0);
  assert.equal(document.body.textContent.includes('synthetic-ui-memory-key'), false);
});

test('gateway verification uses no client key/body and distinguishes model listing from generation', async () => {
  const api = installApi(); const pending = deferred(); const user = userEvent.setup();
  api.on('POST', '/api/gateway/check', async () => { await pending.promise; return reply({ status: 'verified', verified: true, detail: 'All configured aliases are listed.', checked_at: '2026-11-10T00:00:00Z', structured_output_verified: false }); });
  render(<SettingsDrawer onClose={() => {}} onSaved={() => {}} />);
  const verify = await screen.findByRole('button', { name: 'Verify current gateway settings' });
  await user.click(verify); assert.equal(screen.getByRole('button', { name: 'Checking gateway…' }).disabled, true);
  assert.equal(screen.queryByText('Model listing verified'), null);
  assert.equal(api.sent('/api/gateway/check')[0].body, undefined);
  pending.resolve(); await screen.findByText('Model listing verified');
  assert.ok(screen.getByText(/Structured generation remains unverified/));
  api.on('POST', '/api/gateway/check', () => reply({ status: 'missing_models', verified: false, detail: 'Aliases are not available.', missing_models: ['fixture-analyst'], structured_output_verified: false }));
  await user.click(screen.getByRole('button', { name: 'Verify current gateway settings' }));
  await screen.findByText('Gateway check: missing models');
  assert.equal(screen.queryByText('Model listing verified'), null); assert.ok(screen.getByText('Unavailable aliases: fixture-analyst'));
});

test('gateway network failure and invalid settings never claim successful verification or save', async () => {
  const api = installApi(); const user = userEvent.setup(); let saved = 0;
  api.on('POST', '/api/gateway/check', () => reply({ detail: 'Gateway network unavailable.' }, 503));
  api.on('PATCH', '/api/settings', () => reply({ detail: 'Invalid configured aliases.' }, 422));
  render(<SettingsDrawer onClose={() => {}} onSaved={() => saved++} />);
  await screen.findByRole('button', { name: 'Verify current gateway settings' });
  await user.click(screen.getByRole('button', { name: 'Verify current gateway settings' }));
  assert.match((await screen.findByRole('alert')).textContent, /network unavailable/);
  assert.equal(screen.queryByText('Model listing verified'), null);
  await user.click(screen.getByRole('button', { name: 'Apply settings' }));
  assert.match((await screen.findByRole('alert')).textContent, /Invalid configured aliases/);
  assert.equal(screen.queryByText('Settings applied for this session.'), null); assert.equal(saved, 0);
});

test('policy editing submits only changed market-gap threshold and displays version update', async () => {
  const api = installApi(); const user = userEvent.setup();
  render(<SettingsDrawer onClose={() => {}} onSaved={() => {}} />);
  const field = await screen.findByLabelText('Market-gap escalation threshold (%)');
  await waitFor(() => assert.equal(field.value, '30'));
  await user.clear(field); await user.type(field, '25');
  await user.click(screen.getByRole('button', { name: 'Apply decision policy' }));
  await screen.findByText(/Policy version updated/);
  assert.deepEqual(api.sent('/api/policy')[0].body, { market_gap_limit_pct: 25 });
  assert.equal(api.sent('/api/settings').length, 0);
});

test('TLS bypass is unavailable without the server permission flag', async () => {
  const api = installApi(); const user = userEvent.setup();
  render(<SettingsDrawer onClose={() => {}} onSaved={() => {}} />);
  const bypass = await screen.findByRole('switch', { name: 'Disable SSL verification' });
  assert.equal(bypass.disabled, true); assert.equal(bypass.getAttribute('aria-checked'), 'false');
  await user.click(bypass); assert.equal(bypass.getAttribute('aria-checked'), 'false');
  assert.equal(api.sent('/api/settings').length, 0);
});
