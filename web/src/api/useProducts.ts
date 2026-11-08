import { useEffect, useState } from 'react';
import { api, errorMessage } from './client';
import type { Envelope, Product } from './types';

export function useProducts() {
  const [items, setItems] = useState<Product[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  useEffect(() => {
    const controller = new AbortController();
    async function load() {
      try {
        const products: Product[] = [];
        while (!controller.signal.aborted) {
          const page = await api<Envelope<Product>>(`/catalog?limit=500&offset=${products.length}`, { signal: controller.signal });
          products.push(...page.items);
          if (products.length >= page.total) break;
          if (!page.items.length) throw new Error('The catalog changed while loading. Refresh to load the current products.');
        }
        if (!controller.signal.aborted) setItems(products);
      } catch (reason) {
        if (!controller.signal.aborted) setError(errorMessage(reason));
      } finally { if (!controller.signal.aborted) setLoading(false); }
    }
    void load();
    return () => controller.abort();
  }, []);
  return { items, loading, error };
}
