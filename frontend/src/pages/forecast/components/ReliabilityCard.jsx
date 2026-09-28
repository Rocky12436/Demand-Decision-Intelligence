import React from 'react';
import { Award, AlertCircle } from 'lucide-react';

export function ReliabilityCard({ reliability, isTechnicalView }) {
  if (!reliability) return null;

  const championName = reliability.champion_model || reliability.recommended_model || 'Best Method';
  const championWape = reliability.champion_wape;
  const baselineWape = reliability.seasonal_naive_wape;
  const improvementPct = reliability.improvement_pct ?? 0;
  const baselineNotice = reliability.baseline_notice;
  const coverage90 = reliability.coverage_90;

  // Traffic light based on forecast error
  let trafficClass = 'green';
  let trafficLabel = 'Highly Accurate';

  const wapeToCheck = championWape ?? baselineWape;

  if (wapeToCheck !== null && wapeToCheck !== undefined) {
    if (wapeToCheck > 25) {
      trafficClass = 'amber';
      trafficLabel = 'Moderate Error (Higher Variance)';
    } else if (wapeToCheck > 15) {
      trafficClass = 'blue';
      trafficLabel = 'Typical Retail Accuracy';
    }
  }

  // Friendly model name mapping for simple view
  const friendlyModelNames = {
    'MovingAverage_7D': '7-Day Rolling Trend',
    'MovingAverage_30D': '30-Day Rolling Trend',
    'SeasonalNaive': 'Same Weekday Last Week',
    'Naive': 'Recent Demand Baseline',
    'Ridge_LagFeatures': 'Multi-Feature AI Model',
    'Croston_SBA': 'Intermittent Demand Method',
    'Prophet': 'Full Seasonal Prophet Model',
  };
  const displayName = friendlyModelNames[championName] || championName;

  return (
    <div className="forecast-reliability-card">
      <div className="forecast-reliability-header">
        <div>
          <h2 style={{ fontSize: '16px', fontWeight: 700, color: '#0f172a', margin: 0, display: 'flex', alignItems: 'center', flexWrap: 'wrap', gap: '8px' }}>
            <span>How reliable has this forecast been?</span>
            <span className={`forecast-traffic-badge ${trafficClass}`}>
              <span className="traffic-dot" />
              <span>{trafficLabel}</span>
            </span>
          </h2>
          <p style={{ fontSize: '12px', color: '#64748b', marginTop: '4px', margin: 0 }}>
            Tested on historical sales weeks to verify accuracy before predicting the future
          </p>
        </div>

        {isTechnicalView && (
          <div style={{ fontSize: '12px', fontFamily: 'monospace', color: '#64748b', background: '#f8fafc', padding: '4px 8px', borderRadius: '6px', border: '1px solid #e2e8f0' }}>
            Selected: {championName} (raw)
          </div>
        )}
      </div>

      {/* Main explanation sentence */}
      <div className="forecast-reliability-highlight-box">
        {championWape !== null && baselineWape !== null ? (
          <p style={{ margin: 0 }}>
            On past weeks this forecast was off by about{' '}
            <strong style={{ color: '#312e81', fontWeight: 700 }}>{championWape}%</strong> on average. A simple &ldquo;same as last week&rdquo;
            guess was off by <strong style={{ color: '#334155' }}>{baselineWape}%</strong>
            {improvementPct > 0 ? (
              <span>
                , so this method is <strong style={{ color: '#047857', fontWeight: 700 }}>{improvementPct}% better</strong>.
              </span>
            ) : (
              <span>.</span>
            )}
          </p>
        ) : (
          <p style={{ margin: 0 }}>
            {baselineNotice || 'Forecasting models evaluated across chronological test folds.'}
          </p>
        )}

        {baselineNotice && (
          <div style={{ marginTop: '10px', fontSize: '12px', color: '#92400e', background: '#fffbeb', padding: '8px 12px', borderRadius: '6px', border: '1px solid #fde68a', display: 'flex', alignItems: 'flex-start', gap: '8px' }}>
            <AlertCircle style={{ width: '16px', height: '16px', color: '#d97706', flexShrink: 0, marginTop: '2px' }} />
            <span>{baselineNotice}</span>
          </div>
        )}
      </div>

      {/* Visual Bar Comparison */}
      {championWape !== null && baselineWape !== null && (
        <div style={{ paddingTop: '4px' }}>
          <div className="forecast-progress-item">
            <div className="forecast-progress-labels">
              <span style={{ fontWeight: 600, color: '#1e293b', display: 'flex', alignItems: 'center', gap: '6px' }}>
                <Award style={{ width: '15px', height: '15px', color: '#4f46e5' }} />
                <span>Recommended Method ({displayName})</span>
              </span>
              <span style={{ fontWeight: 700, color: '#4338ca' }}>
                {championWape}% average forecast error
              </span>
            </div>
            <div className="forecast-progress-bar-bg">
              <div
                className="forecast-progress-bar-fill fill-champ"
                style={{ width: `${Math.min(100, Math.max(8, championWape * 2))}%` }}
              />
            </div>
          </div>

          <div className="forecast-progress-item">
            <div className="forecast-progress-labels">
              <span style={{ color: '#475569' }}>
                Simple Baseline (&ldquo;Same as last week&rdquo;)
              </span>
              <span style={{ fontWeight: 600, color: '#475569' }}>
                {baselineWape}% average forecast error
              </span>
            </div>
            <div className="forecast-progress-bar-bg">
              <div
                className="forecast-progress-bar-fill fill-baseline"
                style={{ width: `${Math.min(100, Math.max(8, baselineWape * 2))}%` }}
              />
            </div>
          </div>
        </div>
      )}

      {coverage90 !== null && coverage90 !== undefined && (
        <div className="forecast-reliability-footer">
          <span>Range Reliability:</span>
          <span style={{ fontWeight: 600, color: '#1e293b' }}>
            {coverage90}% of past sales fell inside the expected likely range (Target: 90%)
          </span>
        </div>
      )}
    </div>
  );
}
