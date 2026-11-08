import { useEffect, useState } from 'react';
import type { FormEvent } from 'react';
import { BarChart3, ChevronRight, Play, RefreshCw } from 'lucide-react';
import { useSearchParams } from 'react-router-dom';
import { api, errorMessage, timestamp } from '../api/client';
import type { CatalogSummary, PricingRun } from '../api/types';
import { useResource } from '../api/useResource';
import { EmptyState, ErrorNotice, Loading, PageHeading, Status } from '../components/Common';
import { RunReport } from './RunReport';

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
  useEffect(() => {
    if (!runId) { setRun(undefined); return; }
    const controller = new AbortController();
    let timer: number | undefined;
    let lastStatus = '';
    setRun(undefined); setLoadError('');
    async function load() {
      try {
        const value = await api<PricingRun>(`/runs/${encodeURIComponent(runId)}`, { signal: controller.signal });
        if (controller.signal.aborted) return;
        setRun(value); setLoadError('');
        if (value.status !== lastStatus) { lastStatus = value.status; history.reload(); }
        if (!terminalStates.has(value.status)) timer = window.setTimeout(load, 1000);
      } catch (reason) {
        if (!controller.signal.aborted) { setLoadError(errorMessage(reason)); timer = window.setTimeout(load, 3000); }
      }
    }
    void load();
    return () => { controller.abort(); window.clearTimeout(timer); };
  }, [runId, history.reload]);
  async function submit(event: FormEvent) {
    event.preventDefault(); setSubmitting(true); setSubmitError('');
    try {
      const created = await api<PricingRun>('/runs', { method: 'POST', body: JSON.stringify({ ...(category ? { category } : {}), objective, iterations, horizon_days: horizon, seed }) });
      setParams({ id: created.id }); history.reload();
    } catch (reason) { setSubmitError(errorMessage(reason)); }
    finally { setSubmitting(false); }
  }
  return <>
    <PageHeading eyebrow="QUANTITATIVE ANALYSIS" title="Pricing runs">Estimate elasticity, model uncertainty, and compare candidate prices on the same data.</PageHeading>
    <section className="panel run-form-panel"><div className="panel-heading"><div><h2>Create a preview</h2><p>Fixed inputs and a seed make numerical results reproducible.</p></div><span className="neutral-tag">Read-only analysis</span></div><form className="run-form" onSubmit={submit}>
      <label>Scope<select value={category} onChange={event => setCategory(event.target.value)}><option value="">Full catalog</option>{catalog.data?.categories?.map(item => <option key={item.name} value={item.name}>{item.name}</option>)}</select></label>
      <label>Objective<select value={objective} onChange={event => setObjective(event.target.value)}><option value="balanced">Balanced</option><option value="revenue">Revenue-weighted</option><option value="margin">Margin-weighted</option></select></label>
      <label>Horizon (days)<input type="number" min="1" max="90" required value={horizon} onChange={event => setHorizon(Number(event.target.value))} /></label>
      <label>Simulation draws<input type="number" min="100" max="5000" step="100" required value={iterations} onChange={event => setIterations(Number(event.target.value))} /></label>
      <label>Random seed<input type="number" min="0" max="2147483647" required value={seed} onChange={event => setSeed(Number(event.target.value))} /></label>
      <button className="button primary" type="submit" disabled={submitting}><Play size={16} />{submitting ? 'Starting…' : 'Run preview'}</button>
    </form>{submitError && <div className="form-error"><ErrorNotice message={submitError} /></div>}</section>
    <div className="runs-layout"><section className="panel run-history"><div className="panel-heading"><h2>Run history</h2><button className="icon-button" onClick={history.reload} aria-label="Refresh run history"><RefreshCw size={16} /></button></div>{history.error && <div className="panel-body"><ErrorNotice message={history.error} /></div>}{history.data?.items?.length ? <div className="history-items">{history.data.items.map(item => <button key={item.id} className={`history-item ${runId === item.id ? 'selected' : ''}`} onClick={() => setParams({ id: item.id })}><div><strong>Preview {item.id.slice(0, 8)}</strong><ChevronRight size={15} /></div><small>{timestamp(item.created_at)}</small><Status status={item.status} /></button>)}</div> : <div className="history-empty small muted">{history.loading ? 'Loading history…' : 'No previews yet.'}</div>}</section>
      <section className="panel run-result">{runId ? <><div className="panel-heading"><div><h2>Preview {runId.slice(0, 8)}</h2><p>{run ? timestamp(run.created_at) : 'Loading run details'}</p></div>{run && <Status status={run.status} />}</div>{loadError && <div className="panel-body"><ErrorNotice message={loadError} /></div>}{!run && !loadError && <Loading label="Loading pricing run…" />}{run && !terminalStates.has(run.status) && <div className="run-progress"><Loading label={run.stage ? run.stage.replaceAll('_', ' ') : 'Running quantitative analysis…'} /><p className="small muted">Results will appear here when the computation completes.</p></div>}{run?.error && <div className="panel-body"><ErrorNotice message={errorMessage(run.error)} /></div>}{run?.result && <RunReport key={runId} result={run.result} />}{run?.status === 'interrupted' && <div className="notice warning">This run was interrupted. Start a new preview to analyze current inputs.</div>}</> : <EmptyState icon={<BarChart3 size={34} />} title="Your results will appear here"><p>Create a preview or select a run from the history to inspect the numbers.</p></EmptyState>}</section>
    </div>
  </>;
}
