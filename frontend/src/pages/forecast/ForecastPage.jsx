import React, { useState } from 'react';
import { PageShell } from '../../components/ui';
import {
  useForecastSummary,
  ForecastHeader,
  AnswerCards,
  ForecastChart,
  ReliabilityCard,
  NoticeList,
  TechnicalPanel,
} from './components';
import { AlertCircle, RefreshCw, Package } from 'lucide-react';
import './forecast.css';

export default function ForecastPage() {
  const [isTechnicalView, setIsTechnicalView] = useState(false);

  const {
    data,
    loading,
    refreshing,
    refreshProgress,
    error,
    retry,
    skus,
    selectedSku,
    setSelectedSku,
    selectedHorizon,
    setSelectedHorizon,
    refreshForecast,
    lastUpdated,
  } = useForecastSummary();

  // CSV Exporter
  const handleDownloadCsv = () => {
    if (!data?.daily || data.daily.length === 0) return;

    const headers = ['Date', 'Day_of_Week', 'Expected_Demand_Units', 'Likely_Low_Units', 'Likely_High_Units', 'Is_Festival'];
    const rows = data.daily.map((d) => {
      const [year, month, day] = d.date.split('-');
      const dateObj = new Date(Number(year), Number(month) - 1, Number(day));
      const weekday = dateObj.toLocaleDateString('en-US', { weekday: 'short' });
      return [
        d.date,
        weekday,
        d.q50 ?? d.yhat ?? 0,
        d.q05 ?? d.q25 ?? 0,
        d.q95 ?? d.q75 ?? 0,
        d.is_festival ? 'Yes' : 'No',
      ].join(',');
    });

    const csvContent = [headers.join(','), ...rows].join('\n');
    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.setAttribute('href', url);
    link.setAttribute(
      'download',
      `forecast_${data.sku?.product_id || selectedSku}_${selectedHorizon}days_${new Date().toISOString().slice(0, 10)}.csv`
    );
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  return (
    <PageShell maxWidth="1320px">
      <div className="forecast-studio-container">
        {/* Header Controls */}
        <ForecastHeader
          skus={skus}
          selectedSku={selectedSku}
          onSelectSku={setSelectedSku}
          selectedHorizon={selectedHorizon}
          onSelectHorizon={setSelectedHorizon}
          onRefresh={refreshForecast}
          refreshing={refreshing}
          refreshProgress={refreshProgress}
          onDownloadCsv={handleDownloadCsv}
          lastUpdated={lastUpdated}
          isTechnicalView={isTechnicalView}
          onToggleView={() => setIsTechnicalView((prev) => !prev)}
        />

        {/* Loading State / Skeleton */}
        {loading && (
          <div>
            <div className="forecast-skeleton-grid">
              {[1, 2, 3].map((i) => (
                <div key={i} className="forecast-skeleton-box" />
              ))}
            </div>
            <div className="forecast-skeleton-box" style={{ height: '360px', marginBottom: '24px' }} />
            <div className="forecast-skeleton-box" style={{ height: '140px' }} />
          </div>
        )}

        {/* Error State with Retry Button */}
        {!loading && error && (
          <div className="forecast-error-box">
            <div style={{ display: 'inline-flex', padding: '10px', background: '#ffe4e6', borderRadius: '50%', color: '#e11d48', marginBottom: '12px' }}>
              <AlertCircle style={{ width: '28px', height: '28px' }} />
            </div>
            <h3 style={{ fontSize: '18px', fontWeight: 700, color: '#881337', marginBottom: '6px' }}>
              Unable to load forecast
            </h3>
            <p style={{ fontSize: '13px', color: '#be123c', maxWidth: '400px', margin: '0 auto 16px', lineHeight: 1.5 }}>
              {error}
            </p>
            <button
              type="button"
              onClick={retry}
              className="forecast-btn"
              style={{ background: '#e11d48', color: '#ffffff', borderColor: '#be123c', margin: '0 auto' }}
            >
              <RefreshCw style={{ width: '15px', height: '15px' }} />
              <span>Retry Calculation</span>
            </button>
          </div>
        )}

        {/* Meaningful Empty State */}
        {!loading && !error && (!data || !selectedSku) && (
          <div className="forecast-empty-box">
            <div style={{ display: 'inline-flex', padding: '12px', background: '#f1f5f9', borderRadius: '50%', color: '#64748b', marginBottom: '12px' }}>
              <Package style={{ width: '28px', height: '28px' }} />
            </div>
            <h3 style={{ fontSize: '16px', fontWeight: 700, color: '#0f172a', marginBottom: '4px' }}>
              No product selected
            </h3>
            <p style={{ fontSize: '13px', color: '#64748b', maxWidth: '360px', margin: '0 auto' }}>
              Choose an item from the product selector above to view its sales history and demand forecast.
            </p>
          </div>
        )}

        {/* Main Content */}
        {!loading && !error && data && (
          <div>
            {/* 1. Answer Cards (Simple First) */}
            <AnswerCards
              headline={data.headline}
              recommendation={data.recommendation}
              horizonDays={data.horizon_days}
              isTechnicalView={isTechnicalView}
            />

            {/* 2. One Main Chart */}
            <ForecastChart
              history={data.history}
              daily={data.daily}
              isTechnicalView={isTechnicalView}
            />

            {/* 3. Reliability Card */}
            <ReliabilityCard
              reliability={data.reliability}
              isTechnicalView={isTechnicalView}
            />

            {/* 4. Relevant Notices */}
            <NoticeList
              skuClassification={data.sku_classification}
              historicalWarning={data.historical_warning}
              recommendation={data.recommendation}
              models={data.models}
            />

            {/* 5. Technical View (On Demand) */}
            {isTechnicalView && (
              <TechnicalPanel
                models={data.models}
                reliability={data.reliability}
                recommendation={data.recommendation}
                skuClassification={data.sku_classification}
                dataVersion={data.data_version}
                computedAt={data.computed_at}
              />
            )}
          </div>
        )}
      </div>
    </PageShell>
  );
}
