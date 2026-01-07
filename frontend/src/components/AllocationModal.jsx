import React, { useState, useEffect } from 'react';
import { X, DollarSign, TrendingUp, AlertTriangle } from 'lucide-react';

export default function AllocationModal({ isOpen, onClose, strategy, allocation, onSave }) {
  const [equity, setEquity] = useState(0);
  const [leverage, setLeverage] = useState(1);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);
  
  useEffect(() => {
    if (allocation) {
      setEquity(allocation.equity || 0);
      setLeverage(allocation.leverage || 1);
    }
  }, [allocation]);
  
  if (!isOpen) return null;
  
  const exposure = equity * leverage;
  
  const handleSave = async () => {
    setError(null);
    
    if (equity < 0) {
      setError('Equity must be non-negative');
      return;
    }
    if (leverage < 0.1 || leverage > 10) {
      setError('Leverage must be between 0.1x and 10x');
      return;
    }
    
    setSaving(true);
    try {
      await onSave(strategy.id, equity, leverage);
      onClose();
    } catch (err) {
      setError(err.message || 'Failed to update allocation');
    } finally {
      setSaving(false);
    }
  };
  
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      {/* Backdrop */}
      <div 
        className="absolute inset-0 bg-black/70 backdrop-blur-sm"
        onClick={onClose}
      />
      
      {/* Modal */}
      <div className="relative bg-surface border border-border rounded-xl w-full max-w-md p-6 shadow-2xl">
        {/* Header */}
        <div className="flex items-center justify-between mb-6">
          <h2 className="text-xl font-semibold text-primary">Edit Allocation</h2>
          <button 
            onClick={onClose}
            className="p-2 rounded-lg hover:bg-surface-light transition-colors"
          >
            <X className="w-5 h-5 text-secondary" />
          </button>
        </div>
        
        {/* Strategy Info */}
        <div className="bg-surface-light border border-border rounded-lg p-4 mb-6">
          <h3 className="font-semibold text-primary">{strategy?.id}</h3>
          <p className="text-sm text-secondary">{strategy?.type || 'Strategy'}</p>
          {strategy?.symbols && (
            <div className="flex flex-wrap gap-1 mt-2">
              {strategy.symbols.map(sym => (
                <span key={sym} className="text-xs bg-background px-2 py-0.5 rounded font-mono text-secondary">
                  {sym}
                </span>
              ))}
            </div>
          )}
        </div>
        
        {/* Form */}
        <div className="space-y-4">
          {/* Equity Input */}
          <div>
            <label className="block text-sm text-secondary mb-2">
              <DollarSign className="w-4 h-4 inline mr-1" />
              Allocated Equity
            </label>
            <div className="relative">
              <span className="absolute left-3 top-1/2 -translate-y-1/2 text-secondary">$</span>
              <input
                type="number"
                value={equity}
                onChange={(e) => setEquity(parseFloat(e.target.value) || 0)}
                className="w-full bg-background border border-border rounded-lg px-8 py-3 text-primary font-mono focus:outline-none focus:border-primary transition-colors"
                min="0"
                step="1000"
              />
            </div>
          </div>
          
          {/* Leverage Slider */}
          <div>
            <label className="block text-sm text-secondary mb-2">
              <TrendingUp className="w-4 h-4 inline mr-1" />
              Leverage: <span className="text-primary font-semibold">{leverage.toFixed(1)}x</span>
            </label>
            <input
              type="range"
              value={leverage}
              onChange={(e) => setLeverage(parseFloat(e.target.value))}
              className="w-full h-2 bg-surface-light rounded-lg appearance-none cursor-pointer accent-primary"
              min="0.1"
              max="5"
              step="0.1"
            />
            <div className="flex justify-between text-xs text-secondary mt-1">
              <span>0.1x</span>
              <span>1x</span>
              <span>2x</span>
              <span>3x</span>
              <span>5x</span>
            </div>
          </div>
          
          {/* Exposure Preview */}
          <div className="bg-background border border-border rounded-lg p-4">
            <div className="flex justify-between items-center">
              <span className="text-secondary">Total Exposure</span>
              <span className="text-2xl font-semibold font-mono text-primary">
                ${exposure.toLocaleString()}
              </span>
            </div>
            {leverage > 2 && (
              <div className="flex items-center gap-2 mt-2 text-yellow-500 text-sm">
                <AlertTriangle className="w-4 h-4" />
                <span>High leverage increases risk</span>
              </div>
            )}
          </div>
          
          {/* Error */}
          {error && (
            <div className="bg-chart-red-light border border-chart-red rounded-lg p-3 text-chart-red text-sm">
              {error}
            </div>
          )}
        </div>
        
        {/* Actions */}
        <div className="flex gap-3 mt-6">
          <button
            onClick={onClose}
            className="flex-1 btn-outline"
            disabled={saving}
          >
            Cancel
          </button>
          <button
            onClick={handleSave}
            className="flex-1 btn-primary"
            disabled={saving}
          >
            {saving ? 'Saving...' : 'Save Changes'}
          </button>
        </div>
      </div>
    </div>
  );
}
