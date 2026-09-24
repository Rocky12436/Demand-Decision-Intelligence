import React from 'react';
import { AlertCircle, AlertTriangle, CheckCircle2, Info } from 'lucide-react';

/**
 * InsightCallout component
 * Renders the top-of-page "What you need to know" callout (1–2 sentences, plain English)
 * paired with a recommended next action button.
 */
export default function InsightCallout({
  variant = 'info', // 'critical' | 'warning' | 'success' | 'info'
  title = 'What you need to know',
  message,
  actionLabel,
  onAction,
  actionIcon: ActionIcon,
  style = {},
  className = '',
}) {
  const configs = {
    critical: {
      bg: 'var(--status-critical-bg)',
      border: 'var(--status-critical-border)',
      titleColor: 'var(--status-critical-text)',
      icon: AlertCircle,
      iconColor: 'var(--status-critical-icon)',
      btnClass: 'diq-btn-primary',
      btnStyle: { backgroundColor: '#b91c1c', borderColor: '#b91c1c', color: '#ffffff' },
    },
    warning: {
      bg: 'var(--status-warning-bg)',
      border: 'var(--status-warning-border)',
      titleColor: 'var(--status-warning-text)',
      icon: AlertTriangle,
      iconColor: 'var(--status-warning-icon)',
      btnClass: 'diq-btn-primary',
      btnStyle: { backgroundColor: '#b45309', borderColor: '#b45309', color: '#ffffff' },
    },
    success: {
      bg: 'var(--status-success-bg)',
      border: 'var(--status-success-border)',
      titleColor: 'var(--status-success-text)',
      icon: CheckCircle2,
      iconColor: 'var(--status-success-icon)',
      btnClass: 'diq-btn-secondary',
      btnStyle: {},
    },
    info: {
      bg: 'var(--status-info-bg)',
      border: 'var(--status-info-border)',
      titleColor: 'var(--status-info-text)',
      icon: Info,
      iconColor: 'var(--status-info-icon)',
      btnClass: 'diq-btn-primary',
      btnStyle: {},
    },
  };

  const current = configs[variant] || configs.info;
  const LeadingIcon = current.icon;

  return (
    <div
      className={`diq-insight-callout ${className}`}
      style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        flexWrap: 'wrap',
        gap: '12px',
        padding: '12px 16px',
        borderRadius: 'var(--border-radius-lg)',
        backgroundColor: current.bg,
        border: `1px solid ${current.border}`,
        marginBottom: '20px',
        ...style,
      }}
    >
      <div style={{ display: 'flex', alignItems: 'flex-start', gap: '10px', flex: 1, minWidth: '280px' }}>
        <LeadingIcon size={18} color={current.iconColor} style={{ flexShrink: 0, marginTop: '2px' }} />
        <div>
          <div style={{ fontSize: '13px', fontWeight: 600, color: current.titleColor }}>
            {title}
          </div>
          <div style={{ fontSize: '13px', color: 'var(--text-secondary)', marginTop: '2px', lineHeight: 1.4 }}>
            {message}
          </div>
        </div>
      </div>

      {actionLabel && onAction && (
        <button
          onClick={onAction}
          className={`diq-btn ${current.btnClass}`}
          style={{ ...current.btnStyle }}
        >
          {ActionIcon && <ActionIcon size={14} />}
          <span>{actionLabel}</span>
        </button>
      )}
    </div>
  );
}
