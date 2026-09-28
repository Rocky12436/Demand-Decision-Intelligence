import React from 'react';
import {
  ResponsiveContainer,
  ComposedChart,
  Line,
  Area,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
  ReferenceLine,
} from 'recharts';
import { Sparkles } from 'lucide-react';

function formatAxisDate(iso) {
  if (!iso) return '';
  const [year, month, day] = iso.split('-');
  const d = new Date(Number(year), Number(month) - 1, Number(day));
  const weekday = d.toLocaleDateString('en-US', { weekday: 'short' });
  return `${weekday} ${month}/${day}`;
}

function formatFullDate(iso) {
  if (!iso) return '';
  const [year, month, day] = iso.split('-');
  const d = new Date(Number(year), Number(month) - 1, Number(day));
  return d.toLocaleDateString('en-US', { weekday: 'long', month: 'short', day: 'numeric', year: 'numeric' });
}

// Plain-Language Custom Tooltip
function PlainTooltip({ active, payload, isTechnicalView }) {
  if (!active || !payload || !payload.length) return null;

  const dataPoint = payload[0]?.payload;
  if (!dataPoint) return null;

  const isPast = dataPoint.isPast;
  const isFestival = dataPoint.isFestival;

  return (
    <div className="forecast-custom-tooltip">
      <div className="tooltip-date-row">
        <span>{formatFullDate(dataPoint.date)}</span>
        {isFestival && (
          <span className="festival-chip">
            <Sparkles style={{ width: '10px', height: '10px', display: 'inline', marginRight: '3px' }} /> Festival Day
          </span>
        )}
      </div>

      {isPast ? (
        <div className="tooltip-data-row">
          <span style={{ color: '#94a3b8' }}>Actual sales recorded:</span>
          <span className="tooltip-val-actual">
            {Math.round(dataPoint.actual).toLocaleString()} units
          </span>
        </div>
      ) : (
        <div>
          <div className="tooltip-data-row">
            <span style={{ color: '#cbd5e1', fontWeight: 500 }}>Most likely sales:</span>
            <span className="tooltip-val-pred">
              {Math.round(dataPoint.predicted).toLocaleString()} units
            </span>
          </div>

          <div className="tooltip-range-box">
            {isTechnicalView ? (
              <div>
                <div>q50: {dataPoint.predicted}</div>
                <div>q05: {dataPoint.q05} | q95: {dataPoint.q95}</div>
              </div>
            ) : (
              <span>
                <strong>9 in 10 chance</strong> it will be between{' '}
                <strong style={{ color: '#ffffff' }}>{Math.round(dataPoint.likelyLow)}</strong> and{' '}
                <strong style={{ color: '#ffffff' }}>{Math.round(dataPoint.likelyHigh)}</strong> units.
              </span>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

export function ForecastChart({ history = [], daily = [], isTechnicalView }) {
  // Combine historical points and forecast points
  const combinedData = [];

  // 1. History items
  history.forEach((h) => {
    combinedData.push({
      date: h.date,
      displayDate: formatAxisDate(h.date),
      actual: h.units,
      predicted: null,
      rangeBase: null,
      rangeSpan: null,
      isPast: true,
      isFestival: false,
    });
  });

  // 2. Continuous bridge: last history point also initializes the forecast line
  if (history.length > 0 && daily.length > 0) {
    const lastHist = history[history.length - 1];
    // Attach forecast connection point to last history date
    combinedData[combinedData.length - 1].predicted = lastHist.units;
    combinedData[combinedData.length - 1].rangeBase = lastHist.units;
    combinedData[combinedData.length - 1].rangeSpan = 0;
  }

  // 3. Future daily forecast points
  daily.forEach((d) => {
    const p = d.q50 ?? d.yhat ?? 0;
    const low = d.q05 ?? d.q25 ?? Math.max(0, p * 0.8);
    const high = d.q95 ?? d.q75 ?? (p * 1.2);

    combinedData.push({
      date: d.date,
      displayDate: formatAxisDate(d.date),
      actual: null,
      predicted: Math.round(p * 10) / 10,
      likelyLow: Math.round(low * 10) / 10,
      likelyHigh: Math.round(high * 10) / 10,
      rangeBase: Math.round(low * 10) / 10,
      rangeSpan: Math.max(0, Math.round((high - low) * 10) / 10),
      isPast: false,
      isFestival: Boolean(d.is_festival),
      q05: d.q05,
      q25: d.q25,
      q75: d.q75,
      q95: d.q95,
    });
  });

  if (combinedData.length === 0) {
    return (
      <div className="forecast-chart-card" style={{ textAlign: 'center', color: '#94a3b8', padding: '32px' }}>
        No sales or forecast data available to display chart.
      </div>
    );
  }

  // Find split date for reference line
  const splitDate = daily.length > 0 ? daily[0].date : null;

  return (
    <div className="forecast-chart-card" aria-label="Sales and forecast demand chart">
      <div className="forecast-chart-header">
        <div>
          <h2 className="forecast-chart-title">
            Historical Sales & Future Forecast
          </h2>
          <p className="forecast-chart-desc">
            Past actual orders (solid line) transitioning into projected demand with shaded most-likely range
          </p>
        </div>

        {/* Legend pills */}
        <div className="forecast-chart-legend">
          <div className="legend-item">
            <span className="legend-pill-past" />
            <span>Past Sales</span>
          </div>
          <div className="legend-item">
            <span className="legend-pill-pred" />
            <span>Expected Demand</span>
          </div>
          <div className="legend-item">
            <span className="legend-pill-range" />
            <span>Likely Range (9 in 10)</span>
          </div>
        </div>
      </div>

      <div className="forecast-chart-wrapper">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={combinedData} margin={{ top: 10, right: 15, left: -10, bottom: 25 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" vertical={false} />
            <XAxis
              dataKey="date"
              tickFormatter={formatAxisDate}
              tick={{ fontSize: 11, fill: '#64748b' }}
              tickMargin={10}
              interval="preserveStartEnd"
              minTickGap={30}
              stroke="#cbd5e1"
            />
            <YAxis
              tick={{ fontSize: 11, fill: '#64748b' }}
              tickMargin={5}
              stroke="#cbd5e1"
              allowDecimals={false}
            />
            <Tooltip content={<PlainTooltip isTechnicalView={isTechnicalView} />} />

            {/* Shaded Likely Range using stacked transparent base + shaded span */}
            <Area
              type="monotone"
              dataKey="rangeBase"
              stackId="band"
              stroke="none"
              fill="transparent"
              isAnimationActive={false}
              legendType="none"
            />
            <Area
              type="monotone"
              dataKey="rangeSpan"
              stackId="band"
              stroke="none"
              fill="#818cf8"
              fillOpacity={0.25}
              name="Likely Range"
              isAnimationActive={false}
            />

            {/* Past Sales Line */}
            <Line
              type="monotone"
              dataKey="actual"
              stroke="#475569"
              strokeWidth={2}
              dot={{ r: 2.5, fill: '#475569' }}
              activeDot={{ r: 5, fill: '#334155' }}
              name="Past Sales"
              connectNulls={false}
            />

            {/* Future Predicted Demand Line */}
            <Line
              type="monotone"
              dataKey="predicted"
              stroke="#4f46e5"
              strokeWidth={2.5}
              strokeDasharray="4 2"
              dot={{ r: 3, fill: '#4f46e5' }}
              activeDot={{ r: 6, fill: '#4338ca' }}
              name="Expected Demand"
              connectNulls={false}
            />

            {splitDate && (
              <ReferenceLine
                x={splitDate}
                stroke="#94a3b8"
                strokeDasharray="3 3"
                label={{
                  value: 'Today / Forecast Start',
                  position: 'insideTopLeft',
                  fill: '#64748b',
                  fontSize: 10,
                }}
              />
            )}
          </ComposedChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
