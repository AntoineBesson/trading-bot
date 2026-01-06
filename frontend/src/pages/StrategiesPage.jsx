import React, { useState, useEffect } from 'react';
import { 
  Play, 
  Pause, 
  DollarSign, 
  TrendingUp, 
  Activity,
  Layers
} from 'lucide-react';
import { getStatus, getCapital, toggleStrategy } from '../services/api';

function StrategyCard({ strategy, allocation, onToggle }) {
  const isActive = strategy.active;
  
  return (
    <div className="card-hover">
      <div className="flex items-start justify-between mb-4">
        <div>
          <h3 className="text-lg font-semibold text-primary">{strategy.id}</h3>
          <p className="text-sm text-secondary">{strategy.type}</p>
        </div>
        <button
          onClick={() => onToggle(strategy.id)}
          className={`p-2 rounded-lg transition-colors ${
            isActive 
              ? 'bg-chart-green-light text-chart-green hover:bg-chart-green hover:text-white' 
              : 'bg-chart-red-light text-chart-red hover:bg-chart-red hover:text-white'
          }`}
        >
          {isActive ? <Play className="w-5 h-5" /> : <Pause className="w-5 h-5" />}
        </button>
      </div>
      
      <div className="space-y-3">
        {/* Symbols */}
        <div className="flex flex-wrap gap-2">
          {strategy.symbols?.map((symbol) => (
            <span 
              key={symbol} 
              className="px-2 py-1 bg-surface-light border border-border rounded text-xs font-mono text-secondary"
            >
              {symbol}
            </span>
          ))}
        </div>
        
        {/* Allocation */}
        {allocation && (
          <div className="pt-3 border-t border-border">
            <div className="flex items-center justify-between">
              <span className="text-sm text-secondary">Allocated</span>
              <span className="text-lg font-semibold font-mono text-primary">
                ${allocation.equity?.toLocaleString() || '0'}
              </span>
            </div>
            {allocation.leverage > 1 && (
              <div className="flex items-center justify-between mt-1">
                <span className="text-sm text-secondary">Leverage</span>
                <span className="text-sm font-mono text-chart-green">{allocation.leverage}x</span>
              </div>
            )}
          </div>
        )}
      </div>
      
      {/* Status Indicator */}
      <div className="mt-4 pt-3 border-t border-border flex items-center gap-2">
        <div className={`w-2 h-2 rounded-full ${isActive ? 'bg-chart-green animate-pulse' : 'bg-chart-red'}`} />
        <span className="text-xs text-secondary">{isActive ? 'Running' : 'Paused'}</span>
      </div>
    </div>
  );
}

export default function StrategiesPage() {
  const [status, setStatus] = useState(null);
  const [capital, setCapital] = useState({});
  const [loading, setLoading] = useState(true);
  
  const fetchData = async () => {
    try {
      const [statusData, capitalData] = await Promise.all([
        getStatus(),
        getCapital().catch(() => ({ allocations: {}, total_equity: 0 }))
      ]);
      setStatus(statusData);
      setCapital(capitalData);
    } catch (error) {
      console.error('Failed to fetch data:', error);
    } finally {
      setLoading(false);
    }
  };
  
  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 5000);
    return () => clearInterval(interval);
  }, []);
  
  const handleToggle = async (strategyId) => {
    try {
      await toggleStrategy(strategyId);
      fetchData();
    } catch (error) {
      console.error('Failed to toggle strategy:', error);
    }
  };
  
  if (loading) {
    return (
      <div className="p-8 flex items-center justify-center min-h-screen">
        <Activity className="w-8 h-8 text-secondary animate-spin" />
      </div>
    );
  }
  
  const strategies = status?.strategies || [];
  const totalEquity = capital.total_equity || 0;
  const allocations = capital.allocations || {};
  const allocatedCapital = Object.values(allocations).reduce((sum, a) => sum + (a.equity || 0), 0);
  
  return (
    <div className="p-8">
      {/* Header */}
      <div className="mb-8">
        <h1 className="text-3xl font-bold text-primary mb-2">Deployed Strategies</h1>
        <p className="text-secondary">Monitor and manage your active trading strategies</p>
      </div>
      
      {/* Summary Cards */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-8">
        <div className="card">
          <div className="flex items-center gap-3 mb-2">
            <DollarSign className="w-5 h-5 text-secondary" />
            <span className="stat-label">Total Equity</span>
          </div>
          <p className="stat-value font-mono">${totalEquity.toLocaleString()}</p>
        </div>
        
        <div className="card">
          <div className="flex items-center gap-3 mb-2">
            <Layers className="w-5 h-5 text-secondary" />
            <span className="stat-label">Allocated</span>
          </div>
          <p className="stat-value font-mono">${allocatedCapital.toLocaleString()}</p>
        </div>
        
        <div className="card">
          <div className="flex items-center gap-3 mb-2">
            <TrendingUp className="w-5 h-5 text-secondary" />
            <span className="stat-label">Active Strategies</span>
          </div>
          <p className="stat-value">{strategies.filter(s => s.active).length}</p>
        </div>
        
        <div className="card">
          <div className="flex items-center gap-3 mb-2">
            <Activity className="w-5 h-5 text-secondary" />
            <span className="stat-label">Market Regime</span>
          </div>
          <p className={`stat-value ${status?.regime === 'Volatile' ? 'text-chart-red' : 'text-chart-green'}`}>
            {status?.regime || 'Unknown'}
          </p>
        </div>
      </div>
      
      {/* Strategies Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {strategies.map((strategy) => (
          <StrategyCard 
            key={strategy.id}
            strategy={strategy}
            allocation={allocations[strategy.id]}
            onToggle={handleToggle}
          />
        ))}
      </div>
      
      {strategies.length === 0 && (
        <div className="card text-center py-12">
          <Layers className="w-12 h-12 text-secondary mx-auto mb-4" />
          <p className="text-lg text-secondary">No strategies deployed</p>
          <p className="text-sm text-secondary mt-1">Strategies will appear here once initialized</p>
        </div>
      )}
    </div>
  );
}
