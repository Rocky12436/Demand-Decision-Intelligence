import React from 'react';
import { AlertCircle, UploadCloud, Info, Clock, AlertTriangle, CheckCircle2, Sliders } from 'lucide-react';
import { useNavigate } from 'react-router-dom';

export function NoticeList({
  skuClassification,
  historicalWarning,
  recommendation,
  onOpenLeadTimeModal,
}) {
  const navigate = useNavigate();
  const notices = [];

  const nObs = skuClassification?.n_obs ?? 0;
  const skuType = skuClassification?.type;

  // 1. History observation threshold notice
  if (nObs > 0 && nObs < 120) {
    notices.push({
      id: 'history_threshold',
      type: 'warning',
      icon: <Clock className="w-4 h-4 text-amber-700 flex-shrink-0 mt-0.5" />,
      title: 'Limited Historical Data',
      text: `This item has ${nObs} days of sales history. Advanced ML models like Prophet require at least 120 days. Uploading more sales records will unlock higher-accuracy seasonal predictions.`,
      actionLabel: 'Upload More Sales Data',
      onAction: () => navigate('/upload'),
    });
  }

  // 2. Intermittent / Sporadic sales notice
  if (skuType === 'intermittent' || skuType === 'lumpy') {
    notices.push({
      id: 'intermittent_demand',
      type: 'info',
      icon: <Info className="w-4 h-4 text-blue-700 flex-shrink-0 mt-0.5" />,
      title: 'Sells Only Some Days',
      text: 'This item experiences zero sales on several days between customer orders. We use specialized sporadic demand calculations to avoid over-ordering.',
    });
  }

  // 3. Simulated vs Configured inventory & lead time notice
  const isSimulated =
    recommendation?.data_source === 'simulated' ||
    recommendation?.assumptions?.some((a) => a.includes('simulated'));

  if (isSimulated) {
    const leadTimeDisplay = recommendation?.lead_time_days || 7;
    notices.push({
      id: 'simulated_inventory',
      type: 'neutral',
      icon: <AlertCircle className="w-4 h-4 text-slate-700 flex-shrink-0 mt-0.5" />,
      title: 'Simulated Order Assumptions',
      text: `Lead time (${leadTimeDisplay} days) and current stock are simulated estimates because supplier delivery times were not uploaded. Use as guidance rather than strict orders.`,
      actionLabel: 'Update Lead Times',
      actionIcon: <Sliders style={{ width: '14px', height: '14px' }} />,
      onAction: onOpenLeadTimeModal ? onOpenLeadTimeModal : () => navigate('/procurement'),
    });
  } else if (recommendation?.data_source === 'configured') {
    const leadTimeDisplay = recommendation?.lead_time_days || 7;
    const stockDisplay =
      recommendation?.current_stock != null
        ? ` and ${Math.round(recommendation.current_stock).toLocaleString()} on-hand units`
        : '';
    notices.push({
      id: 'configured_inventory',
      type: 'success',
      icon: <CheckCircle2 className="w-4 h-4 text-emerald-700 flex-shrink-0 mt-0.5" />,
      title: 'Configured Supplier Parameters Active',
      text: `Calibrated with verified supplier turnaround of ${leadTimeDisplay} days${stockDisplay}. Reorder points and buffer recommendations match your operational contracts.`,
      actionLabel: 'Adjust Parameters',
      actionIcon: <Sliders style={{ width: '14px', height: '14px' }} />,
      onAction: onOpenLeadTimeModal ? onOpenLeadTimeModal : () => navigate('/procurement'),
    });
  }

  // 4. Historical dataset notice (> 90 days behind)
  if (historicalWarning?.is_historical) {
    notices.push({
      id: 'historical_warning',
      type: 'warning',
      icon: <AlertTriangle className="w-4 h-4 text-amber-700 flex-shrink-0 mt-0.5" />,
      title: 'Historical Dataset Notice',
      text: historicalWarning.message || 'Forecast is calculated based on historical reference data rather than a live real-time feed.',
    });
  }

  if (notices.length === 0) return null;

  return (
    <div className="forecast-notices-container">
      {notices.map((n) => {
        return (
          <div
            key={n.id}
            className={`forecast-notice-card ${n.type || 'neutral'}`}
          >
            <div className="forecast-notice-content">
              {n.icon}
              <div>
                <h4 className="forecast-notice-title">
                  {n.title}
                </h4>
                <p className="forecast-notice-desc">
                  {n.text}
                </p>
              </div>
            </div>

            {n.actionLabel && (
              <button
                type="button"
                onClick={n.onAction}
                className="forecast-notice-btn"
              >
                {n.actionIcon || <UploadCloud style={{ width: '14px', height: '14px' }} />}
                <span>{n.actionLabel}</span>
              </button>
            )}
          </div>
        );
      })}
    </div>
  );
}
