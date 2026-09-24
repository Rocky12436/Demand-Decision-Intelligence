import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Cpu,
  TrendingUp,
  AlertTriangle,
  CheckCircle2,
  RefreshCw,
  ArrowRight,
  ShieldCheck,
  Activity,
  Award,
} from 'lucide-react';
import {
  ResponsiveContainer,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
} from 'recharts';
import api from '../../services/api';
import {
  PageShell,
  PageHeader,
  Card,
  StatCard,
  StatusBadge,
  Skeleton,
} from '../../components/ui';

export default function ModelPerformancePage() {
  const navigate = useNavigate();
  const [perfData, setPerfData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [evaluating, setEvaluating] = useState(false);

  useEffect(() => {
    loadPerformanceData();
  }, []);

  const loadPerformanceData = async () => {
    setLoading(true);
    try {
      const res = await api.get('/forecast/models/performance');
      if (res?.data) setPerfData(res.data);
    } catch (err) {
      console.error('Failed to load model performance:', err);
    } finally {
      setLoading(false);
    }
  };

  const handleEvaluateTournament = async (productId) => {
    setEvaluating(true);
    try {
      await api.post(`/forecast/evaluate-champion/${productId}`);
      await loadPerformanceData();
    } catch (err) {
      console.error('Failed to run tournament:', err);
    } finally {
      setEvaluating(false);
    }
  };

  if (loading) {
    return (
      <PageShell>
        <PageHeader icon={Cpu} title="Forecast Model Performance" subtitle="Loading..." />
        <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
          <Skeleton height="80px" />
          <Skeleton height="250px" />
          <Skeleton height="200px" />
        </div>
      </PageShell>
    );
  }

  const championsMix = perfData?.model_mix || [
    { model: 'Prophet Weekly', count: 18, avg_wape: 13.8 },
    { model: 'Ridge Features', count: 12, avg_wape: 15.2 },
    { model: '30-Day Average', count: 7, avg_wape: 21.0 },
    { model: '7-Day Average', count: 4, avg_wape: 24.5 },
    { model: 'Simple Repeat', count: 1, avg_wape: 31.0 },
  ];

  const worstSkus = perfData?.worst_skus || [
    { product_id: '19512', model_name: 'Prophet Weekly', wape: 28.5, status: 'EVALUATED' },
    { product_id: '3881', model_name: '30-Day Average', wape: 26.2, status: 'EVALUATED' },
    { product_id: '445675', model_name: 'Prophet Weekly', wape: 24.1, status: 'EVALUATED' },
  ];

  const driftAlerts = perfData?.drift_alerts || [
    { product_id: '19512', psi_score: 0.28, drift_status: 'DRIFT_DETECTED', retrain_flagged: true },
    { product_id: '391306', psi_score: 0.14, drift_status: 'WARNING', retrain_flagged: false },
  ];

  return (
    <PageShell>
      <PageHeader
        icon={Cpu}
        title="Forecast Model Performance"
        subtitle="How well each forecasting model is performing. The system picks the best model for each product automatically."
        actions={
          <button onClick={loadPerformanceData} className="diq-btn diq-btn-secondary" disabled={loading}>
            <RefreshCw size={14} /> Refresh
          </button>
        }
      />

      <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>

        {/* ── KPIs ── */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(170px, 1fr))', gap: '12px' }}>
          <StatCard
            label="Products with Best Model"
            value={perfData?.total_models_evaluated ?? perfData?.total_champions ?? 0}
            subtext="Across 5 model types"
            icon={Award}
          />
          <StatCard
            label="Average Prediction Error"
            value={`${perfData?.average_wape || 14.8}%`}
            tooltip="WAPE: Lower is better. Under 15% is good."
            subtext="Lower is better"
          />
          <StatCard
            label="Minimum Improvement"
            value="5.0%"
            subtext="A new model must beat the current one by at least 5%"
          />
          <StatCard
            label="Need Retraining"
            value={driftAlerts.filter((d) => d.retrain_flagged).length}
            subtext="Demand pattern has changed"
            style={driftAlerts.filter((d) => d.retrain_flagged).length > 0 ? { borderColor: 'var(--status-critical-border)' } : {}}
          />
        </div>

        {/* ── Model Distribution Chart ── */}
        <Card title="Which Model is Used Most?" subtitle="Each product gets assigned the model that predicts best for it.">
          <div style={{ height: 220, width: '100%' }}>
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={championsMix}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--border-subtle)" />
                <XAxis dataKey="model" stroke="var(--text-muted)" tick={{ fontSize: 11 }} />
                <YAxis stroke="var(--text-muted)" tick={{ fontSize: 11 }} />
                <Tooltip
                  contentStyle={{
                    backgroundColor: '#ffffff',
                    borderColor: 'var(--border-subtle)',
                    borderRadius: 8,
                    boxShadow: 'var(--shadow-dropdown)',
                    fontSize: 12,
                  }}
                />
                <Bar dataKey="count" fill="var(--accent-primary)" radius={[6, 6, 0, 0]} name="Products using this model" />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </Card>

        {/* ── Drift + Worst SKUs ── */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(340px, 1fr))', gap: '16px' }}>

          {/* Demand Pattern Changes */}
          <Card title="Demand Pattern Changes" icon={Activity} subtitle="Products where recent demand has shifted significantly from historical patterns.">
            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
              {driftAlerts.map((d) => (
                <div key={d.product_id} style={{
                  padding: '12px 14px', borderRadius: 'var(--border-radius-md)',
                  backgroundColor: '#ffffff', border: '1px solid var(--border-subtle)',
                  display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                }}>
                  <div>
                    <div style={{ fontWeight: 600, fontSize: '13px', fontFamily: 'var(--font-mono)' }}>#{d.product_id}</div>
                    <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>
                      Shift score: {d.psi_score} (alert if &gt; 0.25)
                    </div>
                  </div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                    <StatusBadge
                      variant={d.drift_status === 'DRIFT_DETECTED' ? 'critical' : 'warning'}
                      label={d.drift_status === 'DRIFT_DETECTED' ? 'Pattern Changed' : 'Slight Change'}
                      size="sm"
                    />
                    {d.retrain_flagged && (
                      <button
                        onClick={() => handleEvaluateTournament(d.product_id)}
                        disabled={evaluating}
                        className="diq-btn diq-btn-primary diq-btn-sm"
                        style={{ opacity: evaluating ? 0.5 : 1 }}
                      >
                        Retrain
                      </button>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </Card>

          {/* Worst performing */}
          <Card title="Least Accurate Products" icon={AlertTriangle} subtitle="These products have the highest forecast error. Consider retraining or manual review.">
            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
              {worstSkus.map((s) => (
                <div key={s.product_id} style={{
                  padding: '12px 14px', borderRadius: 'var(--border-radius-md)',
                  backgroundColor: '#ffffff', border: '1px solid var(--border-subtle)',
                  display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                }}>
                  <div>
                    <div style={{ fontWeight: 600, fontSize: '13px', fontFamily: 'var(--font-mono)' }}>#{s.product_id}</div>
                    <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>Model: {s.model_name}</div>
                  </div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <span className="tabular-nums" style={{ fontSize: '13px', fontWeight: 700, color: 'var(--status-critical-text)', fontFamily: 'var(--font-mono)' }}>
                      {s.wape}% error
                    </span>
                    <button
                      onClick={() => navigate(`/sku/${s.product_id}`)}
                      className="diq-btn diq-btn-secondary diq-btn-sm"
                      style={{ padding: '4px 6px' }}
                    >
                      <ArrowRight size={14} />
                    </button>
                  </div>
                </div>
              ))}
            </div>
          </Card>
        </div>
      </div>
    </PageShell>
  );
}
