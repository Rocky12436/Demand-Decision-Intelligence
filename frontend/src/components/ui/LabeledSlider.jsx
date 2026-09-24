import React from 'react';

/**
 * LabeledSlider component
 * Enterprise slider instrument with title, plain description, live numeric readout,
 * and named anchor stops.
 */
export default function LabeledSlider({
  label,
  description,
  value,
  min = 0,
  max = 100,
  step = 1,
  unit = '',
  stops = [], // [{ value: 80, label: 'Relaxed' }, { value: 95, label: 'Standard' }]
  onChange,
  style = {},
  className = '',
}) {
  return (
    <div
      className={`diq-labeled-slider ${className}`}
      style={{
        padding: '16px',
        backgroundColor: '#ffffff',
        border: '1px solid var(--border-subtle)',
        borderRadius: 'var(--border-radius-lg)',
        ...style,
      }}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: '4px' }}>
        <span style={{ fontSize: '14px', fontWeight: 600, color: 'var(--text-primary)' }}>
          {label}
        </span>
        <span
          className="tabular-nums"
          style={{
            fontSize: '15px',
            fontWeight: 700,
            color: 'var(--accent-primary)',
            backgroundColor: 'var(--accent-primary-subtle)',
            padding: '2px 8px',
            borderRadius: 'var(--border-radius-sm)',
          }}
        >
          {value}{unit}
        </span>
      </div>

      {description && (
        <p style={{ fontSize: '12px', color: 'var(--text-secondary)', margin: '0 0 12px 0', lineHeight: 1.35 }}>
          {description}
        </p>
      )}

      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        style={{
          width: '100%',
          accentColor: 'var(--accent-primary)',
          cursor: 'pointer',
          margin: '4px 0 8px 0',
        }}
      />

      {stops.length > 0 && (
        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '11px', color: 'var(--text-muted)' }}>
          {stops.map((stop) => (
            <span
              key={stop.value}
              onClick={() => onChange(stop.value)}
              style={{
                cursor: 'pointer',
                fontWeight: value === stop.value ? 600 : 400,
                color: value === stop.value ? 'var(--accent-primary)' : 'var(--text-muted)',
              }}
            >
              {stop.label} ({stop.value}{unit})
            </span>
          ))}
        </div>
      )}
    </div>
  );
}
