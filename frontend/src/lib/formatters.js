/**
 * Safe formatting utilities for Indian enterprise SaaS applications (en-IN).
 * Never crashes, never displays "NaN" or "Invalid Date", always displays "—" for missing values.
 */

/**
 * Format currency in Indian Rupees (₹) with Indian digit grouping (e.g. ₹2,50,000).
 * Optionally compacts large numbers into Lakhs (L) and Crores (Cr).
 */
export function formatINR(value, options = {}) {
  if (value == null || isNaN(value)) return '—';
  const num = Number(value);
  const { compact = false, maxFractionDigits = 1 } = options;

  if (compact) {
    const abs = Math.abs(num);
    if (abs >= 10000000) {
      // 1 Crore = 10,000,000 (100 Lakhs)
      return `₹${(num / 10000000).toFixed(maxFractionDigits)} Cr`;
    }
    if (abs >= 100000) {
      // 1 Lakh = 100,000
      return `₹${(num / 100000).toFixed(maxFractionDigits)} L`;
    }
    if (abs >= 1000) {
      return `₹${(num / 1000).toFixed(maxFractionDigits)} K`;
    }
  }

  return new Intl.NumberFormat('en-IN', {
    style: 'currency',
    currency: 'INR',
    maximumFractionDigits: maxFractionDigits,
  }).format(num);
}

/**
 * Format plain numbers using Indian number grouping (e.g. 12,50,000).
 */
export function formatNumber(value, options = {}) {
  if (value == null || isNaN(value)) return '—';
  const num = Number(value);
  const { compact = false, maxFractionDigits = 1 } = options;

  if (compact) {
    const abs = Math.abs(num);
    if (abs >= 10000000) {
      return `${(num / 10000000).toFixed(maxFractionDigits)} Cr`;
    }
    if (abs >= 100000) {
      return `${(num / 100000).toFixed(maxFractionDigits)} L`;
    }
    if (abs >= 1000) {
      return `${(num / 1000).toFixed(maxFractionDigits)} K`;
    }
  }

  return new Intl.NumberFormat('en-IN', {
    maximumFractionDigits: maxFractionDigits,
  }).format(num);
}

/**
 * Format percentage (e.g. 14.8%). Max 1 decimal place.
 */
export function formatPercent(value, maxFractionDigits = 1) {
  if (value == null || isNaN(value)) return '—';
  const num = Number(value);
  return `${num.toFixed(maxFractionDigits)}%`;
}

/**
 * Safe date formatter. Returns formatted date like "21 Sep 2026" or "—". Never returns "Invalid Date".
 */
export function formatDate(dateInput, includeTime = false) {
  if (!dateInput) return '—';
  try {
    const d = new Date(dateInput);
    if (isNaN(d.getTime())) return '—';

    const day = d.getDate();
    const monthNames = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
    const month = monthNames[d.getMonth()];
    const year = d.getFullYear();

    if (!includeTime) {
      return `${day} ${month} ${year}`;
    }

    const hours = String(d.getHours()).padStart(2, '0');
    const minutes = String(d.getMinutes()).padStart(2, '0');
    return `${day} ${month} ${year}, ${hours}:${minutes}`;
  } catch {
    return '—';
  }
}
