import React from 'react';

/**
 * MetricLeaderboardCard component
 * Extracted directly from ForecastPage model accuracy leaderboard cards.
 * Displays model name, tag, winner badge, color dot, and 3 metric slots (WAPE, MAE, RMSE).
 */
export default function MetricLeaderboardCard({
  title,
  tag,
  color = '#3b82f6',
  isWinner = false,
  isSelected = false,
  metrics = [], // Array of { label: 'WAPE', value: '12.4%', color: '#3b82f6', isKey: true }
  emptyMessage,
  onClick,
  style = {},
  className = '',
}) {
  return (
    <div
      className={`diq-leaderboard-card ${className}`}
      onClick={onClick}
      style={{
        backgroundColor: isSelected ? 'var(--bg-surface-elevated)' : 'var(--bg-surface)',
        border: isSelected
          ? `2px solid ${color}`
          : isWinner
          ? '1px solid var(--accent-emerald)'
          : '1px solid var(--border-subtle)',
        borderRadius: '12px',
        padding: '1.25rem',
        cursor: onClick ? 'pointer' : 'default',
        position: 'relative',
        transition: 'all 0.2s ease',
        boxShadow: '0 4px 6px -1px rgba(0, 0, 0, 0.2)',
        ...style,
      }}
    >
      {isWinner && (
        <span
          style={{
            position: 'absolute',
            top: '0.75rem',
            right: '0.75rem',
            fontSize: '0.7rem',
            fontWeight: 700,
            backgroundColor: 'rgba(16, 185, 129, 0.2)',
            color: 'var(--accent-emerald)',
            padding: '0.15rem 0.5rem',
            borderRadius: '4px',
            letterSpacing: '0.04em',
          }}
        >
          BEST ACCURACY
        </span>
      )}

      <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.75rem' }}>
        <div style={{ width: '10px', height: '10px', borderRadius: '50%', backgroundColor: color, flexShrink: 0 }} />
        <span style={{ fontWeight: 600, fontSize: '0.95rem', color: 'var(--text-primary)' }}>{title}</span>
        {tag && <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>({tag})</span>}
      </div>

      {metrics && metrics.length > 0 ? (
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: `repeat(${metrics.length}, 1fr)`,
            gap: '0.75rem',
            marginTop: '0.5rem',
          }}
        >
          {metrics.map((m, idx) => (
            <div key={m.label || idx}>
              <div
                style={{
                  fontSize: '0.725rem',
                  color: 'var(--text-secondary)',
                  textTransform: 'uppercase',
                  letterSpacing: '0.04em',
                  fontWeight: 500,
                }}
              >
                {m.label}
              </div>
              <div
                style={{
                  fontSize: '1.2rem',
                  fontWeight: 700,
                  color: m.color || (m.isKey ? color : 'var(--text-primary)'),
                  fontFamily: 'var(--font-family-mono, monospace)',
                  marginTop: '0.1rem',
                }}
              >
                {m.value != null ? m.value : '—'}
              </div>
            </div>
          ))}
        </div>
      ) : (
        <div style={{ color: 'var(--text-muted)', fontSize: '0.85rem', fontStyle: 'italic', marginTop: '0.5rem' }}>
          {emptyMessage || 'No evaluation metrics available.'}
        </div>
      )}
    </div>
  );
}
