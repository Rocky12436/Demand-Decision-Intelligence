import React, { useState, useRef, useEffect } from 'react';
import { RefreshCw, Download, Search, Check, ChevronDown, Sliders } from 'lucide-react';

const HORIZON_OPTIONS = [
  { days: 7, label: 'Next 7 days' },
  { days: 14, label: 'Next 14 days' },
  { days: 30, label: 'Next 30 days' },
];

export function ForecastHeader({
  skus = [],
  selectedSku,
  onSelectSku,
  selectedHorizon,
  onSelectHorizon,
  onRefresh,
  refreshing,
  refreshProgress,
  onDownloadCsv,
  lastUpdated,
  isTechnicalView,
  onToggleView,
}) {
  const [dropdownOpen, setDropdownOpen] = useState(false);
  const [searchTerm, setSearchTerm] = useState('');
  const dropdownRef = useRef(null);

  // Close dropdown on outside click
  useEffect(() => {
    function handleClickOutside(event) {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target)) {
        setDropdownOpen(false);
      }
    }
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const activeProduct = skus.find((s) => String(s.product_id) === String(selectedSku));

  const filteredSkus = skus.filter((item) => {
    if (!searchTerm.trim()) return true;
    const term = searchTerm.toLowerCase();
    const nameMatch = (item.name || '').toLowerCase().includes(term);
    const catMatch = (item.category || '').toLowerCase().includes(term);
    const idMatch = (item.product_id || '').toLowerCase().includes(term);
    return nameMatch || catMatch || idMatch;
  });

  return (
    <div className="forecast-header-card">
      <div className="forecast-header-top">
        {/* Title & View Toggle */}
        <div className="forecast-title-group">
          <div className="forecast-title-row">
            <h1 className="forecast-title">Demand Forecasting Studio</h1>
            <button
              type="button"
              onClick={onToggleView}
              aria-label="Toggle technical view"
              className={`forecast-view-toggle ${isTechnicalView ? 'technical-mode' : 'business-mode'}`}
            >
              <Sliders style={{ width: '14px', height: '14px' }} />
              <span>{isTechnicalView ? 'Technical View (Active)' : 'Switch to Technical View'}</span>
            </button>
          </div>
          <p className="forecast-subtitle">
            Accurate, traceable sales predictions for smart inventory restocking
            {lastUpdated && <span className="forecast-update-stamp">• Updated {lastUpdated}</span>}
          </p>
        </div>

        {/* Action Buttons: Refresh & CSV */}
        <div className="forecast-actions-group">
          <button
            type="button"
            onClick={onRefresh}
            disabled={refreshing || !selectedSku}
            className="forecast-btn"
            title="Recalculate models with latest historical sales"
          >
            <RefreshCw className={refreshing ? 'forecast-btn-spin' : ''} style={{ width: '15px', height: '15px' }} />
            <span>{refreshing ? (refreshProgress || 'Computing...') : 'Refresh forecast'}</span>
          </button>

          <button
            type="button"
            onClick={onDownloadCsv}
            disabled={!selectedSku}
            className="forecast-btn"
            title="Export daily forecast predictions as CSV"
          >
            <Download style={{ width: '15px', height: '15px' }} />
            <span>Download CSV</span>
          </button>
        </div>
      </div>

      <div className="forecast-filter-row">
        {/* Searchable Product Picker */}
        <div className="forecast-picker-container" ref={dropdownRef}>
          <label className="forecast-control-label">
            Select Product / Item
          </label>
          <button
            type="button"
            onClick={() => setDropdownOpen(!dropdownOpen)}
            className="forecast-picker-trigger"
            aria-expanded={dropdownOpen}
            aria-haspopup="listbox"
          >
            <div className="forecast-picker-text-wrap">
              {activeProduct ? (
                <div>
                  <span className="forecast-picker-product-name">{activeProduct.name}</span>
                  <span className="forecast-picker-category-tag">{activeProduct.category}</span>
                  <span className="forecast-picker-sku-code">SKU: {activeProduct.product_id}</span>
                </div>
              ) : (
                <span style={{ color: '#94a3b8' }}>Choose a product to forecast...</span>
              )}
            </div>
            <ChevronDown
              style={{
                width: '16px',
                height: '16px',
                color: '#64748b',
                transition: 'transform 0.2s',
                transform: dropdownOpen ? 'rotate(180deg)' : 'none',
              }}
            />
          </button>

          {dropdownOpen && (
            <div className="forecast-dropdown-menu">
              <div className="forecast-dropdown-search-box">
                <Search className="forecast-dropdown-search-icon" style={{ width: '15px', height: '15px' }} />
                <input
                  type="text"
                  placeholder="Search by product name, category, or SKU..."
                  value={searchTerm}
                  onChange={(e) => setSearchTerm(e.target.value)}
                  className="forecast-dropdown-search-input"
                  autoFocus
                />
              </div>
              <div className="forecast-dropdown-list" role="listbox">
                {filteredSkus.length === 0 ? (
                  <div style={{ padding: '16px', textAlign: 'center', fontSize: '13px', color: '#94a3b8' }}>
                    No matching products found
                  </div>
                ) : (
                  filteredSkus.map((item) => {
                    const isSelected = String(item.product_id) === String(selectedSku);
                    return (
                      <button
                        key={item.product_id}
                        type="button"
                        onClick={() => {
                          onSelectSku(item.product_id);
                          setDropdownOpen(false);
                          setSearchTerm('');
                        }}
                        className={`forecast-dropdown-item ${isSelected ? 'selected' : ''}`}
                        role="option"
                        aria-selected={isSelected}
                      >
                        <div>
                          <div className="forecast-dropdown-item-title">{item.name}</div>
                          <div className="forecast-dropdown-item-meta">
                            <span style={{ background: '#f1f5f9', padding: '1px 5px', borderRadius: '3px' }}>
                              {item.category}
                            </span>
                            <span>•</span>
                            <span style={{ fontFamily: 'monospace' }}>SKU #{item.product_id}</span>
                            {item.unit && <span>({item.unit})</span>}
                          </div>
                        </div>
                        {isSelected && <Check style={{ width: '16px', height: '16px', color: '#4f46e5' }} />}
                      </button>
                    );
                  })
                )}
              </div>
            </div>
          )}
        </div>

        {/* Horizon Selector */}
        <div>
          <label className="forecast-control-label">
            Forecast Horizon
          </label>
          <div className="forecast-horizon-group" role="group">
            {HORIZON_OPTIONS.map((opt) => {
              const isSelected = Number(selectedHorizon) === opt.days;
              return (
                <button
                  key={opt.days}
                  type="button"
                  onClick={() => onSelectHorizon(opt.days)}
                  className={`forecast-horizon-btn ${isSelected ? 'active' : ''}`}
                  aria-pressed={isSelected}
                >
                  {opt.label}
                </button>
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
}
