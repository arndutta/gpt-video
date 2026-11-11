import { useState } from 'react';
import { BookOpen } from 'lucide-react';
import { api, errorMessage } from '../api/client';
import { ErrorNotice } from './Common';
import { StructuredEvidence } from './Forecast';

type Source = { citation_id?: string; id?: string; title?: string; text?: string; source_id?: string; version?: string; [key: string]: unknown };

export function citationIds(value: unknown): string[] {
  if (!value) return [];
  if (typeof value === 'string') return [value];
  if (Array.isArray(value)) return [...new Set(value.flatMap(citationIds))];
  if (typeof value === 'object') {
    const source = value as Source;
    if (source.citation_id) return [source.citation_id];
    return ['citations', 'citation_ids', 'sources', 'chunks'].flatMap(key => citationIds(source[key]));
  }
  return [];
}

export function EvidenceSources({ value }: { value: unknown }) {
  const ids = citationIds(value);
  const [selected, setSelected] = useState<Source>();
  const [error, setError] = useState('');
  const [busy, setBusy] = useState('');
  async function inspect(id: string) {
    setBusy(id); setError(''); setSelected(undefined);
    try { setSelected(await api<Source>(`/grounding/citations/${encodeURIComponent(id)}`)); }
    catch (reason) { setError(errorMessage(reason)); }
    finally { setBusy(''); }
  }
  return <div className="form-stack">{ids.length ? ids.map(id => <button key={id} className="citation-button" disabled={!!busy} onClick={() => void inspect(id)}><BookOpen size={13} /> {busy === id ? 'Loading source…' : id}</button>) : <p className="small muted">No document citation IDs supplied.</p>}{error && <ErrorNotice message={error} />}{selected && <div className="citation-content"><strong>{selected.title || selected.source_id}</strong><p>{selected.text}</p><StructuredEvidence value={{ source_id: selected.source_id, version: selected.version, citation_id: selected.citation_id }} /></div>}</div>;
}
