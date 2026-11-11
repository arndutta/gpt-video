import { Clock, RefreshCw, ShieldAlert } from 'lucide-react';
import { api, errorMessage, money, number } from '../api/client';
import type { Dashboard as DashboardData } from '../api/operations';
import { usePolling } from '../api/usePolling';
import { useState } from 'react';
import { ErrorNotice } from '../components/Common';
import { StructuredEvidence } from '../components/Forecast';

function ratio(numerator?: number, denominator?: number) {
  return numerator == null || !denominator ? 'Pending' : `${number(numerator / denominator * 100, 1)}%`;
}

export function Dashboard() {
  const dashboard = usePolling<DashboardData>('/dashboard', 5000);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  async function feedback() {
    setBusy(true); setError('');
    try { await api('/feedback/refresh', { method: 'POST' }); dashboard.reload(); }
    catch (reason) { setError(errorMessage(reason)); }
    finally { setBusy(false); }
  }
  const data = dashboard.data;
  const count = data?.recommendations ?? 0;
  const decisions = data?.decisions;
  const realized = data?.realized;
  return <>
    {(dashboard.error || error) && <ErrorNotice message={error || dashboard.error} />}
    <div className="metric-grid">
      <div className="metric-card"><div className="metric-label">Forecast revenue</div><strong>{money(data?.forecast?.revenue)}</strong><span>{data?.horizon_days ? `${data.horizon_days}-day horizon` : 'Horizon recorded per run'} · {data?.scope || 'Grounded recommendations'}</span></div>
      <div className="metric-card"><div className="metric-label">Forecast gross profit</div><strong>{money(data?.forecast?.gross_profit)}</strong><span>Expected distribution mean · forecast</span></div>
      <div className="metric-card"><div className="metric-label">Human acceptance</div><strong>{ratio(decisions?.approved, decisions?.total)}</strong><span>{number(decisions?.approved)} approved / {number(decisions?.total)} recorded decisions</span></div>
      <div className="metric-card"><div className="metric-label">Automatic share</div><strong>{ratio(decisions?.automatic, count)}</strong><span>{number(decisions?.automatic)} system approvals / {number(count)} recommendations</span></div>
    </div>
    <div className="dashboard-grid">
      <section className="panel"><div className="panel-heading"><div><h2>Autonomy and escalation</h2><p>Band assignment is separate from approval and execution.</p></div></div><div className="panel-body dashboard-bars">{(['auto_approve', 'review', 'escalate'] as const).map(band => <div key={band} className={`dashboard-bar ${band}`}><span>{band === 'auto_approve' ? 'Auto-approve' : band === 'review' ? 'Review' : 'Escalate'}</span><div><span style={{ width: `${count ? (data?.bands?.[band] || 0) / count * 100 : 0}%` }} /></div><strong>{number(data?.bands?.[band] ?? 0)}</strong></div>)}<p className="metric-footnote">Denominator: {number(count)} grounded recommendations. Supervised mode requires a human decision for every band.</p><h3>Escalation causes</h3><StructuredEvidence value={data?.escalation_causes} /></div></section>
      <section className="panel"><div className="panel-heading"><div><h2>Realized performance</h2><p>Aligned post-push sales windows from Commerce.</p></div><button className="icon-button" disabled={busy || !!dashboard.error} onClick={() => void feedback()} aria-label="Refresh realized outcomes"><RefreshCw className={busy ? 'spin' : ''} size={16} /></button></div><div className="panel-body">{(!realized || realized.status === 'pending' || realized.revenue == null) && <div className="pending-outcome"><Clock size={17} /><span>Outcomes remain pending until a complete observation window is available.</span></div>}<div className="mini-metrics"><div><span>Observed revenue</span><strong>{money(realized?.revenue)}</strong></div><div><span>Observed gross profit</span><strong>{money(realized?.gross_profit)}</strong></div></div><p className="metric-footnote">Observed: {number(realized?.observed_skus)} SKUs · Pending: {number(realized?.pending_skus)} SKUs. Missing sales are never treated as zero.</p><StructuredEvidence value={{ forecast_error: realized?.forecast_error, interval_coverage: realized?.interval_coverage, status: realized?.status }} /><details className="report-details"><summary>Matched forecasts for observed SKUs</summary><p className="small muted">These comparisons include only the mature observed SKU windows above. The all-run forecast cards use a separate scope.</p><StructuredEvidence value={{ observed_skus: realized?.observed_skus, matched_forecast: realized?.matched_forecast, matched_baseline_forecast: realized?.matched_baseline_forecast, revenue_error: realized?.revenue_error, gross_profit_error: realized?.gross_profit_error, units_error: realized?.units_error }} /></details></div></section>
      <section className="panel"><div className="panel-heading"><div><h2>AI and conventional baseline</h2><p>Forecast values use a common SKU set and horizon.</p></div></div><div className="table-scroll"><table className="comparison-table"><thead><tr><th>Metric</th><th className="numeric">AI forecast</th><th className="numeric">Baseline forecast</th></tr></thead><tbody><tr><td>Revenue</td><td className="numeric">{money(data?.forecast?.revenue)}</td><td className="numeric">{money(data?.forecast?.baseline_revenue)}</td></tr><tr><td>Gross profit</td><td className="numeric">{money(data?.forecast?.gross_profit)}</td><td className="numeric">{money(data?.forecast?.baseline_gross_profit)}</td></tr></tbody></table></div><p className="report-footnote">These are forecast comparisons. The realized view above requires post-change observations.</p></section>
      <section className="panel"><div className="panel-heading"><div><h2>Stability and learning</h2><p>Retained oscillation incidents and forecast-error trends.</p></div></div><div className="panel-body">{data?.stability?.error_trend === 'widening' && <div className="notice warning"><ShieldAlert size={16} /><span>Forecast error is widening. Review evidence before increasing autonomy.</span></div>}<StructuredEvidence value={data?.stability} /><details className="report-details"><summary>Mode history</summary><StructuredEvidence value={data?.mode_history} /></details></div></section>
    </div>
    {!!data?.limitations?.length && <div className="notice info"><StructuredEvidence value={data.limitations} /></div>}
  </>;
}
