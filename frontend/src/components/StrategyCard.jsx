import React, { useState } from 'react';
// 1. Safety Check: Ensure lucide-react is installed. If this line errors, run 'npm install lucide-react'
import { Activity, Layers, Hash, Play, Pause, Loader, AlertTriangle } from 'lucide-react';
// 2. Safety Check: Ensure this path is correct based on your folder structure
import { startStrategy, stopStrategy } from '../services/api'; 

const StrategyCard = ({ strategy }) => {
  const [loading, setLoading] = useState(false);

  // --- DEFENSIVE CHECK: Prevent Crash if data is missing ---
  if (!strategy) {
    return (
      <div className="bg-red-900/20 border border-red-700 p-4 rounded-xl text-red-400 flex items-center gap-2">
        <AlertTriangle size={20} /> Error: Invalid Strategy Data
      </div>
    );
  }
  // -------------------------------------------------------

  const handleToggle = async () => {
    setLoading(true);
    try {
      if (strategy.active) {
        await stopStrategy(strategy.id);
      } else {
        await startStrategy(strategy.id);
      }
      // Note: We rely on the parent App.jsx polling to update the UI color
    } catch (err) {
      console.error("Failed to toggle strategy", err);
      alert("Error: Could not update strategy. Check console for details.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className={`bg-gray-800 border rounded-xl p-5 transition-all shadow-lg ${strategy.active ? 'border-green-500/30' : 'border-red-500/30 opacity-75'}`}>
      <div className="flex justify-between items-start mb-4">
        <div>
          <h3 className="text-lg font-bold text-white">{strategy.id || "Unknown Strategy"}</h3>
          <span className={`text-xs px-2 py-1 rounded-full border ${strategy.active ? 'bg-green-900/30 text-green-400 border-green-800' : 'bg-red-900/30 text-red-400 border-red-800'}`}>
            {strategy.active ? 'Trading' : 'Paused'}
          </span>
        </div>
        
        {/* CONTROL BUTTON */}
        <button 
          onClick={handleToggle}
          disabled={loading}
          className={`p-3 rounded-full transition-colors ${strategy.active ? 'bg-red-500/20 hover:bg-red-500/40 text-red-400' : 'bg-green-500/20 hover:bg-green-500/40 text-green-400'}`}
        >
          {loading ? <Loader size={20} className="animate-spin" /> : strategy.active ? <Pause size={20} /> : <Play size={20} />}
        </button>
      </div>
      
      <div className="space-y-3">
        <div className="flex justify-between text-sm">
          <span className="text-gray-400 flex items-center gap-2">
            <Layers size={14} /> Type
          </span>
          <span className="text-gray-300 truncate max-w-[150px]">{strategy.type || "Generic"}</span>
        </div>
        
        <div className="mt-4 pt-3 border-t border-gray-700">
           <span className="text-xs text-gray-500 uppercase font-semibold flex items-center gap-1 mb-2">
             <Hash size={10} /> Traded Symbols
           </span>
           <div className="flex flex-wrap gap-2">
             {strategy.symbols && strategy.symbols.length > 0 ? (
                strategy.symbols.map((sym) => (
               <span key={sym} className="text-xs bg-gray-900 text-gray-300 px-2 py-1 rounded border border-gray-700 font-mono">
                 {sym}
               </span>
             ))
             ) : (
                <span className="text-xs text-gray-600 italic">No symbols</span>
             )}
           </div>
        </div>
      </div>
    </div>
  );
};

export default StrategyCard;