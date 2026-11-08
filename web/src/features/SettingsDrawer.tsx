import { useEffect, useState } from 'react';
import type { FormEvent } from 'react';
import { Check, Database, KeyRound, ShieldAlert } from 'lucide-react';
import { api, errorMessage, number } from '../api/client';
import type { Settings } from '../api/types';
import { Drawer, ErrorNotice, Loading } from '../components/Common';

export function SettingsDrawer({ onClose, onSaved }: { onClose: () => void; onSaved: () => void }) {
  const [settings, setSettings] = useState<Settings>();
  const [gatewayUrl, setGatewayUrl] = useState('');
  const [port, setPort] = useState('');
  const [apiKey, setApiKey] = useState('');
  const [verify, setVerify] = useState(true);
  const [error, setError] = useState('');
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  useEffect(() => {
    const controller = new AbortController();
    api<Settings>('/settings', { signal: controller.signal }).then(value => {
      setSettings(value); setGatewayUrl(value.gateway_url || ''); setPort(value.gateway_port ? String(value.gateway_port) : ''); setVerify(value.verify_tls);
    }).catch(reason => { if (!controller.signal.aborted) setError(errorMessage(reason)); });
    return () => controller.abort();
  }, []);
  async function submit(event: FormEvent) {
    event.preventDefault(); setError(''); setSaved(false); setSaving(true);
    const payload: Record<string, unknown> = { gateway_url: gatewayUrl, gateway_port: port ? Number(port) : null, verify_tls: verify };
    if (apiKey) payload.api_key = apiKey;
    setApiKey('');
    try {
      const updated = await api<Settings>('/settings', { method: 'PATCH', body: JSON.stringify(payload) });
      setSettings(updated); setSaved(true); onSaved();
    } catch (reason) { setError(errorMessage(reason)); }
    finally { setSaving(false); }
  }
  return <Drawer title="Workspace settings" subtitle="Runtime configuration for this local session" onClose={onClose}>
    {error && <ErrorNotice message={error} />}
    {!settings && !error && <Loading label="Loading settings…" />}
    {settings && <form className="drawer-body" onSubmit={submit}>
      <div className="section-label"><KeyRound size={17} />Model gateway</div>
      <p className="muted small">Connection settings are ready for the agent integration. Quantitative previews make no LLM calls.</p>
      <label>Gateway URL<input type="url" value={gatewayUrl} onChange={event => { setGatewayUrl(event.target.value); setSaved(false); }} placeholder="https://gateway.example.com" /></label>
      <label>Port <span className="muted">(optional)</span><input type="number" min="1" max="65535" value={port} onChange={event => setPort(event.target.value)} placeholder="Use URL default" /></label>
      <label>API key<div className="input-hint">{settings.key_configured ? 'A key is configured. Enter a value to replace it.' : 'No key configured.'}</div><input type="password" value={apiKey} onChange={event => setApiKey(event.target.value)} autoComplete="off" spellCheck={false} placeholder="Enter a new key" /></label>
      <p className="small muted">Submitted keys stay in server memory. This field clears on submission; saved keys are never returned to the browser.</p>
      <div className="switch-row"><div><strong>Disable SSL verification</strong><p className="small muted">Corporate network prototype only</p></div><button type="button" className={`switch ${!verify ? 'on' : ''}`} role="switch" aria-checked={!verify} aria-label="Disable SSL verification" disabled={!settings.allow_insecure_tls} onClick={() => setVerify(value => !value)}><span /></button></div>
      {!settings.allow_insecure_tls && <p className="small muted">Unavailable unless ALLOW_INSECURE_TLS is enabled on the server.</p>}
      {!verify && <div className="notice warning"><ShieldAlert size={18} /><span>Certificate verification is disabled. Connection identity cannot be verified.</span></div>}
      <button className="button primary" type="submit" disabled={saving}>{saving ? 'Applying settings…' : 'Apply settings'}</button>
      {saved && <p className="success-text" role="status"><Check size={16} />Settings applied for this session.</p>}
      <hr />
      <div className="section-label"><Database size={17} />LLM cache</div>
      {settings.cache?.available === false ? <div className="notice info">LLM caching is not enabled in this build.</div> : <div className="mini-metrics"><div><span>Hits</span><strong>{number(settings.cache?.hits)}</strong></div><div><span>Misses</span><strong>{number(settings.cache?.misses)}</strong></div></div>}
      <p className="small muted">Preview computations do not use the LLM cache. Cache activity appears when grounded agents are enabled.</p>
    </form>}
  </Drawer>;
}
