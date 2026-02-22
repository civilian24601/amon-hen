export interface Cluster {
  id: string;
  label: string;
  summary: string;
  item_count: number;
  status: string;
  first_seen: string;
  last_updated: string;
  source_distribution: Record<string, number>;
  sentiment_distribution: Record<string, number>;
  key_entities: string[];
  key_claims?: string[];
  centroid?: number[];
  items?: Item[];
}

export interface Item {
  id: string;
  title: string | null;
  summary: string;
  source_type: string;
  source_name: string;
  source_url: string;
  published_at: string;
  sentiment: number;
  framing?: string;
  cluster_id?: string;
  cluster_label?: string;
}

export interface SearchResult {
  id: string;
  score: number;
  title: string;
  summary: string;
  source_type: string;
  source_name: string;
  published_at: string;
}

export interface Digest {
  id: string;
  generated_at: string;
  content: string;
  cluster_count: number;
  item_count: number;
  model: string;
}

export interface HealthStatus {
  status: string;
  items_count: number;
  clusters_count: number;
  daily_cost: number;
  total_cost: number;
  sources: SourceHealth[];
  vectors: { name: string; points_count: number };
}

export interface SourceHealth {
  name: string;
  type: string;
  last_fetch: string | null;
  items_fetched: number;
  error_count: number;
}
