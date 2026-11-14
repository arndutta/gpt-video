import assert from 'node:assert/strict';
import { afterEach, test } from 'node:test';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { CatalogPage } from '../src/features/CatalogPage';
import { ForecastBands } from '../src/components/Forecast';
import { installApi, products, reply, resetUi } from './fixtures.mjs';

afterEach(resetUi);

test('catalog refresh recovers summary failures and refreshes the counts and category choices', async () => {
  const api = installApi(); const user = userEvent.setup(); let summaryRequests = 0;
  api.on('GET', '/api/catalog/summary', () => ++summaryRequests === 1
    ? reply({ detail: 'Catalog summary temporarily unavailable' }, 503)
    : reply({ sku_count: 3, categories: [{ name: 'New category', sku_count: 3 }], inventory_units: 30 }));
  render(<CatalogPage />);
  await screen.findByText('Catalog summary temporarily unavailable');
  await screen.findByRole('button', { name: 'Inspect Tea pack' });
  await user.click(screen.getByRole('button', { name: 'Refresh catalog' }));
  await screen.findByRole('option', { name: 'New category' });
  assert.equal(summaryRequests, 2);
  assert.equal(screen.queryByText('Catalog summary temporarily unavailable'), null);
  assert.equal(document.querySelector('.catalog-context strong').textContent, '3');
  assert.equal(api.calls.filter(call => call.path === '/api/catalog').length, 2);
  assert.equal(api.calls.some(call => call.method !== 'GET'), false);
});

test('catalog returns to the last available page when a refresh reduces the product count', async () => {
  const api = installApi(); const user = userEvent.setup(); const requests = []; let total = 30;
  api.on('GET', '/api/catalog', ({ url }) => {
    const offset = Number(url.searchParams.get('offset'));
    requests.push(offset);
    return reply({ items: offset < total ? products : [], total });
  });
  render(<CatalogPage />);
  await screen.findByRole('button', { name: 'Inspect Tea pack' });
  await user.click(screen.getByRole('button', { name: 'Next' }));
  await screen.findByText('26–30 of 30 products');
  total = 10;
  await user.click(screen.getByRole('button', { name: 'Refresh catalog' }));
  await screen.findByText('1–10 of 10 products');
  await waitFor(() => assert.deepEqual(requests, [0, 25, 25, 0]));
  assert.ok(screen.getByRole('button', { name: 'Previous' }).disabled);
  assert.ok(screen.getByRole('button', { name: 'Next' }).disabled);
  assert.ok(screen.getByRole('button', { name: 'Inspect Tea pack' }));
});

test('missing margin centers render as unavailable without passing missing values to the percent formatter', () => {
  render(<ForecastBands forecast={{ margin_rate: { lower: 0.2, upper: 0.4 } }} />);
  assert.equal(document.querySelector('.distribution-heading strong').textContent, '—');
  assert.ok(screen.getByText('Interval unavailable'));
  assert.equal(screen.queryByRole('img'), null);
  assert.equal(screen.queryByText('—%'), null);
  assert.equal(screen.queryByText('0%'), null);
});
