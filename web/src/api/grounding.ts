export const knowledgeCollections = [
  { value: 'user_uploads', label: 'General documents', description: 'Supporting notes and uploaded evidence' },
  { value: 'pricing_policy', label: 'Pricing policies', description: 'Pricing rules and commercial guidance' },
  { value: 'market_intel', label: 'Market intelligence', description: 'Competitor research and market context' },
  { value: 'product_kb', label: 'Product knowledge', description: 'Product details and assortment context' },
] as const;

export type KnowledgeCollection = typeof knowledgeCollections[number]['value'];
export type UploadStatus = 'queued' | 'indexing' | 'ready' | 'failed' | 'interrupted';

export interface CollectionStatistics {
  collection: KnowledgeCollection;
  document_count: number;
  chunk_count: number;
  last_updated: string | null;
  corpus_version: number;
}

export interface GroundingStatistics {
  items: CollectionStatistics[];
  corpus_version: number | null;
  embedding: { provider: 'local' | 'gateway'; available: boolean | null; detail: string; prepare_command?: string };
  status: 'ready' | 'unavailable';
  detail?: string;
}

export interface GroundingUpload {
  id: string;
  filename: string;
  source_id: string;
  title: string;
  collection: KnowledgeCollection;
  status: UploadStatus;
  created_at: string;
  updated_at: string;
  completed_at: string | null;
  error_code?: string | null;
  error?: string | null;
  result?: {
    source_id: string;
    collection: KnowledgeCollection;
    version: string;
    chunk_count: number;
    corpus_version: number;
    changed: boolean;
  } | null;
}

export function collectionLabel(collection: KnowledgeCollection): string {
  return knowledgeCollections.find(item => item.value === collection)?.label || collection;
}

export function uploadPending(job: GroundingUpload): boolean {
  return job.status === 'queued' || job.status === 'indexing';
}
