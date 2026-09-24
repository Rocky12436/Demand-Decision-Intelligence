import React from 'react';

/**
 * PageHeader component
 * Standard enterprise page header: Title (24px), ONE plain sentence explaining
 * what the page does, and at most one primary action on the right.
 */
export default function PageHeader({
  title,
  subtitle,
  icon: Icon,
  actions,
  style = {},
  className = '',
}) {
  return (
    <div
      className={`diq-page-header ${className}`}
      style={{
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'flex-start',
        marginBottom: '20px',
        flexWrap: 'wrap',
        gap: '12px',
        ...style,
      }}
    >
      <div>
        <h1
          style={{
            fontSize: '24px',
            fontWeight: 700,
            color: 'var(--text-primary)',
            display: 'flex',
            alignItems: 'center',
            gap: '8px',
            margin: 0,
            lineHeight: 1.25,
            letterSpacing: '-0.01em',
          }}
        >
          {Icon && <Icon size={24} color="var(--accent-primary)" style={{ flexShrink: 0 }} />}
          <span>{title}</span>
        </h1>
        {subtitle && (
          <p
            style={{
              color: 'var(--text-secondary)',
              fontSize: '14px',
              margin: '4px 0 0 0',
              lineHeight: 1.4,
            }}
          >
            {subtitle}
          </p>
        )}
      </div>

      {actions && (
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '8px',
            flexWrap: 'wrap',
          }}
        >
          {actions}
        </div>
      )}
    </div>
  );
}
