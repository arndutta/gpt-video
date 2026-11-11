import { useEffect, useState } from 'react';
import { SlidersHorizontal } from 'lucide-react';
import { api, errorMessage } from '../api/client';
import { useResource } from '../api/useResource';
import { ErrorNotice, Loading } from '../components/Common';

type Policy = { version: number; thresholds: Record<string, number | string | null>; calibration?: string };
const fields = [
  { key: 'confidence_threshold', label: 'Auto confidence (0–1)', min: 0, max: 1, step: 0.01 },
  { key: 'bulk_confidence_threshold', label: 'Bulk confidence (strictly above)', min: 0, max: 1, step: 0.01 },
  { key: 'auto_delta_pct', label: 'Auto maximum change (%)', min: 0, max: 100, step: 0.1 },
  { key: 'volatility_limit', label: 'Revenue dispersion limit (SD/mean)', min: 0.01, max: 5, step: 0.01 },
  { key: 'margin_proximity_buffer', label: 'Margin floor buffer (fraction)', min: 0, max: 1, step: 0.01 },
  { key: 'minimum_sample', label: 'Auto minimum sample', min: 30, max: 10000, step: 1 },
  { key: 'oscillation_window', label: 'Oscillation history window', min: 2, max: 100, step: 1 },
  { key: 'reversals_threshold', label: 'Direction reversal threshold', min: 1, max: 20, step: 1 },
  { key: 'damping_fraction', label: 'Damped move fraction (0–1)', min: 0.01, max: 1, step: 0.01 },
  { key: 'anomaly_z_threshold', label: 'Novel price anomaly threshold', min: 1, max: 20, step: 0.1 },
  { key: 'market_gap_limit_pct', label: 'Market-gap escalation threshold (%)', min: 0, max: 1000, step: 0.1 },
  { key: 'minimum_change_seconds', label: 'Per-SKU cooldown (seconds)', min: 0, max: 604800, step: 1 },
  { key: 'hold_seconds', label: 'Autonomous Review hold (seconds)', min: 0, max: 86400, step: 1 },
] as const;

export function PolicySettings() {
  const policy = useResource<Policy>('/policy');
  const [values, setValues] = useState<Record<string, string>>({});
  const [dirty, setDirty] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  useEffect(() => { if (policy.data) setValues(Object.fromEntries(fields.map(field => [field.key, String(policy.data!.thresholds[field.key] ?? '')]))); }, [policy.data]);
  async function apply() {
    setBusy(true); setError(''); setNotice('');
    try {
      const changes = Object.fromEntries(dirty.map(key => [key, Number(values[key])]));
      await api('/policy', { method: 'PATCH', body: JSON.stringify(changes) }); setDirty([]); policy.reload(); setNotice('Policy version updated. Pending approvals from the previous policy were canceled; create a fresh run.');
    } catch (reason) { setError(errorMessage(reason)); }
    finally { setBusy(false); }
  }
  return <><hr /><div className="section-label"><SlidersHorizontal size={17} />Decision policy {policy.data ? `· v${policy.data.version}` : ''}</div>{(error || policy.error) && <ErrorNotice message={error || policy.error} />}{policy.loading && !policy.data ? <Loading label="Loading decision policy…" /> : policy.data && <><p className="small muted">Initial demonstration thresholds. They have not been calibrated against real business outcomes. Updating policy invalidates pending approval intents.</p><div className="form-two-columns">{fields.map(field => <label key={field.key}>{field.label}<input type="number" min={field.min} max={field.max} step={field.step} value={values[field.key] || ''} onChange={event => { setValues(value => ({ ...value, [field.key]: event.target.value })); setDirty(keys => [...new Set([...keys, field.key])]); setNotice(''); }} /></label>)}</div><button className="button secondary" type="button" disabled={busy || !dirty.length || dirty.some(key => values[key] === '' || !Number.isFinite(Number(values[key])))} onClick={() => void apply()}>{busy ? 'Updating policy…' : 'Apply decision policy'}</button>{notice && <p className="success-text" role="status">{notice}</p>}</>}</>;
}
