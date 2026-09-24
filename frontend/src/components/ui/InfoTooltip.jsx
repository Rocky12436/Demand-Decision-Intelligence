import React, { useState } from 'react';
import { HelpCircle } from 'lucide-react';

/**
 * InfoTooltip component
 * Non-intrusive tooltip providing plain-language business explanations to store managers.
 */
export default function InfoTooltip({ text, size = 13, style = {} }) {
  const [visible, setVisible] = useState(false);

  if (!text) return null;

  return (
    <span
      style={{
        position: 'relative',
        display: 'inline-flex',
        alignItems: 'center',
        verticalAlign: 'middle',
        cursor: 'help',
        color: 'var(--text-muted)',
        marginLeft: '4px',
        ...style,
      }}
      onMouseEnter={() => setVisible(true)}
      onMouseLeave={() => setVisible(false)}
      onClick={(e) => {
        e.stopPropagation();
        setVisible((v) => !v);
      }}
      aria-label={text}
    >
      <HelpCircle size={size} />
      {visible && (
        <span
          style={{
            position: 'absolute',
            bottom: '100%',
            left: '50%',
            transform: 'translateX(-50%)',
            marginBottom: '6px',
            padding: '6px 10px',
            backgroundColor: '#0f172a',
            color: '#ffffff',
            fontSize: '12px',
            lineHeight: 1.4,
            borderRadius: '6px',
            whiteSpace: 'normal',
            width: 'max-content',
            maxWidth: '240px',
            zIndex: 100,
            boxShadow: '0 4px 6px -1px rgba(0, 0, 0, 0.1)',
            pointerEvents: 'none',
            fontWeight: 400,
            textAlign: 'left',
          }}
        >
          {text}
        </span>
      )}
    </span>
  );
}
