import type { Cluster, Digest, HealthStatus, Item, SearchResult } from './types';

const BASE = '/api';

async function fetchJson<T>(url: string): Promise<T> {
  const resp = await fetch(`${BASE}${url}`);
  if (!resp.ok) throw new Error(`API error: ${resp.status}`);
  return resp.json();
}

export const api = {
  getClusters: () => fetchJson<Cluster[]>('/clusters'),
  getCluster: (id: string) => fetchJson<Cluster>(`/clusters/${id}`),
  getItems: (params?: { since?: string; limit?: number; source_type?: string }) => {
    const qs = new URLSearchParams();
    if (params?.since) qs.set('since', params.since);
    if (params?.limit) qs.set('limit', String(params.limit));
    if (params?.source_type) qs.set('source_type', params.source_type);
    return fetchJson<Item[]>(`/items?${qs}`);
  },
  search: (q: string, limit = 20) =>
    fetchJson<SearchResult[]>(`/search?q=${encodeURIComponent(q)}&limit=${limit}`),
  getDigest: () => fetchJson<Digest>('/digest/latest'),
  getHealth: () => fetchJson<HealthStatus>('/health'),
};
