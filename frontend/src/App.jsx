import React, { useEffect, useState } from 'react';
import axios from 'axios';
import EquityChart from './components/EquityChart';
import { Activity, Server, ShieldCheck, Play, Pause, Loader, AlertTriangle, Hash, Layers } from 'lucide-react';

// --- 1. INTERNAL API CONFIGURATION ---
// We define this here to avoid import errors
const api = axios.create({
  baseURL: '/api', 
  headers: { 'Content-Type': 'application/json' },
});

// --- 2. INTERNAL COMPONENT: STRATEGY CARD ---
const StrategyCard = ({ strategy }) => {
  const [loading, setLoading] = useState(false);

  const toggleStrategy = async () => {
    setLoading(true);
    try {
      const endpoint = strategy.active ? `/strategies/${strategy.id}/stop` : `/strategies/${strategy.id}/start`;
      await api.post(endpoint);
      // We rely on the main loop to update the UI
    } catch (err) {
      alert("Failed to toggle strategy. Check console.");
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className={`bg-gray-800 border rounded-xl p-5 transition-all shadow-lg ${strategy.active ? 'border-green-500/30' : 'border-red-500/30 opacity-75'}`}>
      <div className="flex justify-between items-start mb-4">
        <div>
          <h3 className="text-lg font-bold text-white">{strategy.id}</h3>
          <span className={`text-xs px-2 py-1 rounded-full border ${strategy.active ? 'bg-green-900/30 text-green-400 border-green-800' : 'bg-red-900/30 text-red-400 border-red-800'}`}>
            {strategy.active ? 'Trading' : 'Paused'}
          </span>
        </div>
        <button 
          onClick={toggleStrategy}
          disabled={loading}
          className={`p-3 rounded-full transition-colors ${strategy.active ? 'bg-red-500/20 hover:bg-red-500/40 text-red-400' : 'bg-green-500/20 hover:bg-green-500/40 text-green-400'}`}
        >
          {loading ? <Loader size={20} className="animate-spin" /> : strategy.active ? <Pause size={20} /> : <Play size={20} />}
        </button>
      </div>
      
      <div className="space-y-3">
        <div className="flex justify-between text-sm">
          <span className="text-gray-400 flex items-center gap-2"> <Layers size={14} /> Type </span>
          <span className="text-gray-300 truncate max-w-[150px]">{strategy.type}</span>
        </div>
        <div className="mt-4 pt-3 border-t border-gray-700">
           <span className="text-xs text-gray-500 uppercase font-semibold flex items-center gap-1 mb-2"> <Hash size={10} /> Traded Symbols </span>
           <div className="flex flex-wrap gap-2">
             {strategy.symbols && strategy.symbols.map((sym) => (
               <span key={sym} className="text-xs bg-gray-900 text-gray-300 px-2 py-1 rounded border border-gray-700 font-mono">{sym}</span>
             ))}
           </div>
        </div>
      </div>
    </div>
  );
};

// --- 3. MAIN APP COMPONENT ---
function App() {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [history, setHistory] = useState([]);

  useEffect(() => {
    const fetchData = () => {
      api.get('/status')
        .then(res => {
          setData(res.data);
          setError(null);
          api.get('/history').then(res => setHistory(res.data));
        })
        .catch(err => {
          // Only show error if we have never loaded data before
          if (!data) setError("Connecting to Bot...");
          console.log("Polling error:", err.message);
        });
    };

    fetchData(); 
    const interval = setInterval(fetchData, 2000); // Poll every 2s
    return () => clearInterval(interval);
  }, [data]);

  // Loading State
  if (!data && !error) return <div className="min-h-screen bg-gray-900 flex items-center justify-center text-white"><Activity className="animate-spin text-blue-500" size={40} /></div>;

  return (
    <div className="min-h-screen bg-gray-900 text-white p-8 flex flex-col items-center">
      <header className="w-full max-w-5xl mb-10 flex items-center gap-4">
        <div className="p-3 bg-blue-600/20 rounded-xl border border-blue-500/50">
            <Activity className="text-blue-400" size={32} />
        </div>
        <div>
            <h1 className="text-3xl font-bold">Quant Bot Command Center</h1>
            <p className="text-gray-400 text-sm">Algorithmic Trading Dashboard</p>
        </div>
      </header>

      {/* ERROR BANNER (If API fails) */}
      {error && (
        <div className="bg-red-900/50 border border-red-500 text-red-200 p-4 rounded-xl w-full max-w-5xl mb-6 flex items-center gap-3">
          <AlertTriangle /> {error}
        </div>
      )}

      {/* STATUS BAR */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 w-full max-w-5xl mb-8">
        <div className="bg-gray-800 p-5 rounded-xl border border-gray-700 flex items-center justify-between shadow-lg">
          <div className="flex items-center gap-3"> <Server className="text-gray-400" size={20} /> <span className="text-gray-300 font-medium">System Status</span> </div>
          <div className="flex items-center gap-3">
            <span className="text-sm font-mono text-green-400">{data?.running ? "ONLINE" : "OFFLINE"}</span>
            <span className={`h-3 w-3 rounded-full shadow-[0_0_10px] ${data?.running ? 'bg-green-500 shadow-green-500/50' : 'bg-red-500'}`}></span>
          </div>
        </div>

        <div className="bg-gray-800 p-5 rounded-xl border border-gray-700 flex items-center justify-between shadow-lg">
          <div className="flex items-center gap-3"> <ShieldCheck className="text-gray-400" size={20} /> <span className="text-gray-300 font-medium">Market Regime</span> </div>
          <span className={`px-3 py-1 rounded-lg border text-sm font-bold tracking-wide ${data?.regime === 'Volatile' ? 'bg-red-900/30 text-red-300 border-red-700' : 'bg-purple-900/30 text-purple-300 border-purple-700/50'}`}>
            {data?.regime || "DETECTING..."}
          </span>
        </div>
      </div>

      {/* STRATEGIES */}
      <div className="w-full max-w-5xl">
        <h2 className="text-xl font-bold mb-5 text-gray-200 flex items-center gap-2">
            Active Strategies <span className="bg-gray-800 text-xs py-0.5 px-2 rounded-full text-gray-400 border border-gray-700">{data?.strategies?.length || 0}</span>
        </h2>
        
        {data?.strategies ? (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            {data.strategies.map((strat, index) => (
              <StrategyCard key={index} strategy={strat} />
            ))}
          </div>
        ) : (
          <div className="text-center py-20 bg-gray-800/50 rounded-xl border border-dashed border-gray-700 text-gray-500">Waiting for data...</div>
        )}
      </div>
      
      {/* CHART SECTION */}
      {history.length > 0 ? (
        <EquityChart data={history} />
      ) : (
        <div className="text-gray-500 mt-8">Not enough data for chart yet...</div>
      )}
    </div>
  );
}

export default App;