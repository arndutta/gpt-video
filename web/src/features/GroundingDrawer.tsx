import { useRef, useState } from 'react';
import type { FormEvent } from 'react';
import { FileUp, Info, RefreshCw, Upload } from 'lucide-react';
import { knowledgeCollections } from '../api/grounding';
import type { KnowledgeCollection } from '../api/grounding';
import { Drawer, ErrorNotice } from '../components/Common';
import { GroundingCollections } from './GroundingCollections';
import { GroundingHistory } from './GroundingHistory';
import { useGrounding } from './useGrounding';
import './grounding.css';

export function GroundingDrawer({ onClose }: { onClose: () => void }) {
  const grounding = useGrounding();
  const fileInput = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File>();
  const [collection, setCollection] = useState<KnowledgeCollection>('user_uploads');
  const [title, setTitle] = useState('');
  const [sourceId, setSourceId] = useState('');
  const [version, setVersion] = useState('');
  const [validationError, setValidationError] = useState('');
  const [accepted, setAccepted] = useState('');

  function selectFile(value?: File) {
    setFile(value);
    setAccepted('');
    setValidationError(value ? validateFile(value) : '');
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    setAccepted('');
    const error = file ? validateFile(file) : 'Choose a .txt or .md document first.';
    setValidationError(error);
    if (error || !file) return;
    const body = new FormData();
    body.set('file', file);
    body.set('collection', collection);
    if (title.trim()) body.set('title', title.trim());
    if (sourceId.trim()) body.set('source_id', sourceId.trim());
    if (version.trim()) body.set('version', version.trim());
    const job = await grounding.upload(body);
    if (job) {
      setAccepted(`${job.filename} accepted. Follow its indexing status in upload history.`);
      setFile(undefined);
      if (fileInput.current) fileInput.current.value = '';
    }
  }

  return <Drawer title="Knowledge & grounding" subtitle="Documents, indexing status, and collection statistics" onClose={onClose}>
    <div className="drawer-body grounding-body">
      <div className="grounding-intro"><div className="notice info"><Info size={18} /><span>Documents are available for retrieval. Grounded AI reasoning is next.</span></div><button className="button secondary small-button" type="button" onClick={grounding.refresh} aria-label="Refresh document collections and upload history"><RefreshCw size={15} className={grounding.refreshing ? 'spin' : ''} />Refresh</button></div>
      <form className="grounding-section grounding-upload-form" onSubmit={submit}>
        <div className="grounding-section-heading"><h3><FileUp size={18} />Upload a document</h3></div>
        <p className="small muted">Add pricing policies, market research, or product information for retrieval.</p>
        <label htmlFor="grounding-file">Document<input id="grounding-file" ref={fileInput} type="file" accept=".txt,.md,text/plain,text/markdown" onChange={event => selectFile(event.target.files?.[0])} disabled={grounding.uploading} aria-describedby="grounding-file-hint" /></label>
        <p id="grounding-file-hint" className="input-hint">One UTF-8 text (.txt) or Markdown (.md) file, up to 2 MB. Empty files cannot be indexed.</p>
        <label htmlFor="grounding-collection">Collection<select id="grounding-collection" value={collection} onChange={event => setCollection(event.target.value as KnowledgeCollection)} disabled={grounding.uploading}>{knowledgeCollections.map(item => <option key={item.value} value={item.value}>{item.label}</option>)}</select></label>
        <details className="grounding-advanced"><summary>Document identity & version <span>Optional</span></summary><div>
          <p className="input-hint">Use the same source ID and collection when updating a document. Leave version blank to generate it from the content, or supply a new version for a revision.</p>
          <label htmlFor="grounding-title">Document title<input id="grounding-title" value={title} onChange={event => setTitle(event.target.value)} maxLength={256} placeholder="Use the filename" disabled={grounding.uploading} /></label>
          <label htmlFor="grounding-source">Stable source ID<input id="grounding-source" value={sourceId} onChange={event => setSourceId(event.target.value)} maxLength={128} pattern="[A-Za-z0-9][A-Za-z0-9._:\-]*" title="Start with a letter or number. Use letters, numbers, periods, underscores, colons, or hyphens." placeholder="For example: pricing-policy" spellCheck={false} disabled={grounding.uploading} /></label>
          <label htmlFor="grounding-version">Version<input id="grounding-version" value={version} onChange={event => setVersion(event.target.value)} maxLength={128} placeholder="Generate from content" disabled={grounding.uploading} /></label>
          <p className="input-hint">An existing source version is immutable. Older versions stay available for their citations.</p>
        </div></details>
        {(validationError || grounding.uploadError) && <ErrorNotice message={validationError || grounding.uploadError} />}
        <button type="submit" className="button primary" disabled={grounding.uploading || !file || Boolean(validationError)}><Upload size={16} />{grounding.uploading ? 'Submitting document…' : 'Upload & index'}</button>
        {accepted && <p className="grounding-accepted" role="status">{accepted}</p>}
      </form>
      <GroundingCollections statistics={grounding.statistics} error={grounding.statisticsError} />
      <GroundingHistory uploads={grounding.uploads} loaded={grounding.historyLoaded} error={grounding.historyError} />
    </div>
  </Drawer>;
}

function validateFile(file: File): string {
  if (!/\.(txt|md)$/i.test(file.name)) return 'Choose a text (.txt) or Markdown (.md) document.';
  if (file.size === 0) return 'This file is empty. Choose a document with text to index.';
  if (file.size > 2_000_000) return 'This file exceeds the 2 MB limit. Choose a smaller document.';
  return '';
}
