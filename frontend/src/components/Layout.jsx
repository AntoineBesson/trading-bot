import React from 'react';
import { NavLink, Outlet } from 'react-router-dom';
import { 
  LayoutDashboard, 
  TrendingUp, 
  Shield, 
  Activity,
  Zap 
} from 'lucide-react';

const navItems = [
  { path: '/', icon: LayoutDashboard, label: 'Strategies' },
  { path: '/performance', icon: TrendingUp, label: 'Performance' },
  { path: '/risk', icon: Shield, label: 'Risk' },
];

export default function Layout() {
  return (
    <div className="min-h-screen bg-background flex">
      {/* Sidebar */}
      <aside className="w-64 border-r border-border bg-surface flex flex-col">
        {/* Logo */}
        <div className="p-6 border-b border-border">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 bg-primary rounded-lg flex items-center justify-center">
              <Zap className="w-6 h-6 text-background" />
            </div>
            <div>
              <h1 className="text-lg font-semibold text-primary">Trading Bot</h1>
              <p className="text-xs text-secondary">Algo Trading System</p>
            </div>
          </div>
        </div>
        
        {/* Navigation */}
        <nav className="flex-1 p-4 space-y-1">
          {navItems.map(({ path, icon: Icon, label }) => (
            <NavLink
              key={path}
              to={path}
              className={({ isActive }) =>
                `nav-link ${isActive ? 'active' : ''}`
              }
            >
              <Icon className="w-5 h-5" />
              <span>{label}</span>
            </NavLink>
          ))}
        </nav>
        
        {/* Status Footer */}
        <div className="p-4 border-t border-border">
          <div className="flex items-center gap-2">
            <Activity className="w-4 h-4 text-chart-green animate-pulse" />
            <span className="text-sm text-secondary">System Active</span>
          </div>
        </div>
      </aside>
      
      {/* Main Content */}
      <main className="flex-1 overflow-auto">
        <Outlet />
      </main>
    </div>
  );
}
