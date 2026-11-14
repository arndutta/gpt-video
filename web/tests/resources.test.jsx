import assert from 'node:assert/strict';
import { afterEach, test } from 'node:test';
import { act, renderHook, waitFor } from '@testing-library/react';
import { useResource } from '../src/api/useResource';
import { usePolling } from '../src/api/usePolling';
import { deferred, installApi, reply, resetUi } from './fixtures.mjs';

afterEach(resetUi);

test('a catalog response that finishes parsing after cancellation cannot replace the current query', async () => {
  const api = installApi(); const oldBody = deferred(); let parsing = false; let oldSignal;
  api.on('GET', '/api/catalog', ({ url, init }) => {
    if (url.searchParams.get('search') === 'tea') {
      oldSignal = init.signal;
      return { ok: true, json: () => { parsing = true; return oldBody.promise; } };
    }
    return reply({ items: [{ sku: 'OAT-1' }] });
  });
  const { result, rerender } = renderHook(({ path }) => useResource(path), {
    initialProps: { path: '/catalog?search=tea' },
  });
  await waitFor(() => assert.equal(parsing, true));
  rerender({ path: '/catalog?search=oat' });
  await waitFor(() => assert.equal(result.current.data?.items[0].sku, 'OAT-1'));
  assert.equal(oldSignal.aborted, true);
  await act(async () => { oldBody.resolve({ items: [{ sku: 'TEA-1' }] }); });
  assert.equal(result.current.data.items[0].sku, 'OAT-1');
  assert.equal(result.current.loading, false);
});

test('changing audit filters hides the prior scope while the new response is pending or failed', async () => {
  const api = installApi(); const filtered = deferred();
  api.on('GET', '/api/audit', async ({ url }) => {
    if (url.searchParams.has('run_id')) { await filtered.promise; return reply({ detail: 'Filtered audit unavailable' }, 503); }
    return reply({ items: [{ id: 'other-run-event' }] });
  });
  const { result, rerender } = renderHook(({ path }) => usePolling(path, 60000), {
    initialProps: { path: '/audit' },
  });
  await waitFor(() => assert.equal(result.current.data?.items.length, 1));
  rerender({ path: '/audit?run_id=selected-run' });
  assert.equal(result.current.data, undefined);
  assert.equal(result.current.loading, true);
  await act(async () => { filtered.resolve(); });
  await waitFor(() => assert.equal(result.current.error, 'Filtered audit unavailable'));
  assert.equal(result.current.data, undefined);
  assert.equal(result.current.loading, false);
});

test('polling refresh retains the current scope and its error until a successful retry', async () => {
  const api = installApi(); let attempt = 0; const retry = deferred();
  api.on('GET', '/api/control', async () => {
    attempt += 1;
    if (attempt === 2) return reply({ detail: 'Control disconnected' }, 503);
    if (attempt === 3) await retry.promise;
    return reply({ mode: attempt === 1 ? 'supervised' : 'assisted' });
  });
  const { result } = renderHook(() => usePolling('/control', 60000));
  await waitFor(() => assert.equal(result.current.data?.mode, 'supervised'));
  act(() => result.current.reload());
  await waitFor(() => assert.equal(result.current.error, 'Control disconnected'));
  assert.equal(result.current.data.mode, 'supervised');
  act(() => result.current.reload());
  assert.equal(result.current.loading, true);
  assert.equal(result.current.error, 'Control disconnected');
  await act(async () => { retry.resolve(); });
  await waitFor(() => assert.equal(result.current.data.mode, 'assisted'));
  assert.equal(result.current.error, '');
  assert.equal(result.current.loading, false);
});
