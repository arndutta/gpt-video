import { useCallback, useEffect, useState } from 'react';
import { ArrowLeft, ArrowRight, ArrowUpRight, Boxes, Grid2X2, List, Package, RefreshCw, Search, ShieldCheck, X } from 'lucide-react';
import { money, number } from '../api/client';
import type { CatalogSummary, Envelope, Product } from '../api/types';
import { useResource } from '../api/useResource';
import { Drawer, EmptyState, ErrorNotice, Loading, PageHeading } from '../components/Common';
import './catalog.css';

export function CatalogPage() {
  const [search, setSearch] = useState('');
  const [query, setQuery] = useState('');
  const [category, setCategory] = useState('');
  const [offset, setOffset] = useState(0);
  const [view, setView] = useState<'table' | 'grid'>('table');
  const [sort, setSort] = useState('default');
  const [selected, setSelected] = useState<Product>();
  const closeDetail = useCallback(() => setSelected(undefined), []);
  useEffect(() => { const timer = window.setTimeout(() => { setQuery(search); setOffset(0); }, 250); return () => window.clearTimeout(timer); }, [search]);
  const params = new URLSearchParams({ limit: '25', offset: String(offset) });
  if (query) params.set('q', query);
  if (category) params.set('category', category);
  const catalog = useResource<Envelope<Product>>(`/catalog?${params}`);
  const summary = useResource<CatalogSummary>('/catalog/summary');
  function refresh() { catalog.reload(); summary.reload(); }
  useEffect(() => {
    if (!catalog.loading && catalog.data && offset > 0 && offset >= catalog.data.total) {
      setOffset(Math.max(0, Math.ceil(catalog.data.total / 25) - 1) * 25);
    }
  }, [catalog.loading, catalog.data, offset]);
  const items = [...(catalog.data?.items || [])];
  if (sort === 'name') items.sort((a, b) => a.name.localeCompare(b.name));
  if (sort === 'price-low') items.sort((a, b) => Number(a.current_price) - Number(b.current_price));
  if (sort === 'price-high') items.sort((a, b) => Number(b.current_price) - Number(a.current_price));
  const total = catalog.data?.total || 0;
  return <div className="catalog-page">
    <PageHeading eyebrow="YOUR RETAIL PORTFOLIO" title="Product catalog" action={<button className="button secondary" onClick={refresh}><RefreshCw size={15} />Refresh catalog</button>}>Explore your products, current prices, and the boundaries behind every decision.</PageHeading>
    <div className="catalog-context"><span><span className="catalog-context-icon"><Package size={21} /></span><span><strong>{number(summary.data?.sku_count)}</strong><small>products in your portfolio</small></span></span><span><Boxes size={16} /><strong>{number(summary.data?.categories?.length)}</strong> categories</span><span><ShieldCheck size={16} />Commerce is the source of record</span></div>
    {summary.error && <ErrorNotice message={summary.error} />}
    <section className="panel">
      <div className="table-toolbar catalog-toolbar"><div className="search-field"><Search size={17} /><input aria-label="Search products" placeholder="Find a product or SKU…" value={search} onChange={event => setSearch(event.target.value)} /></div><select aria-label="Filter by category" value={category} onChange={event => { setCategory(event.target.value); setOffset(0); }}><option value="">All categories</option>{summary.data?.categories?.map(item => <option key={item.name} value={item.name}>{item.name}</option>)}</select><div className="catalog-view-toggle" role="group" aria-label="Catalog view"><button aria-label="Table view" title="Table view" aria-pressed={view === 'table'} onClick={() => setView('table')}><List size={17} /></button><button aria-label="Grid view" title="Grid view" aria-pressed={view === 'grid'} onClick={() => setView('grid')}><Grid2X2 size={16} /></button></div></div>
      <div className="catalog-results-heading"><span>{catalog.loading ? 'Loading products…' : `${number(total)} matching products`}{(query || category) && <button className="catalog-clear" onClick={() => { setSearch(''); setQuery(''); setCategory(''); setOffset(0); }}><X size={12} />Clear filters</button>}</span><label>Sort current page<select aria-label="Sort current page" value={sort} onChange={event => setSort(event.target.value)}><option value="default">Default order</option><option value="name">Name A–Z</option><option value="price-low">Price: low to high</option><option value="price-high">Price: high to low</option></select></label></div>
      {catalog.error && <div className="panel-body"><ErrorNotice message={catalog.error} /></div>}
      {catalog.loading ? <Loading label="Loading Commerce catalog…" /> : items.length ? view === 'grid' ? <div className="catalog-product-grid">{items.map(product => <article className="catalog-product-card" key={product.sku}><div className="product-card-top"><span className="product-card-icon"><Package size={26} /></span><span className="category-label">{product.category}</span></div><h2>{product.name}</h2><small>{product.sku}</small><div className="product-card-price"><strong>{money(product.current_price, product.currency)}</strong><span>Current price</span></div><div className="product-card-bounds"><span>MAP floor<strong>{money(product.map_price, product.currency)}</strong></span><span>Unit cost<strong>{money(product.cost, product.currency)}</strong></span></div><button className="product-inspect" onClick={() => setSelected(product)} aria-label={`Inspect ${product.name}`}>Inspect product<ArrowUpRight size={15} /></button></article>)}</div> : <div className="table-scroll"><table><thead><tr><th>Product</th><th>Category</th><th className="numeric">Current price</th><th className="numeric">Unit cost</th><th className="numeric">MAP floor</th><th className="numeric">Price bounds</th><th className="numeric">Version</th></tr></thead><tbody>{items.map(product => <tr key={product.sku}><td><button className="product-cell product-open" onClick={() => setSelected(product)} aria-label={`Inspect ${product.name}`}><span className="product-icon"><Boxes size={17} /></span><span><strong>{product.name}</strong><small>{product.sku}</small></span></button></td><td><span className="category-label">{product.category}</span></td><td className="numeric price-cell">{money(product.current_price, product.currency)}</td><td className="numeric">{money(product.cost, product.currency)}</td><td className="numeric">{money(product.map_price, product.currency)}</td><td className="numeric muted">{money(product.min_price, product.currency)} – {money(product.max_price, product.currency)}</td><td className="numeric muted">v{product.price_version}</td></tr>)}</tbody></table></div> : !catalog.error && <EmptyState icon={<Boxes size={30} />} title="No products found"><p>{query || category ? 'Try a different search or category.' : 'Connect a populated Commerce catalog to begin analysis.'}</p></EmptyState>}
      <div className="table-footer"><span>{total ? `${offset + 1}–${Math.min(offset + 25, total)} of ${number(total)} products` : '0 products'}</span><div><button className="button secondary small-button" disabled={offset === 0 || catalog.loading} onClick={() => setOffset(value => Math.max(0, value - 25))}><ArrowLeft size={15} />Previous</button><button className="button secondary small-button" disabled={offset + 25 >= total || catalog.loading} onClick={() => setOffset(value => value + 25)}>Next<ArrowRight size={15} /></button></div></div>
    </section>
    <div className="notice info"><ShieldCheck size={17} /><span>Explore freely. This catalog is read-only; current prices change only through the governed execution workflow.</span></div>
    {selected && <Drawer title={selected.name} subtitle={`${selected.sku} · ${selected.category}`} onClose={closeDetail}><div className="drawer-body"><div className="catalog-detail-price"><span>Current Commerce price</span><strong>{money(selected.current_price, selected.currency)}</strong><small>Price version {selected.price_version}</small></div><h3>Price constraints</h3><div className="mini-metrics"><div><span>MAP floor</span><strong>{money(selected.map_price, selected.currency)}</strong></div><div><span>Unit cost</span><strong>{money(selected.cost, selected.currency)}</strong></div><div><span>Minimum price</span><strong>{money(selected.min_price, selected.currency)}</strong></div><div><span>Maximum price</span><strong>{money(selected.max_price, selected.currency)}</strong></div></div><h3>Product family</h3><dl className="evidence-list"><div><dt>Family</dt><dd>{selected.family_id}</dd></div><div><dt>Size</dt><dd>{number(selected.size)}</dd></div><div><dt>Currency</dt><dd>{selected.currency}</dd></div></dl><div className="notice info"><ShieldCheck size={17} /><span>This is a read-only snapshot from the current catalog page. Refresh the catalog to load updated Commerce values.</span></div></div></Drawer>}
  </div>;
}
