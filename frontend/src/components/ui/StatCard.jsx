import React from 'react';
import InfoTooltip from './InfoTooltip';

/**
 * StatCard component
 * Enterprise SaaS KPI card: white background, 1px subtle border, 8px radius,
 * tabular-nums for numbers, plain label with InfoTooltip, and concise subtext.
 */
export default function StatCard({
  value,
  label,
  tooltip,
  trend,
  trendDirection = 'neutral', // 'up' | 'down' | 'neutral'
  trendPositive = true,       // whether 'up' is good
  subtext,
  icon: Icon,
  onClick,
  style = {},
  className = '',
}) {
  const isClickable = Boolean(onClick);

  return (
    <div
      className={`diq-stat-card diq-card ${className}`}
      onClick={onClick}
      style={{
        padding: '16px 20px',
        backgroundColor: '#ffffff',
        border: '1px solid var(--border-subtle)',
        borderRadius: 'var(--border-radius-lg)',
        boxShadow: 'var(--shadow-card)',
        cursor: isClickable ? 'pointer' : 'default',
        transition: 'border-color 0.15s ease',
        display: 'flex',
        flexDirection: 'column',
        justifyContent: 'space-between',
        ...style,
      }}
    >
      <div>
        <div
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            marginBottom: '6px',
          }}
        >
          <span
            style={{
              fontSize: '12px',
              fontWeight: 600,
              textTransform: 'uppercase',
              letterSpacing: '0.04em',
              color: 'var(--text-muted)',
              display: 'inline-flex',
              alignItems: 'center',
            }}
          >
            <span>{label}</span>
            {tooltip && <InfoTooltip text={tooltip} size={12} />}
          </span>
          {Icon && (
            <div
              style={{
                color: 'var(--text-muted)',
                display: 'flex',
                alignItems: 'center',
              }}
            >
              <Icon size={16} />
            </div>
          )}
        </div>

        <div
          className="tabular-nums"
          style={{
            fontSize: '24px',
            fontWeight: 700,
            color: 'var(--text-primary)',
            lineHeight: 1.2,
          }}
        >
          {value != null ? value : '—'}
        </div>
      </div>

      {(trend || subtext) && (
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '6px',
            marginTop: '8px',
            fontSize: '12px',
            flexWrap: 'wrap',
          }}
        >
          {trend && (
            <span
              style={{
                fontWeight: 600,
                color:
                  trendDirection === 'up'
                    ? trendPositive ? 'var(--status-success-text)' : 'var(--status-critical-text)'
                    : trendDirection === 'down'
                    ? trendPositive ? 'var(--status-critical-text)' : 'var(--status-success-text)'
                    : 'var(--text-secondary)',
              }}
            >
              {trend}
            </span>
          )}
          {subtext && (
            <span style={{ color: 'var(--text-muted)' }}>
              {subtext}
            </span>
          )}
        </div>
      )}
    </div>
  );
}
