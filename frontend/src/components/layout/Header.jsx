import React, { useState, useEffect } from 'react';
import { Bell, Eye, SlidersHorizontal } from 'lucide-react';
import { useAuth } from '../../context/AuthContext';
import { useBusinessMode } from '../../context/BusinessModeContext';
import api from '../../services/api';
import AlertInboxModal from '../alerts/AlertInboxModal';

/**
 * Enterprise Header component
 * Includes persistent "Simple view / Technical view" toggle, alert notifications, and user status.
 */
export default function Header({ title = 'Dashboard Overview' }) {
  const { user } = useAuth();
  const { isTechnical, toggleMode } = useBusinessMode();
  const userName = user?.full_name || user?.username || 'Store Manager';
  const userRole = user?.role || 'Retail Ops';
  const [unreadCount, setUnreadCount] = useState(0);
  const [showInbox, setShowInbox] = useState(false);

  useEffect(() => {
    fetchUnreadCount();
    const interval = setInterval(fetchUnreadCount, 20000);
    return () => clearInterval(interval);
  }, []);

  const fetchUnreadCount = async () => {
    try {
      const res = await api.get('/alerts/unread-count');
      if (res?.data?.unread_count != null) {
        setUnreadCount(res.data.unread_count);
      }
    } catch {
      // Quiet fail if offline
    }
  };

  return (
    <header
      className="top-navbar"
      style={{
        height: 'var(--header-height)',
        backgroundColor: '#ffffff',
        borderBottom: '1px solid var(--border-subtle)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        padding: '0 24px',
      }}
    >
      {/* Page Title Context */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
        <h2 style={{ fontSize: '15px', fontWeight: 600, color: 'var(--text-primary)', margin: 0 }}>
          {title}
        </h2>
      </div>

      {/* Action Controls & Mode Switch */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
        {/* Persistent Simple vs Technical View Toggle */}
        <div
          style={{
            display: 'inline-flex',
            backgroundColor: 'var(--bg-surface-subtle)',
            border: '1px solid var(--border-subtle)',
            borderRadius: 'var(--border-radius-md)',
            padding: '2px',
          }}
          title={isTechnical ? 'Switch to Simple view (plain business terms)' : 'Switch to Technical view (raw statistical metrics)'}
        >
          <button
            type="button"
            onClick={() => isTechnical && toggleMode()}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '5px',
              padding: '4px 10px',
              borderRadius: 'var(--border-radius-sm)',
              border: 'none',
              backgroundColor: !isTechnical ? '#ffffff' : 'transparent',
              color: !isTechnical ? 'var(--accent-primary)' : 'var(--text-muted)',
              fontWeight: !isTechnical ? 600 : 500,
              fontSize: '12px',
              cursor: 'pointer',
              boxShadow: !isTechnical ? '0 1px 2px 0 rgba(0, 0, 0, 0.05)' : 'none',
              transition: 'all 0.15s ease',
            }}
          >
            <Eye size={13} />
            <span>Simple view</span>
          </button>

          <button
            type="button"
            onClick={() => !isTechnical && toggleMode()}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '5px',
              padding: '4px 10px',
              borderRadius: 'var(--border-radius-sm)',
              border: 'none',
              backgroundColor: isTechnical ? '#ffffff' : 'transparent',
              color: isTechnical ? 'var(--accent-primary)' : 'var(--text-muted)',
              fontWeight: isTechnical ? 600 : 500,
              fontSize: '12px',
              cursor: 'pointer',
              boxShadow: isTechnical ? '0 1px 2px 0 rgba(0, 0, 0, 0.05)' : 'none',
              transition: 'all 0.15s ease',
            }}
          >
            <SlidersHorizontal size={13} />
            <span>Technical view</span>
          </button>
        </div>

        {/* Alerts Bell */}
        <button
          onClick={() => setShowInbox(true)}
          style={{
            background: 'none',
            border: '1px solid var(--border-subtle)',
            borderRadius: 'var(--border-radius-md)',
            color: 'var(--text-secondary)',
            cursor: 'pointer',
            position: 'relative',
            padding: '6px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
          }}
          title="Stock Alerts & Notifications"
          aria-label="Alerts"
        >
          <Bell size={16} />
          {unreadCount > 0 && (
            <span
              style={{
                position: 'absolute',
                top: '-4px',
                right: '-4px',
                backgroundColor: 'var(--status-critical-icon)',
                color: '#ffffff',
                borderRadius: '10px',
                padding: '1px 5px',
                fontSize: '10px',
                fontWeight: 700,
                lineHeight: 1.2,
              }}
            >
              {unreadCount > 99 ? '99+' : unreadCount}
            </span>
          )}
        </button>

        {/* User Identity Pill */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <div
            style={{
              width: 30,
              height: 30,
              borderRadius: '50%',
              backgroundColor: 'var(--accent-primary-subtle)',
              border: '1px solid var(--accent-primary-border)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              color: 'var(--accent-primary)',
              fontWeight: 600,
              fontSize: '12px',
            }}
          >
            {userName.charAt(0).toUpperCase()}
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', lineHeight: 1.2 }}>
            <span style={{ fontSize: '13px', fontWeight: 600, color: 'var(--text-primary)' }}>
              {userName}
            </span>
            <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>
              {userRole}
            </span>
          </div>
        </div>
      </div>

      {showInbox && (
        <AlertInboxModal
          onClose={() => {
            setShowInbox(false);
            fetchUnreadCount();
          }}
        />
      )}
    </header>
  );
}
