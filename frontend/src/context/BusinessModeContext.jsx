import React, { createContext, useContext, useState, useEffect } from 'react';
import { GLOSSARY, getTerm, getTooltip } from '../lib/glossary';
import { HelpCircle } from 'lucide-react';

const BusinessModeContext = createContext();

export function BusinessModeProvider({ children }) {
  // Default to Simple view (non-technical)
  const [isTechnical, setIsTechnical] = useState(() => {
    const saved = localStorage.getItem('demandiq_view_mode');
    return saved === 'technical';
  });

  useEffect(() => {
    localStorage.setItem('demandiq_view_mode', isTechnical ? 'technical' : 'simple');
  }, [isTechnical]);

  const toggleMode = () => setIsTechnical((prev) => !prev);

  return (
    <BusinessModeContext.Provider value={{ isTechnical, toggleMode, setIsTechnical }}>
      {children}
    </BusinessModeContext.Provider>
  );
}

export function useBusinessMode() {
  const context = useContext(BusinessModeContext);
  if (!context) {
    return {
      isTechnical: false,
      toggleMode: () => {},
      setIsTechnical: () => {},
    };
  }
  return context;
}

/**
 * Reusable <Term id="..."/> component
 * In Simple view: Displays plain business label with info tooltip.
 * In Technical view: Displays technical term with optional clarification.
 */
export function Term({ id, showTooltip = true, fallback, className = '', style = {} }) {
  const { isTechnical } = useBusinessMode();
  const entry = GLOSSARY[id];

  if (!entry) {
    return <span className={className} style={style}>{fallback || id}</span>;
  }

  const label = isTechnical ? entry.technical : entry.business;
  const tooltipText = entry.tooltip;

  return (
    <span
      className={`diq-term ${className}`}
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: '0.25rem',
        ...style,
      }}
      title={tooltipText}
    >
      <span>{label}</span>
      {showTooltip && tooltipText && !isTechnical && (
        <span
          style={{
            cursor: 'help',
            color: 'var(--text-muted)',
            display: 'inline-flex',
            alignItems: 'center',
          }}
        >
          <HelpCircle size={13} />
        </span>
      )}
    </span>
  );
}
