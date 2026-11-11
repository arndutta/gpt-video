import assert from 'node:assert/strict';
import { afterEach, test } from 'node:test';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { ReviewPage } from '../src/features/ReviewPage';
import { RecommendationDrawer } from '../src/features/RecommendationDrawer';
import { installApi, recommendation, reply, resetUi } from './fixtures.mjs';

afterEach(resetUi);

function drawer(item, changed = () => {}) {
  return render(<RecommendationDrawer item={item} peers={[item]} onClose={() => {}} onChanged={changed} />);
}

test('review is keyboard reachable, opens with Enter, traps focus and restores it on Escape', async () => {
  installApi({ items: [recommendation()] }); const user = userEvent.setup();
  render(<MemoryRouter><ReviewPage /></MemoryRouter>);
  const product = await screen.findByRole('button', { name: /Product review-1/ });
  for (let n = 0; n < 25 && document.activeElement !== product; n++) await user.tab();
  assert.equal(document.activeElement, product);
  await user.keyboard('{Enter}');
  const dialog = screen.getByRole('dialog');
  assert.equal(document.activeElement, dialog);
  await user.tab(); assert.equal(document.activeElement, within(dialog).getByRole('button', { name: 'Close panel' }));
  await user.tab({ shift: true }); assert.equal(dialog.contains(document.activeElement), true);
  await user.keyboard('{Escape}');
  assert.equal(screen.queryByRole('dialog'), null); assert.equal(document.activeElement, product);
});

test('approve and reject send the exact immutable revision with no manual price', async () => {
  for (const action of ['approve', 'reject']) {
    const api = installApi(); let changed = 0; const user = userEvent.setup();
    drawer(recommendation(), () => changed++);
    await user.selectOptions(screen.getByLabelText('Decision'), action);
    await user.click(screen.getByRole('button', { name: 'Submit decision' }));
    await screen.findByText(/Decision acknowledged/);
    assert.deepEqual(api.sent('/api/recommendations/review-1/decision')[0].body, { action, expected_revision: 2 });
    assert.equal(changed, 1); resetUi();
  }
});

test('price override requires a nonblank reason and sends its candidate only as override', async () => {
  const api = installApi(); const user = userEvent.setup(); drawer(recommendation());
  await user.selectOptions(screen.getByLabelText('Decision'), 'override');
  const submit = screen.getByRole('button', { name: 'Submit decision' });
  assert.equal(submit.disabled, true);
  await user.clear(screen.getByLabelText('Override price')); await user.type(screen.getByLabelText('Override price'), '10.25');
  await user.type(screen.getByLabelText(/Reason/), '   '); assert.equal(submit.disabled, true);
  await user.clear(screen.getByLabelText(/Reason/)); await user.type(screen.getByLabelText(/Reason/), ' Retain margin headroom ');
  await user.click(submit); await screen.findByText(/Decision acknowledged/);
  assert.deepEqual(api.sent('/api/recommendations/review-1/decision')[0].body, { action: 'override', expected_revision: 2, price: '10.25', reason: 'Retain margin headroom' });
});

test('a clean escalation needs a written human reason before approval', async () => {
  const api = installApi(); const user = userEvent.setup(); drawer(recommendation('risk', { band: 'escalate', status: 'escalated' }));
  assert.equal(screen.getByRole('button', { name: 'Submit decision' }).disabled, true);
  await user.type(screen.getByLabelText(/Reason/), 'Reviewed exceptional competitor event');
  await user.click(screen.getByRole('button', { name: 'Submit decision' }));
  await screen.findByText(/Decision acknowledged/);
  assert.equal(api.sent('/api/recommendations/risk/decision')[0].body.reason, 'Reviewed exceptional competitor event');
});

test('compliance veto and unchanged terminal state expose no decision or revert action', async () => {
  const api = installApi();
  for (const patch of [{ status: 'blocked', compliance: { status: 'failed', rules: [] } }, { status: 'unchanged', execution: { unchanged: true } }]) {
    drawer(recommendation('terminal', patch));
    assert.equal(screen.queryByRole('button', { name: 'Submit decision' }), null);
    assert.equal(screen.queryByRole('button', { name: 'Revert this change' }), null);
    resetUi();
  }
  assert.equal(api.calls.some(call => call.method === 'POST'), false);
});

test('stale decision errors remain visible without claiming acknowledgment', async () => {
  const api = installApi(); let changed = 0; const user = userEvent.setup();
  api.on('POST', '/api/recommendations/review-1/decision', () => reply({ detail: 'The revision changed; refresh.' }, 409));
  drawer(recommendation(), () => changed++);
  await user.click(screen.getByRole('button', { name: 'Submit decision' }));
  assert.match((await screen.findByRole('alert')).textContent, /revision changed/);
  assert.equal(screen.queryByText(/Decision acknowledged/), null); assert.equal(changed, 0);
});

test('bulk selection excludes Auto, Escalate, exact-threshold, veto and already applied rows', async () => {
  const items = [recommendation('eligible'), recommendation('auto', { band: 'auto_approve' }),
    recommendation('escalate', { band: 'escalate', status: 'escalated' }), recommendation('boundary', { confidence: 0.8 }),
    recommendation('veto', { compliance: { status: 'failed', rules: [] }, compliance_status: 'failed' }), recommendation('applied', { status: 'applied' })];
  const api = installApi({ items }); const user = userEvent.setup(); render(<MemoryRouter><ReviewPage /></MemoryRouter>);
  const eligible = await screen.findByRole('checkbox', { name: 'Select ELIGIBLE for bulk review' });
  await waitFor(() => assert.equal(eligible.disabled, false));
  for (const id of ['AUTO', 'ESCALATE', 'BOUNDARY', 'VETO', 'APPLIED']) assert.equal(screen.getByRole('checkbox', { name: `Select ${id} for bulk review` }).disabled, true);
  eligible.focus(); await user.keyboard('[Space]'); assert.equal(eligible.checked, true);
  await user.click(screen.getByRole('button', { name: 'Approve 1 selected' }));
  await screen.findByText(/Bulk review decisions acknowledged/);
  assert.deepEqual(api.sent('/api/recommendations/bulk')[0].body, { ids: ['eligible'], expected_revisions: { eligible: 2 } });
  assert.equal(api.sent('/api/recommendations/bulk').length, 1);
  assert.equal(screen.getByRole('checkbox', { name: 'Select ELIGIBLE for bulk review' }).disabled, true);
});

test('review filters and cited source inspection operate on real component state', async () => {
  const api = installApi({ items: [recommendation('tea'), recommendation('oats', { category: 'Snacks', band: 'auto_approve' })] });
  const user = userEvent.setup(); render(<MemoryRouter><ReviewPage /></MemoryRouter>);
  await screen.findByRole('button', { name: /Product tea/ });
  await user.selectOptions(screen.getByLabelText('Category'), 'Snacks');
  assert.equal(screen.queryByRole('button', { name: /Product tea/ }), null);
  await user.selectOptions(screen.getByLabelText('Category'), '');
  await user.type(screen.getByLabelText('Find product'), 'tea');
  await user.click(screen.getByRole('button', { name: /Product tea/ }));
  await user.click(screen.getByRole('button', { name: 'rag:fixture:policy:0' }));
  await screen.findByText('Synthetic policy requires compliance.');
  assert.equal(api.calls.filter(call => call.path.includes('/grounding/citations/')).length, 1);
});

test('confidence/delta/compliance filters and all numeric sorting use displayed recommendation data', async () => {
  installApi({ items: [recommendation('low', { confidence: 0.7, delta_pct: -12, band: 'escalate', impact: {revenue:{mean:10}} }),
    recommendation('high', { confidence: 0.95, delta_pct: 4, band: 'auto_approve', category:'Snacks', impact:{revenue:{mean:30}} }),
    recommendation('veto', { confidence: 0.85, delta_pct: 2, status:'blocked', impact:{revenue:{mean:20}}, compliance_status: 'failed', compliance: { status: 'failed', rules: [] } })] });
  const user = userEvent.setup(); render(<MemoryRouter><ReviewPage /></MemoryRouter>);
  await screen.findByRole('button', { name: /Product low/ });
  const order = () => within(screen.getByRole('table')).getAllByRole('button').map(button => button.textContent);
  assert.match(order()[0], /Product high/);
  await user.selectOptions(screen.getByLabelText('Sort by'), 'confidence'); assert.match(order()[0], /Product high/);
  await user.selectOptions(screen.getByLabelText('Sort by'), 'delta'); assert.match(order()[0], /Product low/);
  await user.selectOptions(screen.getByLabelText('Sort by'), 'band'); assert.match(order()[0], /Product low/);
  await user.selectOptions(screen.getByLabelText('Sort by'), 'category'); assert.match(order()[0], /Product low/);
  await user.selectOptions(screen.getByLabelText('Band'), 'auto_approve'); assert.equal(order().length,1);
  await user.selectOptions(screen.getByLabelText('Band'), '');
  await user.selectOptions(screen.getByLabelText('Disposition'), 'blocked'); assert.match(order()[0],/Product veto/);
  await user.selectOptions(screen.getByLabelText('Disposition'), '');
  await user.selectOptions(screen.getByLabelText('Compliance'), 'passed'); assert.equal(screen.queryByRole('button', { name: /Product veto/ }), null);
  await user.type(screen.getByLabelText('Minimum confidence (%)'), '90'); assert.equal(order().length, 1); assert.match(order()[0], /Product high/);
  await user.type(screen.getByLabelText('Maximum absolute change (%)'), '3');
  assert.ok(screen.getByText('No matching recommendations'));
});

test('unavailable decision policy visibly disables bulk actions instead of using a guessed threshold', async () => {
  const api = installApi({ items: [recommendation()] });
  api.on('GET', '/api/policy', () => reply({ detail: 'Policy service unavailable.' }, 503));
  render(<MemoryRouter><ReviewPage /></MemoryRouter>);
  assert.match((await screen.findByRole('alert')).textContent, /Decision policy unavailable/);
  assert.equal(screen.getByRole('button', { name: 'Select eligible Review items' }).disabled, true);
  assert.equal(screen.getByRole('checkbox', { name: 'Select REVIEW-1 for bulk review' }).disabled, true);
  assert.equal(api.sent('/api/recommendations/bulk').length, 0);
});
