import React from 'react';
import { AlertCircle, RefreshCw } from 'lucide-react';

/**
 * ErrorState component
 * Explicit error screen with clear reason and retry action.
 */
export default function ErrorState({
  title = 'Could not load data',
  message = 'An unexpected error occurred while connecting to the server.',
  onRetry,
  style = {},
  className = '',
}) {
  return (
    <div
      className={`diq-error-state ${className}`}
      style={{
        padding: '32px 20px',
        textAlign: 'center',
        backgroundColor: '#fef2f2',
        border: '1px solid #fecaca',
        borderRadius: 'var(--border-radius-lg)',
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        margin: '16px 0',
        ...style,
      }}
    >
      <div
        style={{
          width: '36px',
          height: '36px',
          borderRadius: '50%',
          backgroundColor: '#fee2e2',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          color: '#b91c1c',
          marginBottom: '10px',
        }}
      >
        <AlertCircle size={20} />
      </div>

      <h4 style={{ fontSize: '15px', fontWeight: 600, color: '#991b1b', margin: '0 0 4px 0' }}>
        {title}
      </h4>

      <p style={{ fontSize: '13px', color: '#7f1d1d', margin: '0 0 14px 0', maxWidth: '420px' }}>
        {message}
      </p>

      {onRetry && (
        <button
          onClick={onRetry}
          className="diq-btn"
          style={{
            backgroundColor: '#ffffff',
            border: '1px solid #fca5a5',
            color: '#991b1b',
          }}
        >
          <RefreshCw size={13} />
          <span>Retry</span>
        </button>
      )}
    </div>
  );
}
