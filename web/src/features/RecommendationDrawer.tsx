import { useState } from 'react';
import type { FormEvent } from 'react';
import { Check, RotateCcw, ShieldAlert, X } from 'lucide-react';
import { api, errorMessage, money, number, timestamp } from '../api/client';
import { bandLabel, canReview } from '../api/operations';
import type { ManagedRecommendation } from '../api/operations';
import { Drawer, ErrorNotice, Status } from '../components/Common';
import { EvidenceSources } from '../components/EvidenceSources';
import { ForecastBands, StructuredEvidence } from '../components/Forecast';

export function BandBadge({ band }: { band: string }) {
  return <span className={`band-tag ${band}`}>{band === 'escalate' ? <ShieldAlert size={11} /> : band === 'auto_approve' ? <Check size={11} /> : <span aria-hidden="true">◇</span>}{bandLabel(band)}</span>;
}

export function RecommendationDrawer({ item, peers, onClose, onChanged }: { item: ManagedRecommendation; peers: ManagedRecommendation[]; onClose: () => void; onChanged: () => void }) {
  const [action, setAction] = useState('approve');
  const [price, setPrice] = useState(String(item.proposed_price));
  const [reason, setReason] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const editable = canReview(item);
  const reasonRequired = action === 'override' || item.band === 'escalate';
  async function decide(event: FormEvent) {
    event.preventDefault(); setBusy(true); setError(''); setNotice('');
    try {
      await api(`/recommendations/${encodeURIComponent(item.id)}/decision`, { method: 'POST', body: JSON.stringify({ action, expected_revision: item.revision, ...(reason.trim() ? { reason: reason.trim() } : {}), ...(action === 'override' ? { price } : {}) }) });
      setNotice('Decision acknowledged by the server. Refreshing the current revision and execution state.'); onChanged();
    } catch (failure) { setError(errorMessage(failure)); }
    finally { setBusy(false); }
  }
  async function revert() {
    setBusy(true); setError(''); setNotice('');
    try { await api(`/recommendations/${encodeURIComponent(item.id)}/revert`, { method: 'POST', body: JSON.stringify({ expected_revision: item.revision }) }); setNotice('Revert requested. Current rules and Commerce versions are checked before any compensating change.'); onChanged(); }
    catch (failure) { setError(errorMessage(failure)); }
    finally { setBusy(false); }
  }
  const family = item.family_id ? peers.filter(peer => peer.family_id === item.family_id).sort((a, b) => (productSize(a) ?? 0) - (productSize(b) ?? 0)) : [];
  const ladderMaximum = Math.max(1, ...family.map(peer => Number(peer.proposed_price)));
  return <Drawer title={item.name || item.sku} subtitle={`${item.sku} · Revision ${item.revision} · ${item.run_id.slice(0, 8)}`} onClose={onClose}><div className="drawer-body">
    <div className="button-row"><BandBadge band={item.band} /><Status status={item.status} /><span className="neutral-tag">{item.approval?.kind === 'automatic' ? 'System decision' : item.approval ? 'Human decision' : 'Awaiting decision'}</span></div>
    {error && <ErrorNotice message={error} />}{notice && <p className="success-text" role="status">{notice}</p>}
    <div className="price-comparison"><div><span>Current price</span><strong>{money(item.current_price, item.currency)}</strong></div><span>→</span><div><span>Proposed price</span><strong>{money(item.proposed_price, item.currency)}</strong></div></div>
    <div className="evidence-grid"><div><span>Price change</span><strong>{number(item.delta_pct, 2)}%</strong></div><div><span>Confidence</span><strong>{number(item.confidence * 100, 1)}%</strong></div><div><span>Mode at decision</span><strong>{item.mode_at_decision}</strong></div><div><span>Hold release</span><strong>{timestamp(item.hold_until || undefined)}</strong></div></div>
    {item.compliance?.status === 'failed' && <div className="notice error"><ShieldAlert size={18} /><span>Compliance veto. Approval, overrides, and automatic execution are blocked for this revision.</span></div>}
    {editable && <form className="decision-form" onSubmit={decide}><h3>Review this revision</h3><label>Decision<select value={action} onChange={event => setAction(event.target.value)}><option value="approve">Approve proposed price</option><option value="reject">Reject recommendation</option><option value="override">Override price with a reason</option></select></label>{action === 'override' && <label>Override price<input type="number" min="0.01" step="0.01" required value={price} onChange={event => setPrice(event.target.value)} /></label>}<label>Reason {reasonRequired ? '(required)' : '(optional)'}<textarea maxLength={2000} required={reasonRequired} value={reason} onChange={event => setReason(event.target.value)} placeholder={item.band === 'escalate' ? 'Explain the explicit human intervention for this escalation.' : 'Record the context behind your decision.'} /></label><p className="small muted">The server checks the current revision, Commerce price, compliance rules, and execution policy.</p><button className="button primary" disabled={busy || (reasonRequired && !reason.trim())} type="submit">{action === 'reject' ? <X size={15} /> : <Check size={15} />}{busy ? 'Submitting…' : 'Submit decision'}</button></form>}
    {item.status === 'applied' && <button className="button secondary" disabled={busy} onClick={() => void revert()}><RotateCcw size={15} />{busy ? 'Requesting…' : 'Revert this change'}</button>}
    <h3>Band reasons and thresholds</h3>{item.band_reasons?.map((entry, index) => <div key={`${entry.code}-${index}`} className="evidence-rule"><div><strong>{entry.code.replaceAll('_', ' ')}</strong></div><p className="small muted">{entry.message}</p><StructuredEvidence value={{ actual: entry.actual, threshold: entry.threshold, passed: entry.passed }} /></div>)}
    <h3>Compliance evidence</h3>{item.compliance?.rules?.map(rule => <div key={rule.rule} className="evidence-rule"><div><Status status={rule.passed ? 'passed' : 'failed'} /><strong>{rule.rule.replaceAll('_', ' ')}</strong></div><StructuredEvidence value={{ actual: rule.actual, threshold: rule.threshold, message: rule.message }} /></div>)}
    <h3>Stability signals</h3><StructuredEvidence value={item.stability} />
    {!!family.length && <><h3>Family price ladder</h3><p className="small muted">Size order for recommendations in this run. A decreasing proposed price is marked as a break.</p><div>{family.map((peer, index) => { const broken = index > 0 && Number(peer.proposed_price) < Number(family[index - 1].proposed_price); return <div key={peer.id} className={`ladder-row ${peer.id === item.id ? 'current' : ''} ${broken ? 'broken' : ''}`}><div>{peer.name || peer.sku}<div className="ladder-bar" style={{ width: `${Number(peer.proposed_price) / ladderMaximum * 100}%` }} /></div><span>{productSize(peer) == null ? 'Size —' : `Size ${productSize(peer)}`}</span><strong>{money(peer.proposed_price, peer.currency)}{broken ? ' · Break' : ''}</strong></div>; })}</div></>}
    <h3>Grounded rationale</h3><StructuredEvidence value={item.rationale} /><EvidenceSources value={{ citations: item.citations, sources: item.sources }} />
    <h3>Forecast distributions</h3><ForecastBands forecast={item.forecast} currency={item.currency} />
    <h3>Baseline comparison</h3><p className="small muted">Conventional baseline price: {money(item.baseline?.price, item.currency)}</p><ForecastBands forecast={item.baseline?.forecast} currency={item.currency} />
    <h3>Elasticity and confidence inputs</h3><StructuredEvidence value={{ elasticity: item.elasticity, confidence_factors: item.confidence_factors }} />
    <details className="report-details"><summary>Retained source inputs and versions</summary><StructuredEvidence value={{ product: item.product_evidence, source_as_of: item.source_as_of, numeric_hash: item.numeric_hash, policy_version: item.policy_version, price_version: item.price_version }} /></details>
    <h3>Assumptions</h3><StructuredEvidence value={item.assumptions} />
    <h3>Approval and execution receipt</h3><StructuredEvidence value={{ approval: item.approval, execution: item.execution }} />
  </div></Drawer>;
}

function productSize(item: ManagedRecommendation): number | undefined {
  const evidence = item.product_evidence;
  return item.size ?? (evidence && typeof evidence === 'object' && 'size' in evidence ? Number(evidence.size) : undefined);
}
