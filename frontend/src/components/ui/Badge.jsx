import React from 'react';

/**
 * Badge component
 * Standard status indicator with semantic colors.
 * Variants: success | warning | critical | neutral | info
 */
export default function Badge({
  variant = 'neutral',
  size = 'md',
  pill = false,
  icon: Icon,
  children,
  style = {},
  className = '',
}) {
  const variantStyles = {
    success: {
      backgroundColor: 'var(--status-success-bg)',
      border: '1px solid var(--status-success-border)',
      color: 'var(--status-success-text)',
    },
    warning: {
      backgroundColor: 'var(--status-warning-bg)',
      border: '1px solid var(--status-warning-border)',
      color: 'var(--status-warning-text)',
    },
    critical: {
      backgroundColor: 'var(--status-critical-bg)',
      border: '1px solid var(--status-critical-border)',
      color: 'var(--status-critical-text)',
    },
    neutral: {
      backgroundColor: 'var(--status-neutral-bg)',
      border: '1px solid var(--status-neutral-border)',
      color: 'var(--status-neutral-text)',
    },
    info: {
      backgroundColor: 'var(--status-info-bg)',
      border: '1px solid var(--status-info-border)',
      color: 'var(--status-info-text)',
    },
  };

  const currentVariant = variantStyles[variant] || variantStyles.neutral;

  const sizeStyles = {
    sm: {
      padding: '2px 8px',
      fontSize: '11px',
    },
    md: {
      padding: '3px 10px',
      fontSize: '12px',
    },
    lg: {
      padding: '5px 12px',
      fontSize: '13px',
    },
  };

  const currentSize = sizeStyles[size] || sizeStyles.md;

  return (
    <span
      className={`diq-badge diq-badge-${variant} ${pill ? 'diq-badge-pill' : ''} ${className}`}
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: '4px',
        borderRadius: pill ? '9999px' : '6px',
        fontWeight: 600,
        lineHeight: 1,
        whiteSpace: 'nowrap',
        ...currentVariant,
        ...currentSize,
        ...style,
      }}
    >
      {Icon && <Icon size={size === 'sm' ? 12 : size === 'lg' ? 16 : 14} style={{ flexShrink: 0 }} />}
      <span>{children}</span>
    </span>
  );
}
