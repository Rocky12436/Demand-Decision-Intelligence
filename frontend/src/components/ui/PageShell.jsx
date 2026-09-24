import React from 'react';

/**
 * PageShell component
 * Centered container with max-width ~1200px for clean desktop-first layout.
 */
export default function PageShell({ children, maxWidth = '1200px', style = {}, className = '' }) {
  return (
    <div
      className={`diq-page-shell ${className}`}
      style={{
        maxWidth,
        margin: '0 auto',
        width: '100%',
        boxSizing: 'border-box',
        ...style,
      }}
    >
      {children}
    </div>
  );
}
