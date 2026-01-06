import React, { useState, useEffect } from 'react';
import { 
  Shield, 
  AlertTriangle, 
  Activity,
  TrendingDown,
  PieChart,
  BarChart3
} from 'lucide-react';
import { getRisk, getHistory } from '../services/api';
import { 
  BarChart, 
  Bar, 
  XAxis, 
  YAxis, 
  CartesianGrid, 
  Tooltip, 
  ResponsiveContainer,
  PieChart as RechartsPie,
  Pie,
  Cell,
  LineChart,
  Line,
  Legend,
  Area,
  AreaChart
} from 'recharts';

function RiskMetricCard({ icon: Icon, label, value, status, description }) {
  const statusColors = {
    good: 'text-chart-green',
    warning: 'text-yellow-500',
    danger: 'text-chart-red',
    neutral: 'text-primary'
  };
  
  return (
    <div className="card">
      <div className="flex items-center gap-3 mb-2">
        <Icon className="w-5 h-5 text-secondary" />
        <span className="stat-label">{label}</span>
      </div>
      <p className={`stat-value font-mono ${statusColors[status] || 'text-primary'}`}>
        {value}
      </p>
      {description && (
        <p className="text-sm text-secondary mt-1">{description}</p>
      )}
    </div>
  );
}

const COLORS = ['#22c55e', '#ef4444', '#a3a3a3', '#ffffff'];

export default function RiskPage() {
  const [risk, setRisk] = useState(null);
  const [history, setHistory] = useState([]);
  const [loading, setLoading] = useState(true);
  
  const fetchData = async () => {
    try {
      const [riskData, historyData] = await Promise.all([
        getRisk().catch(() => null),
        getHistory().catch(() => [])
      ]);
      setRisk(riskData);
      setHistory(historyData);
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
  
  // Calculate drawdown from history
  const calculateDrawdown = () => {
    if (history.length < 2) return [];
    
    let peak = history[0].value;
    return history.map(point => {
      if (point.value > peak) peak = point.value;
      const drawdown = ((point.value - peak) / peak) * 100;
      return {
        time: point.time,
        value: point.value,
        drawdown: drawdown
      };
    });
  };
  
  const drawdownData = calculateDrawdown();
  const currentDrawdown = drawdownData.length > 0 ? drawdownData[drawdownData.length - 1].drawdown : 0;
  const maxDrawdown = Math.min(...drawdownData.map(d => d.drawdown));
  
  // Get exposure by strategy
  const exposureData = risk?.exposure_by_strategy 
    ? Object.entries(risk.exposure_by_strategy).map(([name, value]) => ({
        name: name.replace('_', ' ').split(' ').slice(-2).join(' '),
        value: Math.abs(value)
      }))
    : [];
  
  // VaR status
  const getVarStatus = (var95) => {
    if (!var95) return 'neutral';
    if (var95 > -2) return 'good';
    if (var95 > -5) return 'warning';
    return 'danger';
  };
  
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
      <div className="mb-8">
        <h1 className="text-3xl font-bold text-primary mb-2">Risk Management</h1>
        <p className="text-secondary">Monitor portfolio risk metrics and exposure</p>
      </div>
      
      {/* Risk Summary Cards */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-8">
        <RiskMetricCard 
          icon={TrendingDown}
          label="Current Drawdown"
          value={`${currentDrawdown.toFixed(2)}%`}
          status={currentDrawdown > -5 ? 'good' : currentDrawdown > -10 ? 'warning' : 'danger'}
        />
        <RiskMetricCard 
          icon={AlertTriangle}
          label="Max Drawdown"
          value={`${maxDrawdown.toFixed(2)}%`}
          status={maxDrawdown > -10 ? 'good' : maxDrawdown > -20 ? 'warning' : 'danger'}
        />
        <RiskMetricCard 
          icon={Shield}
          label="VaR (95%)"
          value={risk?.var_95 ? `${risk.var_95.toFixed(2)}%` : 'N/A'}
          status={getVarStatus(risk?.var_95)}
          description="Daily Value at Risk"
        />
        <RiskMetricCard 
          icon={BarChart3}
          label="Total Exposure"
          value={risk?.total_exposure ? `$${risk.total_exposure.toLocaleString()}` : 'N/A'}
          status="neutral"
        />
      </div>
      
      {/* Charts Row */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-8">
        {/* Drawdown Chart */}
        <div className="card">
          <h2 className="text-xl font-semibold text-primary mb-6">Drawdown Over Time</h2>
          <ResponsiveContainer width="100%" height={300}>
            <AreaChart data={drawdownData.slice(-100)}>
              <CartesianGrid strokeDasharray="3 3" stroke="#262626" />
              <XAxis 
                dataKey="time"
                tickFormatter={(t) => new Date(t * 1000).toLocaleDateString()}
                stroke="#a3a3a3"
                tick={{ fill: '#a3a3a3', fontSize: 12 }}
              />
              <YAxis 
                stroke="#a3a3a3"
                tick={{ fill: '#a3a3a3', fontSize: 12 }}
                tickFormatter={(v) => `${v}%`}
              />
              <Tooltip 
                contentStyle={{ 
                  backgroundColor: '#141414', 
                  border: '1px solid #262626',
                  borderRadius: '8px'
                }}
                labelStyle={{ color: '#a3a3a3' }}
                formatter={(value) => [`${value.toFixed(2)}%`, 'Drawdown']}
                labelFormatter={(t) => new Date(t * 1000).toLocaleString()}
              />
              <Area 
                type="monotone" 
                dataKey="drawdown" 
                stroke="#ef4444" 
                fill="rgba(239, 68, 68, 0.2)"
                strokeWidth={2}
              />
            </AreaChart>
          </ResponsiveContainer>
        </div>
        
        {/* Exposure Pie Chart */}
        <div className="card">
          <h2 className="text-xl font-semibold text-primary mb-6">Exposure by Strategy</h2>
          {exposureData.length > 0 ? (
            <ResponsiveContainer width="100%" height={300}>
              <RechartsPie>
                <Pie
                  data={exposureData}
                  cx="50%"
                  cy="50%"
                  innerRadius={60}
                  outerRadius={100}
                  paddingAngle={2}
                  dataKey="value"
                  label={({ name, percent }) => `${name} (${(percent * 100).toFixed(0)}%)`}
                  labelLine={{ stroke: '#a3a3a3' }}
                >
                  {exposureData.map((entry, index) => (
                    <Cell 
                      key={`cell-${index}`} 
                      fill={index % 2 === 0 ? '#ffffff' : '#a3a3a3'} 
                      stroke="#0a0a0a"
                      strokeWidth={2}
                    />
                  ))}
                </Pie>
                <Tooltip 
                  contentStyle={{ 
                    backgroundColor: '#141414', 
                    border: '1px solid #262626',
                    borderRadius: '8px'
                  }}
                  formatter={(value) => [`$${value.toLocaleString()}`, 'Exposure']}
                />
              </RechartsPie>
            </ResponsiveContainer>
          ) : (
            <div className="h-[300px] flex items-center justify-center">
              <p className="text-secondary">No exposure data available</p>
            </div>
          )}
        </div>
      </div>
      
      {/* Risk Breakdown */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Greeks (for options) */}
        {risk?.greeks && (
          <div className="card">
            <h3 className="text-lg font-semibold text-primary mb-4 flex items-center gap-2">
              <PieChart className="w-5 h-5 text-secondary" />
              Portfolio Greeks
            </h3>
            <div className="space-y-3">
              <div className="flex justify-between">
                <span className="text-secondary">Delta</span>
                <span className={`font-mono ${risk.greeks.delta >= 0 ? 'text-chart-green' : 'text-chart-red'}`}>
                  {risk.greeks.delta?.toFixed(2) || '0.00'}
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-secondary">Gamma</span>
                <span className="font-mono text-primary">{risk.greeks.gamma?.toFixed(4) || '0.00'}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-secondary">Theta</span>
                <span className={`font-mono ${risk.greeks.theta >= 0 ? 'text-chart-green' : 'text-chart-red'}`}>
                  {risk.greeks.theta?.toFixed(2) || '0.00'}
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-secondary">Vega</span>
                <span className="font-mono text-primary">{risk.greeks.vega?.toFixed(2) || '0.00'}</span>
              </div>
            </div>
          </div>
        )}
        
        {/* Position Concentration */}
        <div className="card">
          <h3 className="text-lg font-semibold text-primary mb-4 flex items-center gap-2">
            <BarChart3 className="w-5 h-5 text-secondary" />
            Position Limits
          </h3>
          <div className="space-y-4">
            <div>
              <div className="flex justify-between text-sm mb-1">
                <span className="text-secondary">Max Position Size</span>
                <span className="text-primary">{risk?.max_position_pct ? `${risk.max_position_pct}%` : '10%'}</span>
              </div>
              <div className="h-2 bg-surface-light rounded-full overflow-hidden">
                <div 
                  className="h-full bg-chart-green rounded-full transition-all"
                  style={{ width: `${risk?.current_max_position || 0}%` }}
                />
              </div>
            </div>
            <div>
              <div className="flex justify-between text-sm mb-1">
                <span className="text-secondary">Sector Concentration</span>
                <span className="text-primary">{risk?.sector_concentration ? `${risk.sector_concentration}%` : '0%'}</span>
              </div>
              <div className="h-2 bg-surface-light rounded-full overflow-hidden">
                <div 
                  className="h-full bg-primary rounded-full transition-all"
                  style={{ width: `${risk?.sector_concentration || 0}%` }}
                />
              </div>
            </div>
          </div>
        </div>
        
        {/* Risk Alerts */}
        <div className="card">
          <h3 className="text-lg font-semibold text-primary mb-4 flex items-center gap-2">
            <AlertTriangle className="w-5 h-5 text-secondary" />
            Risk Alerts
          </h3>
          {risk?.alerts && risk.alerts.length > 0 ? (
            <div className="space-y-3">
              {risk.alerts.map((alert, idx) => (
                <div 
                  key={idx}
                  className={`p-3 rounded-lg border ${
                    alert.severity === 'high' 
                      ? 'border-chart-red bg-chart-red-light' 
                      : alert.severity === 'medium'
                      ? 'border-yellow-500 bg-yellow-500/10'
                      : 'border-border bg-surface-light'
                  }`}
                >
                  <p className={`text-sm ${
                    alert.severity === 'high' ? 'text-chart-red' : 'text-primary'
                  }`}>
                    {alert.message}
                  </p>
                </div>
              ))}
            </div>
          ) : (
            <div className="flex items-center gap-2 text-chart-green">
              <Shield className="w-5 h-5" />
              <span>No active risk alerts</span>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
