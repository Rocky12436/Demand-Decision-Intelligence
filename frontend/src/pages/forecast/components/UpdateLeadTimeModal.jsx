import React, { useState, useEffect } from 'react';
import {
  X,
  Clock,
  Package,
  Truck,
  ShieldCheck,
  CheckCircle2,
  AlertCircle,
  Loader2,
  ArrowRight,
  Sparkles,
} from 'lucide-react';

export function UpdateLeadTimeModal({
  isOpen,
  onClose,
  sku,
  skuName,
  currentLeadTime = 7,
  currentStock = null,
  isConfigured = false,
  onSuccess,
}) {
  const [leadTimeDays, setLeadTimeDays] = useState(currentLeadTime || 7);
  const [stockLevel, setStockLevel] = useState(currentStock !== null ? currentStock : '');
  const [supplierName, setSupplierName] = useState('Primary Wholesale Distributor');
  const [serviceLevel, setServiceLevel] = useState(95);
  const [loading, setLoading] = useState(false);
  const [fetchLoading, setFetchLoading] = useState(false);
  const [error, setError] = useState(null);
  const [successMsg, setSuccessMsg] = useState(null);

  // Quick preset days
  const PRESETS = [
    { label: '3d (Express/Local)', value: 3 },
    { label: '7d (Standard Domestic)', value: 7 },
    { label: '14d (Regional Warehouse)', value: 14 },
    { label: '21d (Factory Direct)', value: 21 },
    { label: '30d (Import/Sea)', value: 30 },
  ];

  // Load existing parameters on open
  useEffect(() => {
    if (!isOpen || !sku) return;

    setError(null);
    setSuccessMsg(null);
    setFetchLoading(true);

    fetch(`/api/forecast/lead-time?sku=${encodeURIComponent(sku)}`)
      .then((res) => (res.ok ? res.json() : null))
      .then((data) => {
        if (data) {
          setLeadTimeDays(data.lead_time_days || 7);
          if (data.current_stock !== null && data.current_stock !== undefined) {
            setStockLevel(data.current_stock);
          } else {
            setStockLevel('');
          }
          if (data.supplier_name) {
            setSupplierName(data.supplier_name);
          }
          if (data.service_level) {
            setServiceLevel(Math.round(data.service_level * 100));
          }
        }
      })
      .catch((err) => {
        console.warn('Could not prefill lead time settings:', err);
      })
      .finally(() => {
        setFetchLoading(false);
      });
  }, [isOpen, sku]);

  if (!isOpen) return null;

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    setError(null);
    setSuccessMsg(null);

    const parsedStock = stockLevel === '' || stockLevel === null ? null : parseFloat(stockLevel);

    try {
      const res = await fetch('/api/forecast/lead-time', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          product_id: String(sku),
          lead_time_days: parseInt(leadTimeDays, 10),
          current_stock: parsedStock,
          supplier_name: supplierName.trim() || 'Primary Wholesale Distributor',
          service_level: serviceLevel / 100,
        }),
      });

      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || 'Failed to update lead time parameters');
      }

      setSuccessMsg('Lead time and inventory parameters updated successfully.');
      setTimeout(() => {
        if (onSuccess) {
          onSuccess(data);
        }
        onClose();
      }, 700);
    } catch (err) {
      setError(err.message || 'Error saving parameters');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="lead-time-modal-backdrop" onClick={onClose}>
      <div
        className="lead-time-modal-card"
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
      >
        {/* Header */}
        <div className="lead-time-modal-header">
          <div>
            <div className="lead-time-modal-badge">
              <Clock style={{ width: '13px', height: '13px' }} />
              <span>Supply Chain Calibration</span>
            </div>
            <h3 className="lead-time-modal-title">
              Configure Supplier Lead Time & Stock
            </h3>
            <p className="lead-time-modal-subtitle">
              SKU: <span className="lead-time-sku-code">{sku}</span>
              {skuName && ` — ${skuName}`}
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="lead-time-modal-close-btn"
            aria-label="Close modal"
          >
            <X style={{ width: '18px', height: '18px' }} />
          </button>
        </div>

        {/* Informational callout */}
        <div className="lead-time-callout">
          <div className="lead-time-callout-icon">
            <Sparkles style={{ width: '16px', height: '16px', color: '#4f46e5' }} />
          </div>
          <div className="lead-time-callout-text">
            Setting your actual supplier delivery turnaround eliminates simulated assumptions and
            recalculates <strong>Safety Stock</strong> and <strong>Reorder Points</strong> to reflect your real contracts.
          </div>
        </div>

        {fetchLoading ? (
          <div className="lead-time-loading-state">
            <Loader2 className="animate-spin" style={{ width: '28px', height: '28px', color: '#4f46e5' }} />
            <p>Loading active supply-chain parameters...</p>
          </div>
        ) : (
          <form onSubmit={handleSubmit} className="lead-time-modal-form">
            {error && (
              <div className="lead-time-alert error">
                <AlertCircle style={{ width: '16px', height: '16px', flexShrink: 0 }} />
                <span>{error}</span>
              </div>
            )}

            {successMsg && (
              <div className="lead-time-alert success">
                <CheckCircle2 style={{ width: '16px', height: '16px', flexShrink: 0 }} />
                <span>{successMsg}</span>
              </div>
            )}

            {/* 1. Supplier Turnaround / Lead Time */}
            <div className="lead-time-form-group">
              <div className="lead-time-form-label-row">
                <label className="lead-time-label">
                  <Truck style={{ width: '14px', height: '14px', color: '#4f46e5' }} />
                  <span>Supplier Turnaround / Delivery Lead Time</span>
                </label>
                <div className="lead-time-value-pill">
                  {leadTimeDays} {leadTimeDays === 1 ? 'day' : 'days'}
                </div>
              </div>

              {/* Quick Pick Presets */}
              <div className="lead-time-presets-grid">
                {PRESETS.map((p) => {
                  const isActive = parseInt(leadTimeDays, 10) === p.value;
                  return (
                    <button
                      key={p.value}
                      type="button"
                      onClick={() => setLeadTimeDays(p.value)}
                      className={`lead-time-preset-btn ${isActive ? 'active' : ''}`}
                    >
                      {p.label}
                    </button>
                  );
                })}
              </div>

              {/* Slider & Number Input */}
              <div className="lead-time-slider-row">
                <input
                  type="range"
                  min="1"
                  max="90"
                  value={leadTimeDays}
                  onChange={(e) => setLeadTimeDays(parseInt(e.target.value, 10) || 1)}
                  className="lead-time-range-slider"
                />
                <div className="lead-time-number-input-wrap">
                  <input
                    type="number"
                    min="1"
                    max="180"
                    value={leadTimeDays}
                    onChange={(e) => setLeadTimeDays(Math.max(1, parseInt(e.target.value, 10) || 1))}
                    className="lead-time-number-input"
                  />
                  <span className="lead-time-input-unit">days</span>
                </div>
              </div>
            </div>

            {/* 2. Current Stock On-Hand */}
            <div className="lead-time-form-group">
              <div className="lead-time-form-label-row">
                <label className="lead-time-label">
                  <Package style={{ width: '14px', height: '14px', color: '#059669' }} />
                  <span>Current On-Hand Warehouse Stock</span>
                </label>
                <span className="lead-time-subtext">Optional — leave blank for demand-only mode</span>
              </div>
              <div className="lead-time-stock-input-wrap">
                <input
                  type="number"
                  min="0"
                  step="any"
                  placeholder="e.g. 150 (verified inventory units)"
                  value={stockLevel}
                  onChange={(e) => setStockLevel(e.target.value)}
                  className="lead-time-stock-input"
                />
                <span className="lead-time-input-unit">units</span>
              </div>
            </div>

            {/* 3. Supplier Name & Service Level */}
            <div className="lead-time-two-col">
              <div className="lead-time-form-group">
                <label className="lead-time-label">
                  <span>Vendor / Supplier Name</span>
                </label>
                <input
                  type="text"
                  value={supplierName}
                  onChange={(e) => setSupplierName(e.target.value)}
                  placeholder="e.g. Apex Logistics, Global Foods Ltd"
                  className="lead-time-text-input"
                />
              </div>

              <div className="lead-time-form-group">
                <div className="lead-time-form-label-row">
                  <label className="lead-time-label">
                    <ShieldCheck style={{ width: '14px', height: '14px', color: '#0284c7' }} />
                    <span>Target Service Level</span>
                  </label>
                  <span className="lead-time-value-pill blue">{serviceLevel}%</span>
                </div>
                <div className="lead-time-service-pills">
                  {[90, 95, 98, 99].map((lvl) => (
                    <button
                      key={lvl}
                      type="button"
                      onClick={() => setServiceLevel(lvl)}
                      className={`lead-time-service-btn ${serviceLevel === lvl ? 'active' : ''}`}
                    >
                      {lvl}%
                    </button>
                  ))}
                </div>
              </div>
            </div>

            {/* Impact Calculation Preview */}
            <div className="lead-time-impact-card">
              <div className="lead-time-impact-header">
                <strong>Projected Impact:</strong>
              </div>
              <div className="lead-time-impact-stats">
                <div className="lead-time-impact-stat">
                  <span className="lead-time-impact-label">Lead Time Setting</span>
                  <div className="lead-time-impact-val">
                    <span className="strike">{currentLeadTime || 7}d</span>
                    <ArrowRight style={{ width: '12px', height: '12px', color: '#94a3b8' }} />
                    <span className="bold highlight">{leadTimeDays} days</span>
                  </div>
                </div>
                <div className="lead-time-impact-stat">
                  <span className="lead-time-impact-label">Data Status</span>
                  <div className="lead-time-impact-val">
                    <span className="lead-time-status-tag verified">
                      <CheckCircle2 style={{ width: '12px', height: '12px' }} />
                      Verified SLA
                    </span>
                  </div>
                </div>
                <div className="lead-time-impact-stat">
                  <span className="lead-time-impact-label">Notice Banner</span>
                  <div className="lead-time-impact-val">
                    <span className="lead-time-status-tag resolved">
                      Simulation warning resolved
                    </span>
                  </div>
                </div>
              </div>
            </div>

            {/* Footer Buttons */}
            <div className="lead-time-modal-footer">
              <button
                type="button"
                onClick={onClose}
                className="lead-time-btn-secondary"
                disabled={loading}
              >
                Cancel
              </button>
              <button
                type="submit"
                className="lead-time-btn-primary"
                disabled={loading}
              >
                {loading ? (
                  <>
                    <Loader2 className="animate-spin" style={{ width: '14px', height: '14px' }} />
                    <span>Calibrating & Saving...</span>
                  </>
                ) : (
                  <>
                    <CheckCircle2 style={{ width: '15px', height: '15px' }} />
                    <span>Save & Recalculate Recommendation</span>
                  </>
                )}
              </button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
}
