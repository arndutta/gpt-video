import { useEffect, useState } from 'react';
import { ArrowLeft, ArrowRight, Boxes, RefreshCw, Search } from 'lucide-react';
import { money, number } from '../api/client';
import type { CatalogSummary, Envelope, Product } from '../api/types';
import { useResource } from '../api/useResource';
import { EmptyState, ErrorNotice, Loading, PageHeading } from '../components/Common';

export function CatalogPage() {
  const [search, setSearch] = useState('');
  const [query, setQuery] = useState('');
  const [category, setCategory] = useState('');
  const [offset, setOffset] = useState(0);
  useEffect(() => { const timer = window.setTimeout(() => { setQuery(search); setOffset(0); }, 250); return () => window.clearTimeout(timer); }, [search]);
  const params = new URLSearchParams({ limit: '25', offset: String(offset) });
  if (query) params.set('q', query);
  if (category) params.set('category', category);
  const catalog = useResource<Envelope<Product>>(`/catalog?${params}`);
  const summary = useResource<CatalogSummary>('/catalog/summary');
  const items = catalog.data?.items || [];
  const total = catalog.data?.total || 0;
  return <>
    <PageHeading eyebrow="COMMERCE DATA" title="Product catalog" action={<button className="button secondary" onClick={catalog.reload}><RefreshCw size={16} />Refresh catalog</button>}>Current prices and product constraints from the Commerce system of record.</PageHeading>
    <section className="panel">
      <div className="table-toolbar"><div className="search-field"><Search size={17} /><input aria-label="Search products" placeholder="Search name or SKU…" value={search} onChange={event => setSearch(event.target.value)} /></div><select aria-label="Filter by category" value={category} onChange={event => { setCategory(event.target.value); setOffset(0); }}><option value="">All categories</option>{summary.data?.categories?.map(item => <option key={item.name} value={item.name}>{item.name}</option>)}</select><span className="toolbar-count">{number(total)} products</span></div>
      {catalog.error && <div className="panel-body"><ErrorNotice message={catalog.error} /></div>}
      {catalog.loading ? <Loading label="Loading Commerce catalog…" /> : items.length ? <div className="table-scroll"><table><thead><tr><th>Product</th><th>Category</th><th className="numeric">Current price</th><th className="numeric">Unit cost</th><th className="numeric">MAP floor</th><th className="numeric">Price bounds</th><th className="numeric">Version</th></tr></thead><tbody>{items.map(product => <tr key={product.sku}><td><div className="product-cell"><span className="product-icon"><Boxes size={17} /></span><div><strong>{product.name}</strong><small>{product.sku}</small></div></div></td><td><span className="category-label">{product.category}</span></td><td className="numeric price-cell">{money(product.current_price, product.currency)}</td><td className="numeric">{money(product.cost, product.currency)}</td><td className="numeric">{money(product.map_price, product.currency)}</td><td className="numeric muted">{money(product.min_price, product.currency)} – {money(product.max_price, product.currency)}</td><td className="numeric muted">v{product.price_version}</td></tr>)}</tbody></table></div> : !catalog.error && <EmptyState icon={<Boxes size={30} />} title="No products found"><p>{query || category ? 'Try a different search or category.' : 'Connect a populated Commerce catalog to begin analysis.'}</p></EmptyState>}
      <div className="table-footer"><span>{total ? `${offset + 1}–${Math.min(offset + 25, total)} of ${number(total)} products` : '0 products'}</span><div><button className="button secondary small-button" disabled={offset === 0 || catalog.loading} onClick={() => setOffset(value => Math.max(0, value - 25))}><ArrowLeft size={15} />Previous</button><button className="button secondary small-button" disabled={offset + 25 >= total || catalog.loading} onClick={() => setOffset(value => value + 25)}>Next<ArrowRight size={15} /></button></div></div>
    </section>
    <div className="notice info"><Boxes size={18} /><span>This view is read-only. Analysis previews cannot change the live price book.</span></div>
  </>;
}
