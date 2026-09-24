/**
 * DemandIQ Single Source of Truth Glossary
 * Translates complex inventory, forecasting, and data science jargon into plain business language
 * tailored for non-technical retail and inventory store managers in India.
 */

export const GLOSSARY = {
  sku: {
    business: 'Product',
    technical: 'SKU',
    tooltip: 'Unique identification code for each item in your inventory.',
  },
  wape: {
    business: 'Forecast Error',
    technical: 'WAPE (Weighted Absolute Percentage Error)',
    tooltip: 'Average percentage error in sales predictions across all items. Lower is better.',
    unitSuffix: '(lower is better)',
  },
  mae: {
    business: 'Average Unit Error',
    technical: 'MAE (Mean Absolute Error)',
    tooltip: 'Average deviation in physical units between predicted and actual sales.',
  },
  rmse: {
    business: 'Peak Error Sensitivity',
    technical: 'RMSE (Root Mean Square Error)',
    tooltip: 'Emphasizes large forecasting errors or unexpected demand spikes.',
  },
  rop: {
    business: 'Reorder Level',
    technical: 'ROP (Reorder Point)',
    tooltip: 'When current inventory drops to this level, place a new order immediately to avoid running out.',
  },
  safety_stock: {
    business: 'Buffer Stock',
    technical: 'Safety Stock',
    tooltip: 'Emergency reserve units kept on hand to protect against sudden sales surges or delivery delays.',
  },
  moq: {
    business: 'Minimum Order Quantity',
    technical: 'MOQ',
    tooltip: 'Smallest order quantity your supplier accepts for this item.',
  },
  service_level: {
    business: 'In-Stock Protection Target',
    technical: 'Target Service Level (Z-factor)',
    tooltip: 'The probability (e.g. 95%) that a customer will find this product in stock when they want to buy.',
  },
  lead_time: {
    business: 'Supplier Delivery Time',
    technical: 'Lead Time (Days)',
    tooltip: 'Number of calendar days between placing an order and items arriving at your warehouse.',
  },
  review_period: {
    business: 'Order Review Frequency',
    technical: 'Review Period (R)',
    tooltip: 'How often (in days) you check inventory and create replenishment purchase orders.',
  },
  working_capital: {
    business: 'Money Tied Up in Stock',
    technical: 'Working Capital Exposure',
    tooltip: 'Total purchase cost invested in inventory currently sitting on shelves or in transit.',
  },
  holding_cost: {
    business: 'Cost of Storing Stock',
    technical: 'Annual Inventory Carrying Cost',
    tooltip: 'Expense of warehouse space, capital interest, insurance, and handling fees.',
  },
  lost_demand: {
    business: 'Sales Lost From Stockouts',
    technical: 'Unmet Demand / Stockout Cost',
    tooltip: 'Estimated revenue lost because customers arrived to buy but the product was out of stock.',
  },
  psi: {
    business: 'Sales Pattern Shift',
    technical: 'PSI (Population Stability Index)',
    tooltip: 'Detects if customer purchasing habits have changed significantly compared to previous seasons.',
  },
  drift_detected: {
    business: 'Sales Pattern Changed',
    technical: 'DRIFT_DETECTED (PSI > 0.25)',
    tooltip: 'Sales patterns have shifted enough that the forecasting model needs updating.',
  },
  retrain: {
    business: 'Refresh Forecast',
    technical: 'Scheduled Model Retrain',
    tooltip: 'Re-trains prediction models with the latest sales records to restore peak accuracy.',
  },
  champion_model: {
    business: 'Best Forecasting Method',
    technical: 'Champion Model',
    tooltip: 'The prediction algorithm that proved most accurate in recent test evaluations for this product.',
  },
  heuristics_fallback: {
    business: 'Simple Average Forecast',
    technical: 'Moving Average / Naive Heuristic',
    tooltip: 'Conservative backup method used when data history is short or undergoing quality audit.',
  },
  upsert_replace: {
    business: 'Replace Old Data',
    technical: 'Idempotent Overwrite Mode',
    tooltip: 'Overwrites existing daily sales numbers for matching dates with the new uploaded file.',
  },
  upsert_accumulate: {
    business: 'Add to Existing Data',
    technical: 'Incremental Accumulate Mode',
    tooltip: 'Adds new sales numbers to existing quantities rather than replacing them.',
  },
  dead_stock: {
    business: "Stock That Isn't Selling",
    technical: 'Non-Moving / Obsolete Inventory',
    tooltip: 'Inventory with zero sales over recent weeks that is trapping capital and shelf space.',
  },
  abc_xyz: {
    business: 'Top Sellers vs. Unpredictable Items',
    technical: 'ABC-XYZ Demand Classification Matrix',
    tooltip: 'Classifies products by revenue impact (A/B/C) and sales predictability (X/Y/Z).',
  },
  forecast_reliability: {
    business: 'Forecast Reliability',
    technical: 'Fleet Model Accuracy',
    tooltip: 'Overall reliability rating based on error metrics across active products.',
  },
  sales_at_risk: {
    business: 'Sales at Risk',
    technical: 'Stockout Value Exposure',
    tooltip: 'Total rupee revenue threatened by products dangerously close to running out.',
  },
  data_quality: {
    business: 'Data Health Score',
    technical: 'Composite Quality Scorecard',
    tooltip: 'Automated audit checking for missing dates, zero-cost errors, duplicates, and outliers.',
  },
};

/**
 * Helper to get translated term based on active mode (simple vs technical).
 */
export function getTerm(id, isTechnical = false) {
  const entry = GLOSSARY[id];
  if (!entry) return id;
  return isTechnical ? entry.technical : entry.business;
}

export function getTooltip(id) {
  return GLOSSARY[id]?.tooltip || '';
}
