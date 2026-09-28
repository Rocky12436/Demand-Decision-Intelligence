import React from 'react';
import { ShoppingCart, TrendingUp, ShieldCheck } from 'lucide-react';

export function AnswerCards({ headline, recommendation, horizonDays, isTechnicalView }) {
  if (!headline) return null;

  const expectedUnits = Math.round(headline.expected_units ?? 0);
  const likelyLow = Math.round(headline.likely_low ?? 0);
  const likelyHigh = Math.round(headline.likely_high ?? 0);

  const confidence = (headline.confidence || 'MEDIUM').toUpperCase();
  const reasons = headline.confidence_reasons || [];
  const primaryReason = reasons[0]?.text || `Based on historical sales patterns across the past ${horizonDays} days.`;

  const suggestQty = Math.round(recommendation?.suggest_order_qty ?? 0);
  const reorderPoint = Math.round(recommendation?.reorder_point ?? 0);
  const safetyStock = Math.round(recommendation?.safety_stock ?? 0);
  const stockoutRisk = (recommendation?.stockout_risk || 'LOW').toUpperCase();

  // Confidence styling
  const confidenceStyles = {
    HIGH: {
      bg: 'bg-emerald-50 text-emerald-800 border-emerald-300',
      badge: 'bg-emerald-600 text-white',
      desc: 'High confidence — strong consistency and ample sales history.',
    },
    MEDIUM: {
      bg: 'bg-amber-50 text-amber-900 border-amber-300',
      badge: 'bg-amber-600 text-white',
      desc: 'Medium confidence — reasonable historical depth with normal variation.',
    },
    LOW: {
      bg: 'bg-slate-100 text-slate-800 border-slate-300',
      badge: 'bg-slate-700 text-white',
      desc: 'Low confidence — limited history or sporadic demand.',
    },
  }[confidence] || {
    bg: 'bg-slate-50 text-slate-800 border-slate-200',
    badge: 'bg-slate-600 text-white',
    desc: 'Moderate confidence estimate.',
  };

  // Suggested action copy
  let actionTitle = 'Stock is in good standing';
  let actionDetail = 'You currently have sufficient inventory to cover anticipated demand for this period.';

  if (suggestQty > 0) {
    actionTitle = `Order about ${suggestQty.toLocaleString()} units`;
    actionDetail = `Place order soon to prevent stockout. Recommended order trigger when stock drops to ${reorderPoint.toLocaleString()} units.`;
  }

  const confidenceClass = confidence.toLowerCase();

  return (
    <div className="forecast-cards-grid">
      {/* 1. Expected Sales */}
      <div className="forecast-answer-card">
        <div>
          <div className="forecast-card-header">
            <span className="forecast-card-label">Expected Demand</span>
            <div className="forecast-icon-circle indigo">
              <TrendingUp style={{ width: '16px', height: '16px' }} />
            </div>
          </div>

          <div className="forecast-card-subhead">
            You will likely sell about
          </div>
          <div className="forecast-card-hero-metric">
            {expectedUnits.toLocaleString()}{' '}
            <span className="forecast-card-hero-unit">units</span>
          </div>
          <div className="forecast-card-hero-note">
            in the next {horizonDays} days
          </div>
        </div>

        <div>
          <div className="forecast-card-divider">
            <span>Most likely range:</span>
            <strong>{likelyLow.toLocaleString()} to {likelyHigh.toLocaleString()} units</strong>
          </div>

          {isTechnicalView && (
            <div className="forecast-technical-subtext">
              q50: {headline.expected_units} | q25: {headline.likely_low} | q75: {headline.likely_high}
            </div>
          )}
        </div>
      </div>

      {/* 2. Suggested Action */}
      <div className="forecast-answer-card">
        <div>
          <div className="forecast-card-header">
            <span className="forecast-card-label">Suggested Action</span>
            <div className={`forecast-icon-circle ${suggestQty > 0 ? 'amber' : 'emerald'}`}>
              <ShoppingCart style={{ width: '16px', height: '16px' }} />
            </div>
          </div>

          <div className="forecast-action-title">
            {actionTitle}
          </div>
          <p className="forecast-action-desc">
            {actionDetail}
          </p>
        </div>

        <div>
          <div className="forecast-card-divider">
            <span>Extra buffer stock:</span>
            <strong>{safetyStock.toLocaleString()} units</strong>
          </div>

          {isTechnicalView && (
            <div className="forecast-technical-subtext">
              Safety Stock: {recommendation?.safety_stock} | Reorder Point: {recommendation?.reorder_point} | Risk: {stockoutRisk}
            </div>
          )}
        </div>
      </div>

      {/* 3. How Much to Trust This */}
      <div className="forecast-answer-card">
        <div>
          <div className="forecast-card-header">
            <span className="forecast-card-label">How Much To Trust This</span>
            <div className="forecast-icon-circle slate">
              <ShieldCheck style={{ width: '16px', height: '16px' }} />
            </div>
          </div>

          <div style={{ marginBottom: '8px' }}>
            <span className={`forecast-confidence-badge ${confidenceClass}`}>
              {confidence} CONFIDENCE
            </span>
          </div>

          <p className="forecast-confidence-text">
            {primaryReason}
          </p>

          {reasons.length > 1 && (
            <ul className="forecast-confidence-bullets">
              {reasons.slice(1, 3).map((r, i) => (
                <li key={i}>{r.text}</li>
              ))}
            </ul>
          )}
        </div>

        {isTechnicalView && (
          <div className="forecast-technical-subtext" style={{ marginTop: '16px', paddingTop: '8px', borderTop: '1px solid #f1f5f9' }}>
            Confidence reasons count: {reasons.length}
          </div>
        )}
      </div>
    </div>
  );
}
