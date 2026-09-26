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
  Download,
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

  const totalModels = perfData?.total_models_evaluated ?? perfData?.total_champions ?? 0;
  const isZeroState = totalModels === 0;

  const championsMix = (perfData?.champion_model_mix || perfData?.model_mix || []).map(m => ({
    model: m.model_name || m.model,
    count: m.count,
    avg_wape: m.avg_wape || m.percentage
  }));

  const worstSkus = perfData?.worst_performing_skus || perfData?.worst_skus || [];
  const driftAlerts = perfData?.drift_alerts || [];

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

      {/* Zero State Alert Banner */}
      {isZeroState && (
        <div style={{
          padding: '20px 24px',
          backgroundColor: 'var(--surface-card, #ffffff)',
          border: '1px solid var(--border-color, #e2e8f0)',
          borderRadius: '12px',
          marginBottom: '20px',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          gap: '16px',
          boxShadow: '0 1px 3px rgba(0,0,0,0.05)'
        }}>
          <div>
            <div style={{ fontWeight: 600, fontSize: '15px', color: 'var(--text-primary)' }}>
              No Forecasting Models Evaluated Yet
            </div>
            <div style={{ fontSize: '13px', color: 'var(--text-muted)', marginTop: '4px' }}>
              Upload a retail sales CSV file to train and evaluate candidate demand forecast models across your SKUs.
            </div>
          </div>
          <button onClick={() => navigate('/upload')} className="diq-btn diq-btn-primary" style={{ whiteSpace: 'nowrap' }}>
            <Download size={15} /> Upload Sales CSV
          </button>
        </div>
      )}

      <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>

        {/* ── KPIs ── */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(170px, 1fr))', gap: '12px' }}>
          <StatCard
            label="Products with Best Model"
            value={totalModels}
            subtext="Across candidate model tournament"
            icon={Award}
          />
          <StatCard
            label="Average Prediction Error"
            value={isZeroState ? "0.0%" : `${perfData?.average_wape || (perfData?.wape_distribution?.mean) || 0.0}%`}
            tooltip="WAPE: Lower is better. Under 15% is good."
            subtext={isZeroState ? "Awaiting model evaluation" : "Lower is better"}
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
          {championsMix.length === 0 ? (
            <div style={{ height: 160, display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--text-muted)', fontSize: '14px' }}>
              No champion models evaluated yet. Upload sales data to train models.
            </div>
          ) : (
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
          )}
        </Card>

        {/* ── Drift + Worst SKUs ── */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(340px, 1fr))', gap: '16px' }}>

          {/* Demand Pattern Changes */}
          <Card title="Demand Pattern Changes" icon={Activity} subtitle="Products where recent demand has shifted significantly from historical patterns.">
            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
              {driftAlerts.length === 0 ? (
                <div style={{ fontSize: '13px', color: 'var(--text-muted)', padding: '12px 0' }}>
                  No demand pattern changes or drift detected.
                </div>
              ) : (
                driftAlerts.map((d) => (
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
                ))
              )}
            </div>
          </Card>

          {/* Worst performing */}
          <Card title="Least Accurate Products" icon={AlertTriangle} subtitle="These products have the highest forecast error. Consider retraining or manual review.">
            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
              {worstSkus.length === 0 ? (
                <div style={{ fontSize: '13px', color: 'var(--text-muted)', padding: '12px 0' }}>
                  No model forecast errors recorded.
                </div>
              ) : (
                worstSkus.map((s) => (
                  <div key={s.product_id} style={{
                    padding: '12px 14px', borderRadius: 'var(--border-radius-md)',
                    backgroundColor: '#ffffff', border: '1px solid var(--border-subtle)',
                    display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                  }}>
                    <div>
                      <div style={{ fontWeight: 600, fontSize: '13px', fontFamily: 'var(--font-mono)' }}>#{s.product_id}</div>
                      <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>Model: {s.champion_model || s.model_name || 'Baseline'}</div>
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
                ))
              )}
            </div>
          </Card>
        </div>
      </div>
    </PageShell>
  );
}
