import { useState } from 'react';
import { Check, Circle, Play } from 'lucide-react';
import { api, errorMessage, number } from '../api/client';
import type { PricingRun } from '../api/types';
import { ErrorNotice } from '../components/Common';
import { StructuredEvidence } from '../components/Forecast';

const nodes = [
  { key: 'data_context', label: 'Data & Context' },
  { key: 'quantitative', label: 'Quantitative' },
  { key: 'strategy', label: 'Strategy & Reasoning' },
  { key: 'validation', label: 'Validation & Compliance' },
  { key: 'execution', label: 'Execution' },
];

export function RunProgress({ run, onChanged }: { run: PricingRun; onChanged: () => void }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const grounded = run.request?.kind === 'grounded' || run.result?.type === 'grounded_recommendations' || run.result?.kind === 'grounded';
  const current = run.stage === 'human_review' ? 4 : nodes.findIndex(node => (run.stage || '').toLowerCase().includes(node.key));
  const seconds = run.duration_seconds ?? (run.completed_at ? (new Date(run.completed_at).valueOf() - new Date(run.created_at).valueOf()) / 1000 : null);
  async function resume() {
    setBusy(true); setError('');
    try { await api(`/runs/${encodeURIComponent(run.id)}/resume`, { method: 'POST' }); onChanged(); }
    catch (reason) { setError(errorMessage(reason)); }
    finally { setBusy(false); }
  }
  return <>{grounded && <div className="node-progress">{nodes.map((node, index) => { const done = run.status === 'completed' || current > index; return <span key={node.key} className={done ? 'done' : index === current ? 'active' : ''}>{done ? <Check size={12} /> : <Circle size={11} />}{node.label}</span>; })}</div>}
    {(seconds != null || run.token_cost != null || run.metrics) && <details className="report-details"><summary>Run duration, tokens, and cost</summary><StructuredEvidence value={{ duration_seconds: seconds == null ? 'Pending' : number(seconds, 2), estimated_cost_usd: run.token_cost, ...run.metrics }} /></details>}
    {['interrupted', 'failed'].includes(run.status) && grounded && <div className="panel-body"><div className="notice warning">This grounded run stopped. After correcting the cause, resume its checkpoint explicitly. Durable human decisions and current execution authorization are checked again. Starting a loop is a separate action.</div>{error && <ErrorNotice message={error} />}<button className="button secondary" disabled={busy} onClick={() => void resume()}><Play size={15} />{busy ? 'Resuming…' : 'Resume checkpoint'}</button></div>}
  </>;
}
