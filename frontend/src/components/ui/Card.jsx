import React from 'react';

/**
 * Card component
 * The core building block: 12px radius, subtle border, #111827 surface background,
 * configurable padding and optional header/footer slots.
 */
export default function Card({
  title,
  subtitle,
  icon: Icon,
  iconColor,
  actions,
  children,
  padding = '1.5rem',
  style = {},
  className = '',
  footer,
  onClick,
  hoverable = false,
}) {
  const isClickable = Boolean(onClick);

  return (
    <div
      className={`diq-card card ${className}`}
      onClick={onClick}
      style={{
        backgroundColor: 'var(--bg-surface)',
        border: '1px solid var(--border-subtle)',
        borderRadius: '12px',
        padding,
        marginBottom: '1.5rem',
        boxShadow: '0 4px 6px -1px rgba(0, 0, 0, 0.2)',
        cursor: isClickable ? 'pointer' : 'default',
        transition: 'all 0.2s ease',
        ...(hoverable
          ? {
              ':hover': {
                borderColor: 'var(--border-strong)',
                transform: 'translateY(-2px)',
              },
            }
          : {}),
        ...style,
      }}
    >
      {(title || actions) && (
        <div
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            marginBottom: subtitle ? '0.35rem' : '1.25rem',
            flexWrap: 'wrap',
            gap: '0.75rem',
          }}
        >
          {title && (
            <h3
              style={{
                fontSize: '1.1rem',
                fontWeight: 600,
                color: 'var(--text-primary)',
                display: 'flex',
                alignItems: 'center',
                gap: '0.5rem',
                margin: 0,
              }}
            >
              {Icon && <Icon size={20} color={iconColor || 'var(--accent-primary)'} style={{ flexShrink: 0 }} />}
              <span>{title}</span>
            </h3>
          )}
          {actions && (
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              {actions}
            </div>
          )}
        </div>
      )}

      {subtitle && (
        <p
          style={{
            fontSize: '0.85rem',
            color: 'var(--text-secondary)',
            marginBottom: '1.25rem',
            margin: '0 0 1.25rem 0',
          }}
        >
          {subtitle}
        </p>
      )}

      {children}

      {footer && (
        <div
          style={{
            marginTop: '1.25rem',
            paddingTop: '0.85rem',
            borderTop: '1px solid var(--border-subtle)',
          }}
        >
          {footer}
        </div>
      )}
    </div>
  );
}
