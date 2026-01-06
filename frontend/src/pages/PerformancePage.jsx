import React, { useState, useEffect } from 'react';
import { 
  TrendingUp, 
  TrendingDown, 
  Activity,
  Calendar,
  Percent,
  DollarSign
} from 'lucide-react';
import { getHistory, getPerformance } from '../services/api';
import EquityChart from '../components/EquityChart';

function MetricCard({ icon: Icon, label, value, subValue, trend }) {
  const isPositive = trend === 'up' || (typeof value === 'number' && value >= 0);
  
  return (
    <div className="card">
      <div className="flex items-center gap-3 mb-2">
        <Icon className="w-5 h-5 text-secondary" />
        <span className="stat-label">{label}</span>
      </div>
      <p className={`stat-value font-mono ${
        trend ? (isPositive ? 'text-chart-green' : 'text-chart-red') : 'text-primary'
      }`}>
        {typeof value === 'number' 
          ? value.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })
          : value
        }
      </p>
      {subValue && (
        <p className="text-sm text-secondary mt-1">{subValue}</p>
      )}
    </div>
  );
}

export default function PerformancePage() {
  const [history, setHistory] = useState([]);
  const [performance, setPerformance] = useState(null);
  const [loading, setLoading] = useState(true);
  const [timeframe, setTimeframe] = useState('all');
  
  const fetchData = async () => {
    try {
      const [historyData, perfData] = await Promise.all([
        getHistory(),
        getPerformance().catch(() => null)
      ]);
      setHistory(historyData || []);
      setPerformance(perfData);
    } catch (error) {
      console.error('Failed to fetch data:', error);
    } finally {
      setLoading(false);
    }
  };
  
  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 10000);
    return () => clearInterval(interval);
  }, []);
  
  // Filter history based on timeframe
  const getFilteredHistory = () => {
    if (timeframe === 'all' || !history.length) return history;
    
    const now = Date.now() / 1000;
    const timeframes = {
      '1d': 86400,
      '1w': 604800,
      '1m': 2592000,
    };
    
    const cutoff = now - (timeframes[timeframe] || 0);
    return history.filter(point => point.time >= cutoff);
  };
  
  const filteredHistory = getFilteredHistory();
  
  // Calculate returns from history
  const calculateReturns = () => {
    if (filteredHistory.length < 2) return { absolute: 0, percent: 0 };
    const first = filteredHistory[0].value;
    const last = filteredHistory[filteredHistory.length - 1].value;
    return {
      absolute: last - first,
      percent: ((last - first) / first) * 100
    };
  };
  
  const returns = calculateReturns();
  
  if (loading) {
    return (
      <div className="p-8 flex items-center justify-center min-h-screen">
        <Activity className="w-8 h-8 text-secondary animate-spin" />
      </div>
    );
  }
  
  return (
    <div className="p-8">
      {/* Header */}
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="text-3xl font-bold text-primary mb-2">Performance</h1>
          <p className="text-secondary">Track your portfolio performance and returns</p>
        </div>
        
        {/* Timeframe Selector */}
        <div className="flex bg-surface border border-border rounded-lg p-1">
          {['1d', '1w', '1m', 'all'].map((tf) => (
            <button
              key={tf}
              onClick={() => setTimeframe(tf)}
              className={`px-4 py-2 rounded-md text-sm font-medium transition-colors ${
                timeframe === tf 
                  ? 'bg-primary text-background' 
                  : 'text-secondary hover:text-primary'
              }`}
            >
              {tf.toUpperCase()}
            </button>
          ))}
        </div>
      </div>
      
      {/* Summary Metrics */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-8">
        <MetricCard 
          icon={DollarSign}
          label="Total P&L"
          value={returns.absolute}
          trend={returns.absolute >= 0 ? 'up' : 'down'}
        />
        <MetricCard 
          icon={Percent}
          label="Return %"
          value={`${returns.percent >= 0 ? '+' : ''}${returns.percent.toFixed(2)}%`}
          trend={returns.percent >= 0 ? 'up' : 'down'}
        />
        <MetricCard 
          icon={TrendingUp}
          label="Sharpe Ratio"
          value={performance?.sharpe_ratio?.toFixed(2) || 'N/A'}
        />
        <MetricCard 
          icon={Calendar}
          label="Win Rate"
          value={performance?.win_rate ? `${(performance.win_rate * 100).toFixed(1)}%` : 'N/A'}
        />
      </div>
      
      {/* Equity Chart */}
      <div className="card mb-8">
        <div className="flex items-center justify-between mb-6">
          <h2 className="text-xl font-semibold text-primary">Equity Curve</h2>
          <div className="flex items-center gap-2">
            {returns.absolute >= 0 ? (
              <TrendingUp className="w-5 h-5 text-chart-green" />
            ) : (
              <TrendingDown className="w-5 h-5 text-chart-red" />
            )}
            <span className={`font-mono font-semibold ${
              returns.absolute >= 0 ? 'text-chart-green' : 'text-chart-red'
            }`}>
              {returns.absolute >= 0 ? '+' : ''}${returns.absolute.toLocaleString(undefined, { maximumFractionDigits: 2 })}
            </span>
          </div>
        </div>
        <EquityChart data={filteredHistory} />
      </div>
      
      {/* Additional Metrics */}
      {performance && (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div className="card">
            <h3 className="text-lg font-semibold text-primary mb-4">Risk-Adjusted Returns</h3>
            <div className="space-y-3">
              <div className="flex justify-between">
                <span className="text-secondary">Sortino Ratio</span>
                <span className="font-mono text-primary">{performance.sortino_ratio?.toFixed(2) || 'N/A'}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-secondary">Calmar Ratio</span>
                <span className="font-mono text-primary">{performance.calmar_ratio?.toFixed(2) || 'N/A'}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-secondary">Information Ratio</span>
                <span className="font-mono text-primary">{performance.information_ratio?.toFixed(2) || 'N/A'}</span>
              </div>
            </div>
          </div>
          
          <div className="card">
            <h3 className="text-lg font-semibold text-primary mb-4">Trade Statistics</h3>
            <div className="space-y-3">
              <div className="flex justify-between">
                <span className="text-secondary">Total Trades</span>
                <span className="font-mono text-primary">{performance.total_trades || 0}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-secondary">Winning Trades</span>
                <span className="font-mono text-chart-green">{performance.winning_trades || 0}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-secondary">Losing Trades</span>
                <span className="font-mono text-chart-red">{performance.losing_trades || 0}</span>
              </div>
            </div>
          </div>
          
          <div className="card">
            <h3 className="text-lg font-semibold text-primary mb-4">Average Trade</h3>
            <div className="space-y-3">
              <div className="flex justify-between">
                <span className="text-secondary">Avg Win</span>
                <span className="font-mono text-chart-green">
                  ${performance.avg_win?.toLocaleString(undefined, { maximumFractionDigits: 2 }) || '0'}
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-secondary">Avg Loss</span>
                <span className="font-mono text-chart-red">
                  ${performance.avg_loss?.toLocaleString(undefined, { maximumFractionDigits: 2 }) || '0'}
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-secondary">Profit Factor</span>
                <span className="font-mono text-primary">{performance.profit_factor?.toFixed(2) || 'N/A'}</span>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
