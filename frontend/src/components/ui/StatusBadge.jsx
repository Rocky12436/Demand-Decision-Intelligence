import React from 'react';
import { CheckCircle2, AlertTriangle, AlertCircle, Info, MinusCircle } from 'lucide-react';

/**
 * StatusBadge component
 * Strictly pairs status colors with both an icon and clear text label (WCAG AA).
 * Variants: success | warning | critical | neutral | info
 */
export default function StatusBadge({
  variant = 'neutral',
  label,
  children,
  icon: CustomIcon,
  size = 'md',
  style = {},
  className = '',
}) {
  const displayLabel = label || children;

  const config = {
    success: {
      bg: 'var(--status-success-bg)',
      border: 'var(--status-success-border)',
      text: 'var(--status-success-text)',
      defaultIcon: CheckCircle2,
    },
    warning: {
      bg: 'var(--status-warning-bg)',
      border: 'var(--status-warning-border)',
      text: 'var(--status-warning-text)',
      defaultIcon: AlertTriangle,
    },
    critical: {
      bg: 'var(--status-critical-bg)',
      border: 'var(--status-critical-border)',
      text: 'var(--status-critical-text)',
      defaultIcon: AlertCircle,
    },
    neutral: {
      bg: 'var(--status-neutral-bg)',
      border: 'var(--status-neutral-border)',
      text: 'var(--status-neutral-text)',
      defaultIcon: MinusCircle,
    },
    info: {
      bg: 'var(--status-info-bg)',
      border: 'var(--status-info-border)',
      text: 'var(--status-info-text)',
      defaultIcon: Info,
    },
  };

  const current = config[variant] || config.neutral;
  const IconToRender = CustomIcon || current.defaultIcon;

  const fontSizes = {
    sm: { fontSize: '11px', padding: '2px 6px', iconSize: 12 },
    md: { fontSize: '12px', padding: '3px 8px', iconSize: 13 },
    lg: { fontSize: '13px', padding: '4px 10px', iconSize: 14 },
  };

  const sz = fontSizes[size] || fontSizes.md;

  return (
    <span
      className={`diq-status-badge diq-status-${variant} ${className}`}
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: '4px',
        backgroundColor: current.bg,
        border: `1px solid ${current.border}`,
        color: current.text,
        borderRadius: 'var(--border-radius-pill)',
        fontWeight: 600,
        lineHeight: 1.2,
        whiteSpace: 'nowrap',
        ...sz,
        ...style,
      }}
    >
      {IconToRender && <IconToRender size={sz.iconSize} style={{ flexShrink: 0 }} />}
      <span>{displayLabel}</span>
    </span>
  );
}
