import React, { useState, useEffect } from 'react';
import {
  Grid3X3,
  Sliders,
  Sparkles,
  Package,
  Layers,
  Search,
  CheckCircle2,
  AlertCircle,
  RefreshCw,
  Info,
  TrendingUp,
  Settings2,
  X
} from 'lucide-react';
import api from '../../services/api';

const CELL_COLOR_MAP = {
  AX: { border: 'rgba(16, 185, 129, 0.4)', bg: 'rgba(16, 185, 129, 0.08)', text: '#34d399' },
  AY: { border: 'rgba(59, 130, 246, 0.4)', bg: 'rgba(59, 130, 246, 0.08)', text: '#60a5fa' },
  AZ: { border: 'rgba(245, 158, 11, 0.4)', bg: 'rgba(245, 158, 11, 0.08)', text: '#fbbf24' },
  BX: { border: 'rgba(59, 130, 246, 0.3)', bg: 'rgba(59, 130, 246, 0.05)', text: '#93c5fd' },
  BY: { border: 'rgba(245, 158, 11, 0.3)', bg: 'rgba(245, 158, 11, 0.05)', text: '#fcd34d' },
  BZ: { border: 'rgba(239, 68, 68, 0.3)', bg: 'rgba(239, 68, 68, 0.05)', text: '#f87171' },
  CX: { border: 'rgba(148, 163, 184, 0.3)', bg: 'rgba(148, 163, 184, 0.05)', text: '#cbd5e1' },
  CY: { border: 'rgba(245, 158, 11, 0.25)', bg: 'rgba(245, 158, 11, 0.04)', text: '#fde68a' },
  CZ: { border: 'rgba(239, 68, 68, 0.4)', bg: 'rgba(239, 68, 68, 0.1)', text: '#ef4444' },
};

export default function AbcXyzPage() {
  const [matrixData, setMatrixData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [selectedCell, setSelectedCell] = useState('AX');
  const [drilldownData, setDrilldownData] = useState(null);
  const [drilldownLoading, setDrilldownLoading] = useState(false);
  const [skuSearch, setSkuSearch] = useState('');
  
  // Policy tuning modal state
  const [showPolicyModal, setShowPolicyModal] = useState(false);
  const [policyForm, setPolicyForm] = useState(null);
  const [policySaving, setPolicySaving] = useState(false);
  const [successMessage, setSuccessMessage] = useState(null);

  useEffect(() => {
    loadMatrix();
  }, []);

  useEffect(() => {
    if (selectedCell) {
      loadCellSkus(selectedCell);
    }
  }, [selectedCell]);

  const loadMatrix = async () => {
    setLoading(true);
    try {
      const res = await api.get('/classification/matrix');
      if (res?.data) {
        setMatrixData(res.data);
      }
    } catch (err) {
      console.error('Failed to load ABC-XYZ matrix', err);
    } finally {
      setLoading(false);
    }
  };

  const loadCellSkus = async (cell) => {
    setDrilldownLoading(true);
    try {
      const res = await api.get(`/classification/skus?cell=${cell}&limit=100`);
      if (res?.data) {
        setDrilldownData(res.data);
        if (res.data.policy) {
          setPolicyForm({
            cell: cell,
            review_strategy: res.data.policy.review_strategy,
            target_service_level: res.data.policy.target_service_level,
            safety_stock_policy: res.data.policy.safety_stock_policy,
            reorder_automation: res.data.policy.reorder_automation,
            description: res.data.policy.description || '',
          });
        }
      }
    } catch (err) {
      console.error('Failed to load cell SKUs', err);
    } finally {
      setDrilldownLoading(false);
    }
  };

  const handleSavePolicy = async () => {
    if (!policyForm) return;
    setPolicySaving(true);
    try {
      await api.put(`/classification/policies/${policyForm.cell}`, {
        review_strategy: policyForm.review_strategy,
        target_service_level: Number(policyForm.target_service_level),
        safety_stock_policy: policyForm.safety_stock_policy,
        reorder_automation: policyForm.reorder_automation,
        description: policyForm.description,
      });
      setSuccessMessage(`Policy for Cell ${policyForm.cell} updated successfully!`);
      setShowPolicyModal(false);
      loadMatrix();
      loadCellSkus(selectedCell);
      setTimeout(() => setSuccessMessage(null), 4000);
    } catch (err) {
      console.error('Failed to update policy', err);
    } finally {
      setPolicySaving(false);
    }
  };

  const grid = matrixData?.grid || { A: [], B: [], C: [] };
  const totalSkus = matrixData?.total_skus || 0;
  const totalVal = matrixData?.total_annual_value || 0;

  const filteredSkus = (drilldownData?.skus || []).filter(s =>
    s.product_name.toLowerCase().includes(skuSearch.toLowerCase()) ||
    s.product_id.toLowerCase().includes(skuSearch.toLowerCase()) ||
    s.brand_name.toLowerCase().includes(skuSearch.toLowerCase())
  );

  return (
    <div style={{ padding: '1.5rem', maxWidth: '1400px', margin: '0 auto' }}>
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '1.5rem', flexWrap: 'wrap', gap: '1rem' }}>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
            <h1 style={{ fontSize: '1.75rem', fontWeight: 700, color: 'var(--text-primary)' }}>
              ABC-XYZ Policy Matrix
            </h1>
            <span
              style={{
                backgroundColor: 'rgba(59, 130, 246, 0.15)',
                color: '#60a5fa',
                border: '1px solid rgba(59, 130, 246, 0.3)',
                padding: '0.2rem 0.6rem',
                borderRadius: '6px',
                fontSize: '0.75rem',
                fontWeight: 600,
                display: 'flex',
                alignItems: 'center',
                gap: '0.3rem'
              }}
            >
              <Grid3X3 size={13} /> 9-Cell Policy Matrix
            </span>
          </div>
          <p style={{ color: 'var(--text-muted)', fontSize: '0.88rem', marginTop: '0.3rem' }}>
            Segments items by Annual Consumption Value (Pareto ABC 80/15/5%) and Demand Predictability (XYZ CV² &lt;0.25, 0.25-1.0, &gt;1.0) with configurable policies.
          </p>
        </div>

        <div style={{ display: 'flex', gap: '0.6rem' }}>
          <button
            onClick={() => {
              loadMatrix();
              loadCellSkus(selectedCell);
            }}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '0.4rem',
              backgroundColor: 'rgba(255, 255, 255, 0.05)',
              border: '1px solid var(--border-subtle)',
              color: 'var(--text-primary)',
              borderRadius: '8px',
              padding: '0.55rem 1rem',
              fontSize: '0.85rem',
              fontWeight: 500,
              cursor: 'pointer'
            }}
          >
            <RefreshCw size={15} /> Recalculate Matrix
          </button>
        </div>
      </div>

      {/* Success Notification */}
      {successMessage && (
        <div
          style={{
            backgroundColor: 'rgba(16, 185, 129, 0.15)',
            border: '1px solid var(--accent-emerald)',
            color: 'var(--accent-emerald)',
            padding: '0.8rem 1.2rem',
            borderRadius: '8px',
            marginBottom: '1.2rem',
            display: 'flex',
            alignItems: 'center',
            gap: '0.5rem',
            fontSize: '0.9rem',
            fontWeight: 500
          }}
        >
          <CheckCircle2 size={18} /> {successMessage}
        </div>
      )}

      {/* 3x3 Interactive Matrix Grid */}
      <div
        style={{
          backgroundColor: 'var(--bg-surface)',
          border: '1px solid var(--border-subtle)',
          borderRadius: '12px',
          padding: '1.5rem',
          marginBottom: '1.5rem'
        }}
      >
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.2rem' }}>
          <div>
            <h3 style={{ fontSize: '1.15rem', fontWeight: 600, color: 'var(--text-primary)' }}>
              Segmentation Grid ({totalSkus} SKUs · ₹{Math.round(totalVal).toLocaleString()} Annual Value)
            </h3>
            <p style={{ color: 'var(--text-muted)', fontSize: '0.8rem', marginTop: '0.2rem' }}>
              Click on any of the 9 cells to inspect policies and drill down into the classified SKUs.
            </p>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '1rem', fontSize: '0.78rem', color: 'var(--text-muted)' }}>
            <span><strong>X:</strong> Constant (CV² &lt; 0.25)</span>
            <span><strong>Y:</strong> Variable (0.25–1.0)</span>
            <span><strong>Z:</strong> Erratic (CV² &gt; 1.0)</span>
          </div>
        </div>

        {/* 3x3 Grid Structure */}
        <div style={{ display: 'grid', gridTemplateColumns: '80px repeat(3, 1fr)', gap: '0.75rem', alignItems: 'stretch' }}>
          {/* Column Headers */}
          <div></div>
          <div style={{ textAlign: 'center', fontWeight: 700, color: '#60a5fa', fontSize: '0.9rem', padding: '0.4rem', backgroundColor: 'rgba(59, 130, 246, 0.08)', borderRadius: '6px' }}>
            X (Predictable)
          </div>
          <div style={{ textAlign: 'center', fontWeight: 700, color: '#fbbf24', fontSize: '0.9rem', padding: '0.4rem', backgroundColor: 'rgba(245, 158, 11, 0.08)', borderRadius: '6px' }}>
            Y (Variable)
          </div>
          <div style={{ textAlign: 'center', fontWeight: 700, color: '#f87171', fontSize: '0.9rem', padding: '0.4rem', backgroundColor: 'rgba(239, 68, 68, 0.08)', borderRadius: '6px' }}>
            Z (Erratic)
          </div>

          {/* Row A */}
          {['A', 'B', 'C'].map((rowKey) => {
            const rowLabel = rowKey === 'A' ? 'A (Top 80%)' : rowKey === 'B' ? 'B (Next 15%)' : 'C (Last 5%)';
            const rowCells = grid[rowKey] || [];

            return (
              <React.Fragment key={rowKey}>
                {/* Row Header */}
                <div
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    fontWeight: 700,
                    fontSize: '0.85rem',
                    color: 'var(--text-secondary)',
                    backgroundColor: 'rgba(255, 255, 255, 0.03)',
                    borderRadius: '6px',
                    padding: '0.5rem',
                    textAlign: 'center',
                    lineHeight: 1.2
                  }}
                >
                  {rowLabel}
                </div>

                {/* 3 Cell Columns for this row */}
                {rowCells.map((cell) => {
                  const isSelected = selectedCell === cell.cell;
                  const styling = CELL_COLOR_MAP[cell.cell] || CELL_COLOR_MAP.AX;

                  return (
                    <div
                      key={cell.cell}
                      onClick={() => setSelectedCell(cell.cell)}
                      style={{
                        backgroundColor: isSelected ? 'rgba(59, 130, 246, 0.18)' : styling.bg,
                        border: isSelected ? '2px solid #3b82f6' : `1px solid ${styling.border}`,
                        borderRadius: '10px',
                        padding: '1rem',
                        cursor: 'pointer',
                        transition: 'all 0.15s ease',
                        position: 'relative',
                        boxShadow: isSelected ? '0 0 15px rgba(59, 130, 246, 0.25)' : 'none'
                      }}
                    >
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.5rem' }}>
                        <span style={{ fontSize: '1.25rem', fontWeight: 800, color: styling.text }}>
                          {cell.cell}
                        </span>
                        <span
                          style={{
                            fontSize: '0.72rem',
                            fontWeight: 700,
                            padding: '0.15rem 0.5rem',
                            borderRadius: '4px',
                            backgroundColor: 'rgba(255, 255, 255, 0.08)',
                            color: 'var(--text-secondary)'
                          }}
                        >
                          SL: {Math.round((cell.policy?.target_service_level || 0.95) * 100)}%
                        </span>
                      </div>

                      <div style={{ fontSize: '1.15rem', fontWeight: 700, color: 'var(--text-primary)' }}>
                        {cell.sku_count} <span style={{ fontSize: '0.75rem', fontWeight: 400, color: 'var(--text-muted)' }}>SKUs ({cell.sku_percentage}%)</span>
                      </div>

                      <div style={{ fontSize: '0.85rem', fontWeight: 600, color: 'var(--accent-emerald)', marginTop: '0.3rem' }}>
                        ₹{Math.round(cell.annual_consumption_value).toLocaleString()}
                        <span style={{ fontSize: '0.72rem', fontWeight: 400, color: 'var(--text-muted)', marginLeft: '4px' }}>
                          ({cell.value_percentage}%)
                        </span>
                      </div>

                      <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)', marginTop: '0.5rem', lineHeight: 1.2 }}>
                        {cell.policy?.description || `${cell.policy?.review_strategy} · ${cell.policy?.reorder_automation}`}
                      </div>
                    </div>
                  );
                })}
              </React.Fragment>
            );
          })}
        </div>
      </div>

      {/* Cell Drilldown Section */}
      <div
        style={{
          backgroundColor: 'var(--bg-surface)',
          border: '1px solid var(--border-subtle)',
          borderRadius: '12px',
          padding: '1.5rem'
        }}
      >
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '1.2rem', flexWrap: 'wrap', gap: '1rem' }}>
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
              <span
                style={{
                  fontSize: '1.2rem',
                  fontWeight: 800,
                  color: CELL_COLOR_MAP[selectedCell]?.text || '#60a5fa',
                  backgroundColor: CELL_COLOR_MAP[selectedCell]?.bg || 'rgba(59, 130, 246, 0.1)',
                  padding: '0.2rem 0.6rem',
                  borderRadius: '6px'
                }}
              >
                Cell {selectedCell}
              </span>
              <h3 style={{ fontSize: '1.15rem', fontWeight: 600, color: 'var(--text-primary)' }}>
                Active Policy & Classified SKUs ({drilldownData?.total || 0})
              </h3>
            </div>
            <p style={{ color: 'var(--text-muted)', fontSize: '0.84rem', marginTop: '0.3rem' }}>
              {drilldownData?.policy?.description || 'Review strategy and inventory parameters for this cell.'}
            </p>
          </div>

          <div style={{ display: 'flex', gap: '0.6rem' }}>
            <button
              onClick={() => setShowPolicyModal(true)}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '0.4rem',
                backgroundColor: 'rgba(59, 130, 246, 0.15)',
                border: '1px solid rgba(59, 130, 246, 0.3)',
                color: '#60a5fa',
                borderRadius: '8px',
                padding: '0.5rem 1rem',
                fontSize: '0.85rem',
                fontWeight: 600,
                cursor: 'pointer'
              }}
            >
              <Settings2 size={15} /> Tune Policy for {selectedCell}
            </button>
          </div>
        </div>

        {/* Search */}
        <div style={{ position: 'relative', marginBottom: '1rem', maxWidth: '350px' }}>
          <Search size={15} style={{ position: 'absolute', left: '10px', top: '10px', color: 'var(--text-muted)' }} />
          <input
            type="text"
            placeholder="Search by SKU ID, name or brand..."
            value={skuSearch}
            onChange={(e) => setSkuSearch(e.target.value)}
            style={{
              width: '100%',
              padding: '0.5rem 0.8rem 0.5rem 2.1rem',
              backgroundColor: 'var(--bg-surface-elevated)',
              border: '1px solid var(--border-subtle)',
              borderRadius: '8px',
              color: 'var(--text-primary)',
              fontSize: '0.84rem'
            }}
          />
        </div>

        {/* SKUs Table */}
        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.84rem' }}>
            <thead>
              <tr style={{ borderBottom: '1px solid var(--border-subtle)', textAlign: 'left', color: 'var(--text-muted)' }}>
                <th style={{ padding: '0.75rem' }}>SKU ID</th>
                <th style={{ padding: '0.75rem' }}>Product Name</th>
                <th style={{ padding: '0.75rem' }}>Brand / Category</th>
                <th style={{ padding: '0.75rem', textAlign: 'right' }}>Annual Value</th>
                <th style={{ padding: '0.75rem', textAlign: 'right' }}>Mean Daily Demand</th>
                <th style={{ padding: '0.75rem', textAlign: 'right' }}>Std Daily (CV²)</th>
                <th style={{ padding: '0.75rem', textAlign: 'right' }}>Unit Cost</th>
                <th style={{ padding: '0.75rem', textAlign: 'center' }}>Policy Automation</th>
              </tr>
            </thead>
            <tbody>
              {filteredSkus.map((sku) => (
                <tr
                  key={sku.product_id}
                  style={{
                    borderBottom: '1px solid var(--border-subtle)',
                  }}
                >
                  <td style={{ padding: '0.75rem', fontWeight: 600, color: 'var(--accent-primary)' }}>
                    #{sku.product_id}
                  </td>
                  <td style={{ padding: '0.75rem', color: 'var(--text-primary)', fontWeight: 500 }}>
                    {sku.product_name}
                  </td>
                  <td style={{ padding: '0.75rem', color: 'var(--text-secondary)' }}>
                    {sku.brand_name} · <span style={{ color: 'var(--text-muted)' }}>{sku.category}</span>
                  </td>
                  <td style={{ padding: '0.75rem', textAlign: 'right', fontWeight: 700, color: 'var(--accent-emerald)' }}>
                    ₹{Math.round(sku.annual_consumption_value).toLocaleString()}
                  </td>
                  <td style={{ padding: '0.75rem', textAlign: 'right', color: 'var(--text-primary)' }}>
                    {sku.mean_daily_demand.toLocaleString()} / day
                  </td>
                  <td style={{ padding: '0.75rem', textAlign: 'right', color: 'var(--text-secondary)' }}>
                    {sku.std_daily_demand} <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>({sku.cv2})</span>
                  </td>
                  <td style={{ padding: '0.75rem', textAlign: 'right', color: 'var(--accent-cyan)' }}>
                    ₹{sku.unit_cost.toLocaleString()}
                  </td>
                  <td style={{ padding: '0.75rem', textAlign: 'center' }}>
                    <span
                      style={{
                        padding: '0.2rem 0.55rem',
                        borderRadius: '4px',
                        fontSize: '0.72rem',
                        fontWeight: 600,
                        backgroundColor: 'rgba(255, 255, 255, 0.06)',
                        color: 'var(--text-secondary)'
                      }}
                    >
                      {drilldownData?.policy?.reorder_automation || 'AUTOMATED'}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>

          {filteredSkus.length === 0 && !drilldownLoading && (
            <div style={{ textAlign: 'center', padding: '3rem', color: 'var(--text-muted)' }}>
              No SKUs found in Cell {selectedCell} matching the search.
            </div>
          )}
        </div>
      </div>

      {/* Policy Tuning Modal */}
      {showPolicyModal && policyForm && (
        <div
          style={{
            position: 'fixed',
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            backgroundColor: 'rgba(0, 0, 0, 0.75)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 1000,
            padding: '1rem'
          }}
        >
          <div
            style={{
              backgroundColor: 'var(--bg-surface)',
              border: '1px solid var(--border-subtle)',
              borderRadius: '12px',
              padding: '1.5rem',
              width: '100%',
              maxWidth: '520px'
            }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.2rem' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                <Settings2 size={20} color="#3b82f6" />
                <h3 style={{ fontSize: '1.2rem', fontWeight: 700, color: 'var(--text-primary)' }}>
                  Tune Policy: Cell {policyForm.cell}
                </h3>
              </div>
              <button
                onClick={() => setShowPolicyModal(false)}
                style={{ background: 'none', border: 'none', color: 'var(--text-muted)', cursor: 'pointer' }}
              >
                <X size={20} />
              </button>
            </div>

            {/* Target Service Level */}
            <div style={{ marginBottom: '1rem' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '0.4rem' }}>
                <label style={{ fontSize: '0.85rem', fontWeight: 600, color: 'var(--text-secondary)' }}>
                  Target Service Level
                </label>
                <span style={{ fontSize: '0.9rem', fontWeight: 700, color: 'var(--accent-emerald)' }}>
                  {Math.round(policyForm.target_service_level * 100)}%
                </span>
              </div>
              <input
                type="range"
                min="0.50"
                max="0.99"
                step="0.01"
                value={policyForm.target_service_level}
                onChange={(e) => setPolicyForm({ ...policyForm, target_service_level: Number(e.target.value) })}
                style={{ width: '100%', accentColor: 'var(--accent-primary)' }}
              />
            </div>

            {/* Review Strategy */}
            <div style={{ marginBottom: '1rem' }}>
              <label style={{ display: 'block', fontSize: '0.85rem', fontWeight: 600, color: 'var(--text-secondary)', marginBottom: '0.4rem' }}>
                Review Strategy
              </label>
              <select
                value={policyForm.review_strategy}
                onChange={(e) => setPolicyForm({ ...policyForm, review_strategy: e.target.value })}
                style={{
                  width: '100%',
                  padding: '0.55rem',
                  backgroundColor: 'var(--bg-surface-elevated)',
                  border: '1px solid var(--border-subtle)',
                  borderRadius: '6px',
                  color: 'var(--text-primary)'
                }}
              >
                <option value="CONTINUOUS">Continuous Review (Real-time trigger)</option>
                <option value="PERIODIC">Periodic Review (Weekly / Bi-weekly)</option>
                <option value="MIN_MAX">Min/Max Buffer Review</option>
                <option value="MAKE_TO_ORDER">Make to Order / Do Not Stock</option>
              </select>
            </div>

            {/* Reorder Automation */}
            <div style={{ marginBottom: '1rem' }}>
              <label style={{ display: 'block', fontSize: '0.85rem', fontWeight: 600, color: 'var(--text-secondary)', marginBottom: '0.4rem' }}>
                Reorder Automation Rule
              </label>
              <select
                value={policyForm.reorder_automation}
                onChange={(e) => setPolicyForm({ ...policyForm, reorder_automation: e.target.value })}
                style={{
                  width: '100%',
                  padding: '0.55rem',
                  backgroundColor: 'var(--bg-surface-elevated)',
                  border: '1px solid var(--border-subtle)',
                  borderRadius: '6px',
                  color: 'var(--text-primary)'
                }}
              >
                <option value="AUTOMATED">Automated Reorder (Direct draft generation)</option>
                <option value="MANUAL_APPROVAL">Manual Approval Required</option>
                <option value="HUMAN_REVIEW">Strategic Human Review Required</option>
                <option value="DO_NOT_STOCK">Do Not Hold Stock / Delist</option>
              </select>
            </div>

            {/* Description */}
            <div style={{ marginBottom: '1.2rem' }}>
              <label style={{ display: 'block', fontSize: '0.85rem', fontWeight: 600, color: 'var(--text-secondary)', marginBottom: '0.4rem' }}>
                Policy Description & Notes
              </label>
              <textarea
                value={policyForm.description}
                onChange={(e) => setPolicyForm({ ...policyForm, description: e.target.value })}
                rows={2}
                style={{
                  width: '100%',
                  padding: '0.55rem',
                  backgroundColor: 'var(--bg-surface-elevated)',
                  border: '1px solid var(--border-subtle)',
                  borderRadius: '6px',
                  color: 'var(--text-primary)',
                  fontSize: '0.85rem'
                }}
              />
            </div>

            {/* Actions */}
            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.6rem' }}>
              <button
                onClick={() => setShowPolicyModal(false)}
                style={{
                  padding: '0.55rem 1rem',
                  backgroundColor: 'rgba(255, 255, 255, 0.05)',
                  border: '1px solid var(--border-subtle)',
                  borderRadius: '6px',
                  color: 'var(--text-secondary)',
                  cursor: 'pointer'
                }}
              >
                Cancel
              </button>
              <button
                onClick={handleSavePolicy}
                disabled={policySaving}
                style={{
                  padding: '0.55rem 1.2rem',
                  backgroundColor: 'var(--accent-primary)',
                  border: 'none',
                  borderRadius: '6px',
                  color: '#fff',
                  fontWeight: 600,
                  cursor: 'pointer'
                }}
              >
                {policySaving ? 'Saving...' : 'Save Policy Settings'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
