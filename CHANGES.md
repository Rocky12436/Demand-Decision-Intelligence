# Changes Summary: Demand Forecasting Studio Redesign

## Overview
Redesigned the Demand Forecasting Studio (`/forecast`) with a **Simple First, Technical on Demand** product architecture. mart owners can understand expected sales, recommended restocking quantities, and forecast trustworthiness in under 10 seconds, while technical users can toggle into an audit panel with full backtest leaderboards, holdout calibration, and glossary tooltips.

---

## 1. Backend Accuracy, Models, and Traceability

### Fixed Bugs & Engine Upgrades
1. **Model Independence & Skipped Recording (Bug 1)**:
   - Previously, requesting multiple models resulted in duplicate `Ridge_LagFeatures` runs.
   - Now, candidate models (`Naive`, `SeasonalNaive`, `MovingAverage_7D`, `Ridge_LagFeatures`, `Croston_SBA`) run as independent candidates.
   - If a model is ineligible (e.g., history < 60 days for Ridge, history < 120 days for Prophet), the system records `status="SKIPPED"` on `forecast_runs` along with a plain-language `skip_reason` (e.g. `"Ridge_LagFeatures needs at least 60 days of history; this item has only 31 days"`).
2. **Idempotent Runs (Bug 2)**:
   - Added `data_version_hash` (SHA-256 of `dataset_id|product_id|as_of_date`) to `forecast_runs`.
   - Before executing a model, the engine checks for an existing completed run with valid backtest metrics. If present, it reuses the run to avoid duplicate database inserts.
3. **Non-Flat Forecasts & Widening Intervals (Bug 3)**:
   - Aggregated sales per unique calendar date across store locations so history represents true daily demand.
   - Incorporated day-of-week seasonality (DOW) and Indian holiday/festival markers.
   - Prediction interval widths grow with $\sqrt{\text{horizon}}$ steps to reflect compounding forward uncertainty.
4. **Chronological Walk-Forward Backtesting (No Data Leakage)**:
   - Walk-forward backtest evaluated across chronological test folds.
   - Guaranteed zero leakage: `train_d[-1] < test_d[0]` strictly enforced.
   - Calculated metrics: WAPE (%), MAE, RMSE, signed bias, and pinball loss.
5. **Champion Selection Rule**:
   - Champion selected by lowest median WAPE across backtest folds.
   - **Critical Rule**: A champion is **never** declared unless at least 2 models actually ran.
   - If the winning model fails to beat the Seasonal Naive baseline by at least 5%, Seasonal Naive is recommended with a clear notice.
6. **Transparent Confidence Rating**:
   - `HIGH`, `MEDIUM`, or `LOW` computed using transparent rules on observation count, relative improvement over baseline, holdout interval coverage, and SKU intermittency (ADI/CV²).

### API Contract
- `GET /api/forecast/summary?sku={sku}&horizon={7|14|30}`: Unified endpoint providing SKU metadata, headline numbers, daily quantiles (q05..q95), recent history, reliability metrics, model leaderboard, and inventory advice.
- `GET /api/forecast/skus`: Returns top products in the active dataset with product name, category, brand, and SKU code for the searchable dropdown.
- `POST /api/forecast/run`: Asynchronously triggers model computation in a background thread and immediately returns `job_id`.
- `GET /api/forecast/jobs/{job_id}`: Polls the status and progress of background forecasting jobs.

### Database Migration
- Alembic revision `012_forecast_traceability`:
  - Added `model_requested`, `skip_reason`, `data_version_hash`, `history_obs_count`, and `job_id` columns to `forecast_runs`.
  - Added `bias`, `improvement_vs_naive_pct`, `fold_index`, `pinball_loss`, `coverage_50`, and `coverage_90` to `forecast_evaluations`.
  - Created `forecast_jobs` table for asynchronous job tracking.

---

## 2. Frontend Redesign

### Design Principle: Answer First, Evidence Second, Jargon Last
- **Default View: Simple View**
  - All numbers are plain language (no technical acronyms like WAPE, q05, or ADI).
  - Jargon mapped to intuitive concepts:
    - *WAPE* $\rightarrow$ "average forecast error (%)"
    - *q05 to q95* $\rightarrow$ "likely range"
    - *Safety stock* $\rightarrow$ "extra buffer stock"
    - *Reorder point* $\rightarrow$ "order when stock falls to"
    - *Intermittent* $\rightarrow$ "sells only some days"
    - *Champion model* $\rightarrow$ "best method for this item"
- **Toggle View: Technical View**
  - Switches on the `TechnicalPanel` containing the full candidate leaderboard, skipped model audit, holdout calibration percentages, inventory calculation parameters, and interactive glossary tooltips.

### Modular Components
1. `useForecastSummary.js`: Custom hook providing automatic cached fetching on SKU/horizon changes, background polling during refresh, error handling, and retry logic.
2. `ForecastHeader.jsx`: Searchable product dropdown (search by name, category, or SKU code), horizon pills (Next 7, 14, 30 days), "Refresh forecast" button with animated progress, "Download CSV" export, and Technical View switch.
3. `AnswerCards.jsx`: Three high-impact summary cards:
   - Expected sales in horizon with likely low/high bounds.
   - Suggested action (order units, reorder trigger, and buffer stock).
   - Trust rating (Confidence badge + one-sentence plain-language rationale).
4. `ForecastChart.jsx`: Responsive Recharts chart bridging the last 60 days of actual historical sales into the forecasted trajectory with a shaded 90% likely range, Indian festival markers, and plain-language tooltips.
5. `ReliabilityCard.jsx`: Plain-language past accuracy comparison ("off by X% vs Y% for simple baseline, Z% better"), visual comparison bars, and traffic-light badge.
6. `NoticeList.jsx`: High-contrast WCAG AA alerts for limited data history, intermittent sales patterns, and simulated inventory assumptions, including a direct button to Data Upload.
7. `TechnicalPanel.jsx`: Detailed model leaderboard table, skipped reasons, calibration coverage, inventory assumptions, and glossary definitions for every acronym.

---

## 3. Assumptions & Verification
- **Inventory & Lead Time Assumptions**: Supplier lead time defaults to 7 days and current stock is simulated when external stock feeds have not been uploaded. These assumptions are transparently stated in the UI.
- **Traceability**: All numbers displayed on the frontend originate directly from the `/api/forecast/summary` endpoint; no hardcoded or mock values are used.
- **Test Suite**: 10 unit and integration tests passing in `tests/test_forecast_accuracy.py` covering metric calculations, zero leakage walk-forward splits, skipped-model recording, champion rules, and confidence rules.
