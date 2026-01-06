import React from 'react';
import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { AlertTriangle } from 'lucide-react';

import Layout from './components/Layout';
import StrategiesPage from './pages/StrategiesPage';
import PerformancePage from './pages/PerformancePage';
import RiskPage from './pages/RiskPage';

// --- ERROR BOUNDARY ---
class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }

  componentDidCatch(error, errorInfo) {
    console.error("Uncaught error:", error, errorInfo);
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="p-8 bg-background min-h-screen flex flex-col items-center justify-center">
          <div className="card max-w-lg w-full text-center">
            <AlertTriangle className="w-12 h-12 text-chart-red mx-auto mb-4" />
            <h1 className="text-2xl font-bold text-primary mb-2">Something went wrong</h1>
            <pre className="bg-surface-light p-4 rounded-lg border border-border overflow-auto text-xs text-secondary text-left mb-4">
              {this.state.error && this.state.error.toString()}
            </pre>
            <button 
              onClick={() => window.location.reload()} 
              className="btn-primary"
            >
              Reload Page
            </button>
          </div>
        </div>
      );
    }

    return this.props.children; 
  }
}

// --- MAIN APP ---
function App() {
  return (
    <ErrorBoundary>
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<Layout />}>
            <Route index element={<StrategiesPage />} />
            <Route path="performance" element={<PerformancePage />} />
            <Route path="risk" element={<RiskPage />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </ErrorBoundary>
  );
}

export default App;