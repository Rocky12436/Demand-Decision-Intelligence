import React, { useState, useEffect } from 'react';
import { X, Check, Clock, AlertTriangle, AlertCircle, Info, ExternalLink, RefreshCw } from 'lucide-react';
import { useNavigate } from 'react-router-dom';

export default function AlertInboxModal({ isOpen, onClose, onAlertsUpdated }) {
  const [alerts, setAlerts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [filterSeverity, setFilterSeverity] = useState('all');
  const navigate = useNavigate();

  const fetchAlerts = async () => {
    setLoading(true);
    try {
      const res = await fetch('/api/alerts?dataset_id=1');
      if (res.ok) {
        const data = await res.json();
        setAlerts(data.alerts || []);
      }
    } catch (err) {
      console.error('Failed to load alerts:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (isOpen !== false) {
      fetchAlerts();
    }
  }, [isOpen]);

  const handleAcknowledge = async (alertId) => {
    try {
      const res = await fetch(`/api/alerts/${alertId}/acknowledge`, { method: 'POST' });
      if (res.ok) {
        setAlerts(prev => prev.filter(a => a.id !== alertId));
        if (onAlertsUpdated) onAlertsUpdated();
      }
    } catch (err) {
      console.error('Failed to acknowledge alert:', err);
    }
  };

  const handleSnooze = async (alertId) => {
    try {
      const res = await fetch(`/api/alerts/${alertId}/snooze`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ snooze_hours: 24 })
      });
      if (res.ok) {
        setAlerts(prev => prev.filter(a => a.id !== alertId));
        if (onAlertsUpdated) onAlertsUpdated();
      }
    } catch (err) {
      console.error('Failed to snooze alert:', err);
    }
  };

  const filteredAlerts = alerts.filter(a => {
    if (filterSeverity === 'all') return true;
    return a.severity === filterSeverity;
  });

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4">
      <div className="bg-slate-900 border border-slate-700 w-full max-w-2xl rounded-xl shadow-2xl overflow-hidden flex flex-col max-h-[85vh] text-slate-100 animate-in fade-in zoom-in-95 duration-200">
        
        {/* Header */}
        <div className="p-4 border-b border-slate-800 flex items-center justify-between bg-slate-950/80">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-lg bg-blue-500/20 text-blue-400 flex items-center justify-center font-bold">
              🔔
            </div>
            <div>
              <h3 className="font-semibold text-base text-white">System Alert Inbox</h3>
              <p className="text-xs text-slate-400">Proactive alerts deduplicated & severity-gated (Prompt 4.4)</p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <button 
              onClick={fetchAlerts}
              className="p-1.5 rounded-lg hover:bg-slate-800 text-slate-400 hover:text-white transition"
              title="Refresh"
            >
              <RefreshCw size={16} />
            </button>
            <button 
              onClick={onClose}
              className="p-1.5 rounded-lg hover:bg-slate-800 text-slate-400 hover:text-white transition"
            >
              <X size={18} />
            </button>
          </div>
        </div>

        {/* Severity Filter Tabs */}
        <div className="flex border-b border-slate-800 px-4 pt-2 bg-slate-950/40 text-xs gap-2">
          {['all', 'critical', 'warning', 'info'].map(sev => (
            <button
              key={sev}
              onClick={() => setFilterSeverity(sev)}
              className={`pb-2 px-2.5 font-medium uppercase tracking-wider transition-all border-b-2 ${
                filterSeverity === sev 
                  ? 'border-blue-500 text-blue-400' 
                  : 'border-transparent text-slate-400 hover:text-slate-200'
              }`}
            >
              {sev}
            </button>
          ))}
        </div>

        {/* Alerts List */}
        <div className="flex-1 overflow-y-auto p-4 space-y-3">
          {loading ? (
            <div className="text-center py-10 text-slate-400 text-sm">Loading active alerts...</div>
          ) : filteredAlerts.length === 0 ? (
            <div className="text-center py-12 text-slate-500 text-sm">
              <div className="text-3xl mb-2">🎉</div>
              No active alerts matching filter. All systems operational.
            </div>
          ) : (
            filteredAlerts.map(alert => {
              const isCrit = alert.severity === 'critical';
              const isWarn = alert.severity === 'warning';
              const badgeBg = isCrit ? 'bg-red-500/15 text-red-400 border-red-500/30' :
                              isWarn ? 'bg-amber-500/15 text-amber-400 border-amber-500/30' :
                              'bg-blue-500/15 text-blue-400 border-blue-500/30';
              const IconComponent = isCrit ? AlertCircle : isWarn ? AlertTriangle : Info;

              return (
                <div 
                  key={alert.id}
                  className="bg-slate-800/60 border border-slate-700/70 rounded-lg p-3.5 hover:border-slate-600 transition flex flex-col gap-2"
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="flex items-start gap-2.5">
                      <IconComponent size={18} className={`mt-0.5 ${isCrit ? 'text-red-400' : isWarn ? 'text-amber-400' : 'text-blue-400'}`} />
                      <div>
                        <div className="flex items-center gap-2 flex-wrap">
                          <span className={`text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded border ${badgeBg}`}>
                            {alert.type}
                          </span>
                          <h4 className="font-semibold text-sm text-slate-100">{alert.title}</h4>
                        </div>
                        <p className="text-xs text-slate-300 mt-1 leading-relaxed">{alert.body}</p>
                      </div>
                    </div>
                    <span className="text-[10px] text-slate-400 whitespace-nowrap">
                      {alert.fired_at ? new Date(alert.fired_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : 'Now'}
                    </span>
                  </div>

                  {/* Action Bar */}
                  <div className="flex items-center justify-between pt-2 border-t border-slate-700/40 text-xs">
                    {alert.product_id ? (
                      <button
                        onClick={() => {
                          onClose();
                          navigate(`/forecast?sku=${alert.product_id}`);
                        }}
                        className="text-blue-400 hover:text-blue-300 flex items-center gap-1 text-[11px]"
                      >
                        View SKU Analysis <ExternalLink size={12} />
                      </button>
                    ) : <span />}

                    <div className="flex items-center gap-2">
                      <button
                        onClick={() => handleSnooze(alert.id)}
                        className="px-2.5 py-1 rounded bg-slate-700/60 hover:bg-slate-700 text-slate-300 flex items-center gap-1 transition text-xs"
                        title="Snooze for 24h"
                      >
                        <Clock size={12} /> Snooze
                      </button>
                      <button
                        onClick={() => handleAcknowledge(alert.id)}
                        className="px-2.5 py-1 rounded bg-emerald-600 hover:bg-emerald-500 text-white font-medium flex items-center gap-1 transition text-xs"
                      >
                        <Check size={12} /> Acknowledge
                      </button>
                    </div>
                  </div>
                </div>
              );
            })
          )}
        </div>

        {/* Footer */}
        <div className="p-3 border-t border-slate-800 bg-slate-950/60 text-right">
          <button
            onClick={onClose}
            className="px-4 py-1.5 text-xs rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 transition"
          >
            Close
          </button>
        </div>

      </div>
    </div>
  );
}
