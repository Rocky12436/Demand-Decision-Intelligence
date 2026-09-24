import React from 'react';

/**
 * Lightweight Enterprise Markdown Viewer
 * Renders markdown headings, bold, bullet points, numbered lists, blockquotes, and tables
 * without external heavy parser dependencies.
 */
export default function MarkdownViewer({ content = '', className = '' }) {
  if (!content) return null;

  const lines = content.split('\n');
  const renderedElements = [];
  let tableRows = [];
  let inTable = false;
  let listItems = [];
  let inList = false;

  const flushTable = (key) => {
    if (tableRows.length === 0) return null;
    const isHeaderRow = (r) => r.every((c) => c.startsWith('---') || c.includes('---'));
    const validRows = tableRows.filter((r) => !isHeaderRow(r));
    if (validRows.length === 0) {
      tableRows = [];
      inTable = false;
      return null;
    }

    const header = validRows[0];
    const body = validRows.slice(1);

    const el = (
      <div
        key={`table-${key}`}
        style={{
          margin: '12px 0',
          overflowX: 'auto',
          borderRadius: 'var(--border-radius-md)',
          border: '1px solid var(--border-subtle)',
          backgroundColor: 'var(--bg-surface)',
        }}
      >
        <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left', fontSize: '12px' }}>
          <thead>
            <tr style={{ backgroundColor: 'var(--bg-surface-subtle)', borderBottom: '1px solid var(--border-subtle)' }}>
              {header.map((col, idx) => (
                <th key={idx} style={{ padding: '8px 12px', fontWeight: 600, color: 'var(--text-secondary)' }}>
                  {formatInlineText(col.trim())}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {body.map((row, rIdx) => (
              <tr key={rIdx} style={{ borderBottom: '1px solid var(--border-subtle)' }}>
                {row.map((cell, cIdx) => (
                  <td key={cIdx} style={{ padding: '8px 12px', color: 'var(--text-primary)' }}>
                    {formatInlineText(cell.trim())}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    );
    tableRows = [];
    inTable = false;
    return el;
  };

  const flushList = (key) => {
    if (listItems.length === 0) return null;
    const el = (
      <ul
        key={`list-${key}`}
        style={{
          margin: '8px 0',
          paddingLeft: '20px',
          display: 'flex',
          flexDirection: 'column',
          gap: '4px',
          listStyleType: 'disc',
        }}
      >
        {listItems.map((item, idx) => (
          <li key={idx} style={{ color: 'var(--text-primary)', fontSize: '13px', lineHeight: 1.5 }}>
            {formatInlineText(item)}
          </li>
        ))}
      </ul>
    );
    listItems = [];
    inList = false;
    return el;
  };

  for (let i = 0; i < lines.length; i++) {
    const rawLine = lines[i];
    const trimmed = rawLine.trim();

    // Table line
    if (trimmed.startsWith('|') && trimmed.endsWith('|')) {
      if (inList) renderedElements.push(flushList(i));
      inTable = true;
      const cells = trimmed
        .slice(1, -1)
        .split('|')
        .map((c) => c.trim());
      tableRows.push(cells);
      continue;
    } else if (inTable) {
      renderedElements.push(flushTable(i));
    }

    // List item (•, -, *, or 1.)
    if (trimmed.startsWith('• ') || trimmed.startsWith('- ') || trimmed.startsWith('* ')) {
      inList = true;
      listItems.push(trimmed.slice(2));
      continue;
    } else if (/^\d+\.\s/.test(trimmed)) {
      inList = true;
      listItems.push(trimmed.replace(/^\d+\.\s/, ''));
      continue;
    } else if (inList && trimmed === '') {
      renderedElements.push(flushList(i));
    }

    // Headings
    if (trimmed.startsWith('### ')) {
      renderedElements.push(
        <h3
          key={i}
          style={{
            fontSize: '14px',
            fontWeight: 700,
            color: 'var(--text-primary)',
            marginTop: '16px',
            marginBottom: '6px',
            letterSpacing: '-0.01em',
          }}
        >
          {formatInlineText(trimmed.slice(4))}
        </h3>
      );
      continue;
    }
    if (trimmed.startsWith('## ')) {
      renderedElements.push(
        <h2
          key={i}
          style={{
            fontSize: '16px',
            fontWeight: 700,
            color: 'var(--text-primary)',
            marginTop: '18px',
            marginBottom: '8px',
            borderBottom: '1px solid var(--border-subtle)',
            paddingBottom: '4px',
          }}
        >
          {formatInlineText(trimmed.slice(3))}
        </h2>
      );
      continue;
    }
    if (trimmed.startsWith('# ')) {
      renderedElements.push(
        <h1
          key={i}
          style={{
            fontSize: '18px',
            fontWeight: 800,
            color: 'var(--text-primary)',
            marginTop: '20px',
            marginBottom: '10px',
          }}
        >
          {formatInlineText(trimmed.slice(2))}
        </h1>
      );
      continue;
    }

    // Blockquote
    if (trimmed.startsWith('> ')) {
      renderedElements.push(
        <blockquote
          key={i}
          style={{
            margin: '8px 0',
            padding: '8px 14px',
            backgroundColor: 'var(--accent-primary-subtle)',
            borderLeft: '3px solid var(--accent-primary)',
            borderRadius: '0 var(--border-radius-sm) var(--border-radius-sm) 0',
            fontSize: '12px',
            color: 'var(--text-secondary)',
          }}
        >
          {formatInlineText(trimmed.slice(2))}
        </blockquote>
      );
      continue;
    }

    // Regular paragraph
    if (trimmed !== '') {
      renderedElements.push(
        <p
          key={i}
          style={{
            margin: '6px 0',
            fontSize: '13px',
            lineHeight: 1.6,
            color: 'var(--text-primary)',
          }}
        >
          {formatInlineText(trimmed)}
        </p>
      );
    }
  }

  if (inTable) renderedElements.push(flushTable(lines.length));
  if (inList) renderedElements.push(flushList(lines.length));

  return <div className={className}>{renderedElements}</div>;
}

/**
 * Parses bold (**text**), code (`text`), and italic (*text*) into React nodes
 */
function formatInlineText(text) {
  if (!text) return text;
  // Regex to split by bold or code spans
  const parts = [];
  const regex = /(\*\*.*?\*\*|`.*?`)/g;
  let lastIdx = 0;
  let match;

  while ((match = regex.exec(text)) !== null) {
    if (match.index > lastIdx) {
      parts.push(text.substring(lastIdx, match.index));
    }
    const token = match[0];
    if (token.startsWith('**') && token.endsWith('**')) {
      parts.push(
        <strong key={match.index} style={{ fontWeight: 600, color: 'var(--text-primary)' }}>
          {token.slice(2, -2)}
        </strong>
      );
    } else if (token.startsWith('`') && token.endsWith('`')) {
      parts.push(
        <code
          key={match.index}
          style={{
            backgroundColor: 'var(--bg-surface-subtle)',
            border: '1px solid var(--border-subtle)',
            padding: '1px 5px',
            borderRadius: 'var(--border-radius-sm)',
            fontFamily: 'var(--font-mono)',
            fontSize: '11px',
            color: 'var(--accent-primary-text)',
          }}
        >
          {token.slice(1, -1)}
        </code>
      );
    }
    lastIdx = regex.lastIndex;
  }

  if (lastIdx < text.length) {
    parts.push(text.substring(lastIdx));
  }

  return parts.length > 0 ? parts : text;
}
