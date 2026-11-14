import { useState } from 'react';
import { ArrowRight, ArrowUpRight, BarChart3, Boxes, CheckCircle2, Circle, Database, FlaskConical, Layers3, RefreshCw, ShieldCheck, Sparkles, TrendingUp } from 'lucide-react';
import { Link } from 'react-router-dom';
import { number, timestamp } from '../api/client';
import type { CatalogSummary, Health, PricingRun } from '../api/types';
import { useResource } from '../api/useResource';
import { EmptyState, ErrorNotice, PageHeading, Status } from '../components/Common';
import { Dashboard } from './Dashboard';
import './overview.css';

const stages = [
  { label: 'Data', icon: Database, title: 'Start with the evidence.', text: 'Read current Commerce data and retrieve relevant, versioned documents.' },
  { label: 'Quantify', icon: BarChart3, title: 'Make uncertainty visible.', text: 'Estimate elasticity and simulate candidate prices using the shared numerical engine.' },
  { label: 'Strategy', icon: Sparkles, title: 'Understand the reasoning.', text: 'Grounded reasoning explains the computed recommendation with source citations.' },
  { label: 'Validate', icon: ShieldCheck, title: 'Check every constraint.', text: 'Compliance, stability, and approval policy determine how a recommendation can proceed.' },
  { label: 'Execute', icon: CheckCircle2, title: 'Keep execution accountable.', text: 'Only eligible, approved changes reach Commerce through the audited dispatcher.' },
];

export function OverviewPage({ health, refreshHealth }: { health?: Health; refreshHealth: () => void }) {
  const summary = useResource<CatalogSummary>('/catalog/summary');
  const runs = useResource<{ items: PricingRun[] }>('/runs');
  const [activeStage, setActiveStage] = useState(0);
  const commerceReady = health?.commerce?.status === 'ok';
  function refresh() { summary.reload(); runs.reload(); refreshHealth(); }
  const stage = stages[activeStage];
  return <div className="overview-page">
    <PageHeading eyebrow="A CLEARER VIEW OF YOUR BUSINESS" title="Pricing overview" action={<button className="button secondary" onClick={refresh} aria-label="Refresh workspace"><RefreshCw size={15} />Refresh workspace</button>}>Your products, decisions, and evidence. All moving together.</PageHeading>
    <section className="overview-hero">
      <div className="hero-copy"><span className="hero-kicker"><span />YOUR NEXT MOVE, INFORMED</span><h2>Better decisions.<br /><span>Every price.</span></h2><p>Turn your retail data into pricing possibilities. Explore the upside, understand the uncertainty, and review with confidence.</p><div className="hero-actions"><Link className="button primary" to="/runs"><TrendingUp size={16} />New pricing run<ArrowUpRight size={15} /></Link><Link className="hero-secondary" to="/simulation">Explore scenarios<ArrowRight size={15} /></Link></div><div className="hero-footnote"><ShieldCheck size={14} />Evidence-led analysis. Governed execution.</div></div>
      <div className="hero-workflow"><div className="workflow-caption"><span className="workflow-caption-icon"><Layers3 size={16} /></span><div><strong>From evidence to action</strong><small>Explore the five-stage grounded workflow</small></div><span className="workflow-caption-badge">5 stages</span></div><div className="workflow-map" aria-label="Explore pricing workflow stages">{stages.map((item, index) => <button key={item.label} className={`workflow-stage ${index === activeStage ? 'selected' : ''}`} aria-pressed={index === activeStage} onClick={() => setActiveStage(index)} aria-label={`Explore ${item.label} stage`}><span className="workflow-number">0{index + 1}</span><span className="workflow-stage-icon"><item.icon size={21} /></span><strong>{item.label}</strong></button>)}</div><div className="workflow-explanation" key={activeStage}><span>0{activeStage + 1} / 05</span><h3>{stage.title}</h3><p>{stage.text}</p></div><span className="workflow-note">Workflow illustration · select a stage to explore</span></div>
    </section>
    {summary.error && <ErrorNotice message={summary.error} />}
    <div className="metric-grid portfolio-metrics">
      <div className="metric-card"><div className="metric-label">Products in catalog<span className="metric-icon blue"><Boxes size={17} /></span></div><strong>{number(summary.data?.sku_count)}</strong><span>Available for SKU-level analysis</span></div>
      <div className="metric-card"><div className="metric-label">Categories<span className="metric-icon violet"><BarChart3 size={17} /></span></div><strong>{number(summary.data?.categories?.length)}</strong><span>Your distinct product portfolios</span></div>
      <div className="metric-card"><div className="metric-label">Inventory units<span className="metric-icon mint"><Database size={17} /></span></div><strong>{number(summary.data?.inventory_units)}</strong><span>Current Commerce inventory</span></div>
      <div className="metric-card"><div className="metric-label">Operating mode<span className="metric-icon amber"><ShieldCheck size={17} /></span></div><strong className="metric-word" style={{ textTransform: 'capitalize' }}>{health?.mode || 'Unavailable'}</strong><span>Current server operating mode</span></div>
    </div>
    <div className="section-heading"><div><span className="eyebrow">THE BIG PICTURE</span><h2>Decision intelligence</h2></div><span className="section-heading-note"><span className="status-dot" />Server-reported metrics</span></div>
    <Dashboard />
    <div className="overview-grid">
      <section className="panel recent-runs"><div className="panel-heading"><div><h2>Recent pricing runs</h2><p>Your latest analyses and grounded workflows</p></div><Link className="panel-link" to="/runs">View all<ArrowUpRight size={15} /></Link></div>
        {runs.error ? <div className="panel-body"><ErrorNotice message={runs.error} /></div> : runs.data?.items?.length ? <div className="run-list">{runs.data.items.slice(0, 5).map(run => <Link key={run.id} to={`/runs?id=${encodeURIComponent(run.id)}`} className="run-list-item"><span className="run-icon"><BarChart3 size={18} /></span><div><strong>Run {run.id.slice(0, 8)}</strong><small>{timestamp(run.created_at)}</small></div><Status status={run.status} /><ArrowRight size={15} /></Link>)}</div> : <EmptyState icon={<BarChart3 size={31} />} title={runs.loading ? 'Loading run history' : 'Your first run starts here'}><p>Choose a category to estimate price response and compare possible outcomes.</p><Link className="text-link" to="/runs">Create a pricing run<ArrowRight size={15} /></Link></EmptyState>}
      </section>
      <section className="panel readiness-panel"><div className="panel-heading"><div><h2>Workspace readiness</h2><p>Know what is connected before you start.</p></div><span className="readiness-symbol"><ShieldCheck size={19} /></span></div><div className="readiness-list">
        <div>{commerceReady ? <CheckCircle2 className="positive" size={19} /> : <Circle size={19} />}<span><strong>Commerce data</strong><small>{commerceReady ? 'Connected over HTTP' : 'Service unavailable'}</small></span><Status status={commerceReady ? 'ok' : 'unavailable'} /></div>
        <div>{health?.capabilities?.quantitative_preview ? <CheckCircle2 className="positive" size={19} /> : <Circle size={19} />}<span><strong>Quantitative engine</strong><small>Regression, simulation, optimization</small></span></div>
        <div>{health?.capabilities?.grounded_recommendations ? <CheckCircle2 className="positive" size={19} /> : <Circle size={19} />}<span><strong>Grounded agents</strong><small>{health?.capabilities?.grounded_recommendations ? 'Five-stage cited pricing workflow' : 'Configure the gateway and index required evidence'}</small></span></div>
        <div><ShieldCheck size={19} /><span><strong>Price execution</strong><small>Compliance and approval checked before dispatch</small></span><Link className="panel-link" to="/review">Review<ArrowUpRight size={13} /></Link></div>
      </div></section>
    </div>
    <div className="quick-launch-grid"><Link to="/catalog" className="quick-launch"><span className="quick-launch-icon"><Boxes size={22} /></span><div><h3>Know your portfolio</h3><p>Explore current prices and product constraints.</p></div><ArrowUpRight size={18} /></Link><Link to="/simulation" className="quick-launch"><span className="quick-launch-icon mint"><FlaskConical size={22} /></span><div><h3>Explore a what-if</h3><p>Test candidate prices before making a decision.</p></div><ArrowUpRight size={18} /></Link></div>
  </div>;
}
