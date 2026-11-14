import { useEffect, useState } from 'react';
import type { FormEvent } from 'react';
import { Check, Database, KeyRound, ShieldAlert } from 'lucide-react';
import { api, errorMessage, number, timestamp } from '../api/client';
import type { Settings } from '../api/types';
import { Drawer, ErrorNotice, Loading } from '../components/Common';
import { PolicySettings } from './PolicySettings';
import type { ModelMonitor } from '../api/operations';
import { usePolling } from '../api/usePolling';

type GatewayCheck = { status: string; verified: boolean; checked_at?: string; detail: string; structured_output_verified: boolean; missing_roles?: string[]; missing_models?: string[] };

export function SettingsDrawer({ onClose, onSaved }: { onClose: () => void; onSaved: () => void }) {
  const [settings, setSettings] = useState<Settings>();
  const [gatewayUrl, setGatewayUrl] = useState('');
  const [port, setPort] = useState('');
  const [apiKey, setApiKey] = useState('');
  const [verify, setVerify] = useState(true);
  const [error, setError] = useState('');
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [dirty, setDirty] = useState(false);
  function markEdited() { setDirty(true); setSaved(false); setGatewayCheck(undefined); }
  const [models, setModels] = useState<Record<string, string>>({ router: '', narrator: '', analyst: '', strategist: '' });
  const [checkingGateway, setCheckingGateway] = useState(false);
  const [gatewayCheck, setGatewayCheck] = useState<GatewayCheck>();
  const monitor = usePolling<ModelMonitor>('/monitor', 3000);
  const cache = monitor.data?.cache || settings?.cache;
  useEffect(() => {
    const controller = new AbortController();
    api<Settings>('/settings', { signal: controller.signal }).then(value => {
      setSettings(value); setGatewayUrl(value.gateway_url || ''); setPort(value.gateway_port ? String(value.gateway_port) : ''); setVerify(value.verify_tls);
      setModels(Object.fromEntries(['router', 'narrator', 'analyst', 'strategist'].map(role => [role, value.models?.[role] || ''])));
    }).catch(reason => { if (!controller.signal.aborted) setError(errorMessage(reason)); });
    return () => controller.abort();
  }, []);
  async function submit(event: FormEvent) {
    event.preventDefault(); setError(''); setSaved(false); setGatewayCheck(undefined); setSaving(true);
    const payload: Record<string, unknown> = { gateway_url: gatewayUrl, gateway_port: port ? Number(port) : null, verify_tls: verify, ...Object.fromEntries(Object.entries(models).map(([role, model]) => [`model_${role}`, model || null])) };
    if (apiKey) payload.api_key = apiKey;
    setApiKey('');
    try {
      const updated = await api<Settings>('/settings', { method: 'PATCH', body: JSON.stringify(payload) });
      setSettings(updated); setDirty(false); setSaved(true); onSaved();
    } catch (reason) { setError(errorMessage(reason)); }
    finally { setSaving(false); }
  }
  async function verifyGateway() {
    setCheckingGateway(true); setGatewayCheck(undefined); setError('');
    try { setGatewayCheck(await api<GatewayCheck>('/gateway/check', { method: 'POST' })); }
    catch (reason) { setError(errorMessage(reason)); }
    finally { setCheckingGateway(false); }
  }
  return <Drawer title="Workspace settings" subtitle="Runtime configuration for this local session" onClose={onClose}>
    {error && <ErrorNotice message={error} />}
    {!settings && !error && <Loading label="Loading settings…" />}
    {settings && <><form className="drawer-body" onSubmit={submit}><fieldset className="settings-fields" disabled={saving || checkingGateway}>
      <div className="section-label"><KeyRound size={17} />Model gateway</div>
      <p className="muted small">Grounded agents use these backend-only aliases through the configured gateway. Quantitative previews make no language-model calls.</p>
      <label>Gateway URL<input type="url" value={gatewayUrl} onChange={event => { setGatewayUrl(event.target.value); markEdited(); }} placeholder="https://gateway.example.com" /></label>
      <label>Port <span className="muted">(optional)</span><input type="number" min="1" max="65535" value={port} onChange={event => { setPort(event.target.value); markEdited(); }} placeholder="Use URL default" /></label>
      <label>API key<div className="input-hint">{settings.key_configured ? 'A key is configured. Enter a value to replace it.' : 'No key configured.'}</div><input type="password" value={apiKey} onChange={event => { setApiKey(event.target.value); markEdited(); }} autoComplete="off" spellCheck={false} placeholder="Enter a new key" /></label>
      <p className="small muted">Submitted keys stay in server memory. This field clears on submission; saved keys are never returned to the browser.</p>
      <div className="form-two-columns">{['router', 'narrator', 'analyst', 'strategist'].map(role => <label key={role}>{role[0].toUpperCase() + role.slice(1)} model alias<input value={models[role]} onChange={event => { setModels(value => ({ ...value, [role]: event.target.value })); markEdited(); }} placeholder="Gateway model alias" maxLength={200} /></label>)}</div>
      <div className="switch-row"><div><strong>Disable SSL verification</strong><p className="small muted">Corporate network prototype only</p></div><button type="button" className={`switch ${!verify ? 'on' : ''}`} role="switch" aria-checked={!verify} aria-label="Disable SSL verification" disabled={!settings.allow_insecure_tls} onClick={() => { setVerify(value => !value); markEdited(); }}><span /></button></div>
      {!settings.allow_insecure_tls && <p className="small muted">Unavailable unless ALLOW_INSECURE_TLS is enabled on the server.</p>}
      {!verify && <div className="notice warning"><ShieldAlert size={18} /><span>Certificate verification is disabled. Connection identity cannot be verified.</span></div>}
      {dirty && <p className="notice info settings-draft" role="status">You have unapplied gateway changes. Apply settings before verifying this draft.</p>}
      <button className="button primary" type="submit" disabled={saving}>{saving ? 'Applying settings…' : 'Apply settings'}</button>
      {saved && <p className="success-text" role="status"><Check size={16} />Settings applied for this session.</p>}
      <button className="button secondary" type="button" disabled={saving || checkingGateway || dirty} onClick={() => void verifyGateway()}>{checkingGateway ? 'Checking gateway…' : 'Verify current gateway settings'}</button>
      <p className="small muted">Apply edits before verifying. This checks model availability using the current server configuration; it does not verify structured generation.</p>
      {gatewayCheck && <div className={`notice ${gatewayCheck.verified ? 'info' : 'warning'}`} role="status"><div><strong>{gatewayCheck.verified ? 'Model listing verified' : `Gateway check: ${gatewayCheck.status.replaceAll('_', ' ')}`}</strong><p>{gatewayCheck.detail}</p>{gatewayCheck.missing_roles?.length ? <p>Missing roles: {gatewayCheck.missing_roles.join(', ')}</p> : null}{gatewayCheck.missing_models?.length ? <p>Unavailable aliases: {gatewayCheck.missing_models.join(', ')}</p> : null}<small>Checked {timestamp(gatewayCheck.checked_at)} · Structured generation remains unverified</small></div></div>}
      <hr />
      <div className="section-label"><Database size={17} />LLM cache</div>
      {monitor.error && <ErrorNotice message={`Cache monitor unavailable: ${monitor.error}`} />}
      {cache?.available === false ? <div className="notice info">The server reports that LLM caching is unavailable.</div> : <div className="mini-metrics"><div><span>Hits</span><strong>{number(cache?.hits)}</strong></div><div><span>Misses</span><strong>{number(cache?.misses)}</strong></div></div>}
      <p className="small muted">Cache statistics are returned by the server. Open the header monitor for live activity. Model, numeric inputs, policy, and source versions constrain reuse.</p>
    </fieldset></form><div className="drawer-body"><PolicySettings /></div></>}
  </Drawer>;
}
