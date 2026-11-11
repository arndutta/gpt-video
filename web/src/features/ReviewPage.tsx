import { useCallback, useMemo, useState } from 'react';
import { Check, ClipboardCheck, RefreshCw } from 'lucide-react';
import { api, errorMessage, money, number } from '../api/client';
import { canBulkApprove } from '../api/operations';
import type { ManagedRecommendation } from '../api/operations';
import { usePolling } from '../api/usePolling';
import { EmptyState, ErrorNotice, Loading, PageHeading, Status } from '../components/Common';
import { BandBadge, RecommendationDrawer } from './RecommendationDrawer';

type Queue = { items: ManagedRecommendation[]; bulk_confidence_threshold?: number; total?: number };

export function ReviewPage() {
  const queue = usePolling<Queue>('/recommendations', 3000);
  const policy = usePolling<{ version: number; thresholds: { bulk_confidence_threshold: number } }>('/policy', 5000);
  const [selectedId, setSelectedId] = useState('');
  const [checked, setChecked] = useState<string[]>([]);
  const [search, setSearch] = useState('');
  const [band, setBand] = useState('');
  const [category, setCategory] = useState('');
  const [status, setStatus] = useState('');
  const [compliance, setCompliance] = useState('');
  const [confidence, setConfidence] = useState('');
  const [delta, setDelta] = useState('');
  const [sort, setSort] = useState('impact');
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [busy, setBusy] = useState(false);
  const close = useCallback(() => setSelectedId(''), []);
  const items = useMemo(() => queue.data?.items ?? [], [queue.data]);
  const threshold = policy.data?.thresholds.bulk_confidence_threshold ?? queue.data?.bulk_confidence_threshold ?? 0.8;
  const bulkUnavailable = !!queue.error || !!policy.error || !policy.data;
  const filtered = useMemo(() => items.filter(item => `${item.sku} ${item.name || ''}`.toLowerCase().includes(search.toLowerCase()) && (!band || item.band === band) && (!category || item.category === category) && (!status || item.status === status) && (!compliance || item.compliance_status === compliance) && (!confidence || item.confidence * 100 >= Number(confidence)) && (!delta || Math.abs(item.delta_pct) <= Number(delta))).sort((a, b) => sort === 'confidence' ? b.confidence - a.confidence : sort === 'delta' ? Math.abs(b.delta_pct) - Math.abs(a.delta_pct) : sort === 'category' ? (a.category || '').localeCompare(b.category || '') : sort === 'band' ? ['escalate', 'review', 'auto_approve'].indexOf(a.band) - ['escalate', 'review', 'auto_approve'].indexOf(b.band) : impact(b) - impact(a)), [items, search, band, category, status, compliance, confidence, delta, sort]);
  const eligible = checked.map(id => items.find(item => item.id === id)).filter((item): item is ManagedRecommendation => !!item && canBulkApprove(item, threshold));
  const selected = items.find(item => item.id === selectedId);
  const categories = [...new Set(items.map(item => item.category).filter((value): value is string => !!value))].sort();
  async function bulk() {
    if (!eligible.length || policy.error || !policy.data) return;
    setBusy(true); setError(''); setNotice('');
    try { await api('/recommendations/bulk', { method: 'POST', body: JSON.stringify({ ids: eligible.map(item => item.id), expected_revisions: Object.fromEntries(eligible.map(item => [item.id, item.revision])) }) }); setChecked([]); queue.reload(); setNotice('Bulk review decisions acknowledged. Execution outcomes are updated in the queue.'); }
    catch (failure) { setError(errorMessage(failure)); }
    finally { setBusy(false); }
  }
  return <>
    <PageHeading eyebrow="HUMAN AND AUTOMATIC DECISIONS" title="Review queue" action={<button className="button secondary" onClick={queue.reload}><RefreshCw size={16} />Refresh</button>}>Inspect recommendations, compliance evidence, and the decisions behind every price change.</PageHeading>
    {(queue.error || error) && <ErrorNotice message={error || queue.error} />}{notice && <p className="notice info" role="status">{notice}</p>}
    {policy.error && <ErrorNotice message={`Decision policy unavailable. Refresh before bulk approval. ${policy.error}`} />}
    <section className="panel"><div className="review-filters"><label>Find product<input value={search} onChange={event => setSearch(event.target.value)} placeholder="Name or SKU" /></label><label>Band<select value={band} onChange={event => setBand(event.target.value)}><option value="">All bands</option><option value="auto_approve">Auto-approve</option><option value="review">Review</option><option value="escalate">Escalate</option></select></label><label>Category<select value={category} onChange={event => setCategory(event.target.value)}><option value="">All categories</option>{categories.map(value => <option key={value}>{value}</option>)}</select></label><label>Disposition<select value={status} onChange={event => setStatus(event.target.value)}><option value="">All decisions</option>{[...new Set(items.map(item => item.status))].sort().map(value => <option key={value} value={value}>{value.replaceAll('_', ' ')}</option>)}</select></label><label>Compliance<select value={compliance} onChange={event => setCompliance(event.target.value)}><option value="">All verdicts</option><option value="passed">Passed</option><option value="failed">Failed</option></select></label><label>Minimum confidence (%)<input type="number" min="0" max="100" value={confidence} onChange={event => setConfidence(event.target.value)} placeholder="Any confidence" /></label><label>Maximum absolute change (%)<input type="number" min="0" value={delta} onChange={event => setDelta(event.target.value)} placeholder="Any change" /></label><label>Sort by<select value={sort} onChange={event => setSort(event.target.value)}><option value="impact">Forecast revenue impact</option><option value="confidence">Confidence</option><option value="delta">Absolute price change</option><option value="band">Escalate first</option><option value="category">Category</option></select></label></div>
      <div className="review-actions"><button className="button secondary small-button" onClick={() => setChecked(filtered.filter(item => canBulkApprove(item, threshold)).map(item => item.id))} disabled={busy || bulkUnavailable}>Select eligible Review items</button><button className="button primary small-button" onClick={() => void bulk()} disabled={busy || bulkUnavailable || !eligible.length}><Check size={13} />{busy ? 'Approving…' : `Approve ${eligible.length || ''} selected`}</button>{!!checked.length && <button className="text-link" style={{ margin: 0 }} onClick={() => setChecked([])}>Clear</button>}<span className="muted">{filtered.length} of {items.length} loaded · bulk threshold {number(threshold * 100)}%</span></div>
      {queue.loading && !queue.data ? <Loading label="Loading recommendation queue…" /> : filtered.length ? <div className="table-scroll"><table className="review-table"><thead><tr><th aria-label="Select for bulk review" /><th>Product</th><th>Band & decision</th><th className="numeric">Current → proposed</th><th className="numeric">Change</th><th className="numeric">Confidence</th><th>Compliance</th></tr></thead><tbody>{filtered.map(item => <tr key={item.id}><td><input className="selection-checkbox" type="checkbox" aria-label={`Select ${item.sku} for bulk review`} disabled={!canBulkApprove(item, threshold) || busy || bulkUnavailable} checked={checked.includes(item.id)} onChange={event => setChecked(ids => event.target.checked ? [...ids, item.id] : ids.filter(id => id !== item.id))} /></td><td><button className="product-detail-link" onClick={() => setSelectedId(item.id)}><strong>{item.name || item.sku}</strong><small>{item.sku} · {item.category} · v{item.revision}</small></button></td><td><BandBadge band={item.band} /><div style={{ marginTop: 6 }}><Status status={item.status} /></div>{item.approval?.kind === 'automatic' && <small className="muted">System approved</small>}</td><td className="numeric">{money(item.current_price, item.currency)}<br /><strong>{money(item.proposed_price, item.currency)}</strong></td><td className="numeric">{item.delta_pct > 0 ? '+' : ''}{number(item.delta_pct, 1)}%</td><td className="numeric">{number(item.confidence * 100, 1)}%</td><td><Status status={item.compliance_status} /></td></tr>)}</tbody></table></div> : <EmptyState icon={<ClipboardCheck size={32} />} title={items.length ? 'No matching recommendations' : 'Recommendations appear after a grounded run'}><p>{items.length ? 'Adjust the filters to include more decisions.' : 'Start a grounded pricing run with a configured model gateway and indexed evidence.'}</p></EmptyState>}
      <p className="report-footnote">Automatic decisions stay visible. An Auto-approve band item queued in Supervised keeps its band. Bulk approval is restricted to actual Review band items with clean compliance.</p>
    </section>
    {selected && <RecommendationDrawer key={`${selected.id}-${selected.revision}`} item={selected} peers={items.filter(item => item.run_id === selected.run_id)} onClose={close} onChanged={queue.reload} />}
  </>;
}

function impact(item: ManagedRecommendation) {
  const raw = item.impact;
  if (raw && typeof raw === 'object' && 'revenue' in raw) {
    const revenue = raw.revenue;
    if (typeof revenue === 'number') return revenue;
    if (revenue && typeof revenue === 'object' && 'mean' in revenue) return Number(revenue.mean) || 0;
  }
  return Number(item.forecast?.revenue?.mean || 0) - Number(item.current_forecast && typeof item.current_forecast === 'object' && 'revenue' in item.current_forecast ? (item.current_forecast.revenue as { mean?: number })?.mean || 0 : 0);
}
