import React, { useState, useEffect } from 'react';
import { 
  Shield, 
  AlertTriangle, 
  Activity,
  TrendingDown,
  PieChart,
  BarChart3,
  Zap,
  Edit3,
  XOctagon,
  AlertCircle,
  Gauge,
  CloudLightning,
  DollarSign,
  Settings,
  Check
} from 'lucide-react';
import { 
  getRisk, 
  getHistory, 
  getAllocations, 
  updateAllocation, 
  killStrategy, 
  killAllStrategies,
  updateRiskLimits
} from '../services/api';
import { 
  AreaChart,
  Area,
  XAxis, 
  YAxis, 
  CartesianGrid, 
  Tooltip, 
  ResponsiveContainer,
  PieChart as RechartsPie,
  Pie,
  Cell,
  BarChart,
  Bar
} from 'recharts';
import AllocationModal from '../components/AllocationModal';

// Risk Metric Card Component
function RiskMetricCard({ icon: Icon, label, value, status, description, children }) {
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
      {children}
    </div>
  );
}

// Allocation Card Component
function AllocationCard({ strategyId, allocation, onEdit, onKill }) {
  const [killing, setKilling] = useState(false);
  
  const handleKill = async () => {
    if (!confirm(`Are you sure you want to KILL ${strategyId}? This will close all positions.`)) {
      return;
    }
    setKilling(true);
    try {
      await onKill(strategyId);
    } finally {
      setKilling(false);
    }
  };
  
  return (
    <div className={`bg-surface-light border rounded-lg p-4 ${allocation.active ? 'border-border' : 'border-chart-red/30'}`}>
      <div className="flex items-start justify-between mb-3">
        <div>
          <h4 className="font-semibold text-primary text-sm">{strategyId.split('_').slice(-2).join(' ')}</h4>
          <div className="flex items-center gap-2 mt-1">
            <span className={`w-2 h-2 rounded-full ${allocation.active ? 'bg-chart-green' : 'bg-chart-red'}`} />
            <span className="text-xs text-secondary">{allocation.active ? 'Active' : 'Inactive'}</span>
          </div>
        </div>
        <div className="flex gap-1">
          <button
            onClick={() => onEdit(strategyId, allocation)}
            className="p-1.5 rounded hover:bg-background transition-colors"
            title="Edit allocation"
          >
            <Edit3 className="w-4 h-4 text-secondary hover:text-primary" />
          </button>
          <button
            onClick={handleKill}
            disabled={killing}
            className="p-1.5 rounded hover:bg-chart-red-light transition-colors"
            title="Kill strategy"
          >
            <XOctagon className={`w-4 h-4 ${killing ? 'text-secondary animate-pulse' : 'text-chart-red'}`} />
          </button>
        </div>
      </div>
      
      <div className="space-y-2 text-sm">
        <div className="flex justify-between">
          <span className="text-secondary">Equity</span>
          <span className="font-mono text-primary">${allocation.equity?.toLocaleString()}</span>
        </div>
        <div className="flex justify-between">
          <span className="text-secondary">Leverage</span>
          <span className="font-mono text-primary">{allocation.leverage?.toFixed(1)}x</span>
        </div>
        <div className="flex justify-between border-t border-border pt-2 mt-2">
          <span className="text-secondary">Exposure</span>
          <span className="font-mono font-semibold text-primary">${allocation.exposure?.toLocaleString()}</span>
        </div>
      </div>
    </div>
  );
}

// Progress Bar Component
function ProgressBar({ value, max, label, color = 'primary', showWarning = false }) {
  const percent = Math.min((value / max) * 100, 100);
  const isWarning = percent > 70;
  const isDanger = percent > 90;
  
  const barColor = isDanger ? 'bg-chart-red' : isWarning ? 'bg-yellow-500' : `bg-${color}`;
  
  return (
    <div>
      <div className="flex justify-between text-sm mb-1">
        <span className="text-secondary">{label}</span>
        <span className="text-primary font-mono">{value.toFixed(1)}%</span>
      </div>
      <div className="h-2 bg-background rounded-full overflow-hidden">
        <div 
          className={`h-full rounded-full transition-all ${barColor}`}
          style={{ width: `${percent}%` }}
        />
      </div>
      {showWarning && isDanger && (
        <p className="text-xs text-chart-red mt-1 flex items-center gap-1">
          <AlertCircle className="w-3 h-3" /> Exceeds safe threshold
        </p>
      )}
    </div>
  );
}

export default function RiskPage() {
  const [risk, setRisk] = useState(null);
  const [history, setHistory] = useState([]);
  const [allocations, setAllocations] = useState({});
  const [loading, setLoading] = useState(true);
  const [modalOpen, setModalOpen] = useState(false);
  const [selectedStrategy, setSelectedStrategy] = useState(null);
  const [selectedAllocation, setSelectedAllocation] = useState(null);
  const [editingLimits, setEditingLimits] = useState(false);
  const [limits, setLimits] = useState({});
  
  const fetchData = async () => {
    try {
      const [riskData, historyData, allocData] = await Promise.all([
        getRisk().catch(() => null),
        getHistory().catch(() => []),
        getAllocations().catch(() => ({ allocations: {} }))
      ]);
      setRisk(riskData);
      setHistory(historyData);
      setAllocations(allocData.allocations || {});
      if (riskData?.limits) {
        setLimits(riskData.limits);
      }
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
  
  // Handlers
  const handleEditAllocation = (strategyId, allocation) => {
    setSelectedStrategy({ id: strategyId, ...allocation });
    setSelectedAllocation(allocation);
    setModalOpen(true);
  };
  
  const handleSaveAllocation = async (strategyId, equity, leverage) => {
    await updateAllocation(strategyId, equity, leverage);
    fetchData();
  };
  
  const handleKillStrategy = async (strategyId) => {
    try {
      await killStrategy(strategyId);
      fetchData();
    } catch (error) {
      alert(`Failed to kill strategy: ${error.message}`);
    }
  };
  
  const handleKillAll = async () => {
    if (!confirm('⚠️ EMERGENCY KILL ALL ⚠️\n\nThis will close ALL positions across ALL strategies.\n\nAre you absolutely sure?')) {
      return;
    }
    try {
      await killAllStrategies();
      fetchData();
    } catch (error) {
      alert(`Failed to kill all: ${error.message}`);
    }
  };
  
  const handleSaveLimits = async () => {
    try {
      await updateRiskLimits(limits);
      setEditingLimits(false);
      fetchData();
    } catch (error) {
      alert(`Failed to save limits: ${error.message}`);
    }
  };
  
  // VaR status helper
  const getVarStatus = (var95) => {
    if (!var95) return 'neutral';
    if (var95 > -2) return 'good';
    if (var95 > -5) return 'warning';
    return 'danger';
  };
  
  // Exposure chart data
  const exposureData = risk?.exposure_by_strategy 
    ? Object.entries(risk.exposure_by_strategy).map(([name, value]) => ({
        name: name.replace(/_/g, ' ').split(' ').slice(-2).join(' '),
        value: Math.abs(value),
        fullName: name
      }))
    : [];
  
  // Strategy type exposure for bar chart
  const typeExposureData = risk?.strategy_type_exposure
    ? Object.entries(risk.strategy_type_exposure).map(([type, value]) => ({
        name: type.replace('Strategy', ''),
        value: value
      }))
    : [];
  
  if (loading) {
    return (
      <div className="p-8 flex items-center justify-center min-h-screen">
        <Activity className="w-8 h-8 text-secondary animate-spin" />
      </div>
    );
  }
  
  const currentDrawdown = risk?.drawdown?.current || 0;
  const maxDrawdown = risk?.drawdown?.max || 0;
  
  return (
    <div className="p-8">
      {/* Header */}
      <div className="flex items-start justify-between mb-8">
        <div>
          <h1 className="text-3xl font-bold text-primary mb-2">Risk Management</h1>
          <p className="text-secondary">Monitor portfolio risk metrics and control exposure</p>
        </div>
        
        {/* Emergency Kill All Button */}
        <button
          onClick={handleKillAll}
          className="flex items-center gap-2 px-4 py-2 bg-chart-red text-white rounded-lg hover:bg-red-600 transition-colors font-semibold"
        >
          <XOctagon className="w-5 h-5" />
          KILL ALL
        </button>
      </div>
      
      {/* Regime Banner */}
      {risk?.regime && (
        <div className={`mb-6 p-4 rounded-xl border flex items-center justify-between ${
          risk.regime.current === 'Volatile' 
            ? 'bg-chart-red-light border-chart-red' 
            : 'bg-chart-green-light border-chart-green'
        }`}>
          <div className="flex items-center gap-3">
            <CloudLightning className={`w-6 h-6 ${risk.regime.current === 'Volatile' ? 'text-chart-red' : 'text-chart-green'}`} />
            <div>
              <span className={`font-semibold ${risk.regime.current === 'Volatile' ? 'text-chart-red' : 'text-chart-green'}`}>
                Market Regime: {risk.regime.current}
              </span>
              <p className="text-sm text-secondary">
                {risk.regime.current === 'Volatile' 
                  ? 'Increased volatility detected - consider reducing exposure'
                  : 'Market conditions are calm - normal trading mode'
                }
              </p>
            </div>
          </div>
          <span className="text-sm text-secondary">
            Confidence: {((risk.regime.confidence || 0) * 100).toFixed(0)}%
          </span>
        </div>
      )}
      
      {/* Risk Summary Cards - Row 1 */}
      <div className="grid grid-cols-1 md:grid-cols-5 gap-4 mb-6">
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
          icon={AlertCircle}
          label="CVaR (95%)"
          value={risk?.cvar_95 ? `${risk.cvar_95.toFixed(2)}%` : 'N/A'}
          status={getVarStatus(risk?.cvar_95)}
          description="Expected Shortfall"
        />
        <RiskMetricCard 
          icon={DollarSign}
          label="Total Exposure"
          value={risk?.total_exposure ? `$${risk.total_exposure.toLocaleString()}` : 'N/A'}
          status="neutral"
        />
      </div>
      
      {/* Margin & Utilization Row */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-8">
        <div className="card">
          <div className="flex items-center gap-2 mb-4">
            <Gauge className="w-5 h-5 text-secondary" />
            <h3 className="font-semibold text-primary">Margin Utilization</h3>
          </div>
          <ProgressBar 
            value={risk?.margin?.utilization || 0} 
            max={100} 
            label="Used / Available"
            showWarning
          />
          <div className="grid grid-cols-2 gap-4 mt-4 pt-4 border-t border-border">
            <div>
              <span className="text-xs text-secondary">Margin Used</span>
              <p className="font-mono text-primary">${(risk?.margin?.used || 0).toLocaleString()}</p>
            </div>
            <div>
              <span className="text-xs text-secondary">Buying Power</span>
              <p className="font-mono text-chart-green">${(risk?.margin?.buying_power || 0).toLocaleString()}</p>
            </div>
          </div>
        </div>
        
        <div className="card">
          <div className="flex items-center gap-2 mb-4">
            <BarChart3 className="w-5 h-5 text-secondary" />
            <h3 className="font-semibold text-primary">Position Concentration</h3>
          </div>
          <ProgressBar 
            value={risk?.current_max_position || 0} 
            max={limits.max_position_pct || 10} 
            label="Max Single Position"
            showWarning
          />
          <ProgressBar 
            value={risk?.sector_concentration || 0} 
            max={limits.max_sector_concentration || 30} 
            label="Strategy Type Concentration"
            showWarning
          />
        </div>
        
        <div className="card">
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-2">
              <Settings className="w-5 h-5 text-secondary" />
              <h3 className="font-semibold text-primary">Risk Limits</h3>
            </div>
            {editingLimits ? (
              <button onClick={handleSaveLimits} className="p-1 text-chart-green hover:bg-chart-green-light rounded">
                <Check className="w-4 h-4" />
              </button>
            ) : (
              <button onClick={() => setEditingLimits(true)} className="p-1 text-secondary hover:bg-surface-light rounded">
                <Edit3 className="w-4 h-4" />
              </button>
            )}
          </div>
          <div className="space-y-3 text-sm">
            <div className="flex justify-between items-center">
              <span className="text-secondary">Max Position %</span>
              {editingLimits ? (
                <input
                  type="number"
                  value={limits.max_position_pct || 10}
                  onChange={(e) => setLimits({...limits, max_position_pct: parseFloat(e.target.value)})}
                  className="w-16 bg-background border border-border rounded px-2 py-1 text-right font-mono text-primary"
                />
              ) : (
                <span className="font-mono text-primary">{limits.max_position_pct || 10}%</span>
              )}
            </div>
            <div className="flex justify-between items-center">
              <span className="text-secondary">VaR Threshold</span>
              {editingLimits ? (
                <input
                  type="number"
                  value={limits.max_var_threshold || -5}
                  onChange={(e) => setLimits({...limits, max_var_threshold: parseFloat(e.target.value)})}
                  className="w-16 bg-background border border-border rounded px-2 py-1 text-right font-mono text-primary"
                  step="0.5"
                />
              ) : (
                <span className="font-mono text-primary">{limits.max_var_threshold || -5}%</span>
              )}
            </div>
            <div className="flex justify-between items-center">
              <span className="text-secondary">Max Drawdown</span>
              {editingLimits ? (
                <input
                  type="number"
                  value={limits.max_drawdown_threshold || -20}
                  onChange={(e) => setLimits({...limits, max_drawdown_threshold: parseFloat(e.target.value)})}
                  className="w-16 bg-background border border-border rounded px-2 py-1 text-right font-mono text-primary"
                />
              ) : (
                <span className="font-mono text-primary">{limits.max_drawdown_threshold || -20}%</span>
              )}
            </div>
          </div>
        </div>
      </div>
      
      {/* Charts Row */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-8">
        {/* Drawdown Chart */}
        <div className="card">
          <h2 className="text-xl font-semibold text-primary mb-6">Drawdown Over Time</h2>
          <ResponsiveContainer width="100%" height={280}>
            <AreaChart data={drawdownData.slice(-100)}>
              <CartesianGrid strokeDasharray="3 3" stroke="#262626" />
              <XAxis 
                dataKey="time"
                tickFormatter={(t) => new Date(t * 1000).toLocaleDateString()}
                stroke="#a3a3a3"
                tick={{ fill: '#a3a3a3', fontSize: 11 }}
              />
              <YAxis 
                stroke="#a3a3a3"
                tick={{ fill: '#a3a3a3', fontSize: 11 }}
                tickFormatter={(v) => `${v.toFixed(0)}%`}
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
        
        {/* Strategy Type Exposure Bar Chart */}
        <div className="card">
          <h2 className="text-xl font-semibold text-primary mb-6">Exposure by Strategy Type</h2>
          {typeExposureData.length > 0 ? (
            <ResponsiveContainer width="100%" height={280}>
              <BarChart data={typeExposureData} layout="vertical">
                <CartesianGrid strokeDasharray="3 3" stroke="#262626" />
                <XAxis 
                  type="number"
                  stroke="#a3a3a3"
                  tick={{ fill: '#a3a3a3', fontSize: 11 }}
                  tickFormatter={(v) => `$${(v/1000).toFixed(0)}k`}
                />
                <YAxis 
                  type="category"
                  dataKey="name"
                  stroke="#a3a3a3"
                  tick={{ fill: '#a3a3a3', fontSize: 11 }}
                  width={100}
                />
                <Tooltip 
                  contentStyle={{ 
                    backgroundColor: '#141414', 
                    border: '1px solid #262626',
                    borderRadius: '8px'
                  }}
                  formatter={(value) => [`$${value.toLocaleString()}`, 'Exposure']}
                />
                <Bar dataKey="value" fill="#ffffff" radius={[0, 4, 4, 0]} />
              </BarChart>
            </ResponsiveContainer>
          ) : (
            <div className="h-[280px] flex items-center justify-center text-secondary">
              No exposure data available
            </div>
          )}
        </div>
      </div>
      
      {/* Allocation Controls & Greeks */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 mb-8">
        {/* Allocation Controls */}
        <div className="lg:col-span-2 card">
          <div className="flex items-center justify-between mb-6">
            <h2 className="text-xl font-semibold text-primary">Strategy Allocations</h2>
            <span className="text-sm text-secondary">{Object.keys(allocations).length} strategies</span>
          </div>
          
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 max-h-[400px] overflow-y-auto pr-2">
            {Object.entries(allocations).map(([strategyId, allocation]) => (
              <AllocationCard
                key={strategyId}
                strategyId={strategyId}
                allocation={allocation}
                onEdit={handleEditAllocation}
                onKill={handleKillStrategy}
              />
            ))}
          </div>
          
          {Object.keys(allocations).length === 0 && (
            <div className="text-center py-8 text-secondary">
              No allocations found
            </div>
          )}
        </div>
        
        {/* Greeks */}
        <div className="card">
          <div className="flex items-center gap-2 mb-6">
            <PieChart className="w-5 h-5 text-secondary" />
            <h2 className="text-xl font-semibold text-primary">Portfolio Greeks</h2>
          </div>
          
          <div className="space-y-4">
            <div className="flex justify-between items-center p-3 bg-surface-light rounded-lg">
              <div>
                <span className="text-secondary text-sm">Delta (Δ)</span>
                <p className="text-xs text-secondary">Directional exposure</p>
              </div>
              <span className={`text-2xl font-mono font-semibold ${
                (risk?.greeks?.delta || 0) >= 0 ? 'text-chart-green' : 'text-chart-red'
              }`}>
                {risk?.greeks?.delta?.toFixed(2) || '0.00'}
              </span>
            </div>
            
            <div className="flex justify-between items-center p-3 bg-surface-light rounded-lg">
              <div>
                <span className="text-secondary text-sm">Gamma (Γ)</span>
                <p className="text-xs text-secondary">Delta sensitivity</p>
              </div>
              <span className="text-2xl font-mono font-semibold text-primary">
                {risk?.greeks?.gamma?.toFixed(4) || '0.0000'}
              </span>
            </div>
            
            <div className="flex justify-between items-center p-3 bg-surface-light rounded-lg">
              <div>
                <span className="text-secondary text-sm">Theta (Θ)</span>
                <p className="text-xs text-secondary">Time decay / day</p>
              </div>
              <span className={`text-2xl font-mono font-semibold ${
                (risk?.greeks?.theta || 0) >= 0 ? 'text-chart-green' : 'text-chart-red'
              }`}>
                ${risk?.greeks?.theta?.toFixed(0) || '0'}
              </span>
            </div>
            
            <div className="flex justify-between items-center p-3 bg-surface-light rounded-lg">
              <div>
                <span className="text-secondary text-sm">Vega (ν)</span>
                <p className="text-xs text-secondary">Vol sensitivity</p>
              </div>
              <span className="text-2xl font-mono font-semibold text-primary">
                ${risk?.greeks?.vega?.toFixed(0) || '0'}
              </span>
            </div>
          </div>
        </div>
      </div>
      
      {/* Risk Alerts */}
      <div className="card">
        <div className="flex items-center gap-2 mb-4">
          <AlertTriangle className="w-5 h-5 text-secondary" />
          <h2 className="text-xl font-semibold text-primary">Risk Alerts</h2>
          {risk?.alerts?.length > 0 && (
            <span className="px-2 py-0.5 bg-chart-red text-white text-xs rounded-full">
              {risk.alerts.length}
            </span>
          )}
        </div>
        
        {risk?.alerts && risk.alerts.length > 0 ? (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
            {risk.alerts.map((alert, idx) => (
              <div 
                key={idx}
                className={`p-4 rounded-lg border flex items-start gap-3 ${
                  alert.severity === 'high' 
                    ? 'border-chart-red bg-chart-red-light' 
                    : alert.severity === 'medium'
                    ? 'border-yellow-500 bg-yellow-500/10'
                    : 'border-border bg-surface-light'
                }`}
              >
                <AlertCircle className={`w-5 h-5 flex-shrink-0 ${
                  alert.severity === 'high' ? 'text-chart-red' : 'text-yellow-500'
                }`} />
                <p className={`text-sm ${
                  alert.severity === 'high' ? 'text-chart-red' : 'text-primary'
                }`}>
                  {alert.message}
                </p>
              </div>
            ))}
          </div>
        ) : (
          <div className="flex items-center gap-3 p-4 bg-chart-green-light border border-chart-green rounded-lg">
            <Shield className="w-6 h-6 text-chart-green" />
            <span className="text-chart-green font-medium">All risk metrics within acceptable limits</span>
          </div>
        )}
      </div>
      
      {/* Allocation Modal */}
      <AllocationModal
        isOpen={modalOpen}
        onClose={() => setModalOpen(false)}
        strategy={selectedStrategy}
        allocation={selectedAllocation}
        onSave={handleSaveAllocation}
      />
    </div>
  );
}
