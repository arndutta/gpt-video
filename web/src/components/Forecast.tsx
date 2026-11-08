import type { Distribution, Forecast, Recommendation } from '../api/types';
import { money, number } from '../api/client';

export function DistributionBand({ label, distribution, format = money }: { label: string; distribution?: Distribution; format?: (value: unknown) => string }) {
  if (!distribution) return null;
  const lower = distribution.lower, upper = distribution.upper, median = distribution.median ?? distribution.mean;
  const valid = lower != null && upper != null && median != null && Number.isFinite(lower + upper + median);
  const position = valid && upper > lower ? Math.min(100, Math.max(0, (median - lower) / (upper - lower) * 100)) : 50;
  return <div className="distribution-card"><div className="distribution-heading"><span>{label}</span><strong>{format(median)}</strong></div>{valid ? <><div className="distribution-track" role="img" aria-label={`${label}: median ${format(median)}, 95 percent interval ${format(lower)} to ${format(upper)}`}><div className="distribution-range" /><span className="distribution-marker" style={{ left: `${position}%` }} /></div><div className="distribution-labels"><span>{format(lower)}</span><span>95% interval</span><span>{format(upper)}</span></div></> : <p className="small muted">Interval unavailable</p>}</div>;
}

export function ForecastBands({ forecast, currency = 'USD' }: { forecast?: Forecast; currency?: string }) {
  if (!forecast) return <p className="muted">Forecast distributions are unavailable.</p>;
  return <div className="forecast-bands"><DistributionBand label="Revenue" distribution={forecast.revenue} format={value => money(value, currency)} /><DistributionBand label="Gross profit" distribution={forecast.gross_profit} format={value => money(value, currency)} /><DistributionBand label="Units sold" distribution={forecast.units || forecast.demand} format={value => number(value, 1)} /><DistributionBand label="Gross margin" distribution={forecast.margin_rate} format={value => `${number(Number(value) * 100, 1)}%`} /></div>;
}

export function RecommendationEvidence({ item }: { item: Recommendation }) {
  const elasticity = item.elasticity;
  return <div className="drawer-body"><div className="price-comparison"><div><span>Current price</span><strong>{money(item.current_price, item.currency)}</strong></div><span>→</span><div><span>Preview price</span><strong>{money(item.proposed_price, item.currency)}</strong></div></div>
    <div className="notice info">This candidate is an analytical preview. It has no approval status and cannot be pushed to Commerce.</div>
    <h3>Forecast distributions</h3><ForecastBands forecast={item.forecast} currency={item.currency} />
    <h3>Elasticity estimate</h3><div className="evidence-grid"><div><span>Coefficient</span><strong>{number(elasticity?.estimate, 3)}</strong></div><div><span>95% interval</span><strong>{number(elasticity?.lower, 3)} to {number(elasticity?.upper, 3)}</strong></div><div><span>Observations</span><strong>{number(elasticity?.sample_size)}</strong></div><div><span>Confidence</span><strong>{number(item.confidence * 100, 1)}%</strong></div></div>
    <h3>Baseline comparison</h3><p className="muted small">Cost-plus/category-discount price: {money(item.baseline?.price, item.currency)}. Forecasts use the same simulation assumptions.</p><ForecastBands forecast={item.baseline?.forecast} currency={item.currency} />
    <h3>Assumptions</h3><StructuredEvidence value={item.assumptions} />
    {item.confidence_factors && <><h3>Confidence factors</h3><StructuredEvidence value={item.confidence_factors} /></>}
  </div>;
}

export function StructuredEvidence({ value }: { value: unknown }) {
  if (value == null) return <p className="muted small">No additional details supplied.</p>;
  if (typeof value === 'string') return <p className="small muted">{value}</p>;
  if (Array.isArray(value)) return <ul className="assumption-list">{value.map((item, index) => <li key={index}>{typeof item === 'string' ? item : JSON.stringify(item)}</li>)}</ul>;
  if (typeof value === 'object') return <dl className="evidence-list">{Object.entries(value).map(([key, item]) => <div key={key}><dt>{key.replaceAll('_', ' ')}</dt><dd>{typeof item === 'object' ? JSON.stringify(item) : String(item)}</dd></div>)}</dl>;
  return <p className="small muted">{String(value)}</p>;
}
