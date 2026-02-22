import { useEffect, useState } from 'react';
import { api } from '../api';
import type { Digest } from '../types';

export default function DigestView() {
  const [digest, setDigest] = useState<Digest | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.getDigest()
      .then(setDigest)
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <div className="text-gray-500">Loading digest...</div>;

  if (!digest || !digest.content) {
    return (
      <div className="text-gray-500 text-center mt-20">
        <p className="text-2xl mb-2">No digest available</p>
        <p>
          Run <code className="text-amber-400">amon recluster --now</code> to generate one.
        </p>
      </div>
    );
  }

  return (
    <div>
      <h2 className="text-2xl font-bold mb-2">Intelligence Digest</h2>
      <p className="text-gray-500 text-sm mb-6">
        Generated {new Date(digest.generated_at).toLocaleString()} ·{' '}
        {digest.cluster_count} clusters · {digest.item_count} items · {digest.model}
      </p>

      <div className="bg-gray-900 border border-gray-800 rounded-lg p-6 prose prose-invert max-w-none">
        {digest.content.split('\n').map((line, i) => {
          if (line.startsWith('# ')) {
            return <h1 key={i} className="text-xl font-bold text-amber-400 mt-4 mb-2">{line.slice(2)}</h1>;
          }
          if (line.startsWith('## ')) {
            return <h2 key={i} className="text-lg font-semibold text-amber-300 mt-4 mb-2">{line.slice(3)}</h2>;
          }
          if (line.startsWith('- **')) {
            return <p key={i} className="text-gray-300 ml-4 my-1">{line}</p>;
          }
          if (line.startsWith('- ')) {
            return <p key={i} className="text-gray-400 ml-4 my-1">• {line.slice(2)}</p>;
          }
          if (line.trim() === '') {
            return <br key={i} />;
          }
          return <p key={i} className="text-gray-300 my-1">{line}</p>;
        })}
      </div>
    </div>
  );
}
