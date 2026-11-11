import { money, number } from '../api/client';
import type { ScenarioResult } from '../api/operations';
import type { Forecast, Recommendation } from '../api/types';
import { EvidenceSources } from '../components/EvidenceSources';
import { ForecastBands, StructuredEvidence } from '../components/Forecast';

export function ScenarioReport({ scenario }: { scenario: ScenarioResult }) {
  const items = scenario.items || scenario.recommendations || [];
  return <>{items.map((item, index) => <div className="scenario-result-card" key={`${item.sku}-${index}`}><div className="scenario-result-heading"><span>{item.name || item.sku}</span><strong>{money(item.proposed_price, item.currency)}</strong></div><ForecastBands forecast={item.forecast} currency={item.currency} /><div className="margin-risk"><span>Probability of falling below the margin floor</span><strong>{item.forecast?.below_margin_floor_probability == null ? '—' : `${number(item.forecast.below_margin_floor_probability * 100, 2)}%`}</strong></div><h3>Candidate and conventional baseline</h3><Comparison item={item} /><h3>Assumptions</h3><StructuredEvidence value={item.assumptions} /></div>)}
    {scenario.aggregate && <details className="report-details"><summary>Aggregate distributions and assumptions</summary>{scenario.aggregate.forecast && <ForecastBands forecast={scenario.aggregate.forecast} />}<StructuredEvidence value={scenario.aggregate} /></details>}
    {scenario.narrative && <><h3>Grounded interpretation</h3><StructuredEvidence value={scenario.narrative} /><EvidenceSources value={scenario.narrative} /></>}
    {!!scenario.narrative_status && <p className="notice warning">Grounded interpretation unavailable: {String(scenario.narrative_status).replaceAll('_', ' ')}. Numerical results are retained.</p>}
    {scenario.configuration && <details className="report-details"><summary>Simulation configuration and versions</summary><StructuredEvidence value={scenario.configuration} /></details>}
    {!items.length && <StructuredEvidence value={scenario} />}
  </>;
}

function Comparison({ item }: { item: Recommendation }) {
  const current = item.current_forecast as Forecast | undefined;
  const ai = item.ai_forecast as Forecast | undefined;
  const metrics = [{ name: 'Revenue', key: 'revenue' }, { name: 'Gross profit', key: 'gross_profit' }] as const;
  return <div className="table-scroll"><table className="comparison-table"><thead><tr><th>Forecast mean</th><th className="numeric">Candidate</th><th className="numeric">Current</th>{ai && <th className="numeric">AI recommendation</th>}<th className="numeric">Baseline</th></tr></thead><tbody>{metrics.map(metric => <tr key={metric.key}><td>{metric.name}</td><td className="numeric">{money(item.forecast?.[metric.key]?.mean, item.currency)}</td><td className="numeric">{money(current?.[metric.key]?.mean, item.currency)}</td>{ai && <td className="numeric">{money(ai[metric.key]?.mean, item.currency)}</td>}<td className="numeric">{money(item.baseline?.forecast?.[metric.key]?.mean, item.currency)}</td></tr>)}</tbody></table><p className="metric-footnote">Baseline price {money(item.baseline?.price, item.currency)}. All displayed forecasts use the retained horizon and scenario assumptions.</p></div>;
}
