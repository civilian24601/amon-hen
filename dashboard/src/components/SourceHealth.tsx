import { useEffect, useState } from 'react';
import { api } from '../api';
import type { HealthStatus } from '../types';

export default function SourceHealth() {
  const [health, setHealth] = useState<HealthStatus | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.getHealth()
      .then(setHealth)
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <div className="text-gray-500">Loading...</div>;
  if (!health) return <div className="text-red-400">Failed to load health status</div>;

  return (
    <div>
      <h2 className="text-2xl font-bold mb-4">System Health</h2>

      {/* Stats cards */}
      <div className="grid grid-cols-4 gap-4 mb-8">
        <div className="bg-gray-900 border border-gray-800 rounded-lg p-4">
          <p className="text-gray-500 text-sm">Items</p>
          <p className="text-2xl font-bold">{health.items_count}</p>
        </div>
        <div className="bg-gray-900 border border-gray-800 rounded-lg p-4">
          <p className="text-gray-500 text-sm">Clusters</p>
          <p className="text-2xl font-bold">{health.clusters_count}</p>
        </div>
        <div className="bg-gray-900 border border-gray-800 rounded-lg p-4">
          <p className="text-gray-500 text-sm">Daily Cost</p>
          <p className="text-2xl font-bold">${health.daily_cost.toFixed(4)}</p>
        </div>
        <div className="bg-gray-900 border border-gray-800 rounded-lg p-4">
          <p className="text-gray-500 text-sm">Total Cost</p>
          <p className="text-2xl font-bold">${health.total_cost.toFixed(4)}</p>
        </div>
      </div>

      {/* Vectors info */}
      <div className="bg-gray-900 border border-gray-800 rounded-lg p-4 mb-8">
        <h3 className="font-semibold mb-2">Vector Store</h3>
        <p className="text-gray-400 text-sm">
          Points: {health.vectors.points_count}
        </p>
      </div>

      {/* Source status table */}
      <h3 className="text-lg font-semibold mb-3">Source Status</h3>
      {health.sources.length === 0 ? (
        <p className="text-gray-500">No sources have been fetched yet.</p>
      ) : (
        <div className="bg-gray-900 border border-gray-800 rounded-lg overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-gray-800 text-gray-400">
                <th className="text-left px-4 py-2">Source</th>
                <th className="text-left px-4 py-2">Type</th>
                <th className="text-right px-4 py-2">Items</th>
                <th className="text-right px-4 py-2">Errors</th>
                <th className="text-left px-4 py-2">Last Fetch</th>
                <th className="text-center px-4 py-2">Status</th>
              </tr>
            </thead>
            <tbody>
              {health.sources.map((s) => (
                <tr key={s.name} className="border-t border-gray-800 hover:bg-gray-800/50">
                  <td className="px-4 py-2 text-gray-200">{s.name}</td>
                  <td className="px-4 py-2 text-gray-400">{s.type}</td>
                  <td className="px-4 py-2 text-right text-gray-300">{s.items_fetched}</td>
                  <td className="px-4 py-2 text-right">
                    <span className={s.error_count > 0 ? 'text-red-400' : 'text-gray-500'}>
                      {s.error_count}
                    </span>
                  </td>
                  <td className="px-4 py-2 text-gray-500">
                    {s.last_fetch ? new Date(s.last_fetch).toLocaleString() : 'Never'}
                  </td>
                  <td className="px-4 py-2 text-center">
                    <span
                      className={`inline-block w-2 h-2 rounded-full ${
                        s.error_count === 0 ? 'bg-green-400' : 'bg-red-400'
                      }`}
                    />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
