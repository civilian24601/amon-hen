import { useEffect, useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  Cell,
} from 'recharts';
import { api } from '../api';
import type { Cluster } from '../types';

const SENTIMENT_COLORS: Record<string, string> = {
  very_negative: '#ef4444',
  negative: '#f97316',
  neutral: '#a3a3a3',
  positive: '#22c55e',
  very_positive: '#06b6d4',
};

export default function ClusterDetail() {
  const { id } = useParams<{ id: string }>();
  const [cluster, setCluster] = useState<Cluster | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!id) return;
    api.getCluster(id)
      .then(setCluster)
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [id]);

  if (loading) return <div className="text-gray-500">Loading...</div>;
  if (!cluster) return <div className="text-red-400">Cluster not found</div>;

  const sourceDist = Object.entries(cluster.source_distribution).map(([k, v]) => ({
    name: k,
    count: v,
  }));

  const sentimentDist = Object.entries(cluster.sentiment_distribution).map(([k, v]) => ({
    name: k,
    count: v,
    fill: SENTIMENT_COLORS[k] || '#a3a3a3',
  }));

  return (
    <div>
      <Link to="/" className="text-amber-400 text-sm hover:underline mb-4 inline-block">
        &larr; Back to clusters
      </Link>

      <h2 className="text-2xl font-bold mt-2">{cluster.label}</h2>
      <p className="text-gray-400 mt-2">{cluster.summary}</p>

      <div className="grid grid-cols-3 gap-4 mt-6">
        <div className="bg-gray-900 border border-gray-800 rounded p-4">
          <p className="text-gray-500 text-sm">Items</p>
          <p className="text-2xl font-bold">{cluster.item_count}</p>
        </div>
        <div className="bg-gray-900 border border-gray-800 rounded p-4">
          <p className="text-gray-500 text-sm">Status</p>
          <p className="text-2xl font-bold capitalize">{cluster.status}</p>
        </div>
        <div className="bg-gray-900 border border-gray-800 rounded p-4">
          <p className="text-gray-500 text-sm">First Seen</p>
          <p className="text-lg">{new Date(cluster.first_seen).toLocaleDateString()}</p>
        </div>
      </div>

      {/* Charts */}
      <div className="grid grid-cols-2 gap-6 mt-8">
        <div className="bg-gray-900 border border-gray-800 rounded-lg p-4">
          <h3 className="font-semibold mb-3">Source Distribution</h3>
          <ResponsiveContainer width="100%" height={200}>
            <BarChart data={sourceDist}>
              <XAxis dataKey="name" tick={{ fill: '#9ca3af', fontSize: 12 }} />
              <YAxis tick={{ fill: '#9ca3af', fontSize: 12 }} />
              <Tooltip />
              <Bar dataKey="count" fill="#f59e0b" />
            </BarChart>
          </ResponsiveContainer>
        </div>

        <div className="bg-gray-900 border border-gray-800 rounded-lg p-4">
          <h3 className="font-semibold mb-3">Sentiment Distribution</h3>
          <ResponsiveContainer width="100%" height={200}>
            <BarChart data={sentimentDist}>
              <XAxis dataKey="name" tick={{ fill: '#9ca3af', fontSize: 10 }} />
              <YAxis tick={{ fill: '#9ca3af', fontSize: 12 }} />
              <Tooltip />
              <Bar dataKey="count">
                {sentimentDist.map((entry, i) => (
                  <Cell key={i} fill={entry.fill} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Entities & Claims */}
      <div className="grid grid-cols-2 gap-6 mt-6">
        <div>
          <h3 className="font-semibold mb-2">Key Entities</h3>
          <div className="flex flex-wrap gap-2">
            {cluster.key_entities.map((e) => (
              <span key={e} className="bg-gray-800 text-gray-300 px-3 py-1 rounded text-sm">
                {e}
              </span>
            ))}
          </div>
        </div>
        <div>
          <h3 className="font-semibold mb-2">Key Claims</h3>
          <ul className="text-sm text-gray-400 space-y-1">
            {(cluster.key_claims || []).map((c, i) => (
              <li key={i}>• {c}</li>
            ))}
          </ul>
        </div>
      </div>

      {/* Member Items */}
      {cluster.items && cluster.items.length > 0 && (
        <div className="mt-8">
          <h3 className="font-semibold mb-3">Member Items ({cluster.items.length})</h3>
          <div className="space-y-2">
            {cluster.items.map((item) => (
              <div key={item.id} className="bg-gray-900 border border-gray-800 rounded p-3">
                <div className="flex justify-between">
                  <a
                    href={item.source_url}
                    target="_blank"
                    rel="noreferrer"
                    className="text-amber-400 hover:underline text-sm font-medium"
                  >
                    {item.title || item.summary.slice(0, 80)}
                  </a>
                  <span className="text-xs text-gray-500">{item.source_type}</span>
                </div>
                <p className="text-gray-500 text-xs mt-1">{item.summary.slice(0, 120)}</p>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
