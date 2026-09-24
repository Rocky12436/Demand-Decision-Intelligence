/**
 * Sanitized CSV Exporter
 * Prevents CSV Formula Injection (CWE-1236) by escaping leading dangerous characters:
 * '=', '+', '-', '@', '\t', '\r'
 */

export function sanitizeCsvCell(value) {
  if (value === null || value === undefined) {
    return '""';
  }

  let str = String(value);

  // If cell starts with dangerous formula prefixes, neutralize with a leading single quote
  const dangerousPrefixes = ["=", "+", "-", "@", "\t", "\r"];
  if (dangerousPrefixes.some((prefix) => str.startsWith(prefix))) {
    str = `'${str}`;
  }

  // Escape internal double quotes by doubling them
  str = str.replace(/"/g, '""');

  return `"${str}"`;
}

export function exportToCsv(filename, headers, rows) {
  if (!rows || rows.length === 0) {
    console.warn("No rows to export.");
    return;
  }

  const csvRows = [];

  // Header row
  const headerRow = headers.map((h) => sanitizeCsvCell(h.label || h.key || h)).join(",");
  csvRows.push(headerRow);

  // Data rows
  rows.forEach((row) => {
    const rowValues = headers.map((h) => {
      const key = h.key || h;
      const val = row[key];
      return sanitizeCsvCell(val);
    });
    csvRows.push(rowValues.join(","));
  });

  const csvString = csvRows.join("\r\n");
  const blob = new Blob([csvString], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);

  const link = document.createElement("a");
  link.setAttribute("href", url);
  link.setAttribute("download", filename.endsWith(".csv") ? filename : `${filename}.csv`);
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
}
