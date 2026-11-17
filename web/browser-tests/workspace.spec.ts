import { test, expect, type Page, type Locator } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';

test.describe.configure({ mode: 'default' });

async function settled(page: Page) {
  await page.waitForFunction(() => document.getAnimations().every(animation => {
    const end = animation.effect?.getComputedTiming().endTime;
    return !Number.isFinite(end) || animation.playState !== 'running';
  }), undefined, { polling: 'raf', timeout: 5000 });
}

async function ready(page: Page, route = '/') {
  await page.goto(route);
  await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
  await expect(page.getByText('Commerce connected', { exact: true })).toBeVisible();
  await expect(page.getByLabel('Operating mode')).toBeEnabled();
  await settled(page);
}

async function measured(page: Page, control: Locator, observe: () => Promise<unknown>) {
  await page.evaluate(() => {
    document.addEventListener('click', () => { (window as any).__qaStart = performance.now(); }, { once: true, capture: true });
  });
  await control.click();
  await observe();
  return page.evaluate(() => new Promise<number>(resolve => requestAnimationFrame(() => requestAnimationFrame(() => {
    resolve(performance.now() - (window as any).__qaStart);
  }))));
}

for (const theme of ['light', 'dark']) {
  test(`${theme}: seven populated routes fit 1280px and meet WCAG AA`, async ({ page }, info) => {
    const failures: unknown[] = [];
    for (const route of ['/', '/catalog', '/runs', '/review', '/simulation', '/audit', '/discovery']) {
      await ready(page, route);
      if (await page.locator('html').getAttribute('data-theme') !== theme) {
        await page.getByRole('button', { name: `Switch to ${theme} theme` }).click();
      }
      await expect(page.locator('html')).toHaveAttribute('data-theme', theme);
      await settled(page);
      if (route === '/review') await expect(page.locator('.review-table tbody tr')).toHaveCount(15);
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy();
      const result = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21aa']).analyze();
      failures.push(...result.violations.map(item => ({ route, id: item.id, impact: item.impact,
        nodes: item.nodes.map(node => ({ target: node.target, summary: node.failureSummary })) })));
      await page.screenshot({ path: info.outputPath(`${theme}-${route.slice(1) || 'overview'}.png`), fullPage: true });
    }
    await info.attach('accessibility-findings', { body: JSON.stringify(failures, null, 2), contentType: 'application/json' });
    expect(failures).toEqual([]);
  });
}

test('review filters, sorting, keyboard focus, details, citations and family ladder', async ({ page }, info) => {
  await ready(page, '/review');
  await expect(page.locator('.review-table tbody tr')).toHaveCount(15);
  await page.getByRole('button', { name: 'Show Review recommendations', exact: true }).click();
  await expect(page.locator('.review-table tbody tr')).toHaveCount(3);
  await page.getByRole('combobox', { name: 'Sort by' }).selectOption('confidence');
  await page.getByRole('button', { name: 'Show All loaded recommendations', exact: true }).click();
  await page.getByRole('button', { name: 'Reset filters', exact: true }).click();
  const opener = page.locator('.product-detail-link').first();
  await opener.focus();
  await page.keyboard.press('Enter');
  const dialog = page.getByRole('dialog');
  await expect(dialog).toBeVisible();
  await expect(dialog.getByRole('heading', { name: 'Family price ladder' })).toBeVisible();
  await expect(dialog.getByRole('heading', { name: 'Grounded rationale' })).toBeVisible();
  await dialog.locator('.citation-button').first().click();
  await expect(dialog.locator('.citation-content')).toContainText('Human review remains authoritative');
  await expect(dialog.locator('.interval-plot').first()).toBeVisible();
  await settled(page);
  for (let index = 0; index < 35; index++) {
    await page.keyboard.press(index % 2 ? 'Shift+Tab' : 'Tab');
    expect(await dialog.evaluate(element => element.contains(document.activeElement))).toBeTruthy();
  }
  const audit = await new AxeBuilder({ page }).include('[role="dialog"]').withTags(['wcag2a', 'wcag2aa']).analyze();
  await info.attach('drawer-accessibility', { body: JSON.stringify(audit.violations, null, 2), contentType: 'application/json' });
  expect(audit.violations).toEqual([]);
  await page.screenshot({ path: info.outputPath('review-details-ladder.png'), fullPage: true });
  await page.keyboard.press('Escape');
  await expect(dialog).toHaveCount(0);
  await expect(opener).toBeFocused();
  await expect(page.getByText('System approved', { exact: true })).toHaveCount(3);
});

test('scenario distributions, margin risk, stress, saved result, both themes and latency', async ({ page }, info) => {
  await ready(page, '/simulation');
  await page.getByRole('combobox', { name: 'Product', exact: true }).selectOption('SKU-00001');
  await page.getByLabel('Simulation draws', { exact: true }).fill('100');
  await page.getByRole('button', { name: 'Simulate scenario', exact: true }).click();
  await expect(page.getByRole('img', { name: /^Revenue:/ }).first()).toBeVisible();
  await expect(page.getByText('Probability of falling below the margin floor', { exact: true })).toBeVisible();
  const latencies = [];
  for (const theme of ['light', 'dark']) {
    if (await page.locator('html').getAttribute('data-theme') !== theme) {
      latencies.push(await measured(page, page.getByRole('button', { name: `Switch to ${theme} theme` }),
        () => expect(page.locator('html')).toHaveAttribute('data-theme', theme)));
    }
    const lower = page.getByRole('button', { name: 'Revenue lower bound', exact: true }).first();
    latencies.push(await measured(page, lower, () => expect(lower).toHaveAttribute('aria-pressed', 'true')));
    await settled(page);
    const result = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21aa']).analyze();
    expect(result.violations).toEqual([]);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy();
    await page.screenshot({ path: info.outputPath(`scenario-distributions-${theme}.png`), fullPage: true });
  }
  await page.getByLabel('Scenario name', { exact: true }).fill('Browser saved scenario');
  await page.getByRole('button', { name: 'Reevaluate & save', exact: true }).click();
  await expect(page.getByRole('button', { name: /Browser saved scenario/ })).toBeVisible();
  await page.getByRole('button', { name: /Browser saved scenario/ }).click();
  await expect(page.getByRole('status').filter({ hasText: 'Loaded Browser saved scenario' })).toBeVisible();
  await page.getByRole('button', { name: 'Add another SKU', exact: true }).click();
  await page.getByRole('combobox', { name: 'Product 2', exact: true }).selectOption('SKU-00002');
  const stress = page.getByRole('radio', { name: 'Competitor undercut', exact: true });
  await stress.focus();
  await page.keyboard.press('Space');
  await expect(stress).toBeChecked();
  await page.getByRole('button', { name: 'Simulate scenario', exact: true }).click();
  await expect(page.getByRole('img', { name: /^Revenue:/ })).toHaveCount(2);
  await page.reload();
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark');
  expect(Math.max(...latencies)).toBeLessThanOrEqual(500);
  await info.attach('interaction-latency-ms', { body: JSON.stringify(latencies), contentType: 'application/json' });
});

test('persistent header, command search, settings, knowledge and loop drawers', async ({ page }, info) => {
  await ready(page);
  await page.locator('.global-header').evaluate(element => { (element as any).__qaPersistent = true; });
  const catalog = page.getByRole('link', { name: 'Product catalog', exact: true });
  const latency = await measured(page, catalog, () => expect(page).toHaveURL(/\/catalog$/));
  expect(await page.locator('.global-header').evaluate(element => (element as any).__qaPersistent)).toBeTruthy();
  await page.keyboard.press('ControlOrMeta+k');
  await page.getByRole('combobox', { name: 'Search workspace', exact: true }).fill('Scenario lab');
  await page.keyboard.press('Enter');
  await expect(page).toHaveURL(/\/simulation$/);
  for (const [button, heading] of [
    [page.getByRole('button', { name: 'Open workspace settings', exact: true }), 'Workspace settings'],
    [page.getByRole('button', { name: /^Knowledge & grounding/ }), 'Knowledge & grounding'],
    [page.getByRole('button', { name: 'Loop off', exact: true }), 'Continuous pricing loop'],
  ] as const) {
    await button.click();
    await expect(page.getByRole('dialog', { name: heading, exact: true })).toBeVisible();
    if (heading === 'Workspace settings') {
      await expect(page.getByLabel('Disable SSL verification', { exact: true })).toBeDisabled();
      await expect(page.getByPlaceholder('Enter a new key', { exact: true })).toHaveValue('');
    }
    if (heading === 'Knowledge & grounding') await expect(page.getByText('Browser acceptance policy', { exact: true })).toBeVisible();
    await page.screenshot({ path: info.outputPath(`${heading.replaceAll(' ', '-')}.png`), fullPage: true });
    await page.keyboard.press('Escape');
    await expect(page.getByRole('dialog')).toHaveCount(0);
    await expect(button).toBeFocused();
  }
  expect(latency).toBeLessThanOrEqual(500);
  await info.attach('route-latency-ms', { body: JSON.stringify({ latency }), contentType: 'application/json' });
});

test('review decisions and one-confirmation halt are acknowledged by the real backend', async ({ page }) => {
  await ready(page, '/review');
  await page.getByRole('button', { name: 'Show Review recommendations', exact: true }).click();
  await page.getByRole('button', { name: 'Select eligible Review items', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Approve 3 selected', exact: true })).toBeEnabled();
  await page.getByRole('button', { name: 'Approve 3 selected', exact: true }).click();
  await expect(page.getByRole('status').filter({ hasText: 'Bulk review decisions' })).toBeVisible();
  await page.getByRole('button', { name: 'Show Escalate recommendations', exact: true }).click();
  await page.locator('.review-table tbody tr').filter({ hasText: 'escalated' }).first().locator('.product-detail-link').click();
  const submit = page.getByRole('button', { name: 'Submit decision', exact: true });
  await expect(submit).toBeDisabled();
  await page.getByLabel('Reason (required)', { exact: true }).fill('Synthetic browser reviewer rejects the oscillation fixture.');
  await page.getByRole('combobox', { name: 'Decision', exact: true }).selectOption('reject');
  await submit.click();
  await expect(page.getByRole('status').filter({ hasText: 'Decision acknowledged' })).toBeVisible();
  await page.keyboard.press('Escape');
  await page.getByRole('button', { name: 'Show Auto-approve recommendations', exact: true }).click();
  await page.locator('.review-table tbody tr').filter({ hasText: /pending review/i }).first().locator('.product-detail-link').click();
  await page.getByRole('combobox', { name: 'Decision', exact: true }).selectOption('override');
  const price = page.getByRole('spinbutton', { name: 'Override price', exact: true });
  await price.fill((Number(await price.inputValue()) + .01).toFixed(2));
  await page.getByRole('textbox', { name: 'Reason (required)', exact: true }).fill('Synthetic browser override with fresh forecast.');
  await page.getByRole('button', { name: 'Submit decision', exact: true }).click();
  await expect(page.getByRole('dialog').getByText(/Revision 2/)).toBeVisible();
  await expect(page.getByRole('dialog').getByText('Human decision', { exact: true })).toBeVisible();
  await page.keyboard.press('Escape');
  await page.getByRole('button', { name: 'Show Escalate recommendations', exact: true }).click();
  await page.locator('.review-table tbody tr').filter({ hasText: /blocked/i }).first().locator('.product-detail-link').click();
  await expect(page.getByText(/Compliance veto\. Approval, overrides/)).toBeVisible();
  await expect(page.getByRole('button', { name: 'Submit decision', exact: true })).toHaveCount(0);
  await page.keyboard.press('Escape');
  await page.getByLabel('Operating mode', { exact: true }).selectOption('assisted');
  await expect(page.getByRole('status').filter({ hasText: 'Mode changed to assisted' })).toBeVisible();
  let halts = 0;
  page.on('request', request => { if (request.method() === 'POST' && request.url().endsWith('/api/control/kill')) halts++; });
  await page.getByRole('button', { name: 'Halt', exact: true }).click();
  expect(halts).toBe(0);
  await page.getByRole('button', { name: 'Keep current activity', exact: true }).click();
  expect(halts).toBe(0);
  await page.getByRole('button', { name: 'Halt', exact: true }).click();
  await page.getByRole('button', { name: 'Confirm halt', exact: true }).click();
  await expect(page.getByLabel('Operating mode', { exact: true })).toHaveValue('supervised');
  await expect(page.getByRole('status').filter({ hasText: 'Halt acknowledged' })).toBeVisible();
  expect(halts).toBe(1);
});
