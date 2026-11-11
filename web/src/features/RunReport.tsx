import { useCallback, useState } from 'react';
import { ArrowUpRight, CircleCheck, Search, ShieldAlert } from 'lucide-react';
import { money, number } from '../api/client';
import type { PreviewResult, Recommendation } from '../api/types';
import { Drawer, EmptyState } from '../components/Common';
import { RecommendationEvidence, StructuredEvidence } from '../components/Forecast';
import { BandBadge } from './RecommendationDrawer';
import { Link } from 'react-router-dom';
import { EvidenceSources } from '../components/EvidenceSources';

type Quality = { status?: string; blocked?: boolean; checks?: { check?: string; severity?: string; affected_records?: number; message?: string }[] };

export function RunReport({ result }: { result: PreviewResult }) {
  const [search, setSearch] = useState('');
  const [selected, setSelected] = useState<Recommendation>();
  const closeDetails = useCallback(() => setSelected(undefined), []);
  const allItems = result.recommendations || [];
  const items = allItems.filter(item => `${item.sku} ${item.name || ''} ${item.category || ''}`.toLowerCase().includes(search.toLowerCase()));
  const quality = result.quality && typeof result.quality === 'object' ? result.quality as Quality : undefined;
  const warnings = quality?.checks?.filter(check => check.severity !== 'info' && check.severity !== 'pass');
  const confidence = allItems.length ? allItems.reduce((sum, item) => sum + item.confidence, 0) / allItems.length : undefined;
  const grounded = allItems.some(item => typeof item.band === 'string') || result.type === 'grounded_recommendations' || result.kind === 'grounded';
  return <div className="report-content">
    {quality && <div className={`quality-strip ${quality.blocked ? 'blocked' : ''}`}><div>{quality.blocked ? <ShieldAlert size={18} /> : <CircleCheck size={18} />}<strong>Data quality: {quality.status || (quality.blocked ? 'blocked' : 'evaluated')}</strong><span>{quality.checks?.length || 0} checks recorded</span></div>{warnings?.length ? <details><summary>Inspect quality findings</summary><ul>{warnings.map((check, index) => <li key={index}><strong>{check.check?.replaceAll('_', ' ')}</strong> — {check.message} <span className="muted">({number(check.affected_records)} records)</span></li>)}</ul></details> : null}</div>}
    <div className="report-summary"><div><span>{grounded ? 'Recommendations' : 'Candidate previews'}</span><strong>{number(allItems.length)}</strong></div><div><span>Mean confidence</span><strong>{confidence == null ? '—' : `${number(confidence * 100, 1)}%`}</strong></div><div><span>Skipped SKUs</span><strong>{number(result.skipped?.length || 0)}</strong></div><div><span>{grounded ? 'Decisions' : 'Execution'}</span><strong className="small-word">{grounded ? <Link to="/review" className="positive">Review queue</Link> : 'Disabled'}</strong></div></div>
    <div className="table-toolbar"><div><h3>Price candidates</h3><p className="small muted">Select a SKU to inspect distributions and assumptions.</p></div><div className="search-field compact"><Search size={16} /><input aria-label="Filter preview candidates" value={search} onChange={event => setSearch(event.target.value)} placeholder="Filter candidates…" /></div></div>
    {items.length ? <div className="table-scroll"><table className="recommendation-table"><thead><tr><th>Product</th><th className="numeric">Current</th><th className="numeric">{grounded ? 'Proposed' : 'Preview'}</th><th className="numeric">Change</th><th className="numeric">Confidence</th>{grounded && <th>Band</th>}<th /></tr></thead><tbody>{items.map(item => <tr key={item.sku}><td><button className="product-detail-link" onClick={() => setSelected(item)}><strong>{item.name || item.sku}</strong><small>{item.sku} · {item.category || 'SKU'}</small></button></td><td className="numeric">{money(item.current_price, item.currency)}</td><td className="numeric price-cell">{money(item.proposed_price, item.currency)}</td><td className={`numeric ${item.delta_pct > 0 ? 'positive' : ''}`}>{item.delta_pct > 0 ? '+' : ''}{number(item.delta_pct, 1)}%</td><td className="numeric"><div className="confidence-cell"><span>{number(item.confidence * 100, 1)}%</span><span className="confidence-track"><span style={{ width: `${Math.min(100, Math.max(0, item.confidence * 100))}%` }} /></span></div></td>{grounded && <td><BandBadge band={String(item.band || '')} /></td>}<td><button className="icon-button" onClick={() => setSelected(item)} aria-label={`Inspect ${item.sku}`}><ArrowUpRight size={17} /></button></td></tr>)}</tbody></table></div> : <EmptyState title="No price candidates"><p>{search ? 'No products match this filter.' : 'Inspect quality findings and skipped SKUs for more detail.'}</p></EmptyState>}
    {!!result.skipped?.length && <details className="report-details"><summary>{number(result.skipped.length)} SKUs were skipped</summary><StructuredEvidence value={result.skipped} /></details>}
    {result.configuration && <details className="report-details"><summary>Simulation configuration and reproducibility</summary><StructuredEvidence value={result.configuration} /></details>}
    {grounded && ['data_narrative', 'quantitative_narrative', 'validation_narrative'].map(key => result[key] ? <details className="report-details" key={key}><summary>{key.replaceAll('_', ' ')}</summary><StructuredEvidence value={result[key]} /><EvidenceSources value={result[key]} /></details> : null)}
    <p className="report-footnote">{grounded ? 'This report retains run evidence. Open the review queue for current recommendation revisions, decisions, and Commerce outcomes.' : 'Preview prices are read-only analytical candidates. Start a grounded pricing workflow for cited reasoning and compliance review.'}</p>
    {selected && <Drawer title={selected.name || selected.sku} subtitle={`${selected.sku} · Candidate evidence`} onClose={closeDetails}><RecommendationEvidence item={selected} /></Drawer>}
  </div>;
}
