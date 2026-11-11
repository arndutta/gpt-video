import { useState } from 'react';
import { Download, History, RefreshCw } from 'lucide-react';
import { errorMessage, timestamp } from '../api/client';
import type { AuditEvent } from '../api/operations';
import { usePolling } from '../api/usePolling';
import { EmptyState, ErrorNotice, Loading, PageHeading } from '../components/Common';
import { StructuredEvidence } from '../components/Forecast';

export function AuditPage() {
  const [automatic, setAutomatic] = useState(false);
  const [runId, setRunId] = useState('');
  const [sku, setSku] = useState('');
  const [search, setSearch] = useState('');
  const [error, setError] = useState('');
  const [exporting, setExporting] = useState(false);
  const query = new URLSearchParams({ ...(automatic ? { automatic: 'true' } : {}), ...(runId ? { run_id: runId } : {}), ...(sku ? { sku } : {}) }).toString();
  const audit = usePolling<{ items: AuditEvent[]; total?: number }>(`/audit${query ? `?${query}` : ''}`, 5000);
  const filtered = (audit.data?.items || []).filter(event => JSON.stringify(event).toLowerCase().includes(search.toLowerCase()));
  async function download() {
    setExporting(true); setError('');
    try {
      const response = await fetch(`/api/audit/export${query ? `?${query}` : ''}`);
      if (!response.ok) throw new Error(`Audit export failed (${response.status}).`);
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a'); link.href = url; link.download = `pricing-audit-${new Date().toISOString().slice(0, 10)}.json`; link.click();
      window.setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (reason) { setError(errorMessage(reason)); }
    finally { setExporting(false); }
  }
  return <>
    <PageHeading eyebrow="APPEND-ONLY EVIDENCE" title="Audit trail" action={<div className="button-row"><button className="button secondary" onClick={audit.reload}><RefreshCw size={16} />Refresh</button><button className="button secondary" disabled={exporting || !!audit.error} onClick={() => void download()}><Download size={16} />{exporting ? 'Exporting…' : 'Export JSON'}</button></div>}>Follow each run from cited inputs through approval, mode changes, and Commerce receipts.</PageHeading>
    {(audit.error || error) && <ErrorNotice message={error || audit.error} />}
    <section className="panel"><div className="audit-filters"><label>Search loaded events<input value={search} onChange={event => setSearch(event.target.value)} placeholder="Event, actor, decision…" /></label><label>Run ID<input value={runId} onChange={event => setRunId(event.target.value)} placeholder="All runs" /></label><label>SKU<input value={sku} onChange={event => setSku(event.target.value)} placeholder="All products" /></label><label className="check-label"><input className="selection-checkbox" type="checkbox" checked={automatic} onChange={event => setAutomatic(event.target.checked)} />System-only events</label></div>
      {audit.loading && !audit.data ? <Loading label="Loading audit evidence…" /> : filtered.length ? <div className="audit-list">{filtered.map((event, index) => <details key={String(event.id ?? index)} className="audit-event"><summary><History size={15} /><strong>{String(event.event || event.kind || event.action || 'Audit event').replaceAll('_', ' ')}</strong><time>{timestamp(event.created_at || event.timestamp)}</time></summary><StructuredEvidence value={event} /></details>)}</div> : <EmptyState icon={<History size={32} />} title="No matching audit events"><p>Change the filters or run an analysis to inspect its evidence chain.</p></EmptyState>}
      <p className="report-footnote">Showing {filtered.length} events from this response{audit.data?.total != null ? ` (${audit.data.total} matching in storage)` : ''}. Export includes the server-side filters. Audit records cannot be edited here.</p>
    </section>
  </>;
}
