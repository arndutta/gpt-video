import { useCallback, useState } from 'react';
import { Activity, CirclePause, Repeat2, ShieldCheck, Square } from 'lucide-react';
import { api, errorMessage, number } from '../api/client';
import type { ControlState, ModelMonitor, OperatingMode } from '../api/operations';
import { usePolling } from '../api/usePolling';
import { Drawer, ErrorNotice } from '../components/Common';
import { StructuredEvidence } from '../components/Forecast';
import { LoopDrawer } from './LoopDrawer';

export function GlobalControls() {
  const control = usePolling<ControlState>('/control', 2000);
  const monitor = usePolling<ModelMonitor>('/monitor', 2000);
  const [loopOpen, setLoopOpen] = useState(false);
  const [monitorOpen, setMonitorOpen] = useState(false);
  const [confirmKill, setConfirmKill] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const closeLoop = useCallback(() => setLoopOpen(false), []);
  const closeMonitor = useCallback(() => setMonitorOpen(false), []);
  const closeKill = useCallback(() => setConfirmKill(false), []);
  const connected = !!control.data && !control.error;
  async function modeChange(mode: OperatingMode) {
    setBusy(true); setError(''); setNotice('');
    try { await api('/control/mode', { method: 'PATCH', body: JSON.stringify({ mode }) }); control.reload(); setNotice(`Mode changed to ${mode}.`); }
    catch (reason) { setError(errorMessage(reason)); }
    finally { setBusy(false); }
  }
  async function kill() {
    setBusy(true); setError('');
    try {
      await api('/control/kill', { method: 'POST' });
      setConfirmKill(false); control.reload();
      setNotice('Halt acknowledged. Scheduling stopped and mode reset to Supervised. Already-sent requests are reconciled.');
    } catch (reason) { setError(errorMessage(reason)); }
    finally { setBusy(false); }
  }
  const metrics = monitor.data;
  const cost = metrics?.estimated_cost_usd ?? metrics?.cost_usd;
  return <>
    <button className="llm-monitor monitor-button" onClick={() => setMonitorOpen(true)} title="Open token, cost and cache monitor"><Activity size={15} />
      {monitor.error ? 'Monitor unavailable' : metrics ? `${number(metrics.active_calls ?? 0)} active` : 'LLM loading…'}
      <span className="monitor-divider" />{metrics ? `${number((metrics.input_tokens ?? 0) + (metrics.output_tokens ?? 0))} tok · $${number(cost ?? 0, 4)}` : 'Loading…'}
    </button>
    <button className={`loop-state loop-button ${control.data?.loop.running ? 'active' : ''}`} onClick={() => setLoopOpen(true)} title="Open continuous loop controls"><Repeat2 size={14} />{control.error ? 'Loop unavailable' : !control.data ? 'Loop loading…' : control.data.loop.running ? `Loop ${number(control.data.loop.iteration_count ?? 0)}` : 'Loop off'}</button>
    <div className="mode-indicator" title={control.error || 'The server enforces approval and compliance for every mode'}><ShieldCheck size={15} /><select aria-label="Operating mode" value={control.data?.mode ?? ''} disabled={!connected || busy} onChange={event => void modeChange(event.target.value as OperatingMode)}>{!control.data && <option value="">Loading mode…</option>}<option value="supervised">Supervised</option><option value="assisted">Assisted</option><option value="autonomous">Autonomous</option></select></div>
    <button className="kill-button" disabled={!connected || busy} onClick={() => { setError(''); setConfirmKill(true); }} title="Stop scheduling, cancel pending automatic work and reset Supervised"><Square size={12} />Halt</button>
    {control.error && <span className="control-disconnected" role="status">Controls disconnected</span>}
    {(error || notice) && !confirmKill && <div className={`control-toast ${error ? 'error' : ''}`} role={error ? 'alert' : 'status'}><span>{error || notice}</span><button className="icon-button" aria-label="Dismiss status" onClick={() => { setError(''); setNotice(''); }}>×</button></div>}
    {loopOpen && <LoopDrawer state={control.data?.loop} connected={connected} onClose={closeLoop} onChanged={control.reload} holdSeconds={control.data?.hold_seconds} />}
    {monitorOpen && <Drawer title="Language model activity" subtitle="Session totals reported by the server" onClose={closeMonitor}><div className="drawer-body">{monitor.error && <ErrorNotice message={monitor.error} />}<div className="mini-metrics"><div><span>Input tokens</span><strong>{number(metrics?.input_tokens)}</strong></div><div><span>Output tokens</span><strong>{number(metrics?.output_tokens)}</strong></div><div><span>Estimated cost</span><strong>${number(cost, 5)}</strong></div><div><span>Active calls</span><strong>{number(metrics?.active_calls)}</strong></div></div><p className="small muted">Costs are estimates. The pricing source and recorded outcomes are shown below.</p><StructuredEvidence value={metrics} /></div></Drawer>}
    {confirmKill && <Drawer title="Halt automatic activity?" subtitle="One confirmation applies the global halt" onClose={closeKill}><div className="drawer-body"><div className="notice warning"><CirclePause size={20} /><span>Stop the loop, cancel pending automatic changes, and reset to Supervised. Requests already sent to Commerce remain visible until reconciled.</span></div>{error && <ErrorNotice message={error} />}<button className="button danger" disabled={busy} onClick={() => void kill()}>{busy ? 'Halting…' : 'Confirm halt'}</button><button className="button secondary" disabled={busy} onClick={closeKill}>Keep current activity</button></div></Drawer>}
  </>;
}
