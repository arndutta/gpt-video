import { useCallback, useEffect, useState } from 'react';
import { api, errorMessage } from './client';

export function usePolling<T>(path: string, intervalMs = 3000) {
  const [data, setData] = useState<T>();
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const [version, setVersion] = useState(0);
  const reload = useCallback(() => setVersion(value => value + 1), []);
  useEffect(() => {
    const controller = new AbortController();
    let timer: number | undefined;
    async function load() {
      try {
        const value = await api<T>(path, { signal: controller.signal });
        if (!controller.signal.aborted) { setData(value); setError(''); }
      } catch (reason) {
        if (!controller.signal.aborted) setError(errorMessage(reason));
      } finally {
        if (!controller.signal.aborted) { setLoading(false); timer = window.setTimeout(load, intervalMs); }
      }
    }
    void load();
    return () => { controller.abort(); window.clearTimeout(timer); };
  }, [path, intervalMs, version]);
  return { data, error, loading, reload };
}
