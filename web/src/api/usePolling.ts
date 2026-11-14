import { useCallback, useEffect, useState } from 'react';
import { api, errorMessage } from './client';

type Snapshot<T> = { path: string; data?: T; error: string; loading: boolean };

export function usePolling<T>(path: string, intervalMs = 3000) {
  const [snapshot, setSnapshot] = useState<Snapshot<T>>({ path, error: '', loading: true });
  const [version, setVersion] = useState(0);
  const reload = useCallback(() => setVersion(value => value + 1), []);
  useEffect(() => {
    const controller = new AbortController();
    let timer: number | undefined;
    setSnapshot(previous => previous.path === path
      ? { ...previous, loading: true }
      : { path, error: '', loading: true });
    async function load() {
      try {
        const value = await api<T>(path, { signal: controller.signal });
        if (!controller.signal.aborted) setSnapshot({ path, data: value, error: '', loading: false });
      } catch (reason) {
        if (!controller.signal.aborted) setSnapshot(previous => ({ path,
          data: previous.path === path ? previous.data : undefined,
          error: errorMessage(reason), loading: false }));
      } finally {
        if (!controller.signal.aborted) timer = window.setTimeout(load, intervalMs);
      }
    }
    void load();
    return () => { controller.abort(); window.clearTimeout(timer); };
  }, [path, intervalMs, version]);
  const current = snapshot.path === path;
  return { data: current ? snapshot.data : undefined, error: current ? snapshot.error : '',
    loading: current ? snapshot.loading : true, reload };
}
