import { useEffect, useState } from 'react';
import { getStatus } from './services/api';
import { Activity, Server, ShieldCheck } from 'lucide-react';
import StrategyCard from './components/StrategyCard';

function App() {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    // Poll the server every 2 seconds to update live
    const interval = setInterval(() => {
        getStatus()
        .then(res => setData(res.data))
        .catch(err => console.error("Connection lost", err)); // Silent fail for polling
    }, 2000);

    // Initial fetch
    getStatus().then(res => setData(res.data)).catch(err => setError(err.message));

    return () => clearInterval(interval);
  }, []);

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

      {/* Status Bar */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 w-full max-w-5xl mb-8">
        {/* Connection Status */}
        <div className="bg-gray-800 p-5 rounded-xl border border-gray-700 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Server className="text-gray-400" size={20} />
            <span className="text-gray-300 font-medium">System Status</span>
          </div>
          <div className="flex items-center gap-3">
            <span className="text-sm font-mono text-green-400">
               {data?.running ? "ONLINE" : "CONNECTING..."}
            </span>
            <span className={`h-3 w-3 rounded-full shadow-[0_0_10px] ${data?.running ? 'bg-green-500 shadow-green-500/50' : 'bg-red-500'}`}></span>
          </div>
        </div>

        {/* Market Regime (From your JSON) */}
        <div className="bg-gray-800 p-5 rounded-xl border border-gray-700 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <ShieldCheck className="text-gray-400" size={20} />
            <span className="text-gray-300 font-medium">Market Regime</span>
          </div>
          <span className="bg-purple-900/30 text-purple-300 px-3 py-1 rounded-lg border border-purple-700/50 text-sm font-bold tracking-wide">
            {data?.regime || "DETECTING..."}
          </span>
        </div>
      </div>

      {/* Strategies Grid */}
      <div className="w-full max-w-5xl">
        <h2 className="text-xl font-bold mb-5 text-gray-200 flex items-center gap-2">
            Active Strategies
            <span className="bg-gray-800 text-xs py-0.5 px-2 rounded-full text-gray-400 border border-gray-700">
                {data?.strategies?.length || 0}
            </span>
        </h2>
        
        {data && data.strategies ? (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            {data.strategies.map((strat, index) => (
              <StrategyCard key={index} strategy={strat} />
            ))}
          </div>
        ) : (
          <div className="text-center py-20 bg-gray-800/50 rounded-xl border border-dashed border-gray-700">
              <p className="text-gray-500">Loading strategies...</p>
          </div>
        )}
      </div>
    </div>
  );
}

export default App;