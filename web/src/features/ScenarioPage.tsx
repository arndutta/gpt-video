import { useState } from 'react';
import type { FormEvent } from 'react';
import { FlaskConical, Play } from 'lucide-react';
import { api, errorMessage, money, number } from '../api/client';
import type { Recommendation } from '../api/types';
import { useProducts } from '../api/useProducts';
import { EmptyState, ErrorNotice, Loading, PageHeading } from '../components/Common';
import { ForecastBands, StructuredEvidence } from '../components/Forecast';

type Scenario = Partial<Recommendation> & { configuration?: Record<string, unknown>; result?: Partial<Recommendation> };

export function ScenarioPage() {
  const catalog = useProducts();
  const [sku, setSku] = useState('');
  const [price, setPrice] = useState('');
  const [horizon, setHorizon] = useState(14);
  const [iterations, setIterations] = useState(1000);
  const [seed, setSeed] = useState(42);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [scenario, setScenario] = useState<Scenario>();
  const product = catalog.items.find(item => item.sku === sku);
  function selectSku(value: string) {
    setSku(value); setScenario(undefined);
    const next = catalog.items.find(item => item.sku === value);
    setPrice(next?.current_price || '');
  }
  async function submit(event: FormEvent) {
    event.preventDefault(); setBusy(true); setError(''); setScenario(undefined);
    try { setScenario(await api<Scenario>('/scenarios/simulate', { method: 'POST', body: JSON.stringify({ sku, candidate_price: price, horizon_days: horizon, iterations, seed }) })); }
    catch (reason) { setError(errorMessage(reason)); }
    finally { setBusy(false); }
  }
  const result = scenario?.result || scenario;
  return <>
    <PageHeading eyebrow="WHAT-IF ANALYSIS" title="Scenario lab">Test a candidate price using the same elasticity and Monte Carlo engine as pricing previews.</PageHeading>
    <div className="scenario-layout"><section className="panel scenario-form"><div className="panel-heading"><div><h2>Define a scenario</h2><p>One SKU. A price. A range of outcomes.</p></div></div>{catalog.error && <div className="panel-body"><ErrorNotice message={catalog.error} /></div>}<form onSubmit={submit} className="panel-body form-stack">
      <label>Product<select value={sku} onChange={event => selectSku(event.target.value)} required disabled={catalog.loading}><option value="">{catalog.loading ? 'Loading products…' : 'Choose a product'}</option>{catalog.items.map(item => <option key={item.sku} value={item.sku}>{item.name} · {item.sku}</option>)}</select></label>
      {product && <div className="scenario-current"><span>Current price</span><strong>{money(product.current_price, product.currency)}</strong><small>Unit cost {money(product.cost, product.currency)}</small></div>}
      <label>Candidate price<input type="number" min="0.01" step="0.01" required value={price} onChange={event => setPrice(event.target.value)} placeholder="0.00" /></label>
      <div className="form-two-columns"><label>Horizon (days)<input type="number" min="1" max="90" required value={horizon} onChange={event => setHorizon(Number(event.target.value))} /></label><label>Random seed<input type="number" min="0" max="2147483647" required value={seed} onChange={event => setSeed(Number(event.target.value))} /></label></div>
      <label>Simulation draws<input type="number" min="100" max="5000" step="100" required value={iterations} onChange={event => setIterations(Number(event.target.value))} /></label>
      <button className="button primary" disabled={!sku || busy} type="submit"><Play size={16} />{busy ? 'Simulating…' : 'Simulate price'}</button><p className="small muted">Simulation does not approve or apply this price.</p>
    </form></section><section className="panel scenario-results"><div className="panel-heading"><div><h2>Forecast distribution</h2><p>Median and 95% simulation intervals</p></div><span className="neutral-tag">Preview only</span></div>
      {error && <div className="panel-body"><ErrorNotice message={error} /></div>}{busy ? <Loading label="Sampling possible outcomes…" /> : result ? <div className="panel-body"><div className="scenario-result-heading"><span>{result.name || result.sku || product?.name}</span><strong>{money(result.proposed_price ?? price, product?.currency)}</strong></div><ForecastBands forecast={result.forecast} currency={product?.currency} /><div className="margin-risk"><span>Probability of falling below the margin floor</span><strong>{result.forecast?.below_margin_floor_probability == null ? '—' : `${number(result.forecast.below_margin_floor_probability * 100, 2)}%`}</strong></div><h3>Assumptions</h3><StructuredEvidence value={result.assumptions} />{scenario?.configuration && <details className="report-details"><summary>Simulation configuration</summary><StructuredEvidence value={scenario.configuration} /></details>}</div> : !error && <EmptyState icon={<FlaskConical size={34} />} title="Make uncertainty visible"><p>Select a product and a candidate price to explore revenue, profit, units, and margin distributions.</p></EmptyState>}
    </section></div>
  </>;
}
