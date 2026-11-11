import { useState } from 'react';
import type { FormEvent } from 'react';
import { FlaskConical, Play, Plus, Save, Trash2 } from 'lucide-react';
import { api, errorMessage, timestamp } from '../api/client';
import type { SavedScenario, ScenarioRequest, ScenarioResult } from '../api/operations';
import { useProducts } from '../api/useProducts';
import { useResource } from '../api/useResource';
import { EmptyState, ErrorNotice, Loading, PageHeading } from '../components/Common';
import { ScenarioReport } from './ScenarioReport';

export function ScenarioPage() {
  const catalog = useProducts();
  const saved = useResource<{ items: SavedScenario[] }>('/scenarios/saved');
  const [rows, setRows] = useState([{ sku: '', candidate_price: '' }]);
  const [horizon, setHorizon] = useState(14);
  const [iterations, setIterations] = useState(1000);
  const [seed, setSeed] = useState(42);
  const [stress, setStress] = useState<ScenarioRequest['stress']>('none');
  const [narrate, setNarrate] = useState(false);
  const [busy, setBusy] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [scenario, setScenario] = useState<ScenarioResult>();
  const [lastRequest, setLastRequest] = useState<ScenarioRequest>();
  const [name, setName] = useState('');
  function selectSku(index: number, sku: string) {
    const product = catalog.items.find(item => item.sku === sku);
    setRows(items => items.map((row, i) => i === index ? { sku, candidate_price: product?.current_price || '' } : row));
  }
  async function submit(event: FormEvent) {
    event.preventDefault(); setBusy(true); setError(''); setNotice(''); setScenario(undefined);
    const request: ScenarioRequest = { items: rows, horizon_days: horizon, iterations, seed, stress, narrate };
    try { setScenario(await api<ScenarioResult>('/scenarios/batch', { method: 'POST', body: JSON.stringify(request) })); setLastRequest(request); }
    catch (reason) { setError(errorMessage(reason)); }
    finally { setBusy(false); }
  }
  async function save() {
    if (!lastRequest || !name.trim()) return;
    setSaving(true); setError(''); setNotice('');
    try { const item = await api<SavedScenario>('/scenarios/saved', { method: 'POST', body: JSON.stringify({ name: name.trim(), request: lastRequest }) }); setScenario(item.result); saved.reload(); setName(''); setNotice('Scenario reevaluated against current Commerce data and saved with its request and results.'); }
    catch (reason) { setError(errorMessage(reason)); }
    finally { setSaving(false); }
  }
  function load(item: SavedScenario) {
    setRows(item.request.items); setHorizon(item.request.horizon_days); setIterations(item.request.iterations); setSeed(item.request.seed); setStress(item.request.stress || 'none');
    setNarrate(item.request.narrate || false);
    setScenario(item.result); setLastRequest(item.request); setError(''); setNotice(`Loaded ${item.name}. Saved results retain the original inputs; simulate again to use current data.`);
  }
  const duplicate = new Set(rows.map(row => row.sku).filter(Boolean)).size < rows.filter(row => row.sku).length;
  return <>
    <PageHeading eyebrow="WHAT-IF ANALYSIS" title="Scenario lab">Explore one or many candidate prices with shared Monte Carlo assumptions, stress cases, and saved comparisons.</PageHeading>
    <div className="scenario-layout"><section className="panel scenario-form"><div className="panel-heading"><div><h2>Define a scenario</h2><p>Same engine. Inspectable uncertainty.</p></div></div>{catalog.error && <div className="panel-body"><ErrorNotice message={catalog.error} /></div>}<form onSubmit={submit} className="panel-body form-stack">
      {rows.map((row, index) => <div key={index} className="form-stack"><label>Product {rows.length > 1 ? index + 1 : ''}<select value={row.sku} onChange={event => selectSku(index, event.target.value)} required disabled={catalog.loading}><option value="">{catalog.loading ? 'Loading products…' : 'Choose a product'}</option>{catalog.items.map(item => <option key={item.sku} value={item.sku}>{item.name} · {item.sku}</option>)}</select></label><div className="scenario-item-controls"><label style={{ flex: 1 }}>Candidate price<input style={{ width: '100%' }} type="number" min="0.01" step="0.01" required value={row.candidate_price} onChange={event => setRows(items => items.map((item, i) => i === index ? { ...item, candidate_price: event.target.value } : item))} placeholder="0.00" /></label>{rows.length > 1 && <button type="button" className="icon-button" style={{ alignSelf: 'end' }} aria-label={`Remove product ${index + 1}`} onClick={() => setRows(items => items.filter((_, i) => i !== index))}><Trash2 size={16} /></button>}</div></div>)}
      <button type="button" className="button secondary small-button" onClick={() => setRows(items => [...items, { sku: '', candidate_price: '' }])} disabled={rows.length >= 50}><Plus size={14} />Add another SKU</button>
      {duplicate && <p className="small" role="alert">Choose each SKU once.</p>}
      <div className="form-two-columns"><label>Horizon (days)<input type="number" min="1" max="90" required value={horizon} onChange={event => setHorizon(Number(event.target.value))} /></label><label>Random seed<input type="number" min="0" max="4294967295" required value={seed} onChange={event => setSeed(Number(event.target.value))} /></label></div>
      <label>Simulation draws<input type="number" min="100" max="5000" step="100" required value={iterations} onChange={event => setIterations(Number(event.target.value))} /></label>
      <label>Stress preset<select value={stress} onChange={event => setStress(event.target.value as ScenarioRequest['stress'])}><option value="none">Normal assumptions</option><option value="demand_collapse">Demand collapse</option><option value="competitor_undercut">Competitor undercut</option><option value="cost_spike">Cost spike</option></select></label>
      <label className="check-label"><input className="selection-checkbox" type="checkbox" checked={narrate} onChange={event => setNarrate(event.target.checked)} />Add grounded interpretation</label>
      <button className="button primary" disabled={rows.some(row => !row.sku) || duplicate || busy} type="submit"><Play size={16} />{busy ? 'Simulating…' : 'Simulate scenario'}</button><p className="small muted">Simulation does not approve or apply candidate prices.</p>
    </form><div className="panel-heading"><h2>Saved scenarios</h2></div><div className="panel-body saved-scenarios">{saved.error && <ErrorNotice message={saved.error} />}{saved.data?.items?.length ? saved.data.items.map(item => <button key={item.id} onClick={() => load(item)}><strong>{item.name}</strong><small>{timestamp(item.created_at)} · {item.request.items.length} SKUs</small></button>) : <p className="small muted">{saved.loading ? 'Loading saved scenarios…' : 'Save a completed scenario to revisit its assumptions.'}</p>}</div></section>
      <section className="panel scenario-results"><div className="panel-heading"><div><h2>Scenario distributions</h2><p>Medians and 95% simulation intervals</p></div><span className="neutral-tag">Read-only scenario</span></div>
        {(error || notice) && <div className="panel-body">{error && <ErrorNotice message={error} />}{notice && <p className="small muted" role="status">{notice}</p>}</div>}{busy ? <Loading label="Sampling possible outcomes with shared assumptions…" /> : scenario ? <div className="panel-body"><div className="scenario-save"><input aria-label="Scenario name" maxLength={100} value={name} onChange={event => setName(event.target.value)} placeholder="Name this scenario" /><button className="button secondary" disabled={saving || !name.trim()} onClick={() => void save()}><Save size={15} />{saving ? 'Saving…' : 'Reevaluate & save'}</button></div><ScenarioReport scenario={scenario} /></div> : !error && <EmptyState icon={<FlaskConical size={34} />} title="Make uncertainty visible"><p>Choose products and prices to compare revenue, profit, units, and margin distributions under a common scenario.</p></EmptyState>}
      </section></div>
  </>;
}
