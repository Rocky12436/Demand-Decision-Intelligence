import React, { useState, useEffect } from 'react';
import { Outlet, useLocation } from 'react-router-dom';
import Sidebar from './Sidebar';
import Header from './Header';
import FloatingChatBot from '../common/FloatingChatBot';

const titleMap = {
  '/dashboard': 'Dashboard Overview',
  '/upload': 'Data Ingestion & Validation',
  '/forecast': 'Demand Forecasting Engine',
  '/inventory': 'Inventory Intelligence & Risk',
  '/trends': 'Trend Analysis & Anomalies',
  '/price-insights': 'Price Insights & Elasticity',
  '/evaluation': 'Model Performance Evaluation',
  '/assistant': 'AI Advisor & Decision Intelligence Studio',
  '/calendar': 'Indian Festival & Holiday Calendar',
};

export default function Layout() {
  const location = useLocation();
  const pageTitle = titleMap[location.pathname] || 'Demand Decision Intelligence';
  const [degradedInfo, setDegradedInfo] = useState(null);

  useEffect(() => {
    const checkHealth = async () => {
      try {
        const res = await fetch('/api/health');
        if (res.ok) {
          const data = await res.json();
          if (data.is_degraded) {
            setDegradedInfo(data);
          } else {
            setDegradedInfo(null);
          }
        }
      } catch (err) {
        // Ignored in health poll
      }
    };
    checkHealth();
    const interval = setInterval(checkHealth, 15000);
    return () => clearInterval(interval);
  }, []);

  return (
    <div className="app-container">
      <Sidebar />
      <div className="main-content-area">
        {/* Persistent Degraded Mode Banner (Prompt 3.4) */}
        {degradedInfo && (
          <div className="bg-amber-600 text-white text-xs font-semibold py-2.5 px-6 flex items-center justify-between shadow-md sticky top-0 z-50 transition-all">
            <div className="flex items-center gap-2.5">
              <span className="text-base">⚠️</span>
              <span>
                Read-only mode: using cached data from {degradedInfo.degraded_since ? new Date(degradedInfo.degraded_since).toLocaleString() : 'active session'}. All database mutations are blocked until primary database recovers.
              </span>
            </div>
            <span className="uppercase tracking-wider text-[10px] bg-amber-800/80 px-2.5 py-1 rounded font-bold">
              Degraded Mode Active
            </span>
          </div>
        )}
        <Header title={pageTitle} />
        <main className="page-container">
          <Outlet />
        </main>
        <FloatingChatBot />
      </div>
    </div>
  );
}
