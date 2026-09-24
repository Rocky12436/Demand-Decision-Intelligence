import React, { useEffect, useState } from 'react';
import { 
  X, 
  HelpCircle, 
  Layers, 
  Cpu, 
  TrendingUp, 
  Calculator, 
  ShieldAlert, 
  CheckCircle2, 
  AlertCircle,
  Database,
  Calendar,
  Sparkles
} from 'lucide-react';
import api from '../../services/api';

export default function SkuExplainabilityModal({ productId, skuName, onClose }) {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [trace, setTrace] = useState(null);

  useEffect(() => {
    if (!productId) return;
    fetchExplainabilityTrace();
  }, [productId]);

  const fetchExplainabilityTrace = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.get(`/explain/${productId}`);
      setTrace(res.data);
    } catch (err) {
      console.error("Failed to load explainability trace:", err);
      setError(err.response?.data?.detail || "Failed to load trace for this SKU.");
    } finally {
      setLoading(false);
    }
  };

  if (!productId) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm animate-in fade-in duration-200">
      <div className="relative w-full max-w-4xl max-h-[90vh] bg-[#0f172a] border border-slate-700/80 rounded-2xl shadow-2xl flex flex-col overflow-hidden text-slate-100 font-sans">
        
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-800 bg-slate-900/80 backdrop-blur-md">
          <div className="flex items-center gap-3">
            <div className="p-2.5 bg-indigo-500/10 border border-indigo-500/30 rounded-xl text-indigo-400">
              <Calculator className="w-5 h-5" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h2 className="text-lg font-bold text-white tracking-wide">
                  SKU Explainability Trace
                </h2>
                <span className="px-2 py-0.5 text-xs font-mono font-semibold bg-indigo-950 text-indigo-300 border border-indigo-800/60 rounded-md">
                  {productId}
                </span>
                {trace?.classification?.cell && (
                  <span className="px-2 py-0.5 text-xs font-bold bg-amber-500/10 text-amber-300 border border-amber-500/30 rounded-md">
                    Cell {trace.classification.cell}
                  </span>
                )}
              </div>
              <p className="text-xs text-slate-400 mt-0.5">
                {skuName || trace?.sku || "Supply Chain Decision & Math Transparency Audit"}
              </p>
            </div>
          </div>
          <button 
            onClick={onClose}
            className="p-2 text-slate-400 hover:text-white hover:bg-slate-800 rounded-lg transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Modal Body */}
        <div className="flex-1 overflow-y-auto p-6 space-y-6 custom-scrollbar">
          {loading ? (
            <div className="flex flex-col items-center justify-center py-20 space-y-4">
              <div className="w-10 h-10 border-4 border-indigo-500/30 border-t-indigo-500 rounded-full animate-spin" />
              <p className="text-sm text-slate-400">Auditing historical demand, model tournaments, and policy formulas...</p>
            </div>
          ) : error ? (
            <div className="p-4 bg-rose-500/10 border border-rose-500/30 rounded-xl text-rose-300 flex items-center gap-3">
              <AlertCircle className="w-5 h-5 flex-shrink-0" />
              <p className="text-sm">{error}</p>
            </div>
          ) : trace ? (
            <>
              {/* SECTION 1: DATA */}
              <div className="p-4 bg-slate-900/60 border border-slate-800 rounded-xl">
                <div className="flex items-center justify-between mb-3">
                  <div className="flex items-center gap-2 text-sm font-semibold text-slate-200">
                    <Database className="w-4 h-4 text-sky-400" />
                    <span>1. Data Observations & Quality</span>
                  </div>
                  <div className="flex items-center gap-1.5">
                    {trace.data?.data_quality_flags?.map((flag, idx) => (
                      <span key={idx} className="px-2 py-0.5 text-[11px] font-medium bg-sky-950 text-sky-300 border border-sky-800 rounded">
                        {flag}
                      </span>
                    ))}
                  </div>
                </div>
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs">
                  <div className="p-2.5 bg-slate-950/60 rounded-lg border border-slate-800/80">
                    <div className="text-slate-400">Total Observations</div>
                    <div className="text-sm font-bold text-white mt-0.5">{trace.data?.observations_count} days</div>
                  </div>
                  <div className="p-2.5 bg-slate-950/60 rounded-lg border border-slate-800/80">
                    <div className="text-slate-400">Non-Zero Demand Days</div>
                    <div className="text-sm font-bold text-white mt-0.5">{trace.data?.non_zero_days} days</div>
                  </div>
                  <div className="p-2.5 bg-slate-950/60 rounded-lg border border-slate-800/80">
                    <div className="text-slate-400">Total Quantity Sold</div>
                    <div className="text-sm font-bold text-white mt-0.5">{trace.data?.total_quantity} units</div>
                  </div>
                  <div className="p-2.5 bg-slate-950/60 rounded-lg border border-slate-800/80">
                    <div className="text-slate-400">Mean Daily Demand (d̄)</div>
                    <div className="text-sm font-bold text-emerald-400 mt-0.5">{trace.data?.mean_daily_demand} / day</div>
                  </div>
                </div>
              </div>

              {/* SECTION 2: CLASSIFICATION */}
              <div className="p-4 bg-slate-900/60 border border-slate-800 rounded-xl">
                <div className="flex items-center justify-between mb-3">
                  <div className="flex items-center gap-2 text-sm font-semibold text-slate-200">
                    <Layers className="w-4 h-4 text-amber-400" />
                    <span>2. Demand Pattern Classification (SBC & ABC-XYZ)</span>
                  </div>
                  <span className="px-2.5 py-1 text-xs font-bold rounded-lg bg-amber-500/10 text-amber-300 border border-amber-500/30">
                    {trace.classification?.sbc_category || trace.classification?.sbc_class}
                  </span>
                </div>
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs mb-3">
                  <div className="p-2.5 bg-slate-950/60 rounded-lg border border-slate-800/80">
                    <div className="text-slate-400">Average Demand Interval (ADI)</div>
                    <div className="text-sm font-bold text-white mt-0.5">{trace.classification?.adi} <span className="text-[10px] text-slate-500">(cut: 1.32)</span></div>
                  </div>
                  <div className="p-2.5 bg-slate-950/60 rounded-lg border border-slate-800/80">
                    <div className="text-slate-400">Demand Variance (CV²)</div>
                    <div className="text-sm font-bold text-white mt-0.5">{trace.classification?.cv2} <span className="text-[10px] text-slate-500">(cut: 0.49)</span></div>
                  </div>
                  <div className="p-2.5 bg-slate-950/60 rounded-lg border border-slate-800/80">
                    <div className="text-slate-400">ABC Value Tier</div>
                    <div className="text-sm font-bold text-indigo-400 mt-0.5">Tier {trace.classification?.abc_class}</div>
                  </div>
                  <div className="p-2.5 bg-slate-950/60 rounded-lg border border-slate-800/80">
                    <div className="text-slate-400">XYZ Predictability</div>
                    <div className="text-sm font-bold text-indigo-400 mt-0.5">Tier {trace.classification?.xyz_class}</div>
                  </div>
                </div>
                <p className="text-xs text-slate-300 bg-slate-950/40 p-2.5 rounded-lg border border-slate-800/60 leading-relaxed font-mono">
                  {trace.classification?.rule_in_words}
                </p>
              </div>

              {/* SECTION 3: MODEL SELECTION TOURNAMENT */}
              <div className="p-4 bg-slate-900/60 border border-slate-800 rounded-xl">
                <div className="flex items-center justify-between mb-3">
                  <div className="flex items-center gap-2 text-sm font-semibold text-slate-200">
                    <Cpu className="w-4 h-4 text-purple-400" />
                    <span>3. Model Selection Tournament</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="text-xs text-slate-400">Chosen:</span>
                    <span className="px-2.5 py-1 text-xs font-bold rounded-lg bg-emerald-500/10 text-emerald-300 border border-emerald-500/30">
                      {trace.model_selection?.chosen_model}
                    </span>
                  </div>
                </div>
                <div className="overflow-x-auto">
                  <table className="w-full text-left text-xs border border-slate-800 rounded-lg overflow-hidden">
                    <thead className="bg-slate-950 text-slate-400 uppercase font-mono text-[10px]">
                      <tr>
                        <th className="p-2.5">Candidate Model</th>
                        <th className="p-2.5">Tournament Status</th>
                        <th className="p-2.5">Backtest WAPE</th>
                        <th className="p-2.5">Selection / Rejection Rationale</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-800 bg-slate-950/30 font-mono">
                      {trace.model_selection?.candidates?.map((cand, idx) => (
                        <tr key={idx} className={cand.status === 'SELECTED' ? 'bg-emerald-950/20' : ''}>
                          <td className="p-2.5 font-bold text-slate-200">{cand.model_name}</td>
                          <td className="p-2.5">
                            {cand.status === 'SELECTED' ? (
                              <span className="inline-flex items-center gap-1 text-emerald-400 font-bold">
                                <CheckCircle2 className="w-3.5 h-3.5" /> SELECTED
                              </span>
                            ) : (
                              <span className="text-slate-500">REJECTED</span>
                            )}
                          </td>
                          <td className="p-2.5 text-slate-300">{cand.wape ? `${cand.wape}%` : 'N/A'}</td>
                          <td className="p-2.5 text-slate-400 font-sans">
                            {cand.status === 'SELECTED' 
                              ? 'Won backtest tournament with optimal balance of precision and generalizability' 
                              : cand.rejection_reason || 'Outperformed by ensemble winner'}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>

              {/* SECTION 4: FORECAST & QUANTILE BANDS */}
              <div className="p-4 bg-slate-900/60 border border-slate-800 rounded-xl">
                <div className="flex items-center justify-between mb-3">
                  <div className="flex items-center gap-2 text-sm font-semibold text-slate-200">
                    <TrendingUp className="w-4 h-4 text-emerald-400" />
                    <span>4. Forecast & Quantile Decomposition</span>
                  </div>
                  <span className="text-xs text-slate-400">14-Day Planning Horizon</span>
                </div>
                <div className="grid grid-cols-3 gap-3 text-center mb-3">
                  <div className="p-3 bg-slate-950/60 rounded-xl border border-slate-800">
                    <div className="text-[11px] text-slate-400 font-medium">10th Percentile (P10)</div>
                    <div className="text-base font-mono font-bold text-amber-300 mt-1">
                      {trace.forecast?.quantile_band?.p10 ?? trace.forecast?.quantiles?.q10 ?? 'N/A'} units
                    </div>
                  </div>
                  <div className="p-3 bg-emerald-950/20 rounded-xl border border-emerald-800/40">
                    <div className="text-[11px] text-emerald-300 font-medium">Point Forecast (P50)</div>
                    <div className="text-lg font-mono font-extrabold text-emerald-400 mt-1">
                      {trace.forecast?.predicted_daily_demand ?? trace.forecast?.predicted_mean} / day
                    </div>
                  </div>
                  <div className="p-3 bg-slate-950/60 rounded-xl border border-slate-800">
                    <div className="text-[11px] text-slate-400 font-medium">90th Percentile (P90)</div>
                    <div className="text-base font-mono font-bold text-sky-300 mt-1">
                      {trace.forecast?.quantile_band?.p90 ?? trace.forecast?.quantiles?.q90 ?? 'N/A'} units
                    </div>
                  </div>
                </div>
              </div>

              {/* SECTION 5: POLICY ARITHMETIC WITH SUBSTITUTED NUMBERS */}
              <div className="p-4 bg-indigo-950/20 border border-indigo-800/40 rounded-xl space-y-3">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2 text-sm font-semibold text-indigo-300">
                    <Calculator className="w-4 h-4 text-indigo-400" />
                    <span>5. Policy Arithmetic with Substituted Numbers</span>
                  </div>
                  <span className="text-[11px] font-mono text-indigo-300/80 bg-indigo-950 px-2 py-0.5 rounded border border-indigo-800/50">
                    Auditable Proof Trace
                  </span>
                </div>
                
                <div className="space-y-2 font-mono text-xs">
                  <div className="p-2.5 bg-slate-950/80 border border-slate-800 rounded-lg">
                    <div className="text-[11px] text-slate-400 font-sans mb-1 font-semibold">Lead-Time Demand (LTD)</div>
                    <div className="text-indigo-200 font-semibold">
                      {trace.policy_arithmetic?.lead_time_demand?.substituted || trace.policy_arithmetic?.ltd_formula}
                    </div>
                  </div>

                  <div className="p-2.5 bg-slate-950/80 border border-slate-800 rounded-lg">
                    <div className="text-[11px] text-slate-400 font-sans mb-1 font-semibold">King's Safety Stock (SS)</div>
                    <div className="text-indigo-200 font-semibold">
                      {trace.policy_arithmetic?.safety_stock?.substituted || trace.policy_arithmetic?.ss_formula}
                    </div>
                  </div>

                  <div className="p-2.5 bg-slate-950/80 border border-slate-800 rounded-lg">
                    <div className="text-[11px] text-slate-400 font-sans mb-1 font-semibold">Reorder Point (ROP)</div>
                    <div className="text-indigo-200 font-semibold">
                      {trace.policy_arithmetic?.reorder_point?.substituted || trace.policy_arithmetic?.rop_formula}
                    </div>
                  </div>

                  <div className="p-2.5 bg-slate-950/80 border border-slate-800 rounded-lg">
                    <div className="text-[11px] text-slate-400 font-sans mb-1 font-semibold">Target Stock Level (TSL)</div>
                    <div className="text-indigo-200 font-semibold">
                      {trace.policy_arithmetic?.target_stock_level?.substituted || trace.policy_arithmetic?.tsl_formula}
                    </div>
                  </div>
                </div>
              </div>

              {/* SECTION 6: ACTIONS & STATUS */}
              <div className={`p-4 rounded-xl border ${
                trace.actions?.stock_status === 'REORDER_REQUIRED'
                  ? 'bg-rose-950/20 border-rose-800/50'
                  : 'bg-emerald-950/20 border-emerald-800/50'
              }`}>
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center gap-2 text-sm font-semibold text-white">
                    <ShieldAlert className="w-4 h-4" />
                    <span>6. Inventory Health & Action Trigger</span>
                  </div>
                  <span className={`px-2.5 py-1 text-xs font-bold rounded-lg border ${
                    trace.actions?.stock_status === 'REORDER_REQUIRED'
                      ? 'bg-rose-500/20 text-rose-300 border-rose-500/40'
                      : 'bg-emerald-500/20 text-emerald-300 border-emerald-500/40'
                  }`}>
                    {trace.actions?.stock_status}
                  </span>
                </div>
                <div className="text-xs text-slate-300 space-y-1">
                  <p className="font-semibold text-slate-200">{trace.actions?.trigger_condition}</p>
                  <p className="text-slate-400">
                    Current On-Hand: <span className="font-mono text-white font-bold">{trace.actions?.current_stock}</span> units | 
                    Reorder Point: <span className="font-mono text-white font-bold">{trace.actions?.reorder_point}</span> units | 
                    Order Rec: <span className="font-mono text-emerald-400 font-bold">{trace.actions?.recommended_order_quantity}</span> units
                  </p>
                </div>
              </div>
            </>
          ) : null}
        </div>

        {/* Footer */}
        <div className="px-6 py-3 border-t border-slate-800 bg-slate-950/80 flex items-center justify-between text-xs text-slate-400">
          <div className="flex items-center gap-1.5">
            <Sparkles className="w-3.5 h-3.5 text-indigo-400" />
            <span>Auditable transparent AI engine powered by King's Safety Stock & Syntetos-Boylan-Croston</span>
          </div>
          <button 
            onClick={onClose}
            className="px-4 py-1.5 bg-slate-800 hover:bg-slate-700 text-white rounded-lg transition-colors font-medium"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
}
