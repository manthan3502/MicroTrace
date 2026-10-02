import { useEffect, useState } from 'react';
import { getJson } from './api';
export function useData<T>(path: string | null) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    if (!path) { setLoading(false); return; }
    const controller = new AbortController();
    setLoading(true); setError('');
    getJson<T>(path, controller.signal).then(value => {
      if (!controller.signal.aborted) setData(value);
    }).catch((reason: Error) => {
      if (!controller.signal.aborted) setError(reason.message);
    }).finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [path, revision]);
  return { data, error, loading, refresh: () => setRevision(n => n + 1) };
}
