import { useCallback, useEffect, useRef, useState } from 'react';
import { api, errorMessage } from '../api/client';
import { uploadPending } from '../api/grounding';
import type { GroundingStatistics, GroundingUpload } from '../api/grounding';

export function useGrounding() {
  const [statistics, setStatistics] = useState<GroundingStatistics>();
  const [uploads, setUploads] = useState<GroundingUpload[]>([]);
  const [statisticsError, setStatisticsError] = useState('');
  const [historyError, setHistoryError] = useState('');
  const [uploadError, setUploadError] = useState('');
  const [historyLoaded, setHistoryLoaded] = useState(false);
  const [refreshingStatistics, setRefreshingStatistics] = useState(false);
  const [refreshingHistory, setRefreshingHistory] = useState(false);
  const [uploading, setUploading] = useState(false);
  const lifetime = useRef<AbortController | null>(null);
  const statisticsBusy = useRef<AbortController | null>(null);
  const historyBusy = useRef<AbortController | null>(null);
  const knownUploads = useRef(new Map<string, GroundingUpload>());
  const historyVersion = useRef(0);
  const statisticsVersion = useRef(0);

  const refreshStatistics = useCallback(async (): Promise<void> => {
    const controller = lifetime.current;
    if (!controller || controller.signal.aborted || statisticsBusy.current === controller) return;
    statisticsBusy.current = controller;
    const version = statisticsVersion.current;
    setRefreshingStatistics(true);
    try {
      const value = await api<GroundingStatistics>('/grounding/collections', { signal: controller.signal });
      if (!controller.signal.aborted && version === statisticsVersion.current) { setStatistics(value); setStatisticsError(''); }
    } catch (reason) {
      if (!controller.signal.aborted && version === statisticsVersion.current) setStatisticsError(errorMessage(reason));
    } finally {
      if (statisticsBusy.current === controller) statisticsBusy.current = null;
      if (!controller.signal.aborted) setRefreshingStatistics(false);
      if (!controller.signal.aborted && version !== statisticsVersion.current) void refreshStatistics();
    }
  }, []);

  const refreshHistory = useCallback(async (): Promise<void> => {
    const controller = lifetime.current;
    if (!controller || controller.signal.aborted || historyBusy.current === controller) return;
    historyBusy.current = controller;
    const version = historyVersion.current;
    setRefreshingHistory(true);
    try {
      const value = await api<{ items: GroundingUpload[] }>('/grounding/uploads', { signal: controller.signal });
      if (controller.signal.aborted || version !== historyVersion.current) return;
      const completed = value.items.some(job => {
        const previous = knownUploads.current.get(job.id);
        return previous && uploadPending(previous) && !uploadPending(job);
      });
      knownUploads.current = new Map(value.items.map(job => [job.id, job]));
      setUploads(value.items);
      setHistoryError('');
      if (completed) { statisticsVersion.current += 1; void refreshStatistics(); }
    } catch (reason) {
      if (!controller.signal.aborted && version === historyVersion.current) setHistoryError(errorMessage(reason));
    } finally {
      if (historyBusy.current === controller) historyBusy.current = null;
      if (!controller.signal.aborted) { setRefreshingHistory(false); setHistoryLoaded(true); }
      if (!controller.signal.aborted && version !== historyVersion.current) void refreshHistory();
    }
  }, [refreshStatistics]);

  useEffect(() => {
    const controller = new AbortController();
    lifetime.current = controller;
    void refreshStatistics();
    void refreshHistory();
    const timer = window.setInterval(() => void refreshStatistics(), 5000);
    return () => { controller.abort(); window.clearInterval(timer); };
  }, [refreshStatistics, refreshHistory]);

  const pending = uploads.some(uploadPending);
  useEffect(() => {
    const timer = window.setInterval(() => void refreshHistory(), pending ? 1000 : 5000);
    return () => window.clearInterval(timer);
  }, [pending, refreshHistory]);

  async function upload(body: FormData): Promise<GroundingUpload | undefined> {
    const controller = lifetime.current;
    if (!controller || controller.signal.aborted) return;
    setUploading(true);
    setUploadError('');
    try {
      const job = await api<GroundingUpload>('/grounding/uploads', { method: 'POST', body, signal: controller.signal });
      if (controller.signal.aborted) return;
      historyVersion.current += 1;
      knownUploads.current.set(job.id, job);
      setUploads(current => [job, ...current.filter(item => item.id !== job.id)]);
      if (!uploadPending(job)) { statisticsVersion.current += 1; void refreshStatistics(); }
      return job;
    } catch (reason) {
      if (!controller.signal.aborted) setUploadError(errorMessage(reason));
    } finally {
      if (!controller.signal.aborted) setUploading(false);
    }
  }

  return {
    statistics, uploads, statisticsError, historyError, uploadError, historyLoaded, uploading,
    refreshing: refreshingStatistics || refreshingHistory,
    refresh: () => { void refreshStatistics(); void refreshHistory(); }, upload,
  };
}
