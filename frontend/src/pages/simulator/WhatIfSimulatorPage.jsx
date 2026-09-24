import React, { useState, useEffect, useMemo, useRef } from 'react';
import {
  ResponsiveContainer,
  ComposedChart,
  Line,
  Area,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
  Legend,
} from 'recharts';
import {
  Sliders,
  TrendingUp,
  AlertTriangle,
  RotateCcw,
  Save,
  CheckCircle2,
  Loader2,
  X,
} from 'lucide-react';
import api from '../../services/api';
import {
  PageShell,
  PageHeader,
  Card,
  StatCard,
  StatusBadge,
  DataTable,
} from '../../components/ui';

const DEFAULT_SIM_PARAMS = {
  serviceLevel: 0.95,
  leadTimeDays: 7,
  reviewPeriodDays: 7,
  demandMultiplier: 1.0,
  priceChangePct: 0.0,
  budget: 250000,
  holdingCostRate: 0.20,
};

export default function WhatIfSimulatorPage() {
  const [params, setParams] = useState(DEFAULT_SIM_PARAMS);
  const [simulationData, setSimulationData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [savingPolicy, setSavingPolicy] = useState(false);
  const [saveSuccessMsg, setSaveSuccessMsg] = useState(null);
  const [showSaveModal, setShowSaveModal] = useState(false);
  const [selectedCellTarget, setSelectedCellTarget] = useState('ALL');

  // Debounced execution timer ref
  const debounceTimerRef = useRef(null);

  // Trigger simulation whenever params change
  useEffect(() => {
    if (debounceTimerRef.current) {
      clearTimeout(debounceTimerRef.current);
    }
    debounceTimerRef.current = setTimeout(() => {
      runSimulation();
    }, 300);

    return () => {
      if (debounceTimerRef.current) clearTimeout(debounceTimerRef.current);
    };
  }, [params]);

  const runSimulation = async () => {
    setLoading(true);
    try {
      const payload = {
        service_level: parseFloat(params.serviceLevel),
        lead_time_days: parseInt(params.leadTimeDays) || null,
        review_period_days: parseInt(params.reviewPeriodDays) || null,
        demand_multiplier: parseFloat(params.demandMultiplier),
        price_change_pct: parseFloat(params.priceChangePct),
        budget: parseFloat(params.budget) || null,
        holding_cost_rate: parseFloat(params.holdingCostRate),
      };
      const res = await api.post('/inventory/simulate', payload);
      if (res?.data?.status === 'success') {
        setSimulationData(res.data);
      }
    } catch (err) {
      console.error('Simulation failed', err);
    } finally {
      setLoading(false);
    }
  };

  const handleReset = () => {
    setParams(DEFAULT_SIM_PARAMS);
  };

  const handleSavePolicy = async () => {
    setSavingPolicy(true);
    try {
      const payload = {
        service_level: parseFloat(params.serviceLevel),
        lead_time_days: parseInt(params.leadTimeDays) || null,
        review_period_days: parseInt(params.reviewPeriodDays) || null,
        cell: selectedCellTarget,
      };
      const res = await api.post('/inventory/simulate/save-policy', payload);
      if (res?.data?.status === 'success') {
        setShowSaveModal(false);
        setSaveSuccessMsg(`Policy saved! Service level set to ${(params.serviceLevel * 100).toFixed(0)}% for ${selectedCellTarget === 'ALL' ? 'all products' : selectedCellTarget + ' products'}.`);
        setTimeout(() => setSaveSuccessMsg(null), 5000);
      }
    } catch (err) {
      console.error('Failed to save policy', err);
      alert('Failed to save policy. Please try again.');
    } finally {
      setSavingPolicy(false);
    }
  };

  const baseline = simulationData?.baseline || {};
  const scenario = simulationData?.scenario || {};
  const delta = simulationData?.delta || {};
  const costCurve = simulationData?.cost_curve || [];

  const fmtINR = (v) => `₹${Math.round(v || 0).toLocaleString('en-IN')}`;

  return (
    <PageShell maxWidth="1400px">
      <PageHeader
        icon={Sliders}
        title="What-If Simulator"
        subtitle="Drag the sliders to see how changes in delivery time, demand, or pricing affect your stock costs. All numbers update instantly."
        actions={
          <div style={{ display: 'flex', gap: '8px' }}>
            <button onClick={handleReset} className="diq-btn diq-btn-secondary">
              <RotateCcw size={14} /> Reset
            </button>
            <button onClick={() => setShowSaveModal(true)} className="diq-btn diq-btn-primary">
              <Save size={14} /> Save as Policy
            </button>
          </div>
        }
      />

      {saveSuccessMsg && (
        <div style={{
          padding: '10px 14px', borderRadius: 'var(--border-radius-md)', marginBottom: '16px',
          backgroundColor: 'var(--status-success-bg)', border: '1px solid var(--status-success-border)',
          color: 'var(--status-success-text)', fontSize: '13px',
          display: 'flex', alignItems: 'center', gap: '6px',
        }}>
          <CheckCircle2 size={16} /> {saveSuccessMsg}
        </div>
      )}

      <div style={{ display: 'grid', gridTemplateColumns: '1fr', gap: '20px' }}>

        {/* ── Simulation Controls ── */}
        <Card title="Scenario Settings" icon={Sliders} subtitle="Adjust these values to simulate different business scenarios.">
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(250px, 1fr))', gap: '24px' }}>

            {/* Service Level */}
            <SliderControl
              label="Service Level"
              hint="How often do you want to be in stock?"
              value={params.serviceLevel}
              min={0.80} max={0.999} step={0.005}
              displayValue={`${(params.serviceLevel * 100).toFixed(1)}%`}
              onChange={(v) => setParams({ ...params, serviceLevel: v })}
              marks={['80%', '95%', '99.9%']}
            />

            {/* Lead Time */}
            <SliderControl
              label="Supplier Delivery Time"
              hint="Days from placing order to receiving goods"
              value={params.leadTimeDays}
              min={1} max={45} step={1}
              displayValue={`${params.leadTimeDays} days`}
              onChange={(v) => setParams({ ...params, leadTimeDays: v })}
              marks={['1 day', '7 days', '45 days']}
            />

            {/* Review Period */}
            <SliderControl
              label="How Often You Check Stock"
              hint="Days between inventory reviews"
              value={params.reviewPeriodDays}
              min={1} max={30} step={1}
              displayValue={`${params.reviewPeriodDays} days`}
              onChange={(v) => setParams({ ...params, reviewPeriodDays: v })}
              marks={['Daily', 'Weekly', 'Monthly']}
            />

            {/* Demand Multiplier */}
            <SliderControl
              label="Demand Change"
              hint="Simulate a sales surge or slump"
              value={params.demandMultiplier}
              min={0.5} max={2.0} step={0.05}
              displayValue={`${params.demandMultiplier}× (${params.demandMultiplier >= 1 ? '+' : ''}${Math.round((params.demandMultiplier - 1) * 100)}%)`}
              onChange={(v) => setParams({ ...params, demandMultiplier: v })}
              marks={['-50%', 'Normal', '+100%']}
            />

            {/* Price Change */}
            <SliderControl
              label="Price Change"
              hint="Discount or price increase effect"
              value={params.priceChangePct}
              min={-40} max={40} step={1}
              displayValue={`${params.priceChangePct >= 0 ? '+' : ''}${params.priceChangePct}%`}
              onChange={(v) => setParams({ ...params, priceChangePct: v })}
              marks={['-40%', '0%', '+40%']}
            />

            {/* Budget */}
            <div>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '4px' }}>
                <label style={labelStyle}>Total Budget for Purchasing</label>
                <span style={{ fontSize: '13px', fontWeight: 700, color: 'var(--accent-primary)' }}>
                  {fmtINR(params.budget)}
                </span>
              </div>
              <input
                type="number"
                step="10000"
                value={params.budget}
                onChange={(e) => setParams({ ...params, budget: parseFloat(e.target.value) || 0 })}
                style={{
                  width: '100%', padding: '8px 10px', borderRadius: 'var(--border-radius-md)',
                  border: '1px solid var(--border-strong)', backgroundColor: '#ffffff',
                  color: 'var(--text-primary)', fontSize: '13px',
                }}
              />
            </div>
          </div>

          {loading && (
            <div style={{ display: 'flex', alignItems: 'center', gap: '6px', marginTop: '12px', fontSize: '12px', color: 'var(--accent-primary)' }}>
              <Loader2 size={14} style={{ animation: 'spin 1s linear infinite' }} /> Calculating...
            </div>
          )}
        </Card>

        {/* ── Results KPI Cards ── */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(170px, 1fr))', gap: '12px' }}>
          <StatCard
            label="Money Tied in Stock"
            value={fmtINR(scenario.total_working_capital)}
            trend={delta.working_capital_delta > 0
              ? `+${fmtINR(delta.working_capital_delta)}`
              : fmtINR(delta.working_capital_delta)}
            trendDirection={delta.working_capital_delta > 0 ? 'up' : 'down'}
            trendPositive={false}
          />
          <StatCard
            label="Annual Storage Cost"
            value={fmtINR(scenario.total_holding_cost)}
            subtext={`Was ${fmtINR(baseline.total_holding_cost)}`}
          />
          <StatCard
            label="Expected Lost Sales"
            value={`${Math.round(scenario.expected_stockout_units || 0).toLocaleString('en-IN')} units`}
            subtext={`Change: ${Math.round(delta.stockout_units_delta || 0)} units`}
          />
          <StatCard
            label="Total Cost"
            value={fmtINR(scenario.total_cost)}
            trend={delta.total_cost_delta > 0
              ? `+${fmtINR(delta.total_cost_delta)}`
              : fmtINR(delta.total_cost_delta)}
            trendDirection={delta.total_cost_delta > 0 ? 'up' : 'down'}
            trendPositive={false}
          />
        </div>

        {/* Budget warning */}
        {scenario.budget_feasible === false && (
          <div style={{
            padding: '12px 16px', borderRadius: 'var(--border-radius-md)',
            backgroundColor: 'var(--status-critical-bg)', border: '1px solid var(--status-critical-border)',
            color: 'var(--status-critical-text)', fontSize: '13px',
            display: 'flex', alignItems: 'center', gap: '8px',
          }}>
            <AlertTriangle size={18} style={{ flexShrink: 0 }} />
            <div>
              <strong>Over budget:</strong> This scenario needs {fmtINR(scenario.total_spend_required)} but your budget is only {fmtINR(params.budget)}.
              You're {fmtINR(Math.abs(scenario.budget_delta || 0))} over.
            </div>
          </div>
        )}

        {/* ── Cost Trade-Off Chart ── */}
        <Card
          title="Cost vs Service Level"
          subtitle="See how costs rise sharply as you increase service level. Find the sweet spot for your business."
        >
          <div style={{ width: '100%', height: '300px' }}>
            <ResponsiveContainer width="100%" height="100%">
              <ComposedChart data={costCurve} margin={{ top: 10, right: 20, left: 10, bottom: 5 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--border-subtle)" />
                <XAxis
                  dataKey="service_level_pct"
                  tickFormatter={(v) => `${v}%`}
                  stroke="var(--text-muted)"
                  fontSize={11}
                />
                <YAxis
                  tickFormatter={(v) => `₹${(v / 1000).toFixed(0)}k`}
                  stroke="var(--text-muted)"
                  fontSize={11}
                />
                <Tooltip
                  contentStyle={{
                    backgroundColor: '#ffffff',
                    borderColor: 'var(--border-subtle)',
                    borderRadius: '8px',
                    boxShadow: 'var(--shadow-dropdown)',
                    fontSize: 12,
                  }}
                  formatter={(val, name) => [`₹${Math.round(val).toLocaleString('en-IN')}`, name]}
                  labelFormatter={(l) => `Service Level: ${l}%`}
                />
                <Legend />
                <Area
                  type="monotone"
                  dataKey="total_cost"
                  name="Total Cost"
                  fill="rgba(30, 64, 175, 0.08)"
                  stroke="var(--accent-primary)"
                  strokeWidth={2}
                />
                <Line
                  type="monotone"
                  dataKey="holding_cost"
                  name="Storage Cost"
                  stroke="var(--status-success-icon)"
                  strokeWidth={2}
                  dot={false}
                />
                <Line
                  type="monotone"
                  dataKey="stockout_cost"
                  name="Lost Sales Cost"
                  stroke="var(--status-critical-icon)"
                  strokeWidth={2}
                  strokeDasharray="4 4"
                  dot={false}
                />
              </ComposedChart>
            </ResponsiveContainer>
          </div>
        </Card>

        {/* ── Most Affected Products ── */}
        {simulationData?.top_impacted_skus?.length > 0 && (
          <Card title="Most Affected Products" subtitle="These products would see the biggest changes under this scenario.">
            <DataTable
              columns={[
                { key: 'product_id', title: 'Product ID', render: (v) => <span style={{ fontWeight: 600 }}>#{v}</span> },
                {
                  key: 'baseline_ss', title: 'Safety Stock Change',
                  render: (v, row) => (
                    <span className="tabular-nums" style={{ fontFamily: 'var(--font-mono)', fontSize: '12px' }}>
                      {v} → <strong style={{ color: 'var(--accent-primary)' }}>{row.scenario_ss}</strong>
                    </span>
                  )
                },
                {
                  key: 'baseline_rop', title: 'Reorder Point Change',
                  render: (v, row) => (
                    <span className="tabular-nums" style={{ fontFamily: 'var(--font-mono)', fontSize: '12px' }}>
                      {v} → <strong style={{ color: 'var(--accent-primary)' }}>{row.scenario_rop}</strong>
                    </span>
                  )
                },
                { key: 'working_capital_change', title: 'Capital Change', isNumeric: true, render: (v) => fmtINR(v) },
                { key: 'total_cost_change', title: 'Cost Change', isNumeric: true, render: (v) => fmtINR(v) },
              ]}
              data={simulationData.top_impacted_skus}
              keyField="product_id"
            />
          </Card>
        )}
      </div>

      {/* ── Save Policy Modal ── */}
      {showSaveModal && (
        <div style={{
          position: 'fixed', inset: 0, zIndex: 50,
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          backgroundColor: 'rgba(0, 0, 0, 0.4)', padding: '16px',
        }}>
          <div style={{
            backgroundColor: '#ffffff', border: '1px solid var(--border-subtle)',
            borderRadius: '12px', maxWidth: '420px', width: '100%',
            padding: '24px', boxShadow: 'var(--shadow-dropdown)',
          }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
              <h3 style={{ fontSize: '17px', fontWeight: 700, color: 'var(--text-primary)', display: 'flex', alignItems: 'center', gap: '8px' }}>
                <Save size={20} style={{ color: 'var(--accent-primary)' }} />
                Save This Policy
              </h3>
              <button onClick={() => setShowSaveModal(false)} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-muted)' }}>
                <X size={20} />
              </button>
            </div>

            <p style={{ fontSize: '13px', color: 'var(--text-secondary)', marginBottom: '16px' }}>
              This will update your inventory policy with the current settings:
            </p>

            <div style={{
              padding: '12px 14px', backgroundColor: 'var(--bg-surface-subtle)',
              borderRadius: 'var(--border-radius-md)', border: '1px solid var(--border-subtle)',
              fontSize: '13px', marginBottom: '16px',
            }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '4px' }}>
                <span style={{ color: 'var(--text-muted)' }}>Service Level:</span>
                <span style={{ fontWeight: 600 }}>{(params.serviceLevel * 100).toFixed(1)}%</span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <span style={{ color: 'var(--text-muted)' }}>Review Frequency:</span>
                <span style={{ fontWeight: 600 }}>Every {params.reviewPeriodDays} days</span>
              </div>
            </div>

            <div style={{ marginBottom: '16px' }}>
              <label style={labelStyle}>Apply to which products?</label>
              <select
                value={selectedCellTarget}
                onChange={(e) => setSelectedCellTarget(e.target.value)}
                style={{
                  width: '100%', padding: '8px 10px', borderRadius: 'var(--border-radius-md)',
                  border: '1px solid var(--border-strong)', backgroundColor: '#ffffff',
                  color: 'var(--text-primary)', fontSize: '13px',
                }}
              >
                <option value="ALL">All Products</option>
                <option value="AX">AX — High Value, Steady Demand</option>
                <option value="AY">AY — High Value, Variable Demand</option>
                <option value="AZ">AZ — High Value, Unpredictable</option>
                <option value="BX">BX — Medium Value, Steady</option>
                <option value="CX">CX — Low Value, Steady</option>
              </select>
            </div>

            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '8px' }}>
              <button onClick={() => setShowSaveModal(false)} className="diq-btn diq-btn-secondary">
                Cancel
              </button>
              <button onClick={handleSavePolicy} disabled={savingPolicy} className="diq-btn diq-btn-primary" style={{ opacity: savingPolicy ? 0.5 : 1 }}>
                {savingPolicy ? 'Saving...' : 'Save Policy'}
              </button>
            </div>
          </div>
        </div>
      )}

      <style>{`
        @keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }
      `}</style>
    </PageShell>
  );
}

// Reusable slider control component
function SliderControl({ label, hint, value, min, max, step, displayValue, onChange, marks = [] }) {
  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '4px' }}>
        <div>
          <label style={labelStyle}>{label}</label>
          {hint && <div style={{ fontSize: '11px', color: 'var(--text-muted)', marginTop: '-2px' }}>{hint}</div>}
        </div>
        <span style={{ fontSize: '14px', fontWeight: 700, color: 'var(--accent-primary)', whiteSpace: 'nowrap' }}>
          {displayValue}
        </span>
      </div>
      <input
        type="range"
        min={min} max={max} step={step}
        value={value}
        onChange={(e) => onChange(parseFloat(e.target.value))}
        style={{ width: '100%', accentColor: 'var(--accent-primary)', cursor: 'pointer' }}
      />
      {marks.length > 0 && (
        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '10px', color: 'var(--text-muted)' }}>
          {marks.map((m, i) => <span key={i}>{m}</span>)}
        </div>
      )}
    </div>
  );
}

const labelStyle = {
  display: 'block',
  fontSize: '12px',
  fontWeight: 600,
  color: 'var(--text-secondary)',
  marginBottom: '2px',
};
