import React from 'react';
import { Activity, Layers, Hash } from 'lucide-react';

const StrategyCard = ({ strategy }) => {
  return (
    <div className="bg-gray-800 border border-gray-700 rounded-xl p-5 hover:border-gray-600 transition-colors shadow-lg">
      <div className="flex justify-between items-start mb-4">
        <div>
          {/* Using 'id' because your screenshot shows 'id', not 'name' */}
          <h3 className="text-lg font-bold text-white">{strategy.id}</h3>
          <span className={`text-xs px-2 py-1 rounded-full border ${strategy.active ? 'bg-green-900/30 text-green-400 border-green-800' : 'bg-gray-700 text-gray-400 border-gray-600'}`}>
            {strategy.active ? 'Active' : 'Stopped'}
          </span>
        </div>
        <Activity className="text-blue-400" size={24} />
      </div>
      
      <div className="space-y-3">
        <div className="flex justify-between text-sm">
          <span className="text-gray-400 flex items-center gap-2">
            <Layers size={14} /> Type
          </span>
          <span className="text-gray-300 truncate max-w-[150px]">{strategy.type}</span>
        </div>
        
        <div className="mt-4 pt-3 border-t border-gray-700">
           <span className="text-xs text-gray-500 uppercase font-semibold flex items-center gap-1 mb-2">
             <Hash size={10} /> Traded Symbols
           </span>
           <div className="flex flex-wrap gap-2">
             {strategy.symbols && strategy.symbols.map((sym) => (
               <span key={sym} className="text-xs bg-gray-900 text-gray-300 px-2 py-1 rounded border border-gray-700 font-mono">
                 {sym}
               </span>
             ))}
           </div>
        </div>
      </div>
    </div>
  );
};

export default StrategyCard;