import React, { useEffect, useState, useMemo } from 'react';
import {
  Boxes,
  AlertTriangle,
  CheckCircle2,
  RefreshCw,
  Search,
  Sliders,
  ArrowUpDown,
  Loader2,
  Eye,
  ShoppingCart,
  X,
} from 'lucide-react';
import api, { recomputeForecast } from '../../services/api';
import ForwardBuyWidget from './ForwardBuyWidget';
import SkuExplainabilityModal from '../../components/common/SkuExplainabilityModal';
import {
  PageShell,
  PageHeader,
  Card,
  StatCard,
  StatusBadge,
  EmptyState,
} from '../../components/ui';

const Z_SCORES = {
  0.90: 1.282,
  0.95: 1.645,
  0.98: 2.054,
  0.99: 2.326,
};

export default function InventoryPage() {
  const [data, setData] = useState([]);
  const [freshness, setFreshness] = useState(null);
  const [recomputing, setRecomputing] = useState(false);
  const [loading, setLoading] = useState(true);
  const [searchSKU, setSearchSKU] = useState('');
  const [selectedCity, setSelectedCity] = useState('ALL');
  const [leadTimeDays, setLeadTimeDays] = useState(3);
  const [serviceLevel, setServiceLevel] = useState(0.95);
  const [sortField, setSortField] = useState('mean_daily_demand');
  const [sortAsc, setSortAsc] = useState(false);
  const [selectedForwardBuySku, setSelectedForwardBuySku] = useState(null);
  const [selectedExplainSku, setSelectedExplainSku] = useState(null);

  useEffect(() => {
    loadInventoryData();
  }, [selectedCity]);

  const loadInventoryData = async () => {
    setLoading(true);
    try {
      let url = '/inventory/recommendations?limit=500';
      if (selectedCity !== 'ALL') {
        url += `&city_name=${encodeURIComponent(selectedCity)}`;
      }
      const res = await api.get(url);
      if (res?.data?.data) {
        setData(res.data.data);
      }
      if (res?.data?.freshness) {
        setFreshness(res.data.freshness);
      }
    } catch (err) {
      console.error('Failed to load inventory recommendations', err);
      // Fallback sample data if backend endpoint is unavailable
      setData([
        { product_id: 19512, city_name: 'Delhi', mean_daily_demand: 8690.15, std_daily_demand: 878.87 },
        { product_id: 391306, city_name: 'Bengaluru', mean_daily_demand: 6420.50, std_daily_demand: 654.12 },
        { product_id: 12872, city_name: 'Mumbai', mean_daily_demand: 5310.20, std_daily_demand: 540.30 },
        { product_id: 3881, city_name: 'HR-NCR', mean_daily_demand: 4890.00, std_daily_demand: 492.40 },
        { product_id: 445675, city_name: 'Delhi', mean_daily_demand: 4120.80, std_daily_demand: 430.15 },
        { product_id: 1, city_name: 'Delhi', mean_daily_demand: 3250.60, std_daily_demand: 340.20 },
      ]);
    } finally {
      setLoading(false);
    }
  };

  const handleRecomputeNow = async () => {
    setRecomputing(true);
    try {
      await recomputeForecast();
      await loadInventoryData();
    } catch (err) {
      console.error('Recompute failed', err);
    } finally {
      setRecomputing(false);
    }
  };

  // Dynamic calculations based on user sliders
  const processedData = useMemo(() => {
    const z = Z_SCORES[serviceLevel] || 1.645;
    const lt = Number(leadTimeDays) || 3;

    return data.map((item) => {
      const mean = Number(item.mean_daily_demand) || 0;
      const std = Number(item.std_daily_demand) || 0;
      const sigmaL = item.sigma_lead_time_days != null ? Number(item.sigma_lead_time_days) : (0.25 * lt);
      const ltConfidence = item.lead_time_confidence || (item.lead_time_observations_count >= 5 ? 'HIGH' : 'LOW');

      // Dynamic inventory formula (King's formula with lead time variability)
      const varianceDemandTerm = lt * Math.pow(std, 2);
      const varianceLeadTimeTerm = Math.pow(mean, 2) * Math.pow(sigmaL, 2);
      const ssKings = Math.ceil(z * Math.sqrt(varianceDemandTerm + varianceLeadTimeTerm));
      const ssClassical = Math.ceil(z * std * Math.sqrt(lt));
      const ssDelta = ssKings - ssClassical;

      const rop = Math.ceil(mean * lt + ssKings);
      const tsl = Math.ceil(mean * (lt + 7) + ssKings);

      // Status classification with user-friendly labels
      let status = 'HEALTHY';
      let statusVariant = 'success';
      let actionText = 'Stock level OK';

      if (mean > 5000 && std / (mean || 1) > 0.12) {
        status = 'REORDER_NOW';
        statusVariant = 'critical';
        actionText = 'Order now — risk of running out';
      } else if (mean > 3000) {
        status = 'BUFFER_REVIEW';
        statusVariant = 'warning';
        actionText = 'Check supplier delivery times';
      }

      return {
        ...item,
        calculated_ss: ssKings,
        ss_classical: ssClassical,
        ss_delta: ssDelta,
        sigma_lead_time: sigmaL,
        lead_time_confidence: ltConfidence,
        calculated_rop: rop,
        calculated_tsl: tsl,
        status,
        statusVariant,
        actionText,
      };
    });
  }, [data, leadTimeDays, serviceLevel]);

  // Filter and Sort
  const filteredData = useMemo(() => {
    return processedData
      .filter((row) => {
        if (!searchSKU) return true;
        return String(row.product_id).includes(searchSKU.trim());
      })
      .sort((a, b) => {
        let valA = a[sortField];
        let valB = b[sortField];
        if (typeof valA === 'string') {
          return sortAsc ? valA.localeCompare(valB) : valB.localeCompare(valA);
        }
        return sortAsc ? valA - valB : valB - valA;
      });
  }, [processedData, searchSKU, sortField, sortAsc]);

  // KPI Metrics
  const totalSKUs = filteredData.length;
  const reorderUrgentCount = filteredData.filter((r) => r.status === 'REORDER_NOW').length;
  const avgSafetyStock = Math.round(
    filteredData.reduce((acc, r) => acc + r.calculated_ss, 0) / (totalSKUs || 1)
  );

  const toggleSort = (field) => {
    if (sortField === field) {
      setSortAsc(!sortAsc);
    } else {
      setSortField(field);
      setSortAsc(false);
    }
  };

  const SortHeader = ({ field, label, align = 'left' }) => (
    <th
      onClick={() => toggleSort(field)}
      style={{
        ...thStyle,
        textAlign: align,
        cursor: 'pointer',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: '4px', justifyContent: align === 'right' ? 'flex-end' : 'flex-start' }}>
        {label}
        <ArrowUpDown size={11} style={{ opacity: sortField === field ? 1 : 0.3 }} />
      </div>
    </th>
  );

  return (
    <PageShell maxWidth="1400px">
      <PageHeader
        icon={Boxes}
        title="Stock & Reorder Planning"
        subtitle="See how much stock to keep and when to reorder. Adjust delivery time and service level to see changes instantly."
        actions={
          <button onClick={loadInventoryData} className="diq-btn diq-btn-secondary" disabled={loading}>
            <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
            {loading ? 'Loading...' : 'Refresh'}
          </button>
        }
      />

      <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>

        {/* ── KPI Cards ── */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(170px, 1fr))', gap: '12px' }}>
          <StatCard label="Products Tracked" value={totalSKUs.toLocaleString('en-IN')} subtext="In selected city" />
          <StatCard
            label="Need Urgent Reorder"
            value={reorderUrgentCount}
            subtext="High risk of stockout"
            style={reorderUrgentCount > 0 ? { borderColor: 'var(--status-critical-border)' } : {}}
          />
          <StatCard
            label="Avg. Safety Stock"
            value={`${avgSafetyStock.toLocaleString('en-IN')} units`}
            subtext={`Protecting ${Math.round(serviceLevel * 100)}% service`}
          />
          <StatCard
            label="Delivery Time"
            value={`${leadTimeDays} days`}
            subtext="From supplier to warehouse"
          />
        </div>

        {/* ── Settings & Filters ── */}
        <Card title="Settings & Filters" icon={Sliders} subtitle="Change these to see how stock levels would change.">
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '20px' }}>

            {/* Search */}
            <div>
              <label style={labelStyle}>Search Product ID</label>
              <div style={{ position: 'relative' }}>
                <Search size={15} style={{ position: 'absolute', left: '10px', top: '9px', color: 'var(--text-muted)' }} />
                <input
                  type="text"
                  placeholder="e.g. 19512"
                  value={searchSKU}
                  onChange={(e) => setSearchSKU(e.target.value)}
                  style={inputStyle}
                />
              </div>
            </div>

            {/* City filter */}
            <div>
              <label style={labelStyle}>City / Warehouse</label>
              <select
                value={selectedCity}
                onChange={(e) => setSelectedCity(e.target.value)}
                style={selectStyle}
              >
                <option value="ALL">All Cities</option>
                <option value="Delhi">Delhi</option>
                <option value="Bengaluru">Bengaluru</option>
                <option value="Mumbai">Mumbai</option>
                <option value="HR-NCR">HR-NCR</option>
              </select>
            </div>

            {/* Lead time slider */}
            <div>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '4px' }}>
                <label style={labelStyle}>Supplier Delivery Time</label>
                <span style={{ fontSize: '13px', fontWeight: 700, color: 'var(--accent-primary)' }}>{leadTimeDays} days</span>
              </div>
              <input
                type="range"
                min="1"
                max="14"
                step="1"
                value={leadTimeDays}
                onChange={(e) => setLeadTimeDays(Number(e.target.value))}
                style={{ width: '100%', accentColor: 'var(--accent-primary)', cursor: 'pointer' }}
              />
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '10px', color: 'var(--text-muted)' }}>
                <span>1 day</span>
                <span>14 days</span>
              </div>
            </div>

            {/* Service level */}
            <div>
              <label style={labelStyle}>Service Level (how often you want to be in stock)</label>
              <div style={{ display: 'flex', gap: '6px', marginTop: '4px' }}>
                {[0.90, 0.95, 0.98, 0.99].map((lvl) => (
                  <button
                    key={lvl}
                    onClick={() => setServiceLevel(lvl)}
                    className={serviceLevel === lvl ? 'diq-btn diq-btn-primary diq-btn-sm' : 'diq-btn diq-btn-secondary diq-btn-sm'}
                    style={{ flex: 1 }}
                  >
                    {Math.round(lvl * 100)}%
                  </button>
                ))}
              </div>
            </div>
          </div>
        </Card>

        {/* ── Main Data Table ── */}
        <Card
          title="Stock Levels & Reorder Points"
          subtitle="All numbers update live when you change settings above."
          actions={
            <span style={{ fontSize: '12px', color: 'var(--text-muted)' }}>
              Showing {filteredData.length} products
            </span>
          }
        >
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '13px' }}>
              <thead>
                <tr style={{ borderBottom: '1px solid var(--border-subtle)', backgroundColor: 'var(--bg-surface-subtle)' }}>
                  <SortHeader field="product_id" label="Product ID" />
                  <SortHeader field="city_name" label="City" />
                  <SortHeader field="mean_daily_demand" label="Daily Demand" align="right" />
                  <SortHeader field="calculated_ss" label="Safety Stock" align="right" />
                  <SortHeader field="calculated_rop" label="Reorder At" align="right" />
                  <SortHeader field="calculated_tsl" label="Target Stock" align="right" />
                  <th style={{ ...thStyle, textAlign: 'center' }}>Status</th>
                  <th style={{ ...thStyle, textAlign: 'center' }}>Actions</th>
                </tr>
              </thead>
              <tbody>
                {filteredData.length === 0 && !loading ? (
                  <tr>
                    <td colSpan="8" style={{ padding: '40px 16px', textAlign: 'center', color: 'var(--text-muted)' }}>
                      No products match your filters.
                    </td>
                  </tr>
                ) : (
                  filteredData.slice(0, 100).map((row, idx) => (
                    <tr
                      key={`${row.product_id}-${row.city_name}-${idx}`}
                      style={{ borderBottom: '1px solid var(--border-subtle)' }}
                      onMouseEnter={(e) => e.currentTarget.style.backgroundColor = 'var(--bg-surface-subtle)'}
                      onMouseLeave={(e) => e.currentTarget.style.backgroundColor = '#ffffff'}
                    >
                      <td style={tdStyle}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                          <span style={{ fontWeight: 600 }}>#{row.product_id}</span>
                          <StatusBadge
                            variant={row.lead_time_confidence === 'HIGH' ? 'success' : 'warning'}
                            label={row.lead_time_confidence === 'HIGH' ? 'Reliable' : 'Estimated'}
                            size="sm"
                          />
                        </div>
                      </td>
                      <td style={tdStyle}>{row.city_name}</td>
                      <td style={{ ...tdStyle, textAlign: 'right', fontWeight: 500 }} className="tabular-nums">
                        {Math.round(row.mean_daily_demand).toLocaleString('en-IN')}
                      </td>
                      <td style={{ ...tdStyle, textAlign: 'right' }} className="tabular-nums">
                        <div style={{ fontWeight: 600, color: 'var(--accent-primary)' }}>
                          {row.calculated_ss.toLocaleString('en-IN')}
                        </div>
                        {row.ss_delta != null && row.ss_delta !== 0 && (
                          <div style={{ fontSize: '11px', color: 'var(--text-muted)', marginTop: '1px' }}>
                            {row.ss_delta > 0 ? '+' : ''}{row.ss_delta.toLocaleString('en-IN')} vs basic
                          </div>
                        )}
                      </td>
                      <td style={{ ...tdStyle, textAlign: 'right', fontWeight: 700, color: 'var(--status-warning-text)' }} className="tabular-nums">
                        {row.calculated_rop.toLocaleString('en-IN')}
                      </td>
                      <td style={{ ...tdStyle, textAlign: 'right', fontWeight: 500 }} className="tabular-nums">
                        {row.calculated_tsl.toLocaleString('en-IN')}
                      </td>
                      <td style={{ ...tdStyle, textAlign: 'center' }}>
                        <StatusBadge variant={row.statusVariant} label={row.actionText} size="sm" />
                      </td>
                      <td style={{ ...tdStyle, textAlign: 'center' }}>
                        <div style={{ display: 'flex', gap: '4px', justifyContent: 'center' }}>
                          <button
                            onClick={() => setSelectedForwardBuySku(row.product_id)}
                            className="diq-btn diq-btn-secondary diq-btn-sm"
                            title="Simulate bulk purchase savings"
                          >
                            <ShoppingCart size={12} /> Bulk Buy
                          </button>
                          <button
                            onClick={() => setSelectedExplainSku(row.product_id)}
                            className="diq-btn diq-btn-secondary diq-btn-sm"
                            title="See how these numbers were calculated"
                          >
                            <Eye size={12} /> Why?
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>

          {/* Freshness / Staleness footer */}
          <div style={{
            marginTop: '16px', paddingTop: '12px', borderTop: '1px solid var(--border-subtle)',
            display: 'flex', flexWrap: 'wrap', alignItems: 'center', justifyContent: 'space-between',
            gap: '10px', fontSize: '12px', color: 'var(--text-muted)',
          }}>
            <div>
              Last calculated: {freshness?.computed_at ? new Date(freshness.computed_at).toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' }) : 'just now'}
              {' · '}
              <button
                onClick={handleRecomputeNow}
                disabled={recomputing}
                style={{ background: 'none', border: 'none', color: 'var(--accent-primary)', cursor: 'pointer', textDecoration: 'underline', padding: 0, fontSize: '12px', fontWeight: 500 }}
              >
                {recomputing ? 'Recalculating...' : 'Recalculate now'}
              </button>
            </div>

            {freshness?.is_stale && (
              <StatusBadge variant="warning" label="New data available — recalculate recommended" size="sm" />
            )}
          </div>
        </Card>

        {/* ── Forward Buy Simulator ── */}
        {selectedForwardBuySku && (
          <Card
            title={`Bulk Purchase Simulator — Product #${selectedForwardBuySku}`}
            subtitle="See if buying more at once would save money."
            actions={
              <button onClick={() => setSelectedForwardBuySku(null)} className="diq-btn diq-btn-secondary diq-btn-sm">
                <X size={14} /> Close
              </button>
            }
          >
            <ForwardBuyWidget productId={selectedForwardBuySku} />
          </Card>
        )}
      </div>

      {/* SKU Explainability Trace Modal */}
      {selectedExplainSku && (
        <SkuExplainabilityModal
          productId={selectedExplainSku}
          onClose={() => setSelectedExplainSku(null)}
        />
      )}
    </PageShell>
  );
}

// Shared styles
const thStyle = {
  padding: '10px 14px',
  fontSize: '11px',
  fontWeight: 600,
  textTransform: 'uppercase',
  letterSpacing: '0.05em',
  color: 'var(--text-muted)',
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

const inputStyle = {
  width: '100%',
  padding: '8px 8px 8px 32px',
  borderRadius: 'var(--border-radius-md)',
  border: '1px solid var(--border-strong)',
  backgroundColor: '#ffffff',
  color: 'var(--text-primary)',
  fontSize: '13px',
};

const selectStyle = {
  width: '100%',
  padding: '8px 10px',
  borderRadius: 'var(--border-radius-md)',
  border: '1px solid var(--border-strong)',
  backgroundColor: '#ffffff',
  color: 'var(--text-primary)',
  fontSize: '13px',
};
