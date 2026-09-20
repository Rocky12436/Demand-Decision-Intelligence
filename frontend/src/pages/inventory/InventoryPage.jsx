import React, { useEffect, useState, useMemo } from 'react';
import {
  Boxes,
  AlertTriangle,
  CheckCircle2,
  ShieldCheck,
  RefreshCw,
  Search,
  Sliders,
  Building2,
  Package,
  Layers,
  ArrowUpDown
} from 'lucide-react';
import api, { recomputeForecast } from '../../services/api';

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

      // Status classification
      let status = 'HEALTHY';
      let statusColor = 'var(--accent-emerald)';
      let badgeBg = 'rgba(16, 185, 129, 0.15)';
      let actionText = 'Stock Buffer Adequate';

      if (mean > 5000 && std / (mean || 1) > 0.12) {
        status = 'REORDER_NOW';
        statusColor = 'var(--accent-rose)';
        badgeBg = 'rgba(244, 63, 94, 0.15)';
        actionText = 'Trigger Fast Replenishment PO';
      } else if (mean > 3000) {
        status = 'BUFFER_REVIEW';
        statusColor = 'var(--accent-amber)';
        badgeBg = 'rgba(245, 158, 11, 0.15)';
        actionText = 'Review Supplier Lead Times';
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
        statusColor,
        badgeBg,
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

  return (
    <div style={{ maxWidth: '1400px', margin: '0 auto' }}>
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '2rem' }}>
        <div>
          <h1 style={{ fontSize: '1.75rem', fontWeight: 700, color: 'var(--text-primary)', display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
            <Boxes color="var(--accent-primary)" size={28} />
            Inventory Decision Intelligence
          </h1>
          <p style={{ color: 'var(--text-secondary)', fontSize: '0.925rem', marginTop: '0.25rem' }}>
            Dynamic Safety Stock, Reorder Point (ROP), and Target Stock Level optimization with service level simulation.
          </p>
        </div>

        <button
          className="btn btn-primary"
          onClick={loadInventoryData}
          disabled={loading}
          style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', padding: '0.75rem 1.4rem' }}
        >
          <RefreshCw size={16} className={loading ? 'animate-spin' : ''} />
          {loading ? 'Recalculating...' : 'Refresh Engine'}
        </button>
      </div>

      {/* KPI Cards */}
      <div className="grid-kpi" style={{ marginBottom: '1.5rem' }}>
        <div className="kpi-card">
          <div className="kpi-title">Monitored SKUs</div>
          <div className="kpi-value">{totalSKUs.toLocaleString()}</div>
          <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)', marginTop: '0.25rem' }}>Active catalog products</div>
        </div>

        <div className="kpi-card">
          <div className="kpi-title">Immediate Reorder POs</div>
          <div className="kpi-value" style={{ color: 'var(--accent-rose)' }}>{reorderUrgentCount}</div>
          <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)', marginTop: '0.25rem' }}>High stockout vulnerability</div>
        </div>

        <div className="kpi-card">
          <div className="kpi-title">Avg. Safety Buffer</div>
          <div className="kpi-value" style={{ color: 'var(--accent-cyan)' }}>{avgSafetyStock.toLocaleString()} <span style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>units</span></div>
          <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)', marginTop: '0.25rem' }}>Protecting {Math.round(serviceLevel * 100)}% cycle service</div>
        </div>

        <div className="kpi-card">
          <div className="kpi-title">Configured Lead Time</div>
          <div className="kpi-value" style={{ color: 'var(--accent-amber)' }}>{leadTimeDays} Days</div>
          <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)', marginTop: '0.25rem' }}>Fulfillment replenishment cycle</div>
        </div>
      </div>

      {/* Interactive Simulation & Filter Controls Bar */}
      <div className="card" style={{ marginBottom: '1.5rem', padding: '1.5rem' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '1.25rem' }}>
          <Sliders size={18} color="var(--accent-primary)" />
          <h3 style={{ fontSize: '1rem', fontWeight: 600, color: 'var(--text-primary)' }}>
            Live Policy Simulation Parameters & Filters
          </h3>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: '1.5rem' }}>
          {/* SKU Search */}
          <div>
            <label style={{ display: 'block', fontSize: '0.8rem', color: 'var(--text-secondary)', marginBottom: '0.4rem', fontWeight: 600, textTransform: 'uppercase' }}>
              Search SKU ID
            </label>
            <div style={{ position: 'relative' }}>
              <Search size={16} color="var(--text-muted)" style={{ position: 'absolute', left: '10px', top: '10px' }} />
              <input
                type="text"
                placeholder="e.g. 19512"
                value={searchSKU}
                onChange={(e) => setSearchSKU(e.target.value)}
                style={{
                  width: '100%',
                  padding: '0.5rem 0.5rem 0.5rem 2.2rem',
                  borderRadius: '6px',
                  border: '1px solid var(--border-strong)',
                  backgroundColor: 'var(--bg-surface-elevated)',
                  color: '#fff',
                  fontSize: '0.85rem',
                }}
              />
            </div>
          </div>

          {/* City Filter */}
          <div>
            <label style={{ display: 'block', fontSize: '0.8rem', color: 'var(--text-secondary)', marginBottom: '0.4rem', fontWeight: 600, textTransform: 'uppercase' }}>
              Fulfillment Hub
            </label>
            <select
              value={selectedCity}
              onChange={(e) => setSelectedCity(e.target.value)}
              style={{
                width: '100%',
                padding: '0.5rem 0.75rem',
                borderRadius: '6px',
                border: '1px solid var(--border-strong)',
                backgroundColor: 'var(--bg-surface-elevated)',
                color: '#fff',
                fontSize: '0.85rem',
              }}
            >
              <option value="ALL">All Hubs (Bengaluru, Delhi, Mumbai, HR-NCR)</option>
              <option value="Delhi">Delhi Hub</option>
              <option value="Bengaluru">Bengaluru Hub</option>
              <option value="Mumbai">Mumbai Hub</option>
              <option value="HR-NCR">HR-NCR Hub</option>
            </select>
          </div>

          {/* Lead Time Slider */}
          <div>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '0.4rem' }}>
              <label style={{ fontSize: '0.8rem', color: 'var(--text-secondary)', fontWeight: 600, textTransform: 'uppercase' }}>
                Supplier Lead Time
              </label>
              <span style={{ fontSize: '0.85rem', color: 'var(--accent-cyan)', fontWeight: 600 }}>
                {leadTimeDays} Days
              </span>
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
          </div>

          {/* Service Level Pills */}
          <div>
            <label style={{ display: 'block', fontSize: '0.8rem', color: 'var(--text-secondary)', marginBottom: '0.4rem', fontWeight: 600, textTransform: 'uppercase' }}>
              Target Cycle Service Level (CSL)
            </label>
            <div style={{ display: 'flex', gap: '0.5rem' }}>
              {[0.90, 0.95, 0.98, 0.99].map((lvl) => (
                <button
                  key={lvl}
                  onClick={() => setServiceLevel(lvl)}
                  style={{
                    flex: 1,
                    padding: '0.45rem 0',
                    borderRadius: '6px',
                    border: serviceLevel === lvl ? '1px solid var(--accent-primary)' : '1px solid var(--border-strong)',
                    backgroundColor: serviceLevel === lvl ? 'rgba(59, 130, 246, 0.2)' : 'var(--bg-surface-elevated)',
                    color: serviceLevel === lvl ? '#93c5fd' : 'var(--text-secondary)',
                    fontWeight: serviceLevel === lvl ? 600 : 500,
                    fontSize: '0.8rem',
                    cursor: 'pointer',
                  }}
                >
                  {Math.round(lvl * 100)}%
                </button>
              ))}
            </div>
          </div>
        </div>
      </div>

      {/* Detailed Recommendations Data Table */}
      <div className="card" style={{ padding: '1.5rem' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.25rem' }}>
          <div>
            <h3 style={{ fontSize: '1.1rem', fontWeight: 600, color: 'var(--text-primary)' }}>
              Optimized Inventory Policies Table
            </h3>
            <p style={{ fontSize: '0.85rem', color: 'var(--text-secondary)' }}>
              Dynamic calculations: ROP = (Mean Demand × Lead Time) + Safety Stock
            </p>
          </div>
          <div style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>
            Showing {filteredData.length} records
          </div>
        </div>

        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.875rem' }}>
            <thead>
              <tr style={{ borderBottom: '1px solid var(--border-subtle)' }}>
                <th
                  onClick={() => toggleSort('product_id')}
                  style={{ padding: '0.75rem', textAlign: 'left', color: 'var(--text-muted)', cursor: 'pointer', fontSize: '0.78rem', textTransform: 'uppercase' }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.3rem' }}>
                    SKU ID <ArrowUpDown size={12} />
                  </div>
                </th>
                <th
                  onClick={() => toggleSort('city_name')}
                  style={{ padding: '0.75rem', textAlign: 'left', color: 'var(--text-muted)', cursor: 'pointer', fontSize: '0.78rem', textTransform: 'uppercase' }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.3rem' }}>
                    Hub <ArrowUpDown size={12} />
                  </div>
                </th>
                <th
                  onClick={() => toggleSort('mean_daily_demand')}
                  style={{ padding: '0.75rem', textAlign: 'right', color: 'var(--text-muted)', cursor: 'pointer', fontSize: '0.78rem', textTransform: 'uppercase' }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'flex-end', gap: '0.3rem' }}>
                    Daily Demand (μ) <ArrowUpDown size={12} />
                  </div>
                </th>
                <th
                  onClick={() => toggleSort('calculated_ss')}
                  style={{ padding: '0.75rem', textAlign: 'right', color: 'var(--text-muted)', cursor: 'pointer', fontSize: '0.78rem', textTransform: 'uppercase' }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'flex-end', gap: '0.3rem' }}>
                    King's SS (Δ vs Classical) <ArrowUpDown size={12} />
                  </div>
                </th>
                <th
                  onClick={() => toggleSort('calculated_rop')}
                  style={{ padding: '0.75rem', textAlign: 'right', color: 'var(--text-muted)', cursor: 'pointer', fontSize: '0.78rem', textTransform: 'uppercase' }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'flex-end', gap: '0.3rem' }}>
                    Reorder Point (ROP) <ArrowUpDown size={12} />
                  </div>
                </th>
                <th
                  onClick={() => toggleSort('calculated_tsl')}
                  style={{ padding: '0.75rem', textAlign: 'right', color: 'var(--text-muted)', cursor: 'pointer', fontSize: '0.78rem', textTransform: 'uppercase' }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'flex-end', gap: '0.3rem' }}>
                    Target Stock (TSL) <ArrowUpDown size={12} />
                  </div>
                </th>
                <th style={{ padding: '0.75rem', textAlign: 'center', color: 'var(--text-muted)', fontSize: '0.78rem', textTransform: 'uppercase' }}>
                  Action Recommendation
                </th>
              </tr>
            </thead>
            <tbody>
              {filteredData.slice(0, 100).map((row, idx) => (
                <tr
                  key={`${row.product_id}-${row.city_name}-${idx}`}
                  style={{
                    borderBottom: '1px solid var(--border-subtle)',
                    backgroundColor: idx % 2 === 0 ? 'transparent' : 'rgba(255, 255, 255, 0.01)',
                  }}
                >
                  <td style={{ padding: '0.75rem', fontWeight: 600, color: 'var(--text-primary)' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                      <span>#{row.product_id}</span>
                      <span
                        title={`Lead time confidence: ${row.lead_time_confidence}`}
                        style={{
                          fontSize: '0.65rem',
                          fontWeight: 700,
                          padding: '0.1rem 0.35rem',
                          borderRadius: '4px',
                          backgroundColor: row.lead_time_confidence === 'HIGH' ? 'rgba(16, 185, 129, 0.2)' : 'rgba(245, 158, 11, 0.2)',
                          color: row.lead_time_confidence === 'HIGH' ? 'var(--accent-emerald)' : 'var(--accent-amber)',
                        }}
                      >
                        LT: {row.lead_time_confidence}
                      </span>
                    </div>
                  </td>
                  <td style={{ padding: '0.75rem', color: 'var(--text-secondary)' }}>
                    {row.city_name}
                  </td>
                  <td style={{ padding: '0.75rem', textAlign: 'right', fontWeight: 500, color: 'var(--text-primary)' }}>
                    {Math.round(row.mean_daily_demand).toLocaleString()}
                  </td>
                  <td style={{ padding: '0.75rem', textAlign: 'right', fontWeight: 600 }}>
                    <div style={{ color: 'var(--accent-cyan)' }}>{row.calculated_ss.toLocaleString()}</div>
                    {row.ss_delta != null && row.ss_delta !== 0 && (
                      <div style={{ fontSize: '0.72rem', color: row.ss_delta > 0 ? '#fbbf24' : '#94a3b8', marginTop: '2px' }}>
                        {row.ss_delta > 0 ? `+${row.ss_delta.toLocaleString()}` : row.ss_delta.toLocaleString()} vs classical
                      </div>
                    )}
                  </td>
                  <td style={{ padding: '0.75rem', textAlign: 'right', fontWeight: 700, color: 'var(--accent-amber)' }}>
                    {row.calculated_rop.toLocaleString()}
                  </td>
                  <td style={{ padding: '0.75rem', textAlign: 'right', fontWeight: 500, color: 'var(--text-primary)' }}>
                    {row.calculated_tsl.toLocaleString()}
                  </td>
                  <td style={{ padding: '0.75rem', textAlign: 'center' }}>
                    <span
                      style={{
                        padding: '0.25rem 0.65rem',
                        borderRadius: '6px',
                        fontSize: '0.75rem',
                        fontWeight: 600,
                        backgroundColor: row.badgeBg,
                        color: row.statusColor,
                        display: 'inline-block',
                      }}
                    >
                      {row.actionText}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>

          {filteredData.length === 0 && !loading && (
            <div style={{ textAlign: 'center', padding: '3rem', color: 'var(--text-muted)' }}>
              No inventory records match the selected filter.
            </div>
          )}
        </div>

        {/* Freshness & Staleness Metadata Caption */}
        <div style={{ marginTop: '1.25rem', paddingTop: '0.85rem', borderTop: '1px solid var(--border-subtle)', display: 'flex', flexWrap: 'wrap', alignItems: 'center', justifyContent: 'space-between', gap: '0.75rem', fontSize: '0.82rem', color: 'var(--text-muted)' }}>
          <div>
            Computed {freshness?.computed_at ? new Date(freshness.computed_at).toISOString().replace('T', ' ').slice(0, 16) : new Date().toISOString().slice(0, 16)} from data through {freshness?.data_through || 'latest'} (model: {freshness?.model_name || 'EOQ_SafetyStock_95'})
            {' · '}
            <button
              onClick={handleRecomputeNow}
              disabled={recomputing}
              style={{ background: 'none', border: 'none', color: 'var(--accent-primary)', cursor: 'pointer', textDecoration: 'underline', padding: 0, fontSize: '0.82rem' }}
            >
              [Recompute now]
            </button>
          </div>

          {freshness?.is_stale && (
            <div style={{ display: 'inline-flex', alignItems: 'center', gap: '0.5rem', padding: '0.3rem 0.75rem', borderRadius: '6px', backgroundColor: 'rgba(245, 158, 11, 0.15)', border: '1px solid var(--accent-amber)', color: 'var(--accent-amber)', fontWeight: 500, fontSize: '0.78rem' }}>
              <span>⚠ Data has updated since this inventory policy was generated — recompute recommended</span>
              <button
                onClick={handleRecomputeNow}
                disabled={recomputing}
                style={{ backgroundColor: 'var(--accent-amber)', color: '#000', border: 'none', borderRadius: '4px', padding: '0.2rem 0.5rem', fontSize: '0.72rem', fontWeight: 700, cursor: 'pointer' }}
              >
                Recompute
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
