import { useState } from 'react';
import { api } from '../api';
import type { SearchResult } from '../types';

export default function SearchPanel() {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<SearchResult[]>([]);
  const [loading, setLoading] = useState(false);
  const [searched, setSearched] = useState(false);

  const handleSearch = async () => {
    if (!query.trim()) return;
    setLoading(true);
    setSearched(true);
    try {
      const data = await api.search(query);
      setResults(data);
    } catch {
      setResults([]);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div>
      <h2 className="text-2xl font-bold mb-4">Semantic Search</h2>
      <p className="text-gray-500 text-sm mb-6">Search across all enriched content by meaning, not keywords.</p>

      <div className="flex gap-3 mb-6">
        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
          placeholder="e.g., climate policy divergence between nations..."
          className="flex-1 bg-gray-900 border border-gray-700 rounded-lg px-4 py-2 text-gray-200 placeholder-gray-600 focus:outline-none focus:border-amber-500"
        />
        <button
          onClick={handleSearch}
          disabled={loading}
          className="bg-amber-600 hover:bg-amber-500 text-gray-950 font-semibold px-6 py-2 rounded-lg transition disabled:opacity-50"
        >
          {loading ? 'Searching...' : 'Search'}
        </button>
      </div>

      {searched && results.length === 0 && !loading && (
        <p className="text-gray-500 text-center mt-10">No results found.</p>
      )}

      <div className="space-y-3">
        {results.map((r) => (
          <div key={r.id} className="bg-gray-900 border border-gray-800 rounded-lg p-4">
            <div className="flex justify-between items-start">
              <h3 className="font-medium text-amber-400">{r.title || 'Untitled'}</h3>
              <span className="text-xs bg-gray-800 text-gray-400 px-2 py-0.5 rounded shrink-0 ml-3">
                {(r.score * 100).toFixed(1)}%
              </span>
            </div>
            <p className="text-gray-400 text-sm mt-1">{r.summary.slice(0, 200)}</p>
            <div className="flex gap-3 mt-2 text-xs text-gray-600">
              <span>{r.source_type}</span>
              <span>{r.source_name}</span>
              <span>{new Date(r.published_at).toLocaleDateString()}</span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
