import React from 'react';
import { Inbox } from 'lucide-react';

/**
 * EmptyState component
 * Clean icon, one plain-English explanation, and a primary action button.
 */
export default function EmptyState({
  icon: Icon = Inbox,
  title = 'No records found',
  description = 'There is currently no data available for this section.',
  actionLabel,
  onAction,
  style = {},
  className = '',
}) {
  return (
    <div
      className={`diq-empty-state ${className}`}
      style={{
        padding: '40px 20px',
        textAlign: 'center',
        backgroundColor: '#ffffff',
        border: '1px solid var(--border-subtle)',
        borderRadius: 'var(--border-radius-lg)',
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        ...style,
      }}
    >
      <div
        style={{
          width: '40px',
          height: '40px',
          borderRadius: '50%',
          backgroundColor: 'var(--bg-surface-subtle)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          color: 'var(--text-muted)',
          marginBottom: '12px',
        }}
      >
        <Icon size={20} />
      </div>

      <h4 style={{ fontSize: '15px', fontWeight: 600, color: 'var(--text-primary)', margin: '0 0 4px 0' }}>
        {title}
      </h4>

      <p style={{ fontSize: '13px', color: 'var(--text-secondary)', margin: '0 0 16px 0', maxWidth: '360px' }}>
        {description}
      </p>

      {actionLabel && onAction && (
        <button onClick={onAction} className="diq-btn diq-btn-primary">
          {actionLabel}
        </button>
      )}
    </div>
  );
}
