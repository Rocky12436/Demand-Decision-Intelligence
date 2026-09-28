import React from 'react';
import { Layers, HelpCircle, Check, AlertCircle } from 'lucide-react';

const GLOSSARY = {
  WAPE: 'Weighted Absolute Percentage Error: Sum of absolute errors divided by total actual demand. Lower is better. 0% is perfect.',
  MAE: 'Mean Absolute Error: The average absolute magnitude of the errors in units. Lower is better.',
  RMSE: 'Root Mean Squared Error: Penalizes large outlier errors more heavily than small ones.',
  Bias: 'Signed Error: Positive means the model consistently over-forecasts; negative means under-forecasting.',
  Coverage: 'Empirical coverage: The percentage of actual holdout data points that fell inside the prediction interval.',
  'ADI / CV²': 'Average Demand Interval & Coefficient of Variation: Classifies whether SKU is smooth, intermittent, or lumpy.',
  'Data Version': 'Unique SHA-256 fingerprint representing the exact historical dataset and as-of cutoff date used.',
};

export function TechnicalPanel({
  models = [],
  reliability = {},
  recommendation = {},
  skuClassification = {},
  dataVersion = '',
  computedAt = '',
}) {

  const championRaw = reliability?.champion_model_raw;
  const coverage50 = reliability?.coverage_50;
  const coverage90 = reliability?.coverage_90;
  const foldsUsed = reliability?.folds_used;

  return (
    <div className="forecast-tech-panel">
      {/* Header */}
      <div className="forecast-tech-header">
        <div className="forecast-tech-title">
          <Layers style={{ width: '20px', height: '20px', color: '#818cf8' }} />
          <span>Technical Forecasting Engine & Audit Trail</span>
        </div>
        <div style={{ fontSize: '11px', color: '#94a3b8', fontFamily: 'monospace' }}>
          Computed at: {computedAt ? new Date(computedAt).toLocaleString() : 'N/A'}
        </div>
      </div>

      {/* Glossary Bar */}
      <div className="forecast-tech-glossary-box">
        <div style={{ fontWeight: 600, color: '#e2e8f0', marginBottom: '6px', display: 'flex', alignItems: 'center', gap: '6px' }}>
          <HelpCircle style={{ width: '14px', height: '14px', color: '#818cf8' }} />
          <span>Metric Glossary & Definitions:</span>
        </div>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px' }}>
          {Object.entries(GLOSSARY).map(([term, desc]) => (
            <div key={term} className="glossary-item">
              <span className="glossary-item-term">{term}</span>
              <div className="glossary-item-popup">
                <strong style={{ color: '#ffffff', display: 'block', marginBottom: '4px' }}>{term}</strong>
                <span>{desc}</span>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Model Leaderboard Table */}
      <div>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '10px' }}>
          <h4 style={{ fontSize: '13px', fontWeight: 600, color: '#f1f5f9', margin: 0 }}>
            Model Backtest Leaderboard (Chronological Walk-Forward Folds)
          </h4>
          <span style={{ fontSize: '11px', color: '#94a3b8' }}>
            Champion requires lowest WAPE & beats Seasonal Naive baseline by &ge; 5%
          </span>
        </div>

        <div className="forecast-tech-table-wrap">
          <table className="forecast-tech-table">
            <thead>
              <tr>
                <th>Model Candidate</th>
                <th>Status</th>
                <th style={{ textAlign: 'right' }}>WAPE (%)</th>
                <th style={{ textAlign: 'right' }}>MAE</th>
                <th style={{ textAlign: 'right' }}>RMSE</th>
                <th style={{ textAlign: 'right' }}>Bias (Signed)</th>
                <th style={{ textAlign: 'right' }}>vs Seasonal Naive</th>
              </tr>
            </thead>
            <tbody>
              {models.map((m) => {
                const isChamp = m.is_champion || m.name === championRaw;
                const isSkipped = m.status === 'skipped';
                const isFailed = m.status === 'failed';

                return (
                  <tr key={m.name} className={isChamp ? 'champion-row' : ''}>
                    <td style={{ fontFamily: 'monospace' }}>
                      <span>{m.name}</span>
                      {isChamp && <span className="champion-tag">Champion</span>}
                    </td>
                    <td>
                      {isSkipped ? (
                        <span className="status-chip-skipped" title={m.skip_reason}>
                          <AlertCircle style={{ width: '13px', height: '13px' }} />
                          <span>Skipped</span>
                        </span>
                      ) : isFailed ? (
                        <span style={{ color: '#fb7185', fontSize: '11px' }}>Failed</span>
                      ) : (
                        <span className="status-chip-evaluated">
                          <Check style={{ width: '13px', height: '13px' }} />
                          <span>Evaluated</span>
                        </span>
                      )}
                    </td>
                    <td style={{ textAlign: 'right', fontFamily: 'monospace', color: '#ffffff' }}>
                      {m.wape !== null && m.wape !== undefined ? `${m.wape.toFixed(1)}%` : '—'}
                    </td>
                    <td style={{ textAlign: 'right', fontFamily: 'monospace', color: '#cbd5e1' }}>
                      {m.mae !== null && m.mae !== undefined ? m.mae.toFixed(2) : '—'}
                    </td>
                    <td style={{ textAlign: 'right', fontFamily: 'monospace', color: '#cbd5e1' }}>
                      {m.rmse !== null && m.rmse !== undefined ? m.rmse.toFixed(2) : '—'}
                    </td>
                    <td style={{ textAlign: 'right', fontFamily: 'monospace' }}>
                      {m.bias !== null && m.bias !== undefined ? (
                        <span style={{ color: m.bias > 0 ? '#fcd34d' : '#7dd3fc' }}>
                          {m.bias > 0 ? `+${m.bias.toFixed(2)}` : m.bias.toFixed(2)}
                        </span>
                      ) : (
                        '—'
                      )}
                    </td>
                    <td style={{ textAlign: 'right', fontFamily: 'monospace' }}>
                      {m.improvement_vs_naive_pct !== null && m.improvement_vs_naive_pct !== undefined ? (
                        <span style={{ color: m.improvement_vs_naive_pct > 0 ? '#34d399' : '#94a3b8', fontWeight: m.improvement_vs_naive_pct > 0 ? 700 : 400 }}>
                          {m.improvement_vs_naive_pct > 0 ? `+${m.improvement_vs_naive_pct}%` : `${m.improvement_vs_naive_pct}%`}
                        </span>
                      ) : (
                        '—'
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>

        {/* Skipped Models Detailed Audit */}
        {models.some((m) => m.status === 'skipped') && (
          <div style={{ marginTop: '10px', background: '#020617', padding: '12px 16px', borderRadius: '8px', border: '1px solid #1e293b', fontSize: '12px' }}>
            <span style={{ fontWeight: 600, color: '#e2e8f0', display: 'block', marginBottom: '4px' }}>
              Eligibility & Exclusion Audit:
            </span>
            <ul style={{ margin: 0, paddingLeft: '18px', color: '#94a3b8' }}>
              {models
                .filter((m) => m.status === 'skipped')
                .map((m) => (
                  <li key={m.name} style={{ marginBottom: '2px' }}>
                    <strong style={{ color: '#e2e8f0' }}>{m.name}:</strong> {m.skip_reason}
                  </li>
                ))}
            </ul>
          </div>
        )}
      </div>

      {/* Grid: Interval Calibration & Inventory Parameters */}
      <div className="forecast-tech-subgrid">
        {/* Interval Coverage & Calibration */}
        <div className="forecast-tech-subcard">
          <div className="forecast-tech-subcard-title">
            Prediction Interval Holdout Calibration
          </div>
          <div>
            <div className="forecast-tech-row">
              <span style={{ color: '#94a3b8' }}>90% Range Empirical Coverage:</span>
              <span style={{ fontFamily: 'monospace', fontWeight: 600, color: '#34d399' }}>
                {coverage90 !== null && coverage90 !== undefined ? `${coverage90}%` : 'N/A'} (Target: 90%)
              </span>
            </div>
            <div className="forecast-tech-row">
              <span style={{ color: '#94a3b8' }}>50% Range Empirical Coverage:</span>
              <span style={{ fontFamily: 'monospace', fontWeight: 600, color: '#38bdf8' }}>
                {coverage50 !== null && coverage50 !== undefined ? `${coverage50}%` : 'N/A'} (Target: 50%)
              </span>
            </div>
            <div className="forecast-tech-row">
              <span style={{ color: '#94a3b8' }}>Walk-Forward Folds Evaluated:</span>
              <span style={{ fontFamily: 'monospace', color: '#e2e8f0' }}>{foldsUsed ?? 0} folds</span>
            </div>
            <div className="forecast-tech-row">
              <span style={{ color: '#94a3b8' }}>SKU Classification (ADI / CV²):</span>
              <span style={{ fontFamily: 'monospace', color: '#e2e8f0' }}>
                {skuClassification?.type} (ADI: {skuClassification?.adi}, CV²: {skuClassification?.cv2})
              </span>
            </div>
          </div>
        </div>

        {/* Inventory Parameters & Assumptions */}
        <div className="forecast-tech-subcard">
          <div className="forecast-tech-subcard-title">
            Inventory Recommendation Parameters
          </div>
          <div>
            <div className="forecast-tech-row">
              <span style={{ color: '#94a3b8' }}>Target Service Level:</span>
              <span style={{ fontFamily: 'monospace', color: '#e2e8f0' }}>
                {recommendation?.service_level ? `${recommendation.service_level * 100}%` : '95%'}
              </span>
            </div>
            <div className="forecast-tech-row">
              <span style={{ color: '#94a3b8' }}>Lead Time Used:</span>
              <span style={{ fontFamily: 'monospace', color: '#e2e8f0' }}>
                {recommendation?.lead_time_days ?? 7} days ({recommendation?.data_source || 'simulated'})
              </span>
            </div>
            <div className="forecast-tech-row">
              <span style={{ color: '#94a3b8' }}>Reorder Point (ROP):</span>
              <span style={{ fontFamily: 'monospace', color: '#a5b4fc', fontWeight: 600 }}>
                {recommendation?.reorder_point ?? '—'} units
              </span>
            </div>
            <div className="forecast-tech-row">
              <span style={{ color: '#94a3b8' }}>Safety Stock (Buffer):</span>
              <span style={{ fontFamily: 'monospace', color: '#a5b4fc', fontWeight: 600 }}>
                {recommendation?.safety_stock ?? '—'} units
              </span>
            </div>
          </div>
        </div>
      </div>

      {/* Footer Fingerprint */}
      <div className="forecast-tech-footer">
        <div>
          Data Version Fingerprint: <span style={{ color: '#e2e8f0' }}>{dataVersion || 'N/A'}</span>
        </div>
        <div>Direct Multi-Horizon Step Quantiles • No In-Sample Leakage</div>
      </div>
    </div>
  );
}
