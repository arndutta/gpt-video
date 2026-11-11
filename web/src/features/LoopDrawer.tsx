import { useEffect, useState } from 'react';
import type { FormEvent } from 'react';
import { Play, Square } from 'lucide-react';
import { api, errorMessage, number, timestamp } from '../api/client';
import type { LoopState } from '../api/operations';
import type { CatalogSummary } from '../api/types';
import { useResource } from '../api/useResource';
import { Drawer, ErrorNotice, Status } from '../components/Common';
import { StructuredEvidence } from '../components/Forecast';
import { Link } from 'react-router-dom';
import { emptyRunConstraints, serializeRunConstraints } from '../api/runConstraints';
import { RunConstraints } from '../components/RunConstraints';

export function LoopDrawer({ state, connected, onClose, onChanged, holdSeconds }: { state?: LoopState; connected: boolean; onClose: () => void; onChanged: () => void; holdSeconds?: number }) {
  const categories = useResource<CatalogSummary>('/catalog/summary');
  const [category, setCategory] = useState('');
  const [interval, setInterval] = useState(60);
  const [cap, setCap] = useState('');
  const [horizon, setHorizon] = useState(14);
  const [objective, setObjective] = useState('balanced');
  const [constraints, setConstraints] = useState(emptyRunConstraints);
  const constraintCategories = category ? [category] : categories.data?.categories.map(item => item.name) || [];
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [now, setNow] = useState(Date.now());
  useEffect(() => { const timer = window.setInterval(() => setNow(Date.now()), 1000); return () => window.clearInterval(timer); }, []);
  const nextAt = state?.next_run_at ? new Date(state.next_run_at).valueOf() : null;
  const countdown = nextAt && Number.isFinite(nextAt) ? Math.max(0, Math.ceil((nextAt - now) / 1000)) : null;
  const iterations = [...(state?.iterations || [])].sort((a, b) => b.iteration - a.iteration).slice(0, 20);
  async function start(event: FormEvent) {
    event.preventDefault(); setBusy(true); setError(''); setNotice('');
    try {
      const limits = serializeRunConstraints(constraints, constraintCategories);
      await api('/loop', { method: 'POST', body: JSON.stringify({ request: { kind: 'grounded', ...(category ? { category } : {}), objective, horizon_days: horizon, iterations: 1000, seed: 42, ...(limits ? { constraints: limits } : {}) }, interval_seconds: interval, max_iterations: cap ? Number(cap) : null }) });
      onChanged(); setNotice('Loop start acknowledged. The next iteration uses the current mode and policies.');
    } catch (reason) { setError(errorMessage(reason)); }
    finally { setBusy(false); }
  }
  async function stop() {
    setBusy(true); setError(''); setNotice('');
    try { await api('/loop/stop', { method: 'POST' }); onChanged(); setNotice('Loop stop acknowledged. Existing review items remain available.'); }
    catch (reason) { setError(errorMessage(reason)); }
    finally { setBusy(false); }
  }
  return <Drawer title="Continuous pricing loop" subtitle="Scheduling starts only from an explicit action" onClose={onClose}><div className="drawer-body">
    {error && <ErrorNotice message={error} />}{!connected && <ErrorNotice message="Controls are disconnected. Refresh the service connection before starting or stopping." />}
    {notice && <p className="success-text" role="status">{notice}</p>}
    <div className="loop-summary"><Status status={state?.status || 'unavailable'} /><strong>{state?.running ? 'Scheduling is active' : 'Scheduling is off'}</strong><p className="small muted">Scheduling stays off after every server restart. A failed iteration stops the session.</p></div>
    <div className="mini-metrics"><div><span>Completed iterations</span><strong>{number(state?.iteration_count ?? 0)}{state?.max_iterations ? ` / ${state.max_iterations}` : ''}</strong></div><div><span>Next iteration</span><strong className="small-word">{state?.running ? countdown == null ? 'Running / waiting' : `${countdown}s` : 'Off'}</strong></div></div>
    {state?.error && <ErrorNotice message={state.error} />}
    <section aria-label="Recent loop decisions" className="form-stack"><h3>Iteration decisions</h3><p className="small muted">Server-reported counts separate automatic approvals, queued review, and Commerce outcomes. A running or failed iteration does not imply success.</p>{iterations.length ? <><div className="table-scroll"><table className="loop-decisions"><thead><tr><th>Iteration / run</th><th className="numeric">Auto approved</th><th className="numeric">Queued</th><th className="numeric">Applied</th><th className="numeric">No change</th><th className="numeric">Unknown</th><th className="numeric">Blocked</th></tr></thead><tbody>{iterations.map(item => <tr key={`${item.iteration}-${item.run_id}`}><td><Link className="positive" to={`/runs?id=${encodeURIComponent(item.run_id)}`} onClick={onClose}>#{item.iteration} · {item.run_id.slice(0, 8)}</Link><div style={{ marginTop: 7 }}><Status status={item.status} /></div><small className="muted">{item.decisions ? `${number(item.decisions.total)} recommendations` : 'Decision counts pending'}</small></td>{(['auto_approved', 'queued', 'applied', 'unchanged', 'unknown', 'blocked'] as const).map(key => <td key={key} className="numeric">{item.decisions ? number(item.decisions[key]) : '—'}</td>)}</tr>)}</tbody></table></div><p className="small muted">Showing the most recent {iterations.length} of {state?.iterations?.length} iteration records returned for this session.</p></> : <p className="small muted">No iteration decision records are available for this session yet.</p>}</section>
    {state?.running ? <><StructuredEvidence value={{ session_id: state.session_id, interval_seconds: state.interval_seconds, next_run: timestamp(state.next_run_at || undefined), last_run_id: state.last_run_id, scope: state.request }} /><button className="button secondary" disabled={busy || !connected} onClick={() => void stop()}><Square size={15} />{busy ? 'Stopping…' : 'Stop scheduling'}</button></> : <form className="form-stack" onSubmit={start}>
      <label>Scope<select value={category} onChange={event => setCategory(event.target.value)}><option value="">Full catalog</option>{categories.data?.categories.map(item => <option key={item.name} value={item.name}>{item.name}</option>)}</select></label>
      <label>Objective<select value={objective} onChange={event => setObjective(event.target.value)}><option value="balanced">Balanced</option><option value="revenue">Revenue-weighted</option><option value="margin">Margin-weighted</option></select></label>
      <div className="form-two-columns"><label>Interval (seconds)<input type="number" min="5" max="86400" value={interval} onChange={event => setInterval(Number(event.target.value))} required /></label><label>Forecast horizon (days)<input type="number" min="1" max="90" value={horizon} onChange={event => setHorizon(Number(event.target.value))} required /></label></div>
      <label>Maximum iterations <span className="muted">(optional)</span><input type="number" min="1" max="1000" value={cap} onChange={event => setCap(event.target.value)} placeholder="Until stopped" /></label>
      <RunConstraints categories={constraintCategories} value={constraints} onChange={setConstraints} disabled={busy || !connected} />
      <p className="small muted">The full grounded pipeline runs once per interval with no overlap. Autonomous Review hold: {holdSeconds ?? '—'} seconds. Review items remain subject to their approval policy.</p>
      <button className="button primary" type="submit" disabled={busy || !connected}><Play size={15} />{busy ? 'Starting…' : 'Start loop'}</button>
    </form>}
  </div></Drawer>;
}
