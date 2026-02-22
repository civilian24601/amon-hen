import { Routes, Route, Link, useLocation } from 'react-router-dom';
import ClusterMap from './components/ClusterMap';
import ClusterDetail from './components/ClusterDetail';
import SearchPanel from './components/SearchPanel';
import DigestView from './components/DigestView';
import SourceHealth from './components/SourceHealth';

const navItems = [
  { path: '/', label: 'Clusters' },
  { path: '/search', label: 'Search' },
  { path: '/digest', label: 'Digest' },
  { path: '/sources', label: 'Sources' },
];

export default function App() {
  const location = useLocation();

  return (
    <div className="min-h-screen flex">
      {/* Sidebar */}
      <nav className="w-56 bg-gray-900 border-r border-gray-800 p-4 flex flex-col gap-1">
        <h1 className="text-xl font-bold text-amber-400 mb-6 tracking-wide">
          AMON HEN
        </h1>
        <p className="text-xs text-gray-500 mb-4">Narrative Intelligence</p>
        {navItems.map((item) => (
          <Link
            key={item.path}
            to={item.path}
            className={`px-3 py-2 rounded text-sm transition ${
              location.pathname === item.path
                ? 'bg-gray-800 text-amber-400'
                : 'text-gray-400 hover:bg-gray-800 hover:text-gray-200'
            }`}
          >
            {item.label}
          </Link>
        ))}
      </nav>

      {/* Main content */}
      <main className="flex-1 p-6 overflow-auto">
        <Routes>
          <Route path="/" element={<ClusterMap />} />
          <Route path="/cluster/:id" element={<ClusterDetail />} />
          <Route path="/search" element={<SearchPanel />} />
          <Route path="/digest" element={<DigestView />} />
          <Route path="/sources" element={<SourceHealth />} />
        </Routes>
      </main>
    </div>
  );
}
