import React from 'react';

/**
 * Skeleton component
 * Clean placeholder blocks matching final layout shape during data fetch.
 */
export default function Skeleton({ width = '100%', height = '16px', borderRadius = '4px', style = {} }) {
  return (
    <div
      style={{
        width,
        height,
        borderRadius,
        backgroundColor: '#e2e8f0',
        animation: 'pulse 1.5s ease-in-out infinite',
        ...style,
      }}
    />
  );
}

export function SkeletonCard({ count = 1 }) {
  return (
    <div style={{ display: 'grid', gridTemplateColumns: `repeat(${count}, minmax(0, 1fr))`, gap: '16px', width: '100%' }}>
      {Array.from({ length: count }).map((_, i) => (
        <div
          key={i}
          style={{
            padding: '16px 20px',
            backgroundColor: '#ffffff',
            border: '1px solid var(--border-subtle)',
            borderRadius: 'var(--border-radius-lg)',
            display: 'flex',
            flexDirection: 'column',
            gap: '10px',
          }}
        >
          <Skeleton width="40%" height="12px" />
          <Skeleton width="60%" height="28px" />
          <Skeleton width="50%" height="12px" />
        </div>
      ))}
    </div>
  );
}
