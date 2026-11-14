import assert from 'node:assert/strict';
import { afterEach, test } from 'node:test';
import { act, render, renderHook, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { PolicySettings } from '../src/features/PolicySettings';
import { GroundingDrawer } from '../src/features/GroundingDrawer';
import { useGrounding } from '../src/features/useGrounding';
import { deferred, initialPolicy, installApi, reply, resetUi } from './fixtures.mjs';

afterEach(resetUi);

const uploadJob = (status = 'queued') => ({ id: 'upload-1', filename: 'policy.md', source_id: 'policy',
  title: 'Pricing policy', collection: 'pricing_policy', status, created_at: '2026-11-14T00:00:00Z',
  updated_at: '2026-11-14T00:00:00Z', completed_at: status === 'ready' ? '2026-11-14T00:00:01Z' : null,
  result: status === 'ready' ? { source_id: 'policy', collection: 'pricing_policy', version: 'v1',
    chunk_count: 2, corpus_version: 1, changed: true } : null });
const statistics = (version = 0) => ({ items: [], corpus_version: version, status: 'ready',
  embedding: { provider: 'local', available: true, detail: 'Explicit test fixture' } });

test('a history read begun before upload cannot erase the accepted job or miss its completion', async () => {
  const api = installApi(); const oldHistory = deferred(); const freshHistory = deferred();
  let historyReads = 0; let collectionReads = 0;
  api.on('GET', '/api/grounding/uploads', async () => {
    historyReads += 1;
    if (historyReads === 1) return { ok: true, json: () => oldHistory.promise };
    await freshHistory.promise;
    return reply({ items: [uploadJob('ready')] });
  });
  api.on('GET', '/api/grounding/collections', () => reply(statistics(collectionReads++)));
  api.on('POST', '/api/grounding/uploads', () => reply(uploadJob(), 202));
  const { result } = renderHook(() => useGrounding());
  await waitFor(() => assert.equal(historyReads, 1));
  await act(async () => { await result.current.upload(new FormData()); });
  assert.equal(result.current.uploads[0].status, 'queued');
  await act(async () => { oldHistory.resolve({ items: [] }); });
  await waitFor(() => assert.equal(historyReads, 2));
  assert.equal(result.current.uploads[0].id, 'upload-1');
  await act(async () => { freshHistory.resolve(); });
  await waitFor(() => assert.equal(result.current.uploads[0].status, 'ready'));
  await waitFor(() => assert.equal(result.current.statistics.corpus_version, 1));
  assert.equal(collectionReads, 2);
});

test('a completed upload invalidates an in-flight collection snapshot and requests current counts', async () => {
  const api = installApi(); const oldStatistics = deferred(); let collectionReads = 0;
  const versions = [];
  api.on('GET', '/api/grounding/collections', () => ++collectionReads === 1
    ? { ok: true, json: () => oldStatistics.promise } : reply(statistics(1)));
  api.on('POST', '/api/grounding/uploads', () => reply(uploadJob('ready'), 202));
  const { result } = renderHook(() => {
    const state = useGrounding(); versions.push(state.statistics?.corpus_version); return state;
  });
  await waitFor(() => assert.equal(collectionReads, 1));
  await act(async () => { await result.current.upload(new FormData()); });
  await act(async () => { oldStatistics.resolve(statistics(0)); });
  await waitFor(() => assert.equal(result.current.statistics?.corpus_version, 1));
  assert.equal(collectionReads, 2);
  assert.equal(versions.includes(0), false, 'A pre-publication snapshot must not replace current collection state.');
});

test('pending policy updates freeze the submitted draft and a failed request retains it for retry', async () => {
  const api = installApi(); const pending = deferred(); const user = userEvent.setup(); let attempts = 0;
  api.on('PATCH', '/api/policy', async ({ body }) => {
    if (++attempts === 1) { await pending.promise; return reply({ detail: 'Policy temporarily unavailable' }, 503); }
    api.on('GET', '/api/policy', () => reply({ version: 2, thresholds: { ...initialPolicy, ...body } }));
    return reply({ version: 2, thresholds: { ...initialPolicy, ...body } });
  });
  render(<PolicySettings />);
  const field = await screen.findByLabelText('Market-gap escalation threshold (%)');
  await waitFor(() => assert.equal(field.value, '30'));
  await user.clear(field); await user.type(field, '25');
  await user.click(screen.getByRole('button', { name: 'Apply decision policy' }));
  for (const input of screen.getAllByRole('spinbutton')) assert.equal(input.disabled, true);
  await user.type(field, '9'); assert.equal(field.value, '25');
  assert.deepEqual(api.sent('/api/policy')[0].body, { market_gap_limit_pct: 25 });
  await act(async () => { pending.resolve(); });
  await screen.findByText('Policy temporarily unavailable');
  assert.equal(field.disabled, false); assert.equal(field.value, '25');
  assert.equal(screen.queryByText(/Policy version updated/), null);
  await user.clear(field); await user.type(field, '24');
  await user.click(screen.getByRole('button', { name: 'Apply decision policy' }));
  await screen.findByText(/Policy version updated/);
  assert.deepEqual(api.sent('/api/policy')[1].body, { market_gap_limit_pct: 24 });
  assert.equal((await screen.findByLabelText('Market-gap escalation threshold (%)')).value, '24');
});

test('document upload submits multipart identity and retains safe indexing failure evidence', async () => {
  const api = installApi(); const user = userEvent.setup();
  api.on('POST', '/api/grounding/uploads', ({ body }) => {
    assert.ok(body instanceof FormData);
    assert.equal(body.get('file').name, 'policy.md');
    assert.equal(body.get('collection'), 'pricing_policy');
    assert.equal(body.get('source_id'), 'demo-policy');
    assert.equal(body.get('version'), 'v2');
    return reply({ ...uploadJob('failed'), error: 'Indexing unavailable. Retry this document.', error_code: 'indexing_failed' }, 202);
  });
  render(<GroundingDrawer onClose={() => {}} />);
  await user.upload(screen.getByLabelText('Document'), new File(['Review every price change.'], 'policy.md', { type: 'text/markdown' }));
  await user.selectOptions(screen.getByLabelText('Collection'), 'pricing_policy');
  await user.click(screen.getByText('Document identity & version'));
  await user.type(screen.getByLabelText('Stable source ID'), 'demo-policy');
  await user.type(screen.getByLabelText('Version'), 'v2');
  await user.click(screen.getByRole('button', { name: 'Upload & index' }));
  await screen.findByText('Indexing unavailable. Retry this document.');
  assert.ok(screen.getByText('Any previously indexed version remains available.'));
  assert.equal(screen.getByLabelText('Document').files.length, 0);
  assert.equal(api.sent('/api/grounding/uploads').length, 1);
  assert.equal(api.calls.filter(call => call.method !== 'GET' && call.path !== '/api/grounding/uploads').length, 0);
});
