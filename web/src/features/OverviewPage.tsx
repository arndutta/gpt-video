import { ArrowRight, BarChart3, Boxes, CheckCircle2, Circle, Database, RefreshCw, ShieldCheck, TrendingUp } from 'lucide-react';
import { Link } from 'react-router-dom';
import { number, timestamp } from '../api/client';
import type { CatalogSummary, Health, PricingRun } from '../api/types';
import { useResource } from '../api/useResource';
import { EmptyState, ErrorNotice, PageHeading, Status } from '../components/Common';

export function OverviewPage({ health, refreshHealth }: { health?: Health; refreshHealth: () => void }) {
  const summary = useResource<CatalogSummary>('/catalog/summary');
  const runs = useResource<{ items: PricingRun[] }>('/runs');
  const commerceReady = health?.commerce?.status === 'ok';
  function refresh() { summary.reload(); runs.reload(); refreshHealth(); }
  return <>
    <PageHeading eyebrow="YOUR PRICING WORKSPACE" title="Pricing overview" action={<Link className="button primary" to="/runs"><TrendingUp size={17} />New pricing preview</Link>}>Explore your catalog, test a price, and understand the uncertainty behind it.</PageHeading>
    {summary.error && <ErrorNotice message={summary.error} />}
    <div className="metric-grid">
      <div className="metric-card"><div className="metric-label">Products in catalog<Boxes size={17} /></div><strong>{number(summary.data?.sku_count)}</strong><span>Available for SKU-level analysis</span></div>
      <div className="metric-card"><div className="metric-label">Categories<BarChart3 size={17} /></div><strong>{number(summary.data?.categories?.length)}</strong><span>Distinct product portfolios</span></div>
      <div className="metric-card"><div className="metric-label">Inventory units<Database size={17} /></div><strong>{number(summary.data?.inventory_units)}</strong><span>Current Commerce inventory</span></div>
      <div className="metric-card"><div className="metric-label">Operating mode<ShieldCheck size={17} /></div><strong className="metric-word">Supervised</strong><span>Automatic price changes disabled</span></div>
    </div>
    <div className="overview-grid">
      <section className="panel">
        <div className="panel-heading"><div><h2>Recent pricing runs</h2><p>A history of your quantitative previews</p></div><button className="icon-button" onClick={refresh} aria-label="Refresh workspace"><RefreshCw size={17} /></button></div>
        {runs.error ? <div className="panel-body"><ErrorNotice message={runs.error} /></div> : runs.data?.items?.length ? <div className="run-list">{runs.data.items.slice(0, 5).map(run => <Link key={run.id} to={`/runs?id=${encodeURIComponent(run.id)}`} className="run-list-item"><span className="run-icon"><BarChart3 size={19} /></span><div><strong>Preview {run.id.slice(0, 8)}</strong><small>{timestamp(run.created_at)}</small></div><Status status={run.status} /><ArrowRight size={16} /></Link>)}</div> : <EmptyState icon={<BarChart3 size={31} />} title={runs.loading ? 'Loading run history' : 'Your first preview starts here'}><p>Choose a category to estimate price response and compare uncertain outcomes.</p><Link className="text-link" to="/runs">Create a pricing preview <ArrowRight size={15} /></Link></EmptyState>}
      </section>
      <section className="panel readiness-panel"><div className="panel-heading"><div><h2>Workspace readiness</h2><p>What is available in this build</p></div></div><div className="readiness-list">
        <div>{commerceReady ? <CheckCircle2 className="positive" size={20} /> : <Circle size={20} />}<span><strong>Commerce data</strong><small>{commerceReady ? 'Connected over HTTP' : 'Service unavailable'}</small></span><Status status={commerceReady ? 'ok' : 'unavailable'} /></div>
        <div>{health?.capabilities?.quantitative_preview ? <CheckCircle2 className="positive" size={20} /> : <Circle size={20} />}<span><strong>Quantitative engine</strong><small>Regression, simulation, optimization</small></span></div>
        <div><Circle size={20} /><span><strong>Grounded agents</strong><small>Planned for orchestration milestone</small></span><span className="small muted">Pending</span></div>
        <div><ShieldCheck size={20} /><span><strong>Price execution</strong><small>No approvals or automatic writes</small></span><span className="small muted">Disabled</span></div>
      </div></section>
    </div>
    <section className="method-panel"><div className="method-intro"><span className="section-label">THE ANALYSIS PATH</span><h2>Every forecast starts with the data.</h2><p>Three deterministic steps make a preview reproducible and its uncertainty visible.</p></div><div className="method-steps"><div><span>01</span><strong>Estimate elasticity</strong><p>Learn price response from observed SKU history.</p></div><ArrowRight size={18} /><div><span>02</span><strong>Model uncertainty</strong><p>Sample elasticity, costs, seasonality, and competitors.</p></div><ArrowRight size={18} /><div><span>03</span><strong>Compare prices</strong><p>Evaluate forecast distributions within constraints.</p></div></div></section>
  </>;
}
