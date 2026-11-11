import { CircleCheck, Database, Info, ShieldAlert } from 'lucide-react';
import { number, timestamp } from '../api/client';
import { knowledgeCollections } from '../api/grounding';
import type { GroundingStatistics } from '../api/grounding';
import { ErrorNotice, Loading } from '../components/Common';

export function GroundingCollections({ statistics, error }: { statistics?: GroundingStatistics; error: string }) {
  const hasSnapshot = statistics && statistics.corpus_version !== null && Number.isFinite(statistics.corpus_version)
    && knowledgeCollections.every(collection => statistics.items.some(item => item.collection === collection.value
      && Number.isFinite(item.document_count) && item.document_count >= 0
      && Number.isFinite(item.chunk_count) && item.chunk_count >= 0));
  const totals = hasSnapshot ? statistics.items.reduce((sum, item) => ({
    documents: sum.documents + item.document_count, chunks: sum.chunks + item.chunk_count,
  }), { documents: 0, chunks: 0 }) : undefined;
  const embedding = statistics?.embedding;
  return <section className="grounding-section" aria-labelledby="grounding-collections-title">
    <div className="grounding-section-heading"><h3 id="grounding-collections-title"><Database size={17} />Document collections</h3>{hasSnapshot && <span>Corpus {number(statistics.corpus_version)}</span>}</div>
    <p className="small muted">Indexed documents are split into searchable chunks. Counts reflect the current document versions.</p>
    {error && <ErrorNotice message={`Could not refresh collections: ${error}`} />}
    {!statistics && !error && <Loading label="Loading document collections…" />}
    {statistics && <>
      {statistics.items.length === 0 && statistics.status === 'unavailable' && <div className="notice warning"><ShieldAlert size={17} /><span>{statistics.detail || 'Knowledge storage is unavailable. Check the server configuration and refresh.'}</span></div>}
      <div className="grounding-totals"><div><strong>{number(totals?.documents)}</strong><span>Documents</span></div><div><strong>{number(totals?.chunks)}</strong><span>Searchable chunks</span></div></div>
      <div className="grounding-collection-list">{knowledgeCollections.map(collection => {
        const item = statistics.items.find(value => value.collection === collection.value);
        return <article className="grounding-collection" key={collection.value}>
          <div><h4>{collection.label}</h4><p>{collection.description}</p><small>Last updated {timestamp(item?.last_updated || undefined)}</small></div>
          <div className="grounding-collection-count"><strong>{number(item?.document_count)} <span>docs</span></strong><small>{number(item?.chunk_count)} chunks</small></div>
        </article>;
      })}</div>
      {embedding && <div className={`grounding-embedding notice ${embedding.available === false ? 'warning' : 'info'}`}>
        {embedding.available === true ? <CircleCheck size={18} /> : embedding.available === false ? <ShieldAlert size={18} /> : <Info size={18} />}
        <div><strong>{embedding.provider === 'local' ? 'Local embeddings' : 'Gateway embeddings'}: {embedding.available === true ? 'ready' : embedding.available === false ? 'unavailable' : 'not checked'}</strong><p>{embedding.detail}</p>
          {embedding.provider === 'local' && embedding.available === false && <><p>Prepare the model on the server, then refresh this panel.</p><code>{embedding.prepare_command || '.venv/bin/python -m scripts.rag prepare'}</code></>}
        </div>
      </div>}
    </>}
  </section>;
}
