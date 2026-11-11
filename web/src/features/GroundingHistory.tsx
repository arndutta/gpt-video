import { CircleCheck, CircleX, Clock3, FileText, History, LoaderCircle, TriangleAlert } from 'lucide-react';
import { number, timestamp } from '../api/client';
import { collectionLabel } from '../api/grounding';
import type { GroundingUpload, UploadStatus } from '../api/grounding';
import { ErrorNotice, Loading } from '../components/Common';

const statuses = {
  queued: { label: 'Queued', icon: Clock3, className: 'pending' },
  indexing: { label: 'Indexing', icon: LoaderCircle, className: 'pending' },
  ready: { label: 'Ready', icon: CircleCheck, className: 'ready' },
  failed: { label: 'Failed', icon: CircleX, className: 'failed' },
  interrupted: { label: 'Interrupted', icon: TriangleAlert, className: 'failed' },
} satisfies Record<UploadStatus, { label: string; icon: typeof Clock3; className: string }>;

function UploadItem({ job }: { job: GroundingUpload }) {
  const status = statuses[job.status];
  return <li className="grounding-upload">
    <div className="grounding-upload-heading"><FileText size={18} /><div><strong>{job.title || job.filename}</strong><small>{job.filename} · {collectionLabel(job.collection)}</small></div><span className={`grounding-job-status ${status.className}`}><status.icon size={13} className={job.status === 'indexing' ? 'spin' : ''} />{status.label}</span></div>
    <p className="grounding-source">Source ID <code>{job.source_id}</code></p>
    {job.status === 'queued' && <p className="small muted">Waiting to index. You can close this panel while the upload continues.</p>}
    {job.status === 'indexing' && <p className="small muted">Creating searchable chunks. You can close this panel while indexing continues.</p>}
    {job.status === 'ready' && job.result && <p className="grounding-upload-result"><CircleCheck size={14} />{job.result.changed ? `${number(job.result.chunk_count)} chunks indexed` : 'This version is already indexed'}<span>Version {job.result.version}</span></p>}
    {(job.status === 'failed' || job.status === 'interrupted') && <div className="grounding-upload-error"><p>{job.error || (job.status === 'interrupted' ? 'Indexing was interrupted. Submit the file again to retry.' : 'The document could not be indexed. Check the file and try again.')}</p><p>Any previously indexed version remains available.</p>{job.error_code && <small>Reference: {job.error_code}</small>}</div>}
    <div className="grounding-upload-time"><span>Submitted {timestamp(job.created_at)}</span>{job.completed_at && <span>Finished {timestamp(job.completed_at)}</span>}</div>
  </li>;
}

export function GroundingHistory({ uploads, loaded, error }: { uploads: GroundingUpload[]; loaded: boolean; error: string }) {
  return <section className="grounding-section" aria-labelledby="grounding-history-title">
    <div className="grounding-section-heading"><h3 id="grounding-history-title"><History size={17} />Upload history</h3><span>{number(uploads.length)} uploads</span></div>
    <p className="small muted">History is saved on the server. Pending uploads update automatically while this panel is open.</p>
    {error && <ErrorNotice message={`Could not refresh upload history: ${error}`} />}
    {!loaded && !error && <Loading label="Loading upload history…" />}
    {loaded && uploads.length === 0 && !error && <div className="grounding-empty"><FileText size={25} /><strong>No documents uploaded yet</strong><p>Choose a text or Markdown file to add your first document.</p></div>}
    {uploads.length > 0 && <ul className="grounding-upload-list">{uploads.map(job => <UploadItem key={job.id} job={job} />)}</ul>}
  </section>;
}
