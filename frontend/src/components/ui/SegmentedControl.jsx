import React from 'react';

/**
 * SegmentedControl component
 * Stripe-like segmented control with smooth indicator for binary or multi-option choices.
 */
export default function SegmentedControl({
  options = [], // [{ value: 'replace', label: 'Replace old data', description: '...' }]
  value,
  onChange,
  size = 'md',
  style = {},
  className = '',
}) {
  return (
    <div
      className={`diq-segmented-control ${className}`}
      style={{
        display: 'inline-flex',
        backgroundColor: 'var(--bg-surface-subtle)',
        border: '1px solid var(--border-subtle)',
        borderRadius: 'var(--border-radius-md)',
        padding: '3px',
        gap: '2px',
        ...style,
      }}
    >
      {options.map((opt) => {
        const isSelected = opt.value === value;
        return (
          <button
            key={opt.value}
            type="button"
            onClick={() => onChange(opt.value)}
            style={{
              padding: size === 'sm' ? '4px 10px' : '6px 14px',
              borderRadius: 'var(--border-radius-sm)',
              border: 'none',
              backgroundColor: isSelected ? '#ffffff' : 'transparent',
              color: isSelected ? 'var(--text-primary)' : 'var(--text-muted)',
              fontWeight: isSelected ? 600 : 500,
              fontSize: size === 'sm' ? '12px' : '13px',
              cursor: 'pointer',
              boxShadow: isSelected ? '0 1px 2px 0 rgba(0, 0, 0, 0.05)' : 'none',
              transition: 'all 0.15s ease',
              whiteSpace: 'nowrap',
            }}
          >
            {opt.label}
          </button>
        );
      })}
    </div>
  );
}
