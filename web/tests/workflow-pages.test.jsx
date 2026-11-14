import assert from 'node:assert/strict';
import { afterEach, test } from 'node:test';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { RunsPage } from '../src/features/RunsPage';
import { ReviewPage } from '../src/features/ReviewPage';
import { ScenarioPage } from '../src/features/ScenarioPage';
import { DiscoveryPage } from '../src/features/DiscoveryPage';
import { AuditPage } from '../src/features/AuditPage';
import { deferred, installApi, recommendation, reply, resetUi } from './fixtures.mjs';

afterEach(resetUi);

test('workflow cards support keyboard selection and configure inputs without starting a run', async () => {
  const api = installApi(); const user = userEvent.setup();
  render(<MemoryRouter><RunsPage /></MemoryRouter>);
  const preview = screen.getByRole('radio', { name: 'Quantitative preview' });
  const grounded = screen.getByRole('radio', { name: 'Grounded pricing workflow' });
  assert.equal(preview.checked, true);
  preview.focus(); await user.keyboard('{ArrowRight}');
  assert.equal(grounded.checked, true);
  await user.keyboard('{Enter}');
  assert.equal(api.sent('/api/runs').length, 0, 'Choosing a workflow must not submit the form.');
  assert.ok(screen.getByText(/Requires a gateway and indexed evidence/));
  await user.clear(screen.getByLabelText('Horizon (days)')); await user.type(screen.getByLabelText('Horizon (days)'), '7');
  const summary = document.querySelector('.run-configuration-summary');
  assert.match(summary.textContent, /Grounded workflow/); assert.match(summary.textContent, /7 days/);
  assert.equal(api.sent('/api/runs').length, 0);
  await user.click(preview); assert.equal(grounded.checked, false);
  assert.equal(api.calls.some(call => call.method !== 'GET'), false);
});

test('run history filters the loaded response and opens a retained review run without execution', async () => {
  const runs = [
    { id: 'review-run-123', status: 'awaiting_review', created_at: '2026-11-12T00:00:00Z', request: { kind: 'grounded' } },
    { id: 'done-run-123', status: 'completed', created_at: '2026-11-12T00:00:00Z' },
    { id: 'failed-run-123', status: 'failed', created_at: '2026-11-12T00:00:00Z' },
  ];
  const api = installApi({ runs }); const user = userEvent.setup();
  render(<MemoryRouter><RunsPage /></MemoryRouter>);
  await screen.findByRole('button', { name: /Run done-run/ });
  await user.selectOptions(screen.getByLabelText('Filter run history'), 'review');
  assert.equal(screen.queryByRole('button', { name: /Run done-run/ }), null);
  assert.ok(screen.getByText('1 of 3 loaded runs'));
  await user.click(screen.getByRole('button', { name: /Run review-r/ }));
  await screen.findByRole('heading', { name: 'Run review-r' });
  assert.equal(screen.getByRole('button', { name: /Run review-r/ }).getAttribute('aria-pressed'), 'true');
  assert.ok(screen.getByRole('link', { name: 'Review pending recommendations' }));
  await user.selectOptions(screen.getByLabelText('Filter run history'), 'stopped');
  assert.ok(screen.getByRole('button', { name: /Run failed-r/ }));
  assert.equal(api.calls.some(call => call.method !== 'GET'), false);
});

test('review band shortcuts reflect loaded bands and warn about selections hidden by filters', async () => {
  const api = installApi({ items: [recommendation('review'), recommendation('escalate', { band: 'escalate', status: 'escalated' }), recommendation('auto', { band: 'auto_approve' })] });
  const user = userEvent.setup(); render(<MemoryRouter><ReviewPage /></MemoryRouter>);
  await screen.findByRole('button', { name: /Product review/ });
  await waitFor(() => assert.equal(screen.getByRole('button', { name: 'Select eligible Review items' }).disabled, false));
  await user.click(screen.getByRole('button', { name: 'Show Review recommendations' }));
  assert.equal(screen.getByLabelText('Band').value, 'review');
  assert.equal(screen.queryByRole('button', { name: /Product escalate/ }), null);
  await user.click(screen.getByRole('button', { name: 'Select eligible Review items' }));
  await user.click(screen.getByRole('button', { name: 'Show Escalate recommendations' }));
  assert.ok(screen.getByText('1 selected item is outside the current filters. Bulk approval includes all eligible selected items.'));
  assert.equal(screen.getByRole('button', { name: 'Approve 1 selected' }).disabled, false);
  assert.equal(screen.getByRole('checkbox', { name: 'Select ESCALATE for bulk review' }).disabled, true);
  await user.click(screen.getByRole('button', { name: 'Reset filters' }));
  assert.equal(screen.getByLabelText('Band').value, '');
  assert.equal(screen.queryByText(/outside the current filters/), null);
  assert.equal(api.calls.some(call => call.method !== 'GET'), false);
});

test('stress cards support keyboard selection and summarize unique SKUs without simulating', async () => {
  const api = installApi(); const user = userEvent.setup(); render(<ScenarioPage />);
  await screen.findByRole('option', { name: 'Tea pack · BEV-1' });
  const normal = screen.getByRole('radio', { name: 'Normal assumptions' });
  normal.focus(); await user.keyboard('{ArrowRight}');
  assert.equal(screen.getByRole('radio', { name: 'Demand collapse' }).checked, true);
  await user.keyboard('{Enter}');
  await user.selectOptions(screen.getByLabelText('Product'), 'BEV-1');
  assert.match(screen.getByLabelText('Scenario setup summary').textContent, /1 selected SKU/);
  await user.click(screen.getByRole('button', { name: 'Add another SKU' }));
  await user.selectOptions(screen.getByLabelText('Product 2'), 'BEV-1');
  assert.match(screen.getByLabelText('Scenario setup summary').textContent, /1 selected SKU/);
  assert.equal(screen.getByRole('button', { name: 'Simulate scenario' }).disabled, true);
  assert.equal(api.calls.some(call => call.method !== 'GET'), false);
});

test('question starters fill an editable draft and retain the answered question after the next draft', async () => {
  const api = installApi(); const pending = deferred(); const user = userEvent.setup();
  api.on('POST', '/api/discovery/chat', async () => { await pending.promise; return reply({ answer: 'Inspect the current source policy.', citations: ['rag:fixture:policy:0'] }); });
  render(<DiscoveryPage />);
  await user.click(screen.getByRole('button', { name: /Understand the policy/ }));
  const question = screen.getByLabelText('Question'); const original = question.value;
  assert.equal(document.activeElement, question);
  assert.match(original, /pricing policy constraints/); assert.equal(api.sent('/api/discovery/chat').length, 0);
  await user.click(screen.getByRole('button', { name: 'Ask a question' }));
  assert.equal(api.sent('/api/discovery/chat')[0].body.query, original);
  assert.equal(question.disabled, true);
  assert.equal(screen.getByRole('button', { name: /Find the evidence/ }).disabled, true);
  pending.resolve(); await screen.findByText('Inspect the current source policy.');
  await user.click(screen.getByRole('button', { name: /Find the evidence/ }));
  assert.notEqual(question.value, original);
  const response = screen.getByText('Evidence response').closest('.chat-response');
  assert.ok(within(response).getByText(original));
  assert.equal(api.sent('/api/discovery/chat').length, 1);
  assert.equal(api.calls.filter(call => call.method !== 'GET' && call.path !== '/api/discovery/chat').length, 0);
});

test('audit timeline exposes recorded actor and identifiers while reset clears server and local filters', async () => {
  const api = installApi(); const user = userEvent.setup(); const queries = [];
  api.on('GET', '/api/audit', ({ url }) => { queries.push(url.searchParams.toString()); return reply({ items: [{ id: 1, event: 'decision_approved', actor: 'system', run_id: 'run-7', sku: 'SKU-7', created_at: '2026-11-12T00:00:00Z' }], total: 1 }); });
  render(<AuditPage />);
  const event = await screen.findByText('decision approved'); const summary = event.closest('summary');
  assert.ok(within(summary).getByText('system')); assert.ok(within(summary).getByText('Run run-7'));
  assert.ok(within(summary).getByText('SKU-7'));
  await user.click(summary); assert.equal(summary.parentElement.open, true);
  await user.type(screen.getByLabelText('Run ID'), 'run-7');
  await user.type(screen.getByLabelText('SKU'), 'SKU-7');
  await user.click(screen.getByLabelText('System-only events'));
  await waitFor(() => assert.equal(new URLSearchParams(queries.at(-1)).get('automatic'), 'true'));
  await user.type(screen.getByLabelText('Search loaded events'), 'missing');
  assert.ok(screen.getByRole('heading', { name: 'No matching audit events' }));
  await user.click(screen.getByRole('button', { name: 'Reset audit filters' }));
  await waitFor(() => assert.equal(queries.at(-1), ''));
  assert.equal(screen.getByLabelText('Run ID').value, ''); assert.equal(screen.getByLabelText('SKU').value, '');
  assert.equal(screen.getByLabelText('Search loaded events').value, '');
  assert.equal(screen.getByLabelText('System-only events').checked, false);
  assert.equal(api.calls.some(call => call.method !== 'GET'), false);
});
