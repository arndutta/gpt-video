import { useCallback, useEffect, useState } from 'react';
import type { FormEvent } from 'react';
import { BarChart3, ChevronRight, Play, RefreshCw } from 'lucide-react';
import { Link, useSearchParams } from 'react-router-dom';
import { api, errorMessage, timestamp } from '../api/client';
import type { CatalogSummary, PricingRun } from '../api/types';
import { useResource } from '../api/useResource';
import { EmptyState, ErrorNotice, Loading, PageHeading, Status } from '../components/Common';
import { RunReport } from './RunReport';
import { RunProgress } from './RunProgress';
import { emptyRunConstraints, serializeRunConstraints } from '../api/runConstraints';
import { RunConstraints } from '../components/RunConstraints';

const terminalStates = new Set(['completed', 'failed', 'interrupted', 'cancelled']);

export function RunsPage() {
  const [params, setParams] = useSearchParams();
  const runId = params.get('id') || '';
  const history = useResource<{ items: PricingRun[] }>('/runs');
  const catalog = useResource<CatalogSummary>('/catalog/summary');
  const [run, setRun] = useState<PricingRun>();
  const [loadError, setLoadError] = useState('');
  const [submitError, setSubmitError] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [category, setCategory] = useState('');
  const [objective, setObjective] = useState('balanced');
  const [iterations, setIterations] = useState(1000);
  const [horizon, setHorizon] = useState(14);
  const [seed, setSeed] = useState(42);
  const [kind, setKind] = useState('quantitative_preview');
  const [constraints, setConstraints] = useState(emptyRunConstraints);
  const constraintCategories = category ? [category] : catalog.data?.categories.map(item => item.name) || [];
  const [detailVersion, setDetailVersion] = useState(0);
  const refreshRun = useCallback(() => { history.reload(); setDetailVersion(value => value + 1); }, [history.reload]);
  useEffect(() => {
    if (!runId) { setRun(undefined); return; }
    const controller = new AbortController();
    let timer: number | undefined;
    let lastStatus = '';
    let loading = false;
    const source = new EventSource(`/api/runs/${encodeURIComponent(runId)}/events`);
    setRun(undefined); setLoadError('');
    async function load() {
      if (loading || controller.signal.aborted) return;
      loading = true; window.clearTimeout(timer);
      try {
        const value = await api<PricingRun>(`/runs/${encodeURIComponent(runId)}`, { signal: controller.signal });
        if (controller.signal.aborted) return;
        setRun(value); setLoadError('');
        if (value.status !== lastStatus) { lastStatus = value.status; history.reload(); }
        if (terminalStates.has(value.status) || value.status === 'awaiting_review') source.close();
        if (!terminalStates.has(value.status)) timer = window.setTimeout(load, 1000);
      } catch (reason) {
        if (!controller.signal.aborted) { setLoadError(errorMessage(reason)); timer = window.setTimeout(load, 3000); }
      } finally { loading = false; }
    }
    source.addEventListener('progress', event => {
      try {
        const progress: unknown = JSON.parse((event as MessageEvent).data);
        if (!progress || typeof progress !== 'object' || !('id' in progress) || progress.id !== runId || !('status' in progress) || typeof progress.status !== 'string') return;
        const update = progress as Pick<PricingRun, 'id' | 'status' | 'stage' | 'completed_at' | 'error'>;
        setRun(current => current ? { ...current, ...update } : current);
        if (terminalStates.has(update.status) || update.status === 'awaiting_review') { source.close(); void load(); }
      } catch { /* Polling remains the fallback for malformed or interrupted streams. */ }
    });
    void load();
    return () => { controller.abort(); source.close(); window.clearTimeout(timer); };
  }, [runId, detailVersion, history.reload]);
  async function submit(event: FormEvent) {
    event.preventDefault(); setSubmitting(true); setSubmitError('');
    try {
      const limits = serializeRunConstraints(constraints, constraintCategories);
      const created = await api<PricingRun>('/runs', { method: 'POST', body: JSON.stringify({ kind, ...(category ? { category } : {}), objective, iterations, horizon_days: horizon, seed, ...(limits ? { constraints: limits } : {}) }) });
      setParams({ id: created.id }); history.reload();
    } catch (reason) { setSubmitError(errorMessage(reason)); }
    finally { setSubmitting(false); }
  }
  return <>
    <PageHeading eyebrow="ANALYSIS AND DECISIONS" title="Pricing runs">Run a quantitative preview or a grounded pricing workflow with review and audited execution.</PageHeading>
    <section className="panel run-form-panel"><div className="panel-heading"><div><h2>Create a pricing run</h2><p>Fixed inputs and a seed make numerical results reproducible.</p></div><span className="neutral-tag">{kind === 'grounded' ? 'Mode-based approval policy' : 'Read-only preview'}</span></div><form className="run-form" onSubmit={submit}>
      <label>Workflow<select value={kind} onChange={event => setKind(event.target.value)}><option value="quantitative_preview">Quantitative preview</option><option value="grounded">Grounded pricing workflow</option></select></label>
      <label>Scope<select value={category} onChange={event => setCategory(event.target.value)}><option value="">Full catalog</option>{catalog.data?.categories?.map(item => <option key={item.name} value={item.name}>{item.name}</option>)}</select></label>
      <label>Objective<select value={objective} onChange={event => setObjective(event.target.value)}><option value="balanced">Balanced</option><option value="revenue">Revenue-weighted</option><option value="margin">Margin-weighted</option></select></label>
      <label>Horizon (days)<input type="number" min="1" max="90" required value={horizon} onChange={event => setHorizon(Number(event.target.value))} /></label>
      <label>Simulation draws<input type="number" min="100" max="5000" step="100" required value={iterations} onChange={event => setIterations(Number(event.target.value))} /></label>
      <label>Random seed<input type="number" min="0" max="2147483647" required value={seed} onChange={event => setSeed(Number(event.target.value))} /></label>
      <RunConstraints categories={constraintCategories} value={constraints} onChange={setConstraints} disabled={submitting} />
      <button className="button primary" type="submit" disabled={submitting}><Play size={16} />{submitting ? 'Starting…' : 'Start run'}</button>
    </form>{submitError && <div className="form-error"><ErrorNotice message={submitError} /></div>}</section>
    <div className="runs-layout"><section className="panel run-history"><div className="panel-heading"><h2>Run history</h2><button className="icon-button" onClick={history.reload} aria-label="Refresh run history"><RefreshCw size={16} /></button></div>{history.error && <div className="panel-body"><ErrorNotice message={history.error} /></div>}{history.data?.items?.length ? <div className="history-items">{history.data.items.map(item => <button key={item.id} className={`history-item ${runId === item.id ? 'selected' : ''}`} onClick={() => setParams({ id: item.id })}><div><strong>Run {item.id.slice(0, 8)}</strong><ChevronRight size={15} /></div><small>{timestamp(item.created_at)}</small><Status status={item.status} /></button>)}</div> : <div className="history-empty small muted">{history.loading ? 'Loading history…' : 'No runs yet.'}</div>}</section>
      <section className="panel run-result">{runId ? <><div className="panel-heading"><div><h2>Run {runId.slice(0, 8)}</h2><p>{run ? timestamp(run.created_at) : 'Loading run details'}</p></div>{run && <Status status={run.status} />}</div>{loadError && <div className="panel-body"><ErrorNotice message={loadError} /></div>}{!run && !loadError && <Loading label="Loading pricing run…" />}{run && <RunProgress run={run} onChanged={refreshRun} />}{run && !terminalStates.has(run.status) && !['waiting_review', 'awaiting_review'].includes(run.status) && <div className="run-progress"><Loading label={run.stage ? run.stage.replaceAll('_', ' ') : 'Running pricing analysis…'} /><p className="small muted">Progress reconnects automatically while this page is open.</p></div>}{run?.error && <div className="panel-body"><ErrorNotice message={errorMessage(run.error)} /></div>}{run?.result && <RunReport key={runId} result={run.result} />}{run && ['waiting_review', 'awaiting_review'].includes(run.status) && <div className="panel-body"><Link className="button primary" to="/review">Review pending recommendations</Link></div>}</> : <EmptyState icon={<BarChart3 size={34} />} title="Your results will appear here"><p>Create a pricing run or select a run from history to inspect its evidence.</p></EmptyState>}</section>
    </div>
  </>;
}
