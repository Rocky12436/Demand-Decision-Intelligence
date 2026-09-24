import React from 'react';
import { AlertTriangle, X } from 'lucide-react';

/**
 * ConfirmDialog component
 * Accessible confirmation modal for destructive or major actions.
 */
export default function ConfirmDialog({
  isOpen,
  title = 'Are you sure?',
  message = 'This action cannot be undone.',
  confirmLabel = 'Confirm',
  cancelLabel = 'Cancel',
  isDestructive = false,
  onConfirm,
  onCancel,
}) {
  if (!isOpen) return null;

  return (
    <div
      style={{
        position: 'fixed',
        top: 0,
        left: 0,
        right: 0,
        bottom: 0,
        backgroundColor: 'rgba(15, 23, 42, 0.4)',
        backdropFilter: 'blur(2px)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        zIndex: 9999,
        padding: '16px',
      }}
      onClick={onCancel}
    >
      <div
        style={{
          backgroundColor: '#ffffff',
          borderRadius: 'var(--border-radius-lg)',
          boxShadow: 'var(--shadow-dropdown)',
          maxWidth: '440px',
          width: '100%',
          padding: '20px',
          border: '1px solid var(--border-subtle)',
        }}
        onClick={(e) => e.stopPropagation()}
      >
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '12px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            {isDestructive && <AlertTriangle size={18} color="var(--status-critical-icon)" />}
            <h3 style={{ fontSize: '16px', fontWeight: 600, color: 'var(--text-primary)', margin: 0 }}>
              {title}
            </h3>
          </div>
          <button
            onClick={onCancel}
            style={{ background: 'none', border: 'none', color: 'var(--text-muted)', cursor: 'pointer', padding: 0 }}
          >
            <X size={18} />
          </button>
        </div>

        <p style={{ fontSize: '13px', color: 'var(--text-secondary)', margin: '0 0 20px 0', lineHeight: 1.4 }}>
          {message}
        </p>

        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '8px' }}>
          <button onClick={onCancel} className="diq-btn diq-btn-secondary">
            {cancelLabel}
          </button>
          <button
            onClick={onConfirm}
            className="diq-btn diq-btn-primary"
            style={isDestructive ? { backgroundColor: '#b91c1c', borderColor: '#b91c1c' } : {}}
          >
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
