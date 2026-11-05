import React, { useState, useEffect, useMemo, useCallback } from 'react';

export default function App() {
  const [activeTab, setActiveTab] = useState('shelf');
  const [books, setBooks] = useState([]);
  const [chapters, setChapters] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [apiUrl, setApiUrl] = useState(() => localStorage.getItem('audit_api_url') || 'http://127.0.0.1:8000');

  const fetchData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [bRes, cRes] = await Promise.all([
        fetch(`${apiUrl}/books`),
        fetch(`${apiUrl}/chapters?limit=200`)
      ]);
      if (!bRes.ok || !cRes.ok) throw new Error('API connection failed');
      const bData = await bRes.json();
      const cData = await cRes.json();
      setBooks(bData);
      setChapters(cData);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [apiUrl]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const telemetry = useMemo(() => {
    const validated = chapters.filter(c => c.validation_status);
    const passed = validated.filter(c => c.validation_status === 'passed');
    return {
      passRate: validated.length > 0 ? Math.round((passed.length / validated.length) * 100) : 100,
      totalBooks: books.length,
      totalChapters: chapters.length,
      validatedCount: validated.length
    };
  }, [books, chapters]);

  return (
    <div className="flex h-screen bg-slate-950 text-slate-100">
      {/* Sidebar */}
      <aside className="w-64 bg-slate-900 border-r border-slate-800 p-5 flex flex-col justify-between">
        <div>
          <div className="flex items-center gap-3 mb-6">
            <div className="w-8 h-8 rounded-lg bg-indigo-600 flex items-center justify-center font-bold text-white shadow">
              AI
            </div>
            <div>
              <h1 className="font-bold text-base text-white">Audit Shelf</h1>
              <p className="text-xs text-indigo-400 font-mono">React v18</p>
            </div>
          </div>
          <nav className="space-y-1">
            {['shelf', 'books', 'chapters', 'diff', 'telemetry'].map((tab) => (
              <button
                key={tab}
                onClick={() => setActiveTab(tab)}
                className={`w-full text-left px-3.5 py-2.5 rounded-lg text-sm font-medium capitalize transition-all ${
                  activeTab === tab ? 'bg-indigo-600 text-white' : 'text-slate-400 hover:bg-slate-800/60 hover:text-white'
                }`}
              >
                {tab}
              </button>
            ))}
          </nav>
        </div>
        <div className="text-xs font-mono text-slate-500 truncate">{apiUrl}</div>
      </aside>

      {/* Main Content */}
      <main className="flex-1 overflow-y-auto p-8">
        <header className="flex justify-between items-center mb-8">
          <div>
            <h2 className="text-2xl font-bold capitalize text-white">{activeTab} View</h2>
            <p className="text-xs text-slate-400 mt-1">Git-like versioning and validation gate tracking</p>
          </div>
          <button
            onClick={fetchData}
            className="px-4 py-2 text-xs font-semibold bg-indigo-600 hover:bg-indigo-500 rounded-lg text-white transition-colors"
          >
            Refresh
          </button>
        </header>

        {/* Telemetry Stats */}
        <div className="grid grid-cols-4 gap-4 mb-8">
          <div className="p-4 bg-slate-900 border border-slate-800 rounded-xl">
            <div className="text-xs text-slate-400 uppercase font-semibold">Books</div>
            <div className="text-2xl font-bold mt-1 text-white">{telemetry.totalBooks}</div>
          </div>
          <div className="p-4 bg-slate-900 border border-slate-800 rounded-xl">
            <div className="text-xs text-slate-400 uppercase font-semibold">Chapters</div>
            <div className="text-2xl font-bold mt-1 text-white">{telemetry.totalChapters}</div>
          </div>
          <div className="p-4 bg-slate-900 border border-slate-800 rounded-xl">
            <div className="text-xs text-slate-400 uppercase font-semibold">Gate Checks</div>
            <div className="text-2xl font-bold mt-1 text-white">{telemetry.validatedCount}</div>
          </div>
          <div className="p-4 bg-slate-900 border border-slate-800 rounded-xl">
            <div className="text-xs text-slate-400 uppercase font-semibold">Gate Pass Rate</div>
            <div className={`text-2xl font-bold mt-1 ${telemetry.passRate >= 80 ? 'text-emerald-400' : 'text-amber-400'}`}>
              {telemetry.passRate}%
            </div>
          </div>
        </div>

        {error && (
          <div className="p-4 bg-red-950/60 border border-red-800 text-red-200 text-xs rounded-xl mb-6">
            {error}
          </div>
        )}

        {/* Tab views */}
        {activeTab === 'shelf' && (
          <div className="grid grid-cols-3 gap-4">
            {books.map(b => (
              <div key={b.id} className="p-5 bg-slate-900 border border-slate-800 rounded-xl shadow-sm">
                <div className="flex justify-between items-start mb-2">
                  <h4 className="font-semibold text-white">{b.title}</h4>
                  <span className="px-2 py-0.5 text-xs font-bold rounded bg-indigo-500/10 text-indigo-400 border border-indigo-500/20">
                    v{b.version}
                  </span>
                </div>
                <div className="text-xs font-mono text-slate-400">
                  {b.id} • {b.feature} • {b.chapter_ids.length} chapters
                </div>
              </div>
            ))}
          </div>
        )}

        {activeTab === 'books' && (
          <div className="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden shadow-sm">
            <table className="w-full text-left text-xs">
              <thead className="bg-slate-850 text-slate-400 uppercase font-semibold border-b border-slate-800">
                <tr>
                  <th className="py-3 px-4">ID</th>
                  <th className="py-3 px-4">Title</th>
                  <th className="py-3 px-4">Feature</th>
                  <th className="py-3 px-4">Version</th>
                  <th className="py-3 px-4">Chapters</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800">
                {books.map(b => (
                  <tr key={b.id} className="hover:bg-slate-800/40">
                    <td className="py-3 px-4 font-mono text-indigo-400">{b.id}</td>
                    <td className="py-3 px-4 font-medium text-white">{b.title}</td>
                    <td className="py-3 px-4 text-slate-300">{b.feature}</td>
                    <td className="py-3 px-4 font-mono">v{b.version}</td>
                    <td className="py-3 px-4 font-mono">{b.chapter_ids.length}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {activeTab === 'chapters' && (
          <div className="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden shadow-sm">
            <table className="w-full text-left text-xs">
              <thead className="bg-slate-850 text-slate-400 uppercase font-semibold border-b border-slate-800">
                <tr>
                  <th className="py-3 px-4">ID</th>
                  <th className="py-3 px-4">Actor</th>
                  <th className="py-3 px-4">Gate Status</th>
                  <th className="py-3 px-4">Prompt</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800">
                {chapters.map(ch => (
                  <tr key={ch.id} className="hover:bg-slate-800/40">
                    <td className="py-3 px-4 font-mono text-indigo-400">{ch.id}</td>
                    <td className="py-3 px-4 text-slate-200">{ch.actor}</td>
                    <td className="py-3 px-4">
                      {ch.validation_status ? (
                        <span className={`px-2 py-0.5 rounded font-mono font-bold text-[10px] ${
                          ch.validation_status === 'passed' ? 'bg-emerald-500/10 text-emerald-400' : 'bg-red-500/10 text-red-400'
                        }`}>
                          {ch.validation_status.toUpperCase()}
                        </span>
                      ) : '—'}
                    </td>
                    <td className="py-3 px-4 text-slate-300 truncate max-w-md">{ch.prompt}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </main>
    </div>
  );
}
