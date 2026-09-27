import React, { useEffect, useState, useMemo } from 'react';
import {
  TrendingUp,
  TrendingDown,
  AlertTriangle,
  Search,
  RefreshCw,
  Activity,
  BarChart2,
  Download,
} from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import {
  ResponsiveContainer,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
  Cell,
} from 'recharts';
import api from '../../services/api';
import {
  PageShell,
  PageHeader,
  Card,
  StatCard,
  StatusBadge,
  SegmentedControl,
  EmptyState,
} from '../../components/ui';

export default function TrendsPage() {
  const navigate = useNavigate();
  const [alerts, setAlerts] = useState([]);
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(true);

  // Filters
  const [severityFilter, setSeverityFilter] = useState('ALL');
  const [typeFilter, setTypeFilter] = useState('ALL');
  const [selectedCity, setSelectedCity] = useState('ALL');
  const [searchSKU, setSearchSKU] = useState('');

  useEffect(() => {
    loadData();
  }, [severityFilter, typeFilter, selectedCity]);

  const loadData = async () => {
    setLoading(true);
    try {
      let url = `/analytics/anomalies?limit=250&severity=${severityFilter}`;
      if (typeFilter !== 'ALL') {
        url += `&anomaly_type=${encodeURIComponent(typeFilter)}`;
      }
      if (selectedCity !== 'ALL') {
        url += `&city_name=${encodeURIComponent(selectedCity)}`;
      }

      const [alertsRes, sumRes] = await Promise.all([
        api.get(url).catch(() => null),
        api.get('/analytics/summary').catch(() => null),
      ]);

      if (alertsRes?.data?.alerts) {
        setAlerts(alertsRes.data.alerts);
      }
      if (sumRes?.data) {
        setSummary(sumRes.data);
      }
    } catch (err) {
      console.error('Failed to load anomaly detection data', err);
    } finally {
      setLoading(false);
    }
  };

  // Filter by SKU search client side
  const filteredAlerts = useMemo(() => {
    if (!searchSKU.trim()) return alerts;
    return alerts.filter((a) => String(a.product_id).includes(searchSKU.trim()));
  }, [alerts, searchSKU]);

  // Chart data
  const chartData = useMemo(() => {
    if (!summary) return [];
    const spike = summary.anomaly_type_breakdown?.SPIKE_DEMAND ?? 0;
    const drop = summary.anomaly_type_breakdown?.DROP_STOCKOUT ?? 0;
    const crit = summary.severity_breakdown?.CRITICAL ?? 0;
    const med = summary.severity_breakdown?.MEDIUM ?? 0;
    if (spike === 0 && drop === 0 && crit === 0 && med === 0) return [];
    return [
      { name: 'Demand Spikes', count: spike, color: 'var(--status-warning-icon)' },
      { name: 'Sudden Drops', count: drop, color: 'var(--status-critical-icon)' },
      { name: 'Critical', count: crit, color: '#dc2626' },
      { name: 'Medium', count: med, color: 'var(--accent-primary)' },
    ];
  }, [summary]);

  const totalAnomalies = summary?.total_anomalies ?? alerts.length ?? 0;
  const spikeCount = summary?.anomaly_type_breakdown?.SPIKE_DEMAND ?? 0;
  const dropCount = summary?.anomaly_type_breakdown?.DROP_STOCKOUT ?? 0;
  const criticalCount = summary?.severity_breakdown?.CRITICAL ?? 0;

  return (
    <PageShell maxWidth="1400px">
      <PageHeader
        icon={Activity}
        title="Unusual Activity & Alerts"
        subtitle="Automatic detection of unexpected demand spikes, drops, and potential stockout situations."
        actions={
          <button onClick={loadData} disabled={loading} className="diq-btn diq-btn-secondary">
            <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
            {loading ? 'Checking...' : 'Refresh'}
          </button>
        }
      />

      <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>

        {/* ── Zero State Alert Banner ── */}
        {totalAnomalies === 0 && alerts.length === 0 && !loading && (
          <div style={{
            padding: '20px 24px',
            backgroundColor: 'var(--surface-card, #ffffff)',
            border: '1px solid var(--border-color, #e2e8f0)',
            borderRadius: '12px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            gap: '16px',
            boxShadow: '0 1px 3px rgba(0,0,0,0.05)'
          }}>
            <div>
              <div style={{ fontWeight: 600, fontSize: '15px', color: 'var(--text-primary)' }}>
                No Anomaly or Surge Alerts Recorded
              </div>
              <div style={{ fontSize: '13px', color: 'var(--text-muted)', marginTop: '4px' }}>
                Upload your retail sales CSV file to detect sudden demand spikes, drops, and stockout conditions.
              </div>
            </div>
            <button onClick={() => navigate('/upload')} className="diq-btn diq-btn-primary" style={{ whiteSpace: 'nowrap' }}>
              <Download size={15} /> Upload Sales CSV
            </button>
          </div>
        )}

        {/* ── KPI Summary ── */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(170px, 1fr))', gap: '12px' }}>
          <StatCard label="Total Alerts" value={totalAnomalies.toLocaleString('en-IN')} subtext="Unusual events found" icon={AlertTriangle} />
          <StatCard label="Demand Spikes" value={`${spikeCount.toLocaleString('en-IN')}`} subtext="Unexpected sales surges" />
          <StatCard label="Sudden Drops" value={`${dropCount.toLocaleString('en-IN')}`} subtext="Possible stockout situations" />
          <StatCard
            label="Critical Alerts"
            value={criticalCount.toLocaleString('en-IN')}
            subtext="Need immediate attention"
            style={criticalCount > 0 ? { borderColor: 'var(--status-critical-border)' } : {}}
          />
        </div>

        {/* ── Chart + Filters ── */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(340px, 1fr))', gap: '16px' }}>

          {/* Chart */}
          <Card title="Alert Breakdown" icon={BarChart2} subtitle="Distribution by type and severity.">
            <div style={{ height: 200, width: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              {chartData.length > 0 ? (
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={chartData} margin={{ top: 10, right: 10, left: -15, bottom: 0 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="var(--border-subtle)" />
                    <XAxis dataKey="name" stroke="var(--text-muted)" fontSize={11} tickLine={false} />
                    <YAxis stroke="var(--text-muted)" fontSize={11} />
                    <Tooltip
                      contentStyle={{
                        backgroundColor: '#ffffff',
                        borderColor: 'var(--border-subtle)',
                        borderRadius: 8,
                        boxShadow: 'var(--shadow-dropdown)',
                        fontSize: 12,
                      }}
                    />
                    <Bar dataKey="count" radius={[4, 4, 0, 0]}>
                      {chartData.map((entry, index) => (
                        <Cell key={`cell-${index}`} fill={entry.color} />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              ) : (
                <div style={{ textAlign: 'center', color: 'var(--text-muted)', fontSize: '13px' }}>
                  No anomaly distribution data recorded yet.
                </div>
              )}
            </div>
          </Card>

          {/* Filters */}
          <Card title="Filters" subtitle="Narrow down alerts to find what matters.">
            <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>

              {/* Search */}
              <div>
                <label style={labelStyle}>Search Product ID</label>
                <div style={{ position: 'relative' }}>
                  <Search size={15} style={{ position: 'absolute', left: '10px', top: '9px', color: 'var(--text-muted)' }} />
                  <input
                    type="text"
                    placeholder="e.g. 176190"
                    value={searchSKU}
                    onChange={(e) => setSearchSKU(e.target.value)}
                    style={{
                      width: '100%', padding: '8px 8px 8px 32px',
                      borderRadius: 'var(--border-radius-md)',
                      border: '1px solid var(--border-strong)',
                      backgroundColor: '#ffffff', color: 'var(--text-primary)',
                      fontSize: '13px',
                    }}
                  />
                </div>
              </div>

              {/* Severity */}
              <div>
                <label style={labelStyle}>Severity Level</label>
                <SegmentedControl
                  size="sm"
                  value={severityFilter}
                  onChange={setSeverityFilter}
                  options={[
                    { value: 'ALL', label: 'All' },
                    { value: 'CRITICAL', label: 'Critical' },
                    { value: 'MEDIUM', label: 'Medium' },
                    { value: 'LOW', label: 'Low' },
                  ]}
                />
              </div>

              {/* Type */}
              <div>
                <label style={labelStyle}>Event Type</label>
                <SegmentedControl
                  size="sm"
                  value={typeFilter}
                  onChange={setTypeFilter}
                  options={[
                    { value: 'ALL', label: 'All Types' },
                    { value: 'SPIKE_DEMAND', label: 'Spikes' },
                    { value: 'DROP_STOCKOUT', label: 'Drops' },
                  ]}
                />
              </div>
            </div>
          </Card>
        </div>

        {/* ── Alerts Table ── */}
        <Card
          title="Detected Alerts"
          subtitle="Unusual demand patterns compared to what was expected."
          actions={<span style={{ fontSize: '12px', color: 'var(--text-muted)' }}>Showing {filteredAlerts.length} alerts</span>}
        >
          {filteredAlerts.length === 0 && !loading ? (
            <EmptyState
              icon={Activity}
              title="No alerts found"
              description="No unusual activity was detected for the selected filters."
            />
          ) : (
            <div style={{ overflowX: 'auto' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '13px' }}>
                <thead>
                  <tr style={{ borderBottom: '1px solid var(--border-subtle)', backgroundColor: 'var(--bg-surface-subtle)' }}>
                    <th style={thStyle}>Date</th>
                    <th style={thStyle}>Product & City</th>
                    <th style={{ ...thStyle, textAlign: 'right' }}>Actual</th>
                    <th style={{ ...thStyle, textAlign: 'right' }}>Expected</th>
                    <th style={{ ...thStyle, textAlign: 'right' }}>Difference</th>
                    <th style={{ ...thStyle, textAlign: 'center' }}>Type</th>
                    <th style={{ ...thStyle, textAlign: 'center' }}>Severity</th>
                    <th style={thStyle}>Suggested Action</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredAlerts.slice(0, 50).map((row, idx) => {
                    const isSpike = row.anomaly_type === 'SPIKE_DEMAND';
                    const variancePct = row.expected_demand
                      ? Math.round(((row.actual_demand - row.expected_demand) / row.expected_demand) * 100)
                      : 0;

                    const severityVariant = row.severity === 'CRITICAL' ? 'critical'
                      : row.severity === 'MEDIUM' ? 'warning' : 'neutral';

                    return (
                      <tr
                        key={`${row.product_id}-${row.date_}-${idx}`}
                        style={{ borderBottom: '1px solid var(--border-subtle)' }}
                        onMouseEnter={(e) => e.currentTarget.style.backgroundColor = 'var(--bg-surface-subtle)'}
                        onMouseLeave={(e) => e.currentTarget.style.backgroundColor = '#ffffff'}
                      >
                        <td style={tdStyle}>{row.date_}</td>
                        <td style={tdStyle}>
                          <div style={{ fontWeight: 600 }}>#{row.product_id}</div>
                          <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>{row.city_name}</div>
                        </td>
                        <td style={{ ...tdStyle, textAlign: 'right', fontWeight: 600 }} className="tabular-nums">
                          {Math.round(row.actual_demand).toLocaleString('en-IN')}
                        </td>
                        <td style={{ ...tdStyle, textAlign: 'right', color: 'var(--text-muted)' }} className="tabular-nums">
                          {Math.round(row.expected_demand).toLocaleString('en-IN')}
                        </td>
                        <td style={{ ...tdStyle, textAlign: 'right' }} className="tabular-nums">
                          <span style={{
                            fontWeight: 700, fontSize: '12px',
                            color: isSpike ? 'var(--status-warning-text)' : 'var(--status-critical-text)',
                          }}>
                            {variancePct > 0 ? `+${variancePct}%` : `${variancePct}%`}
                          </span>
                        </td>
                        <td style={{ ...tdStyle, textAlign: 'center' }}>
                          <StatusBadge
                            variant={isSpike ? 'warning' : 'critical'}
                            icon={isSpike ? TrendingUp : TrendingDown}
                            label={isSpike ? 'Spike' : 'Drop'}
                            size="sm"
                          />
                        </td>
                        <td style={{ ...tdStyle, textAlign: 'center' }}>
                          <StatusBadge variant={severityVariant} label={row.severity} size="sm" />
                        </td>
                        <td style={{ ...tdStyle, fontSize: '12px', color: 'var(--text-secondary)' }}>
                          {row.action_recommendation || '—'}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </Card>
      </div>
    </PageShell>
  );
}

const thStyle = {
  padding: '10px 14px',
  fontSize: '11px',
  fontWeight: 600,
  textTransform: 'uppercase',
  letterSpacing: '0.05em',
  color: 'var(--text-muted)',
  textAlign: 'left',
  whiteSpace: 'nowrap',
};

const tdStyle = {
  padding: '11px 14px',
  verticalAlign: 'middle',
  color: 'var(--text-primary)',
};

const labelStyle = {
  display: 'block',
  fontSize: '11px',
  fontWeight: 600,
  textTransform: 'uppercase',
  letterSpacing: '0.04em',
  color: 'var(--text-muted)',
  marginBottom: '4px',
};
