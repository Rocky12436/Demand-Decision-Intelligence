import React from 'react';

/**
 * DataTable component
 * Enterprise table: right-aligned numbers, tabular-nums, sticky header, row hover,
 * clear column widths, status badges, single action per row max.
 */
export default function DataTable({
  columns = [],
  data = [],
  keyField = 'id',
  onRowClick,
  selectedRowId,
  emptyMessage = 'No records found.',
  className = '',
  style = {},
}) {
  return (
    <div
      style={{
        overflowX: 'auto',
        width: '100%',
        backgroundColor: '#ffffff',
        border: '1px solid var(--border-subtle)',
        borderRadius: 'var(--border-radius-lg)',
        ...style,
      }}
      className={className}
    >
      <table
        style={{
          width: '100%',
          borderCollapse: 'collapse',
          fontSize: '13px',
          textAlign: 'left',
        }}
      >
        <thead>
          <tr
            style={{
              backgroundColor: 'var(--bg-surface-subtle)',
              borderBottom: '1px solid var(--border-subtle)',
              position: 'sticky',
              top: 0,
              zIndex: 1,
            }}
          >
            {columns.map((col, idx) => (
              <th
                key={col.key || idx}
                style={{
                  padding: '10px 14px',
                  fontSize: '11px',
                  fontWeight: 600,
                  textTransform: 'uppercase',
                  letterSpacing: '0.05em',
                  color: 'var(--text-muted)',
                  textAlign: col.align || (col.isNumeric ? 'right' : 'left'),
                  width: col.width || 'auto',
                  whiteSpace: 'nowrap',
                  ...col.headerStyle,
                }}
              >
                {col.title || col.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {data.length === 0 ? (
            <tr>
              <td
                colSpan={columns.length}
                style={{
                  padding: '36px 16px',
                  textAlign: 'center',
                  color: 'var(--text-muted)',
                  fontSize: '13px',
                }}
              >
                {emptyMessage}
              </td>
            </tr>
          ) : (
            data.map((row, rowIdx) => {
              const rowKey = row[keyField] ?? rowIdx;
              const isSelected = selectedRowId != null && selectedRowId === rowKey;
              const isClickable = Boolean(onRowClick);

              return (
                <tr
                  key={rowKey}
                  onClick={() => isClickable && onRowClick(row)}
                  style={{
                    borderBottom: rowIdx === data.length - 1 ? 'none' : '1px solid var(--border-subtle)',
                    backgroundColor: isSelected ? 'var(--accent-primary-subtle)' : '#ffffff',
                    cursor: isClickable ? 'pointer' : 'default',
                    transition: 'background-color 0.1s ease',
                  }}
                  onMouseEnter={(e) => {
                    if (!isSelected) e.currentTarget.style.backgroundColor = 'var(--bg-surface-subtle)';
                  }}
                  onMouseLeave={(e) => {
                    if (!isSelected) e.currentTarget.style.backgroundColor = '#ffffff';
                  }}
                >
                  {columns.map((col, colIdx) => {
                    const isNum = col.isNumeric || col.align === 'right';
                    let val;
                    if (col.render) {
                      try {
                        val = col.render(row[col.key], row, rowIdx);
                      } catch {
                        val = col.render(row, row, rowIdx);
                      }
                    } else {
                      val = row[col.key];
                    }

                    return (
                      <td
                        key={col.key || colIdx}
                        className={isNum ? 'tabular-nums' : ''}
                        style={{
                          padding: '11px 14px',
                          textAlign: col.align || (isNum ? 'right' : 'left'),
                          color: col.color || 'var(--text-primary)',
                          fontFamily: col.mono ? 'var(--font-mono, monospace)' : 'inherit',
                          fontSize: '13px',
                          verticalAlign: 'middle',
                          ...col.cellStyle,
                        }}
                      >
                        {val != null ? val : '—'}
                      </td>
                    );
                  })}
                </tr>
              );
            })
          )}
        </tbody>
      </table>
    </div>
  );
}
