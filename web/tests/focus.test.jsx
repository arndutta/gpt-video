import assert from 'node:assert/strict';
import { afterEach, test } from 'node:test';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Drawer } from '../src/components/Common';
import { focusableElements } from '../src/components/focus';
import { resetUi } from './fixtures.mjs';

afterEach(resetUi);

function ids(root) { return focusableElements(root).map(element => element.id); }

test('native modal stops exclude hidden ancestry, disabled fieldsets and negative tabindex', () => {
  render(<div data-testid="root">
    <button id="start">Start</button>
    <input id="hidden-type" type="hidden" />
    <button id="negative" tabIndex={-1}>Programmatic only</button>
    <button id="disabled" disabled>Disabled</button>
    <div hidden><button id="hidden">Hidden</button></div>
    <div inert><button id="inert">Inert</button></div>
    <div style={{ display: 'none' }}><button id="display">No display</button></div>
    <div style={{ visibility: 'hidden' }}><button id="visibility">Not visible</button></div>
    <fieldset disabled><legend><button id="legend">Legend exception</button></legend><input id="fieldset" /></fieldset>
    <button id="end">End</button>
  </div>);
  assert.deepEqual(ids(screen.getByTestId('root')), ['start', 'legend', 'end']);
});

test('closed disclosures retain the first summary and hide the rest of their contents', () => {
  render(<div data-testid="root">
    <details><summary id="closed-summary">Closed options</summary><button id="closed">Hidden option</button><summary id="second-summary">Second summary</summary></details>
    <details open><summary id="open-summary">Open options</summary><button id="open">Visible option</button></details>
    <details><summary id="outer">Outer</summary><details open><summary id="nested-summary">Nested</summary><button id="nested">Nested option</button></details></details>
  </div>);
  assert.deepEqual(ids(screen.getByTestId('root')), ['closed-summary', 'open-summary', 'open', 'outer']);
});

test('radio tab stops preserve visually hidden checked controls and separate form owners', () => {
  render(<div data-testid="root">
    <form id="first-form"><input id="first-unchecked" type="radio" name="workflow" /><input id="first-checked" type="radio" name="workflow" defaultChecked style={{ opacity: 0 }} /></form>
    <form id="second-form"><input id="second-first" type="radio" name="workflow" /><input id="second-last" type="radio" name="workflow" /></form>
    <form id="external-form"><input id="external-first" type="radio" name="workflow" /></form>
    <input id="external-checked" type="radio" name="workflow" form="external-form" defaultChecked />
    <input id="unnamed-a" type="radio" /><input id="unnamed-b" type="radio" />
    <input id="disabled-checked" type="radio" name="disabled-group" defaultChecked disabled /><input id="enabled-fallback" type="radio" name="disabled-group" />
  </div>);
  assert.deepEqual(ids(screen.getByTestId('root')), ['first-checked', 'second-first', 'external-checked', 'unnamed-a', 'unnamed-b', 'enabled-fallback']);
});

test('radio grouping includes the checked owner outside the modal and honors positive tab order', () => {
  render(<><input id="outside-choice" type="radio" name="shared-choice" defaultChecked /><div data-testid="root">
    <input id="inside-choice" type="radio" name="shared-choice" />
    <button id="ordinary">Ordinary</button><button id="positive-two" tabIndex={2}>Second</button><button id="positive-one" tabIndex={1}>First</button>
  </div></>);
  assert.deepEqual(ids(screen.getByTestId('root')), ['positive-one', 'positive-two', 'ordinary']);
});

test('Drawer wraps Tab at a closed summary rather than hidden or disabled tail controls', async () => {
  const user = userEvent.setup();
  render(<Drawer title="Native focus boundary" onClose={() => {}}>
    <button>Visible action</button>
    <details><summary>Advanced options</summary><button>Closed option</button></details>
    <fieldset disabled><input aria-label="Disabled tail" /></fieldset>
    <div hidden><button>Hidden tail</button></div>
  </Drawer>);
  const dialog = screen.getByRole('dialog');
  assert.equal(document.activeElement, dialog);
  await user.tab({ shift: true });
  assert.equal(document.activeElement, screen.getByText('Advanced options'));
  await user.tab();
  assert.equal(document.activeElement, screen.getByRole('button', { name: 'Close panel' }));
  await user.tab({ shift: true });
  assert.equal(document.activeElement, screen.getByText('Advanced options'));
});

test('Drawer wraps at the checked radio card even when an unchecked sibling follows it', async () => {
  const user = userEvent.setup();
  render(<Drawer title="Radio focus boundary" onClose={() => {}}>
    <label><input type="radio" name="mode-card" defaultChecked style={{ opacity: 0 }} />Forecast card</label>
    <label><input type="radio" name="mode-card" style={{ opacity: 0 }} />Grounded card</label>
  </Drawer>);
  const checked = screen.getByRole('radio', { name: 'Forecast card' });
  await user.tab({ shift: true });
  assert.equal(document.activeElement, checked);
  await user.tab();
  assert.equal(document.activeElement, screen.getByRole('button', { name: 'Close panel' }));
});

test('Drawer recaptures Tab when its focused control disappears during an update', async () => {
  const user = userEvent.setup();
  const onClose = () => {};
  function Content({ showAction }) {
    return <><button>Outside the modal</button><Drawer title="Updating content" onClose={onClose}>
      {showAction && <button>Temporary action</button>}
      <button>Last action</button>
    </Drawer></>;
  }
  const view = render(<Content showAction />);
  screen.getByRole('button', { name: 'Temporary action' }).focus();
  view.rerender(<Content showAction={false} />);
  assert.ok(document.activeElement === document.body, 'Removing the focused control leaves focus on the document.');
  await user.tab();
  assert.ok(document.activeElement === screen.getByRole('button', { name: 'Close panel' }), 'Tab recaptures focus at the start of the modal.');
  screen.getByRole('button', { name: 'Outside the modal' }).focus();
  await user.tab({ shift: true });
  assert.ok(document.activeElement === screen.getByRole('button', { name: 'Last action' }), 'Shift+Tab recaptures focus at the end of the modal.');
});

test('Drawer retains focus across new close callbacks and invokes the latest callback', async () => {
  const user = userEvent.setup(); const closed = [];
  const view = render(<Drawer title="Stable focus" onClose={() => closed.push('old')}><input aria-label="Draft" /></Drawer>);
  const input = screen.getByRole('textbox', { name: 'Draft' });
  await user.type(input, 'draft');
  view.rerender(<Drawer title="Stable focus" onClose={() => closed.push('latest')}><input aria-label="Draft" /></Drawer>);
  assert.ok(document.activeElement === input, 'Parent updates must not steal focus from the draft.');
  assert.equal(document.body.style.overflow, 'hidden');
  await user.keyboard('{Escape}');
  assert.deepEqual(closed, ['latest']);
});
