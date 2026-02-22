import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  ScatterChart,
  Scatter,
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

function dominantSentiment(dist: Record<string, number>): string {
  let max = 0;
  let key = 'neutral';
  for (const [k, v] of Object.entries(dist)) {
    if (v > max) {
      max = v;
      key = k;
    }
  }
  return key;
}

function clusterColor(cluster: Cluster): string {
  const dominant = dominantSentiment(cluster.sentiment_distribution);
  return SENTIMENT_COLORS[dominant] || '#a3a3a3';
}

// Simple 2D projection: use first 2 centroid values if available
function projectClusters(clusters: Cluster[]): { x: number; y: number; cluster: Cluster }[] {
  return clusters.map((c, i) => {
    const x = c.centroid && c.centroid.length > 0 ? c.centroid[0] : Math.cos((i / clusters.length) * Math.PI * 2);
    const y = c.centroid && c.centroid.length > 1 ? c.centroid[1] : Math.sin((i / clusters.length) * Math.PI * 2);
    return { x, y, cluster: c };
  });
}

interface TooltipPayload {
  payload?: { cluster: Cluster };
}

function CustomTooltip({ active, payload }: { active?: boolean; payload?: TooltipPayload[] }) {
  if (active && payload && payload[0]?.payload?.cluster) {
    const c = payload[0].payload.cluster;
    return (
      <div className="bg-gray-800 border border-gray-700 rounded p-3 text-sm max-w-xs">
        <p className="font-semibold text-amber-400">{c.label}</p>
        <p className="text-gray-300 mt-1">{c.summary.slice(0, 120)}...</p>
        <p className="text-gray-500 mt-1">
          {c.item_count} items · {c.status}
        </p>
      </div>
    );
  }
  return null;
}

export default function ClusterMap() {
  const [clusters, setClusters] = useState<Cluster[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    api.getClusters()
      .then(setClusters)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <div className="text-gray-500">Loading clusters...</div>;
  if (error) return <div className="text-red-400">Error: {error}</div>;
  if (clusters.length === 0) {
    return (
      <div className="text-gray-500 text-center mt-20">
        <p className="text-2xl mb-2">No clusters yet</p>
        <p>Run <code className="text-amber-400">amon seed</code> then <code className="text-amber-400">amon recluster --now</code> to populate.</p>
      </div>
    );
  }

  const points = projectClusters(clusters);

  return (
    <div>
      <h2 className="text-2xl font-bold mb-4">Narrative Cluster Map</h2>
      <p className="text-gray-500 text-sm mb-6">
        {clusters.length} active clusters · Dot size = item count · Color = dominant sentiment
      </p>

      <div className="bg-gray-900 rounded-lg p-4 border border-gray-800 mb-8" style={{ height: 500 }}>
        <ResponsiveContainer width="100%" height="100%">
          <ScatterChart>
            <XAxis type="number" dataKey="x" tick={false} axisLine={false} />
            <YAxis type="number" dataKey="y" tick={false} axisLine={false} />
            <Tooltip content={<CustomTooltip />} />
            <Scatter data={points}>
              {points.map((p, i) => (
                <Cell
                  key={i}
                  fill={clusterColor(p.cluster)}
                  r={Math.max(6, Math.min(30, p.cluster.item_count))}
                />
              ))}
            </Scatter>
          </ScatterChart>
        </ResponsiveContainer>
      </div>

      {/* Cluster list */}
      <h3 className="text-lg font-semibold mb-3">All Clusters</h3>
      <div className="grid gap-3">
        {clusters.map((c) => (
          <Link
            key={c.id}
            to={`/cluster/${c.id}`}
            className="bg-gray-900 border border-gray-800 rounded-lg p-4 hover:border-amber-600 transition block"
          >
            <div className="flex justify-between items-start">
              <div>
                <h4 className="font-semibold text-amber-400">{c.label}</h4>
                <p className="text-gray-400 text-sm mt-1">{c.summary.slice(0, 150)}</p>
              </div>
              <div className="text-right text-sm text-gray-500 shrink-0 ml-4">
                <p>{c.item_count} items</p>
                <span
                  className={`inline-block px-2 py-0.5 rounded text-xs mt-1 ${
                    c.status === 'active'
                      ? 'bg-green-900 text-green-300'
                      : c.status === 'emerging'
                      ? 'bg-amber-900 text-amber-300'
                      : 'bg-gray-800 text-gray-400'
                  }`}
                >
                  {c.status}
                </span>
              </div>
            </div>
            <div className="flex gap-2 mt-2 flex-wrap">
              {c.key_entities.slice(0, 5).map((e) => (
                <span key={e} className="text-xs bg-gray-800 text-gray-300 px-2 py-0.5 rounded">
                  {e}
                </span>
              ))}
            </div>
          </Link>
        ))}
      </div>
    </div>
  );
}
