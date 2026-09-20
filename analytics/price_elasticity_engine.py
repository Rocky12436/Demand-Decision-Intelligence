"""
Price Elasticity & Discount Optimization Engine (Stage 7)
Project: Demand-Decision-Intelligence System

Logic:
- Log-Log regression model to compute Price Elasticity of Demand (PED = % change in quantity / % change in price)
  ln(Q) = beta_0 + beta_1 * ln(P)
  where beta_1 is PED.
- Classify SKUs:
  - Elastic (PED < -1)
  - Inelastic (-1 <= PED <= 0)
  - Anomalous (PED > 0)
- Discount Sensitivity: Calculate optimal discount range and projected revenue impact.
"""

import os
import json
import numpy as np
import pandas as pd
from pathlib import Path
from typing import Dict, List, Any, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEMAND_CSV = PROJECT_ROOT / "dataset" / "processed" / "daily_product_demand.csv"
PRODUCT_CSV = PROJECT_ROOT / "dataset" / "raw" / "products" / "dim_product.csv"
REPORT_JSON = PROJECT_ROOT / "reports" / "price_elasticity_report.json"


class PriceElasticityEngine:
    def __init__(self, demand_path: Path = DEMAND_CSV, product_path: Path = PRODUCT_CSV):
        self.demand_path = demand_path
        self.product_path = product_path
        self.product_meta = {}
        self._load_metadata()

    def _load_metadata(self):
        """Loads product metadata (name, category, brand) from dim_product.csv if available."""
        if self.product_path.exists():
            try:
                df_prod = pd.read_csv(self.product_path)
                for _, row in df_prod.iterrows():
                    pid = int(row["product_id"])
                    self.product_meta[pid] = {
                        "product_name": str(row.get("product_name", f"SKU #{pid}")),
                        "l0_category": str(row.get("l0_category", "General")),
                        "l1_category": str(row.get("l1_category", "General")),
                        "l2_category": str(row.get("l2_category", "General")),
                        "brand_name": str(row.get("brand_name", "Generic")) if pd.notna(row.get("brand_name")) else "Generic",
                    }
            except Exception as e:
                print(f"Warning loading product metadata: {e}")

    def run_analysis(self, min_samples: int = 5) -> Dict[str, Any]:
        """Runs log-log regression per SKU to compute PED, classification, and recommendations."""
        if not self.demand_path.exists():
            raise FileNotFoundError(f"Demand file not found: {self.demand_path}")

        # Read demand dataset
        df = pd.read_csv(self.demand_path)

        # Filter positive quantity and revenue
        df = df[(df["daily_quantity"] > 0) & (df["daily_revenue"] > 0)].copy()
        df["unit_price"] = df["daily_revenue"] / df["daily_quantity"]

        results = []
        
        # Group by product_id
        grouped = df.groupby("product_id")

        for product_id, group in grouped:
            n_obs = len(group)
            if n_obs < min_samples:
                continue

            prices = group["unit_price"].values
            quantities = group["daily_quantity"].values

            # Filter valid positive numbers for log
            valid_mask = (prices > 0) & (quantities > 0)
            if valid_mask.sum() < min_samples:
                continue

            log_p = np.log(prices[valid_mask])
            log_q = np.log(quantities[valid_mask])

            # Check price variance
            p_std = np.std(log_p)
            if p_std < 1e-4:
                # Virtually fixed price, default PED coefficient to slightly elastic (-1.15) or category estimate
                ped = -1.15
            else:
                # OLS regression: ln(Q) = beta_0 + beta_1 * ln(P)
                # beta_1 is PED
                slope, intercept = np.polyfit(log_p, log_q, 1)
                ped = float(slope)

            # Cap extreme noisy estimates to realistic economic range [-5.0, 3.0]
            ped_bounded = max(-5.0, min(3.0, round(ped, 3)))

            # Classification logic
            if ped_bounded < -1.0:
                category = "Elastic"
            elif -1.0 <= ped_bounded <= 0.0:
                category = "Inelastic"
            else:
                category = "Anomalous"

            base_price = float(np.mean(prices))
            base_daily_qty = float(np.mean(quantities))
            base_daily_revenue = float(base_price * base_daily_qty)

            # Calculate Optimal Discount & Pricing Recommendation
            if category == "Elastic":
                # For elastic products, a moderate discount stimulates demand and increases total revenue
                # Test discounts 5%, 10%, 15%, 20%
                best_discount = 0.10  # default 10%
                max_revenue_gain = 0.0

                for d in [0.05, 0.10, 0.15, 0.20]:
                    # % change in price = -d
                    # % change in qty = ped_bounded * (-d) = -ped_bounded * d (>0)
                    pct_delta_q = -ped_bounded * d
                    new_p = base_price * (1 - d)
                    new_q = base_daily_qty * (1 + pct_delta_q)
                    new_rev = new_p * new_q
                    rev_gain = new_rev - base_daily_revenue
                    if rev_gain > max_revenue_gain:
                        max_revenue_gain = rev_gain
                        best_discount = d

                recommended_discount_pct = round(best_discount * 100, 1)
                optimal_price = round(base_price * (1 - best_discount), 2)
                proj_vol_change_pct = round(-ped_bounded * best_discount * 100, 1)
                proj_revenue_impact_pct = round((max_revenue_gain / base_daily_revenue) * 100, 1) if base_daily_revenue > 0 else 0.0
                action_text = f"Apply {recommended_discount_pct}% discount to boost volume by +{proj_vol_change_pct}%."

            elif category == "Inelastic":
                # For inelastic products, discounts erode revenue. Recommend 0% discount or slight premium.
                recommended_discount_pct = 0.0
                optimal_price = round(base_price, 2)
                proj_vol_change_pct = 0.0
                proj_revenue_impact_pct = 0.0
                action_text = "Maintain price / 0% discount. Inelastic demand ensures steady margins."

            else:  # Anomalous (PED > 0)
                recommended_discount_pct = 0.0
                optimal_price = round(base_price, 2)
                proj_vol_change_pct = 0.0
                proj_revenue_impact_pct = 0.0
                action_text = "Flagged for pricing audit. Positive price-quantity correlation detected."

            meta = self.product_meta.get(int(product_id), {})
            product_name = meta.get("product_name", f"SKU #{product_id}")
            l0_cat = meta.get("l0_category", "General")
            l1_cat = meta.get("l1_category", "General")
            brand = meta.get("brand_name", "Generic")

            results.append({
                "product_id": int(product_id),
                "product_name": product_name,
                "category": l0_cat,
                "sub_category": l1_cat,
                "brand": brand,
                "observations": int(n_obs),
                "avg_unit_price": round(base_price, 2),
                "avg_daily_quantity": round(base_daily_qty, 1),
                "avg_daily_revenue": round(base_daily_revenue, 2),
                "price_elasticity": ped_bounded,
                "classification": category,
                "recommended_discount_pct": recommended_discount_pct,
                "optimal_price": optimal_price,
                "projected_vol_change_pct": proj_vol_change_pct,
                "projected_revenue_impact_pct": proj_revenue_impact_pct,
                "action_recommendation": action_text
            })

        # Sort results by total daily revenue descending
        results.sort(key=lambda x: x["avg_daily_revenue"], reverse=True)

        # Summary statistics
        elastic_count = sum(1 for r in results if r["classification"] == "Elastic")
        inelastic_count = sum(1 for r in results if r["classification"] == "Inelastic")
        anomalous_count = sum(1 for r in results if r["classification"] == "Anomalous")
        total_skus = len(results)
        avg_elasticity = round(float(np.mean([r["price_elasticity"] for r in results])), 3) if total_skus > 0 else 0.0

        output_data = {
            "status": "success",
            "metadata": {
                "total_analyzed_skus": total_skus,
                "elastic_count": elastic_count,
                "inelastic_count": inelastic_count,
                "anomalous_count": anomalous_count,
                "avg_price_elasticity": avg_elasticity,
                "methodology": "Log-Log Ordinary Least Squares (OLS) Regression"
            },
            "skus": results
        }

        # Save precomputed report
        REPORT_JSON.parent.mkdir(parents=True, exist_ok=True)
        with open(REPORT_JSON, "w") as f:
            json.dump(output_data, f, indent=2)

        print(f"Price Elasticity analysis completed: {total_skus} SKUs analyzed. Saved to {REPORT_JSON}")
        return output_data


if __name__ == "__main__":
    engine = PriceElasticityEngine()
    engine.run_analysis()
