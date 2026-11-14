import { useState } from 'react';
import type { Distribution, Forecast, Recommendation } from '../api/types';
import { money, number } from '../api/client';
import { EvidenceSources } from './EvidenceSources';
import './forecast.css';

export function DistributionBand({ label, distribution, format = money }: { label: string; distribution?: Distribution; format?: (value: unknown) => string }) {
  const [selected, setSelected] = useState<'lower' | 'median' | 'upper'>('median');
  if (!distribution) return null;
  const lower = distribution.lower, upper = distribution.upper, median = distribution.median ?? distribution.mean;
  const valid = lower != null && upper != null && median != null && Number.isFinite(lower + upper + median) && lower <= upper && (distribution.median == null || (median >= lower && median <= upper));
  const domainLow = valid ? Math.min(lower, median) : 0;
  const domainHigh = valid ? Math.max(upper, median) : 0;
  const pointX = (value?: number) => value != null && domainHigh > domainLow ? 20 + (value - domainLow) / (domainHigh - domainLow) * 260 : 150;
  const central = distribution.median != null ? 'Median' : 'Mean';
  const points = [{ key: 'lower' as const, title: 'Lower bound', value: lower, x: pointX(lower) }, { key: 'median' as const, title: central, value: median, x: pointX(median) }, { key: 'upper' as const, title: 'Upper bound', value: upper, x: pointX(upper) }];
  const current = points.find(point => point.key === selected)!;
  const display = (value: unknown) => value == null || !Number.isFinite(Number(value)) ? '—' : format(value);
  return <div className="distribution-card interval-card"><div className="distribution-heading"><span>{label}</span><strong>{display(median)}</strong></div>{valid ? <>
    <svg className="interval-plot" viewBox="0 0 300 74" role="img" aria-label={`${label}: ${central.toLowerCase()} ${display(median)}, 95 percent interval ${display(lower)} to ${display(upper)}`}><line className="interval-guide" x1="20" y1="18" x2="20" y2="62" /><line className="interval-guide" x1="150" y1="18" x2="150" y2="62" /><line className="interval-guide" x1="280" y1="18" x2="280" y2="62" /><rect className="interval-fill" x={pointX(lower)} y="33" width={pointX(upper) - pointX(lower)} height="16" rx="8" /><line className="interval-line" x1={pointX(lower)} y1="41" x2={pointX(upper)} y2="41" />{points.map(point => <g key={point.key} className={`interval-point ${selected === point.key ? 'active' : ''}`}><circle className="interval-halo" cx={point.x} cy="41" r="10" /><line x1={point.x} y1={point.key === 'median' ? 26 : 34} x2={point.x} y2={point.key === 'median' ? 56 : 48} /><circle cx={point.x} cy="41" r={point.key === 'median' ? 5 : 3.5} /></g>)}</svg>
    <div className="interval-controls" role="group" aria-label={`${label} interval values`}>{points.map(point => <button key={point.key} aria-label={`${label} ${point.title.toLowerCase()}`} aria-pressed={selected === point.key} onClick={() => setSelected(point.key)} onFocus={() => setSelected(point.key)} onMouseEnter={() => setSelected(point.key)}><span>{point.title}</span><strong>{display(point.value)}</strong></button>)}</div>
    <div className="interval-caption"><span>95% simulation interval</span><span aria-live="polite">{current.title}: {display(current.value)}</span></div>
  </> : <p className="small muted interval-unavailable">Interval unavailable</p>}</div>;
}

export function ForecastBands({ forecast, currency = 'USD' }: { forecast?: Forecast; currency?: string }) {
  if (!forecast) return <p className="muted">Forecast distributions are unavailable.</p>;
  return <div className="forecast-bands"><DistributionBand label="Revenue" distribution={forecast.revenue} format={value => money(value, currency)} /><DistributionBand label="Gross profit" distribution={forecast.gross_profit} format={value => money(value, currency)} /><DistributionBand label="Units sold" distribution={forecast.units || forecast.demand} format={value => number(value, 1)} /><DistributionBand label="Gross margin" distribution={forecast.margin_rate} format={value => `${number(Number(value) * 100, 1)}%`} /></div>;
}

export function RecommendationEvidence({ item }: { item: Recommendation }) {
  const elasticity = item.elasticity;
  const grounded = typeof item.band === 'string' || !!item.rationale;
  return <div className="drawer-body"><div className="price-comparison"><div><span>Current price</span><strong>{money(item.current_price, item.currency)}</strong></div><span>→</span><div><span>{grounded ? 'Proposed price' : 'Preview price'}</span><strong>{money(item.proposed_price, item.currency)}</strong></div></div>
    <div className="notice info">{grounded ? 'This is retained run evidence. Current decisions, revisions, and execution outcomes are available in the review queue.' : 'This candidate is an analytical preview. It has no approval status and cannot be pushed to Commerce.'}</div>
    {grounded && <><h3>Grounded rationale</h3><StructuredEvidence value={item.rationale} /><EvidenceSources value={{ citations: item.citations, sources: item.sources }} /><h3>Rules, banding, and stability</h3><StructuredEvidence value={{ band: item.band, band_reasons: item.band_reasons, compliance: item.compliance, stability: item.stability }} /></>}
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
