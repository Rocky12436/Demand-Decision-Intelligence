import React, { useEffect, useState, useMemo } from 'react';
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
  TrendingUp,
  Cpu,
  Sparkles,
  BarChart3,
  Calendar,
  CheckCircle2,
  AlertCircle,
  RefreshCw,
  Award,
  Layers,
  Activity,
  History,
} from 'lucide-react';
import api, { recomputeForecast } from '../../services/api';
import { PageShell, PageHeader, Card, DataTable, Badge, MetricLeaderboardCard } from '../../components/ui';

const HORIZONS = [7, 14, 30];
const AVAILABLE_MODELS = [
  { id: 'prophet', name: 'Facebook Prophet', tag: 'ML / Seasonality', color: '#3b82f6' },
  { id: 'moving_avg', name: 'Moving Average (7d)', tag: 'Statistical', color: '#f59e0b' },
  { id: 'naive', name: 'Naive Baseline', tag: 'Baseline', color: '#06b6d4' },
];

export default function ForecastPage() {
  // Config state
  const [topProducts, setTopProducts] = useState(['19512', '391306', '12872', '3881', '445675']);
  const [selectedProduct, setSelectedProduct] = useState('19512');
  const [selectedHorizon, setSelectedHorizon] = useState(7);
  const [selectedModels, setSelectedModels] = useState(['prophet', 'moving_avg', 'naive']);
  const [activeModelTab, setActiveModelTab] = useState('prophet');

  // Data state
  const [runs, setRuns] = useState([]);
  const [activeRunDetail, setActiveRunDetail] = useState(null);
  const [loading, setLoading] = useState(false);
  const [chartLoading, setChartLoading] = useState(false);
  const [runningForecast, setRunningForecast] = useState(false);
  const [feedbackMsg, setFeedbackMsg] = useState('');
  const [errorMsg, setErrorMsg] = useState('');
  const [freshness, setFreshness] = useState(null);
  const [historicalWarning, setHistoricalWarning] = useState(null);
  const [modelFallbackReason, setModelFallbackReason] = useState(null);
  const [confidenceTier, setConfidenceTier] = useState(null);
  const [effectiveModel, setEffectiveModel] = useState(null);
  const [chartMode, setChartMode] = useState('fan_chart'); // 'fan_chart' | 'standard'
  const [qualityScorecard, setQualityScorecard] = useState(null);

  // 1. Initial Load: Fetch top products & existing runs
  useEffect(() => {
    loadInitialData();
  }, []);

  const loadInitialData = async () => {
    setLoading(true);
    try {
      // Fetch demand summary to discover top products
      const sumRes = await api.get('/api/demand/summary').catch(() => null);
      if (sumRes?.data?.top_products_by_qty?.length > 0) {
        const pIds = sumRes.data.top_products_by_qty.map((p) => p.product_id);
        setTopProducts(pIds);
        if (!pIds.includes(selectedProduct)) {
          setSelectedProduct(pIds[0]);
        }
      }

      // Fetch data quality scorecard & gate status
      const qRes = await api.get('/api/quality/scorecard').catch(() => null);
      if (qRes?.data) {
        setQualityScorecard(qRes.data);
      }

      // Fetch base forecast freshness & historical warning
      const fRes = await api.get('/api/forecast').catch(() => null);
      if (fRes?.data?.freshness) {
        setFreshness(fRes.data.freshness);
      }
      if (fRes?.data?.historical_warning) {
        setHistoricalWarning(fRes.data.historical_warning);
      }

      // Fetch existing forecast runs
      await loadRuns();
    } catch (err) {
      console.error('Failed to load initial forecast data', err);
    } finally {
      setLoading(false);
    }
  };

  const loadRuns = async () => {
    try {
      const res = await api.get('/api/forecast/runs?page=1&page_size=50');
      if (res?.data?.results) {
        setRuns(res.data.results);
      }
    } catch (err) {
      console.error('Failed to fetch runs', err);
    }
  };

  // 2. Load detail for selected product, horizon, and active model
  useEffect(() => {
    loadSelectedRunDetail();
  }, [selectedProduct, selectedHorizon, activeModelTab, runs]);

  const loadSelectedRunDetail = async () => {
    // Find matching completed run in memory
    const match = runs.find(
      (r) =>
        r.product_id === String(selectedProduct) &&
        r.horizon_days === Number(selectedHorizon) &&
        r.model_name === activeModelTab &&
        r.status === 'complete'
    );

    if (match) {
      setChartLoading(true);
      try {
        const { data } = await api.get(`/api/forecast/${match.id}`);
        setActiveRunDetail(data);
        if (data?.freshness) {
          setFreshness(data.freshness);
        }
        setModelFallbackReason(data?.model_fallback_reason || data?.freshness?.model_fallback_reason || null);
        setConfidenceTier(data?.confidence_tier || data?.freshness?.confidence_tier || null);
        setEffectiveModel(data?.model_name || null);
      } catch (err) {
        console.error('Failed to fetch run details', err);
      } finally {
        setChartLoading(false);
      }
    } else {
      // Try SKU level dynamic forecast
      try {
        const { data } = await api.get(`/api/forecast?product_id=${selectedProduct}&horizon_days=${selectedHorizon}&model_name=${activeModelTab}`);
        if (data?.freshness) {
          setFreshness(data.freshness);
        }
        if (data?.historical_warning) {
          setHistoricalWarning(data.historical_warning);
        }
        setModelFallbackReason(data?.model_fallback_reason || null);
        setConfidenceTier(data?.confidence_tier || null);
        setEffectiveModel(data?.model_name || null);
        if (data?.forecast) {
          setActiveRunDetail(data);
        }
      } catch (err) {
        // ignore
      }
    }
  };

  const handleRecomputeNow = async () => {
    setRunningForecast(true);
    setFeedbackMsg('Recomputing forecast synchronously...');
    setErrorMsg('');
    try {
      const res = await recomputeForecast(null, [selectedProduct]);
      if (res?.freshness) {
        setFreshness(res.freshness);
      }
      if (res?.historical_warning) {
        setHistoricalWarning(res.historical_warning);
      }
      setFeedbackMsg(`Forecast recomputed successfully for SKU ${selectedProduct}!`);
      await loadRuns();
      await loadSelectedRunDetail();
    } catch (err) {
      setErrorMsg(err.message || 'Recompute failed');
    } finally {
      setRunningForecast(false);
    }
  };

  // 3. Trigger new forecast run
  const handleTriggerForecast = async () => {
    setRunningForecast(true);
    setFeedbackMsg('');
    setErrorMsg('');
    try {
      const payload = {
        product_ids: [selectedProduct],
        models: selectedModels,
        horizon_days: selectedHorizon,
      };
      const { data } = await api.post('/api/forecast/run', payload);
      setFeedbackMsg(`Successfully generated ${data.successful_runs} forecast model run(s)!`);
      await loadRuns();
    } catch (err) {
      const detail = err.response?.data?.detail;
      setErrorMsg(typeof detail === 'string' ? detail : 'Failed to run forecast.');
    } finally {
      setRunningForecast(false);
    }
  };

  // 4. Transform points into chart series
  const chartData = useMemo(() => {
    if (!activeRunDetail?.points?.length) return [];
    return activeRunDetail.points.map((p) => {
      const dateLabel = typeof p.forecast_date === 'string' ? p.forecast_date.slice(5) : p.forecast_date;
      return {
        date: dateLabel,
        fullDate: p.forecast_date,
        Actual: p.actual != null ? Math.round(p.actual) : null,
        Forecast: Math.round(p.yhat),
        LowerCI: p.yhat_lower != null ? Math.round(p.yhat_lower) : null,
        UpperCI: p.yhat_upper != null ? Math.round(p.yhat_upper) : null,
        isFuture: p.is_future,
      };
    });
  }, [activeRunDetail]);

  // Find competing runs for the current product & horizon to render comparison leaderboard
  const comparisonRuns = useMemo(() => {
    return runs.filter(
      (r) =>
        r.product_id === String(selectedProduct) &&
        r.horizon_days === Number(selectedHorizon) &&
        r.status === 'complete' &&
        r.evaluation != null
    );
  }, [runs, selectedProduct, selectedHorizon]);

  // Find best model by WAPE (or MAE)
  const bestModel = useMemo(() => {
    if (!comparisonRuns.length) return null;
    const sorted = [...comparisonRuns].sort((a, b) => {
      const wapeA = a.evaluation?.wape ?? Infinity;
      const wapeB = b.evaluation?.wape ?? Infinity;
      return wapeA - wapeB;
    });
    return sorted[0];
  }, [comparisonRuns]);

  // Format helper
  const fmt = (n) =>
    n == null ? '—' : Number(n).toLocaleString('en-US', { maximumFractionDigits: 1 });

  return (
    <PageShell>
      {/* Header */}
      <PageHeader
        title="Demand Forecasting & Evaluation Studio"
        subtitle="Chronological multi-horizon predictions with Naive, Moving Average, and Facebook Prophet models."
        icon={TrendingUp}
        actions={
          <>
            {qualityScorecard && qualityScorecard.status !== 'empty_dataset' && (
              <Badge
                variant={qualityScorecard.quality_gate_passed ? 'success' : 'critical'}
                icon={qualityScorecard.quality_gate_passed ? CheckCircle2 : AlertCircle}
                size="lg"
              >
                Quality Gate: {qualityScorecard.quality_gate_passed ? 'PASSED' : 'FAILED'} ({qualityScorecard.composite_score}/100)
              </Badge>
            )}

            <button
              className="btn btn-primary"
              onClick={handleTriggerForecast}
              disabled={runningForecast}
              style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', padding: '0.75rem 1.4rem' }}
            >
              <RefreshCw size={16} className={runningForecast ? 'animate-spin' : ''} />
              {runningForecast ? 'Training Models...' : 'Run Forecast'}
            </button>
          </>
        }
      />

      {/* Alerts */}
      {feedbackMsg && (
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem', padding: '0.85rem 1.25rem', backgroundColor: 'rgba(16, 185, 129, 0.12)', border: '1px solid var(--accent-emerald)', borderRadius: '8px', color: 'var(--accent-emerald)', marginBottom: '1.5rem' }}>
          <CheckCircle2 size={18} />
          <span>{feedbackMsg}</span>
        </div>
      )}
      {errorMsg && (
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem', padding: '0.85rem 1.25rem', backgroundColor: 'rgba(244, 63, 94, 0.12)', border: '1px solid var(--accent-rose)', borderRadius: '8px', color: 'var(--accent-rose)', marginBottom: '1.5rem' }}>
          <AlertCircle size={18} />
          <span>{errorMsg}</span>
        </div>
      )}

      {/* Retrospective Warning Banner for Outdated Datasets */}
      {historicalWarning && historicalWarning.is_historical && (
        <div style={{
          display: 'flex',
          alignItems: 'flex-start',
          gap: '0.85rem',
          padding: '1rem 1.25rem',
          backgroundColor: 'rgba(245, 158, 11, 0.12)',
          border: '1px solid #f59e0b',
          borderRadius: '8px',
          color: '#fbbf24',
          marginBottom: '1.5rem',
          boxShadow: '0 1px 3px rgba(0,0,0,0.1)'
        }}>
          <AlertCircle size={22} style={{ flexShrink: 0, marginTop: '2px', color: '#f59e0b' }} />
          <div>
            <div style={{ fontWeight: 600, fontSize: '0.95rem', color: '#f59e0b', marginBottom: '0.2rem' }}>
              Historical Retrospective Mode
            </div>
            <div style={{ fontSize: '0.85rem', color: '#fef3c7', lineHeight: 1.5 }}>
              {historicalWarning.message || `Forecast horizon is anchored to historical data through ${historicalWarning.as_of} (${historicalWarning.days_behind} days ago). Predictions represent retrospective projections, not live real-time conditions.`}
            </div>
          </div>
        </div>
      )}

      {/* Controls Bar */}
      <div className="card" style={{ display: 'flex', flexWrap: 'wrap', gap: '1.5rem', alignItems: 'center', justifyContent: 'space-between' }}>
        {/* Product SKU Selector */}
        <div>
          <label style={{ display: 'block', fontSize: '0.8rem', textTransform: 'uppercase', letterSpacing: '0.05em', color: 'var(--text-secondary)', marginBottom: '0.4rem', fontWeight: 600 }}>
            Target Product SKU
          </label>
          <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
            {topProducts.slice(0, 5).map((pid) => (
              <button
                key={pid}
                onClick={() => setSelectedProduct(pid)}
                style={{
                  padding: '0.45rem 0.9rem',
                  borderRadius: '6px',
                  border: selectedProduct === pid ? '1px solid var(--accent-primary)' : '1px solid var(--border-strong)',
                  backgroundColor: selectedProduct === pid ? 'rgba(59, 130, 246, 0.2)' : 'var(--bg-surface-elevated)',
                  color: selectedProduct === pid ? '#93c5fd' : 'var(--text-secondary)',
                  fontWeight: selectedProduct === pid ? 600 : 500,
                  fontSize: '0.85rem',
                  cursor: 'pointer',
                  transition: 'all 0.15s ease',
                }}
              >
                SKU #{pid}
              </button>
            ))}
          </div>
        </div>

        {/* Horizon Selector */}
        <div>
          <label style={{ display: 'block', fontSize: '0.8rem', textTransform: 'uppercase', letterSpacing: '0.05em', color: 'var(--text-secondary)', marginBottom: '0.4rem', fontWeight: 600 }}>
            Forecast Horizon
          </label>
          <div style={{ display: 'flex', gap: '0.5rem' }}>
            {HORIZONS.map((h) => (
              <button
                key={h}
                onClick={() => setSelectedHorizon(h)}
                style={{
                  padding: '0.45rem 1rem',
                  borderRadius: '6px',
                  border: selectedHorizon === h ? '1px solid var(--accent-cyan)' : '1px solid var(--border-strong)',
                  backgroundColor: selectedHorizon === h ? 'rgba(6, 182, 212, 0.2)' : 'var(--bg-surface-elevated)',
                  color: selectedHorizon === h ? '#67e8f9' : 'var(--text-secondary)',
                  fontWeight: selectedHorizon === h ? 600 : 500,
                  fontSize: '0.85rem',
                  cursor: 'pointer',
                  transition: 'all 0.15s ease',
                }}
              >
                {h} Days
              </button>
            ))}
          </div>
        </div>

        {/* Model Selector for Training */}
        <div>
          <label style={{ display: 'block', fontSize: '0.8rem', textTransform: 'uppercase', letterSpacing: '0.05em', color: 'var(--text-secondary)', marginBottom: '0.4rem', fontWeight: 600 }}>
            Active Models
          </label>
          <div style={{ display: 'flex', gap: '0.75rem', alignItems: 'center' }}>
            {AVAILABLE_MODELS.map((m) => {
              const active = selectedModels.includes(m.id);
              return (
                <label
                  key={m.id}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: '0.35rem',
                    fontSize: '0.85rem',
                    color: active ? 'var(--text-primary)' : 'var(--text-muted)',
                    cursor: 'pointer',
                  }}
                >
                  <input
                    type="checkbox"
                    checked={active}
                    onChange={(e) => {
                      if (e.target.checked) {
                        setSelectedModels([...selectedModels, m.id]);
                      } else if (selectedModels.length > 1) {
                        setSelectedModels(selectedModels.filter((id) => id !== m.id));
                      }
                    }}
                    style={{ accentColor: 'var(--accent-primary)', cursor: 'pointer' }}
                  />
                  <span>{m.name}</span>
                </label>
              );
            })}
          </div>
        </div>
      </div>

      {/* Model Leaderboard & Evaluation Overview */}
      <div style={{ marginBottom: '1.5rem' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.75rem' }}>
          <h2 style={{ fontSize: '1.1rem', fontWeight: 600, color: 'var(--text-primary)', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <Award size={20} color="var(--accent-amber)" />
            Model Accuracy Leaderboard (Holdout Evaluation Split)
          </h2>
          {bestModel && (
            <Badge variant="success" pill>
              Top Performer: {bestModel.model_name.toUpperCase()} (WAPE {bestModel.evaluation?.wape}%)
            </Badge>
          )}
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: '1rem' }}>
          {AVAILABLE_MODELS.map((m) => {
            const run = comparisonRuns.find((r) => r.model_name === m.id);
            const isWinner = bestModel?.model_name === m.id;
            const isSelected = activeModelTab === m.id;
            const metrics = run?.evaluation
              ? [
                  { label: 'WAPE', value: run.evaluation.wape != null ? `${run.evaluation.wape}%` : '—', color: m.color, isKey: true },
                  { label: 'MAE', value: fmt(run.evaluation.mae) },
                  { label: 'RMSE', value: fmt(run.evaluation.rmse) },
                ]
              : [];

            return (
              <MetricLeaderboardCard
                key={m.id}
                title={m.name}
                tag={m.tag}
                color={m.color}
                isWinner={isWinner}
                isSelected={isSelected}
                metrics={metrics}
                emptyMessage='No run found for this configuration. Click "Run Forecast" to train.'
                onClick={() => setActiveModelTab(m.id)}
              />
            );
          })}
        </div>
      </div>

      {/* Main Forecast Chart Card */}
      <div className="card" style={{ padding: '1.75rem' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.5rem', flexWrap: 'wrap', gap: '1rem' }}>
          <div>
            <h3 style={{ fontSize: '1.15rem', fontWeight: 700, color: 'var(--text-primary)', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              <Activity size={20} color={AVAILABLE_MODELS.find((m) => m.id === activeModelTab)?.color || '#3b82f6'} />
              {chartMode === 'fan_chart' ? 'Probabilistic Fan Chart (Quantile Forecasts)' : 'Time Series Prediction Curve & 80% Confidence Interval'}
            </h3>
            <p style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', marginTop: '0.2rem', display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
              <span>Showing {effectiveModel ? effectiveModel.toUpperCase() : activeModelTab.toUpperCase()} model | Product SKU #{selectedProduct} | {selectedHorizon}-Day Horizon</span>
              {confidenceTier && (
                <Badge
                  variant={confidenceTier === 'HIGH' ? 'success' : confidenceTier === 'MEDIUM' ? 'warning' : 'critical'}
                  size="sm"
                >
                  Confidence: {confidenceTier}
                </Badge>
              )}
            </p>
          </div>

          <div style={{ display: 'flex', gap: '0.75rem', alignItems: 'center' }}>
            {/* Fan Chart Toggle */}
            <div style={{ display: 'flex', backgroundColor: 'var(--bg-surface-elevated)', padding: '0.25rem', borderRadius: '8px', border: '1px solid var(--border-subtle)' }}>
              <button
                onClick={() => setChartMode('fan_chart')}
                style={{
                  padding: '0.35rem 0.75rem',
                  borderRadius: '6px',
                  border: 'none',
                  backgroundColor: chartMode === 'fan_chart' ? 'var(--accent-primary)' : 'transparent',
                  color: chartMode === 'fan_chart' ? '#fff' : 'var(--text-secondary)',
                  fontWeight: 600,
                  fontSize: '0.78rem',
                  cursor: 'pointer',
                }}
              >
                Fan Chart (Quantiles)
              </button>
              <button
                onClick={() => setChartMode('standard')}
                style={{
                  padding: '0.35rem 0.75rem',
                  borderRadius: '6px',
                  border: 'none',
                  backgroundColor: chartMode === 'standard' ? 'var(--accent-primary)' : 'transparent',
                  color: chartMode === 'standard' ? '#fff' : 'var(--text-secondary)',
                  fontWeight: 600,
                  fontSize: '0.78rem',
                  cursor: 'pointer',
                }}
              >
                Standard (80% CI)
              </button>
            </div>

            {/* Model toggle pills inside chart header */}
            <div style={{ display: 'flex', gap: '0.5rem', backgroundColor: 'var(--bg-surface-elevated)', padding: '0.3rem', borderRadius: '8px' }}>
              {AVAILABLE_MODELS.map((m) => (
                <button
                  key={m.id}
                  onClick={() => setActiveModelTab(m.id)}
                  style={{
                    padding: '0.4rem 0.85rem',
                    borderRadius: '6px',
                    border: 'none',
                    backgroundColor: activeModelTab === m.id ? m.color : 'transparent',
                    color: activeModelTab === m.id ? '#fff' : 'var(--text-secondary)',
                    fontWeight: activeModelTab === m.id ? 600 : 500,
                    fontSize: '0.8rem',
                    cursor: 'pointer',
                    transition: 'all 0.15s ease',
                  }}
                >
                  {m.name}
                </button>
              ))}
            </div>
          </div>
        </div>

        {/* Chart Viewport */}
        {chartLoading ? (
          <div style={{ height: '360px', display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--text-muted)' }}>
            <RefreshCw size={24} className="animate-spin" style={{ marginRight: '0.5rem' }} />
            Loading prediction points...
          </div>
        ) : chartMode === 'fan_chart' && activeRunDetail?.fan_chart?.length > 0 ? (
          <div style={{ width: '100%', height: 380 }}>
            <ResponsiveContainer>
              <ComposedChart data={activeRunDetail.fan_chart} margin={{ top: 10, right: 20, left: 0, bottom: 0 }}>
                <defs>
                  <linearGradient id="fan90Gradient" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#3b82f6" stopOpacity={0.20} />
                    <stop offset="95%" stopColor="#3b82f6" stopOpacity={0.05} />
                  </linearGradient>
                  <linearGradient id="fan50Gradient" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#6366f1" stopOpacity={0.35} />
                    <stop offset="95%" stopColor="#6366f1" stopOpacity={0.15} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--border-subtle)" />
                <XAxis
                  dataKey="date"
                  stroke="var(--text-muted)"
                  fontSize={12}
                  tickLine={false}
                />
                <YAxis
                  stroke="var(--text-muted)"
                  fontSize={12}
                  tickLine={false}
                  tickFormatter={(v) => (v >= 1000 ? `${(v / 1000).toFixed(1)}k` : v)}
                />
                <Tooltip
                  content={({ active, payload, label }) => {
                    if (active && payload && payload.length) {
                      const d = payload[0]?.payload;
                      return (
                        <div
                          style={{
                            backgroundColor: 'var(--bg-surface)',
                            border: '1px solid var(--border-strong)',
                            borderRadius: '8px',
                            padding: '0.85rem',
                            fontSize: '0.85rem',
                            boxShadow: '0 4px 12px rgba(0,0,0,0.5)',
                          }}
                        >
                          <div style={{ fontWeight: 700, color: 'var(--text-primary)', marginBottom: '0.35rem' }}>
                            {d?.date} (Quantile Fan Projection)
                          </div>
                          <div style={{ color: '#60a5fa', fontWeight: 600 }}>
                            Median (q50): {d?.q50} units | Mean: {d?.mean}
                          </div>
                          <div style={{ color: 'var(--text-secondary)', fontSize: '0.78rem', marginTop: '0.25rem' }}>
                            50% Interquartile [q25–q75]: [{d?.q25} – {d?.q75}]
                          </div>
                          <div style={{ color: 'var(--text-secondary)', fontSize: '0.78rem' }}>
                            90% Interval [q05–q95]: [{d?.q05} – {d?.q95}]
                          </div>
                          <div style={{ color: '#f59e0b', fontSize: '0.75rem', marginTop: '0.25rem' }}>
                            99th Percentile Spike (q99): {d?.q99} units
                          </div>
                        </div>
                      );
                    }
                    return null;
                  }}
                />
                <Legend verticalAlign="top" height={36} />

                {/* Outer 90% Band (q95) */}
                <Area
                  type="monotone"
                  dataKey="q95"
                  name="90% Upper Band (q95)"
                  stroke="#3b82f6"
                  strokeDasharray="2 2"
                  fill="url(#fan90Gradient)"
                  isAnimationActive={false}
                />
                {/* Inner 50% Band (q75) */}
                <Area
                  type="monotone"
                  dataKey="q75"
                  name="50% Upper Band (q75)"
                  stroke="#6366f1"
                  fill="url(#fan50Gradient)"
                  isAnimationActive={false}
                />
                {/* Median Line */}
                <Line
                  type="monotone"
                  dataKey="q50"
                  name="Median Demand (q50)"
                  stroke="#38bdf8"
                  strokeWidth={2.5}
                  dot={{ r: 3, fill: '#38bdf8' }}
                />
                {/* Lower Bound (q05) */}
                <Line
                  type="monotone"
                  dataKey="q05"
                  name="90% Lower Band (q05)"
                  stroke="#64748b"
                  strokeDasharray="3 3"
                  strokeWidth={1.5}
                  dot={false}
                />
              </ComposedChart>
            </ResponsiveContainer>
          </div>
        ) : chartData.length > 0 ? (
          <div style={{ width: '100%', height: 380 }}>
            <ResponsiveContainer>
              <ComposedChart data={chartData} margin={{ top: 10, right: 20, left: 0, bottom: 0 }}>
                <defs>
                  <linearGradient id="ciGradient" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="var(--accent-primary)" stopOpacity={0.25} />
                    <stop offset="95%" stopColor="var(--accent-primary)" stopOpacity={0.03} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--border-subtle)" />
                <XAxis
                  dataKey="date"
                  stroke="var(--text-muted)"
                  fontSize={12}
                  tickLine={false}
                />
                <YAxis
                  stroke="var(--text-muted)"
                  fontSize={12}
                  tickLine={false}
                  tickFormatter={(v) => (v >= 1000 ? `${(v / 1000).toFixed(1)}k` : v)}
                />
                <Tooltip
                  content={({ active, payload, label }) => {
                    if (active && payload && payload.length) {
                      const d = payload[0]?.payload;
                      return (
                        <div
                          style={{
                            backgroundColor: 'var(--bg-surface)',
                            border: '1px solid var(--border-strong)',
                            borderRadius: '8px',
                            padding: '0.85rem',
                            fontSize: '0.85rem',
                            boxShadow: '0 4px 12px rgba(0,0,0,0.5)',
                          }}
                        >
                          <div style={{ fontWeight: 700, color: 'var(--text-primary)', marginBottom: '0.35rem' }}>
                            {d?.fullDate} {d?.isFuture ? '(Future Projection)' : '(Holdout Test)'}
                          </div>
                          {d?.Actual != null && (
                            <div style={{ color: '#fff', display: 'flex', justifyContent: 'space-between', gap: '1rem' }}>
                              <span>Actual Demand:</span>
                              <strong>{d.Actual.toLocaleString()} units</strong>
                            </div>
                          )}
                          <div style={{ color: AVAILABLE_MODELS.find((m) => m.id === activeModelTab)?.color || '#3b82f6', display: 'flex', justifyContent: 'space-between', gap: '1rem' }}>
                            <span>Forecast (yhat):</span>
                            <strong>{d?.Forecast?.toLocaleString()} units</strong>
                          </div>
                          {d?.LowerCI != null && (
                            <div style={{ color: 'var(--text-secondary)', fontSize: '0.78rem', marginTop: '0.2rem' }}>
                              80% CI: [{d.LowerCI.toLocaleString()} – {d.UpperCI.toLocaleString()}]
                            </div>
                          )}
                        </div>
                      );
                    }
                    return null;
                  }}
                />
                <Legend verticalAlign="top" height={36} />

                {/* Upper CI boundary / area */}
                <Area
                  type="monotone"
                  dataKey="UpperCI"
                  name="80% Upper CI"
                  stroke="none"
                  fill="url(#ciGradient)"
                  isAnimationActive={false}
                />
                {/* Predicted line */}
                <Line
                  type="monotone"
                  dataKey="Forecast"
                  name={`Predicted (${activeModelTab.toUpperCase()})`}
                  stroke={AVAILABLE_MODELS.find((m) => m.id === activeModelTab)?.color || '#3b82f6'}
                  strokeWidth={2.5}
                  dot={{ r: 3, fill: AVAILABLE_MODELS.find((m) => m.id === activeModelTab)?.color || '#3b82f6' }}
                  activeDot={{ r: 6 }}
                />
                {/* Actual historical line */}
                <Line
                  type="monotone"
                  dataKey="Actual"
                  name="Historical Actual"
                  stroke="#f9fafb"
                  strokeWidth={2}
                  strokeDasharray="4 4"
                  dot={{ r: 3, fill: '#f9fafb' }}
                />
              </ComposedChart>
            </ResponsiveContainer>
          </div>
        ) : (
          <div style={{ padding: '3rem', textAlign: 'center', color: 'var(--text-muted)' }}>
            No forecast points available for this product and model combination. Click <strong>"Run Forecast"</strong> above to generate forecasts.
          </div>
        )}

        {/* Probabilistic Safety Stock & Quantile Calibration Scorecard */}
        {activeRunDetail?.quantile_safety_stock && (
          <div style={{ marginTop: '1.5rem', paddingTop: '1.25rem', borderTop: '1px solid var(--border-subtle)', display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: '1rem' }}>
            <div style={{ backgroundColor: 'var(--bg-surface-elevated)', padding: '1rem', borderRadius: '10px', border: '1px solid var(--border-subtle)' }}>
              <div style={{ fontSize: '0.78rem', color: 'var(--text-secondary)', fontWeight: 600, textTransform: 'uppercase' }}>
                Direct Quantile Safety Stock (95% SL)
              </div>
              <div style={{ display: 'flex', alignItems: 'baseline', gap: '0.5rem', marginTop: '0.35rem' }}>
                <span style={{ fontSize: '1.4rem', fontWeight: 700, color: 'var(--accent-primary)' }}>
                  {activeRunDetail.quantile_safety_stock.ss_quantile} units
                </span>
                <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                  vs King's: {activeRunDetail.quantile_safety_stock.ss_kings} u | Classical: {activeRunDetail.quantile_safety_stock.ss_classical} u
                </span>
              </div>
              <div style={{ fontSize: '0.75rem', color: activeRunDetail.quantile_safety_stock.delta_vs_kings < 0 ? 'var(--accent-emerald)' : 'var(--accent-amber)', marginTop: '0.3rem' }}>
                Δ vs King's: {activeRunDetail.quantile_safety_stock.delta_vs_kings >= 0 ? '+' : ''}{activeRunDetail.quantile_safety_stock.delta_vs_kings} units (Non-parametric empirical buffer)
              </div>
            </div>

            {activeRunDetail?.quantiles_evaluation && (
              <div style={{ backgroundColor: 'var(--bg-surface-elevated)', padding: '1rem', borderRadius: '10px', border: '1px solid var(--border-subtle)' }}>
                <div style={{ fontSize: '0.78rem', color: 'var(--text-secondary)', fontWeight: 600, textTransform: 'uppercase' }}>
                  Quantile Calibration & Pinball Loss
                </div>
                <div style={{ display: 'flex', alignItems: 'baseline', gap: '0.5rem', marginTop: '0.35rem' }}>
                  <span style={{ fontSize: '1.4rem', fontWeight: 700, color: 'var(--accent-emerald)' }}>
                    {activeRunDetail.quantiles_evaluation.calibration_coverage_90}%
                  </span>
                  <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                    Coverage (Target: 90.0% | Error: {activeRunDetail.quantiles_evaluation.calibration_error}%)
                  </span>
                </div>
                <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary)', marginTop: '0.3rem' }}>
                  Mean Pinball Loss: {activeRunDetail.quantiles_evaluation.mean_pinball_loss} (Asymmetric quantile penalty)
                </div>
              </div>
            )}
          </div>
        )}


        {/* Model Sufficiency Fallback Alert Banner */}
        {modelFallbackReason && (
          <div style={{
            marginTop: '1.25rem',
            padding: '0.75rem 1rem',
            borderRadius: '8px',
            backgroundColor: 'rgba(245, 158, 11, 0.12)',
            border: '1px solid rgba(245, 158, 11, 0.4)',
            color: '#fbbf24',
            fontSize: '0.84rem',
            display: 'flex',
            alignItems: 'center',
            gap: '0.65rem'
          }}>
            <AlertCircle size={18} style={{ flexShrink: 0, color: '#f59e0b' }} />
            <div>
              <strong style={{ color: '#f59e0b' }}>Model History Guard Triggered ({confidenceTier || 'LOW'} Confidence): </strong>
              <span>{modelFallbackReason}</span>
              <div style={{ fontSize: '0.76rem', color: '#fef3c7', marginTop: '0.2rem' }}>
                Prediction intervals have been widened to ±30% to honestly reflect estimation uncertainty on limited history.
              </div>
            </div>
          </div>
        )}

        {/* Freshness & Staleness Metadata Caption */}
        <div style={{ marginTop: '1.25rem', paddingTop: '0.85rem', borderTop: '1px solid var(--border-subtle)', display: 'flex', flexWrap: 'wrap', alignItems: 'center', justifyContent: 'space-between', gap: '0.75rem', fontSize: '0.82rem', color: 'var(--text-muted)' }}>
          <div>
            Computed {freshness?.computed_at ? new Date(freshness.computed_at).toISOString().replace('T', ' ').slice(0, 16) : new Date().toISOString().slice(0, 16)} from data through {freshness?.data_through || 'latest'} (model: {freshness?.model_name || activeModelTab})
            {' · '}
            <button
              onClick={handleRecomputeNow}
              disabled={runningForecast}
              style={{ background: 'none', border: 'none', color: 'var(--accent-primary)', cursor: 'pointer', textDecoration: 'underline', padding: 0, fontSize: '0.82rem' }}
            >
              [Recompute now]
            </button>
          </div>

          {freshness?.is_stale && (
            <div style={{ display: 'inline-flex', alignItems: 'center', gap: '0.5rem', padding: '0.3rem 0.75rem', borderRadius: '6px', backgroundColor: 'rgba(245, 158, 11, 0.15)', border: '1px solid var(--accent-amber)', color: 'var(--accent-amber)', fontWeight: 500, fontSize: '0.78rem' }}>
              <span>⚠ Data has updated since this forecast was generated — recompute recommended</span>
              <button
                onClick={handleRecomputeNow}
                disabled={runningForecast}
                style={{ backgroundColor: 'var(--accent-amber)', color: '#000', border: 'none', borderRadius: '4px', padding: '0.2rem 0.5rem', fontSize: '0.72rem', fontWeight: 700, cursor: 'pointer' }}
              >
                Recompute
              </button>
            </div>
          )}
        </div>
      </div>

      {/* Runs History Table */}
      <Card
        title="Recent Forecast Database Runs"
        icon={History}
        iconColor="var(--accent-purple)"
        actions={
          <span style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
            {runs.length} runs recorded in database
          </span>
        }
      >
        <DataTable
          columns={[
            { key: 'id', title: 'Run ID', render: (val) => <span style={{ fontWeight: 600 }}>#{val}</span> },
            { key: 'product_id', title: 'Product SKU', render: (val) => `SKU #${val}` },
            {
              key: 'model_name',
              title: 'Model',
              render: (val) => {
                const variant = val === 'prophet' ? 'info' : val === 'moving_avg' ? 'warning' : 'cyan';
                return <Badge variant={variant}>{val.toUpperCase()}</Badge>;
              },
            },
            { key: 'horizon_days', title: 'Horizon', render: (val) => <span style={{ color: 'var(--text-secondary)' }}>{val} Days</span> },
            {
              key: 'status',
              title: 'Status',
              render: (val) => (
                <Badge variant={val === 'complete' ? 'success' : 'critical'} icon={val === 'complete' ? CheckCircle2 : AlertCircle}>
                  {val}
                </Badge>
              ),
            },
            {
              key: 'wape',
              title: 'WAPE',
              mono: true,
              render: (_, row) => (
                <span style={{ fontWeight: 600, color: 'var(--text-primary)' }}>
                  {row.evaluation?.wape != null ? `${row.evaluation.wape}%` : '—'}
                </span>
              ),
            },
            {
              key: 'mae',
              title: 'MAE',
              render: (_, row) => <span style={{ color: 'var(--text-secondary)' }}>{fmt(row.evaluation?.mae)}</span>,
            },
            {
              key: 'rmse',
              title: 'RMSE',
              render: (_, row) => <span style={{ color: 'var(--text-secondary)' }}>{fmt(row.evaluation?.rmse)}</span>,
            },
            {
              key: 'created_at',
              title: 'Created At',
              render: (val) => (
                <span style={{ color: 'var(--text-muted)', fontSize: '0.8rem' }}>
                  {new Date(val).toLocaleString()}
                </span>
              ),
            },
          ]}
          data={runs.slice(0, 10)}
          selectedRowId={activeRunDetail?.id}
          onRowClick={(r) => {
            setSelectedProduct(r.product_id);
            setSelectedHorizon(r.horizon_days);
            setActiveModelTab(r.model_name);
          }}
          emptyMessage="No forecast runs recorded yet."
        />
      </Card>
    </PageShell>
  );
}
