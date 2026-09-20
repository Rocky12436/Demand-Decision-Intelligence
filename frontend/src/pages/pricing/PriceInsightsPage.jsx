import React, { useState, useEffect, useMemo } from "react";
import { Link } from "react-router-dom";
import { getPricingElasticity, recalculateElasticity } from "../../services/api";

export default function PriceInsightsPage() {
  const [loading, setLoading] = useState(true);
  const [recalculating, setRecalculating] = useState(false);
  const [error, setError] = useState("");
  const [data, setData] = useState(null);

  // Filters & State
  const [filterClass, setFilterClass] = useState("ALL");
  const [searchTerm, setSearchTerm] = useState("");
  const [selectedCategory, setSelectedCategory] = useState("ALL");

  // Simulator State
  const [selectedSkuId, setSelectedSkuId] = useState(null);
  const [simDiscount, setSimDiscount] = useState(10); // percentage 0-30%

  useEffect(() => {
    fetchInsights();
  }, []);

  const fetchInsights = async () => {
    try {
      setLoading(true);
      setError("");
      const res = await getPricingElasticity(500);
      setData(res);
      if (res.skus && res.skus.length > 0) {
        setSelectedSkuId(res.skus[0].product_id);
      }
    } catch (err) {
      setError(err.message || "Failed to load pricing elasticity data.");
    } finally {
      setLoading(false);
    }
  };

  const handleRecalculate = async () => {
    try {
      setRecalculating(true);
      await recalculateElasticity();
      await fetchInsights();
    } catch (err) {
      alert("Error recalculating elasticity: " + err.message);
    } finally {
      setRecalculating(false);
    }
  };

  // Filtered SKUs
  const filteredSkus = useMemo(() => {
    if (!data || !data.skus) return [];
    return data.skus.filter((sku) => {
      const matchClass =
        filterClass === "ALL" ||
        sku.classification.toUpperCase() === filterClass.toUpperCase();
      const matchSearch =
        sku.product_name.toLowerCase().includes(searchTerm.toLowerCase()) ||
        sku.brand.toLowerCase().includes(searchTerm.toLowerCase()) ||
        String(sku.product_id).includes(searchTerm);
      const matchCategory =
        selectedCategory === "ALL" ||
        sku.category.toLowerCase() === selectedCategory.toLowerCase();
      return matchClass && matchSearch && matchCategory;
    });
  }, [data, filterClass, searchTerm, selectedCategory]);

  // Unique Categories
  const categories = useMemo(() => {
    if (!data || !data.skus) return [];
    const setCat = new Set(data.skus.map((s) => s.category));
    return Array.from(setCat);
  }, [data]);

  // Selected SKU for Simulator
  const selectedSku = useMemo(() => {
    if (!data || !data.skus) return null;
    return data.skus.find((s) => s.product_id === selectedSkuId) || data.skus[0];
  }, [data, selectedSkuId]);

  // Dynamic Simulation Calculations
  const simResults = useMemo(() => {
    if (!selectedSku) return null;
    const baseP = selectedSku.avg_unit_price;
    const baseQ = selectedSku.avg_daily_quantity;
    const baseR = selectedSku.avg_daily_revenue;
    const ped = selectedSku.price_elasticity;

    const discountDec = simDiscount / 100;
    const simPrice = Math.max(0.01, baseP * (1 - discountDec));
    // % Change in Volume = PED * (% Change in Price) = PED * (-discountDec) = -PED * discountDec
    const pctVolChange = -ped * discountDec;
    const simQty = baseQ * (1 + pctVolChange);
    const simRevenue = simPrice * simQty;
    const revUplift = simRevenue - baseR;
    const revUpliftPct = baseR > 0 ? (revUplift / baseR) * 100 : 0;

    let marginOpportunity = "Neutral";
    if (ped < -1 && revUplift > 0) marginOpportunity = "High Volume & Revenue Uplift";
    else if (ped >= -1 && ped <= 0 && simDiscount > 0) marginOpportunity = "Revenue Dilution Risk (Inelastic)";
    else if (ped > 0) marginOpportunity = "Anomalous Price-Quantity Dynamics";

    return {
      basePrice: baseP.toFixed(2),
      simPrice: simPrice.toFixed(2),
      baseQty: baseQ.toFixed(1),
      simQty: simQty.toFixed(1),
      pctVolChange: (pctVolChange * 100).toFixed(1),
      baseRev: baseR.toLocaleString('en-IN', { maximumFractionDigits: 2 }),
      simRev: simRevenue.toLocaleString('en-IN', { maximumFractionDigits: 2 }),
      revUplift: revUplift.toLocaleString('en-IN', { maximumFractionDigits: 2 }),
      revUpliftPct: revUpliftPct.toFixed(1),
      marginOpportunity,
    };
  }, [selectedSku, simDiscount]);

  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[60vh] space-y-4">
        <div className="w-12 h-12 border-4 border-indigo-600 border-t-transparent rounded-full animate-spin"></div>
        <p className="text-gray-600 font-medium animate-pulse">
          Computing Price Elasticity Log-Log Models...
        </p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-8 max-w-4xl mx-auto">
        <div className="p-6 bg-red-50 border border-red-200 rounded-2xl text-red-700 space-y-3">
          <h3 className="text-lg font-bold flex items-center gap-2">
            ⚠️ Error Loading Price Insights
          </h3>
          <p>{error}</p>
          <button
            onClick={fetchInsights}
            className="px-4 py-2 bg-red-600 text-white font-semibold rounded-lg hover:bg-red-700 transition"
          >
            Retry Loading
          </button>
        </div>
      </div>
    );
  }

  const meta = data?.metadata || {};

  return (
    <div className="p-6 max-w-7xl mx-auto space-y-8">
      {/* Header Banner */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 bg-gradient-to-r from-slate-900 via-indigo-950 to-slate-900 text-white p-6 rounded-2xl shadow-xl">
        <div>
          <div className="inline-flex items-center gap-2 px-3 py-1 bg-indigo-500/20 text-indigo-300 border border-indigo-500/30 text-xs font-semibold rounded-full mb-2">
            Stage 7 • Log-Log OLS Regression Model
          </div>
          <h1 className="text-3xl font-extrabold tracking-tight">
            Price Elasticity & Discount Insights Engine
          </h1>
          <p className="text-slate-300 text-sm mt-1">
            Analyze Price Elasticity of Demand (PED), classify SKU sensitivity, and dynamically simulate optimal discount strategies.
          </p>
        </div>
        <div className="flex items-center gap-3 flex-wrap">
          <Link
            to="/market-prices"
            className="inline-flex items-center gap-2 px-4 py-3 bg-slate-800 hover:bg-slate-700 text-cyan-300 border border-cyan-500/30 font-semibold rounded-xl transition shadow-lg text-sm"
          >
            <span>🏛️ Live Govt PMD Rates</span>
          </Link>
          <button
            onClick={handleRecalculate}
            disabled={recalculating}
            className="inline-flex items-center gap-2 px-5 py-3 bg-indigo-600 hover:bg-indigo-500 text-white font-semibold rounded-xl transition shadow-lg disabled:opacity-50"
          >
            {recalculating ? (
              <>
                <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin"></div>
                <span>Recalculating...</span>
              </>
            ) : (
              <>
                <span>⚡ Recalculate Model</span>
              </>
            )}
          </button>
        </div>
      </div>

      {/* Metric Cards Grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-4">
        <div className="p-5 bg-white border border-gray-100 rounded-2xl shadow-sm hover:shadow-md transition">
          <p className="text-xs font-medium text-gray-500 uppercase tracking-wider">Analyzed SKUs</p>
          <div className="text-2xl font-bold text-gray-900 mt-1">{meta.total_analyzed_skus || 0}</div>
          <p className="text-xs text-gray-400 mt-1">Total active products</p>
        </div>

        <div className="p-5 bg-white border border-emerald-100 rounded-2xl shadow-sm hover:shadow-md transition">
          <p className="text-xs font-medium text-emerald-600 uppercase tracking-wider">Elastic SKUs</p>
          <div className="text-2xl font-bold text-emerald-700 mt-1">{meta.elastic_count || 0}</div>
          <p className="text-xs text-emerald-600/80 mt-1">PED &lt; -1.0 (Discount Responsive)</p>
        </div>

        <div className="p-5 bg-white border border-blue-100 rounded-2xl shadow-sm hover:shadow-md transition">
          <p className="text-xs font-medium text-blue-600 uppercase tracking-wider">Inelastic SKUs</p>
          <div className="text-2xl font-bold text-blue-700 mt-1">{meta.inelastic_count || 0}</div>
          <p className="text-xs text-blue-600/80 mt-1">-1.0 ≤ PED ≤ 0.0 (Margin Steady)</p>
        </div>

        <div className="p-5 bg-white border border-amber-100 rounded-2xl shadow-sm hover:shadow-md transition">
          <p className="text-xs font-medium text-amber-600 uppercase tracking-wider">Anomalous SKUs</p>
          <div className="text-2xl font-bold text-amber-700 mt-1">{meta.anomalous_count || 0}</div>
          <p className="text-xs text-amber-600/80 mt-1">PED &gt; 0.0 (Audit Flagged)</p>
        </div>

        <div className="p-5 bg-white border border-indigo-100 rounded-2xl shadow-sm hover:shadow-md transition">
          <p className="text-xs font-medium text-indigo-600 uppercase tracking-wider">Avg Price Elasticity</p>
          <div className="text-2xl font-bold text-indigo-700 mt-1">{meta.avg_price_elasticity || 0}</div>
          <p className="text-xs text-indigo-600/80 mt-1">Log-log mean coefficient</p>
        </div>
      </div>

      {/* Discount Simulator Card */}
      {selectedSku && simResults && (
        <div className="bg-gradient-to-br from-indigo-900 to-slate-900 text-white rounded-3xl p-6 shadow-xl space-y-6">
          <div className="flex flex-col md:flex-row md:items-center justify-between border-b border-indigo-800/60 pb-4 gap-4">
            <div>
              <span className="text-xs font-semibold text-indigo-300 uppercase tracking-widest">
                Interactive Discount Simulator
              </span>
              <h2 className="text-xl font-bold text-white mt-1">
                Real-Time Price & Revenue Impact Calculator
              </h2>
            </div>

            {/* SKU Dropdown Selector */}
            <div className="w-full md:w-80">
              <label className="block text-xs font-medium text-indigo-200 mb-1">
                Select Product for Simulation:
              </label>
              <select
                value={selectedSku.product_id}
                onChange={(e) => setSelectedSkuId(Number(e.target.value))}
                className="w-full px-3 py-2 bg-indigo-950/80 border border-indigo-700 rounded-xl text-white text-sm focus:ring-2 focus:ring-indigo-400 outline-none"
              >
                {data.skus.map((s) => (
                  <option key={s.product_id} value={s.product_id}>
                    {s.product_name} (₹{s.avg_unit_price} • PED: {s.price_elasticity})
                  </option>
                ))}
              </select>
            </div>
          </div>

          {/* Slider & Metrics Row */}
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-8 items-center">
            {/* Slider Control */}
            <div className="lg:col-span-5 space-y-4 bg-indigo-950/50 p-5 rounded-2xl border border-indigo-800/40">
              <div className="flex justify-between items-center">
                <span className="text-sm font-semibold text-indigo-200">
                  Simulated Discount Rate:
                </span>
                <span className="text-2xl font-black text-indigo-400">
                  {simDiscount}%
                </span>
              </div>
              <input
                type="range"
                min="0"
                max="30"
                step="1"
                value={simDiscount}
                onChange={(e) => setSimDiscount(Number(e.target.value))}
                className="w-full h-2 bg-indigo-900 rounded-lg appearance-none cursor-pointer accent-indigo-400"
              />
              <div className="flex justify-between text-xs text-indigo-300">
                <span>0% (Full Price)</span>
                <span>15% (Recommended)</span>
                <span>30% (Max Promo)</span>
              </div>
              <div className="p-3 bg-indigo-900/60 rounded-xl border border-indigo-700/50 text-xs text-indigo-200 space-y-1">
                <p>
                  <strong>Category:</strong> {selectedSku.category} • <strong>Brand:</strong> {selectedSku.brand}
                </p>
                <p>
                  <strong>PED Coefficient:</strong>{" "}
                  <span className={selectedSku.price_elasticity < -1 ? "text-emerald-300 font-bold" : "text-amber-300 font-bold"}>
                    {selectedSku.price_elasticity} ({selectedSku.classification})
                  </span>
                </p>
              </div>
            </div>

            {/* Impact Metric Cards */}
            <div className="lg:col-span-7 grid grid-cols-1 sm:grid-cols-3 gap-4">
              <div className="bg-slate-800/80 border border-slate-700 p-4 rounded-2xl">
                <p className="text-xs font-medium text-slate-400">Unit Price Impact</p>
                <div className="text-xl font-bold text-white mt-1">₹{simResults.simPrice}</div>
                <p className="text-xs text-slate-400 mt-1 line-through">Base: ₹{simResults.basePrice}</p>
              </div>

              <div className="bg-slate-800/80 border border-slate-700 p-4 rounded-2xl">
                <p className="text-xs font-medium text-slate-400">Projected Volume Gain</p>
                <div className="text-xl font-bold text-emerald-400 mt-1">
                  +{simResults.pctVolChange}%
                </div>
                <p className="text-xs text-slate-400 mt-1">{simResults.simQty} units/day</p>
              </div>

              <div className="bg-slate-800/80 border border-slate-700 p-4 rounded-2xl">
                <p className="text-xs font-medium text-slate-400">Daily Revenue Uplift</p>
                <div className={`text-xl font-bold mt-1 ${Number(simResults.revUpliftPct) >= 0 ? 'text-indigo-300' : 'text-rose-400'}`}>
                  {Number(simResults.revUpliftPct) >= 0 ? '+' : ''}{simResults.revUpliftPct}%
                </div>
                <p className="text-xs text-slate-400 mt-1">₹{simResults.simRev} / day</p>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Main Insights Data Table */}
      <div className="bg-white border border-gray-200 rounded-3xl shadow-sm overflow-hidden space-y-4">
        {/* Table Toolbar */}
        <div className="p-6 border-b border-gray-100 flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div>
            <h3 className="text-lg font-bold text-gray-900">
              SKU Price Elasticity & Recommendation Matrix
            </h3>
            <p className="text-xs text-gray-500 mt-0.5">
              Showing {filteredSkus.length} product elasticity profiles
            </p>
          </div>

          <div className="flex flex-wrap items-center gap-3">
            {/* Search Bar */}
            <input
              type="text"
              placeholder="Search SKU name or brand..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              className="px-4 py-2 border border-gray-300 rounded-xl text-sm focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 outline-none w-60"
            />

            {/* Category Filter */}
            <select
              value={selectedCategory}
              onChange={(e) => setSelectedCategory(e.target.value)}
              className="px-3 py-2 border border-gray-300 rounded-xl text-sm focus:ring-2 focus:ring-indigo-500 outline-none"
            >
              <option value="ALL">All Categories</option>
              {categories.map((cat) => (
                <option key={cat} value={cat}>
                  {cat}
                </option>
              ))}
            </select>

            {/* Elasticity Class Tabs */}
            <div className="flex bg-gray-100 p-1 rounded-xl">
              {["ALL", "Elastic", "Inelastic", "Anomalous"].map((cls) => (
                <button
                  key={cls}
                  onClick={() => setFilterClass(cls)}
                  className={`px-3 py-1.5 text-xs font-semibold rounded-lg transition ${
                    filterClass === cls
                      ? "bg-white text-indigo-700 shadow-sm"
                      : "text-gray-600 hover:text-gray-900"
                  }`}
                >
                  {cls}
                </button>
              ))}
            </div>
          </div>
        </div>

        {/* Data Table */}
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm border-collapse">
            <thead>
              <tr className="bg-gray-50 border-b border-gray-200 text-xs font-semibold text-gray-500 uppercase tracking-wider">
                <th className="py-3.5 px-4">SKU & Product Name</th>
                <th className="py-3.5 px-4">Category & Brand</th>
                <th className="py-3.5 px-4">Avg Price (₹)</th>
                <th className="py-3.5 px-4">PED Coeff</th>
                <th className="py-3.5 px-4">Elasticity Class</th>
                <th className="py-3.5 px-4">Rec. Discount</th>
                <th className="py-3.5 px-4">Optimal Price</th>
                <th className="py-3.5 px-4">Proj. Rev Uplift</th>
                <th className="py-3.5 px-4">Action Recommendation</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {filteredSkus.length === 0 ? (
                <tr>
                  <td colSpan="9" className="text-center py-8 text-gray-400">
                    No matching SKUs found for selected filters.
                  </td>
                </tr>
              ) : (
                filteredSkus.map((sku) => (
                  <tr
                    key={sku.product_id}
                    className="hover:bg-indigo-50/40 transition cursor-pointer"
                    onClick={() => setSelectedSkuId(sku.product_id)}
                  >
                    <td className="py-3.5 px-4 font-semibold text-gray-900">
                      <div>{sku.product_name}</div>
                      <div className="text-xs font-normal text-gray-400">ID: #{sku.product_id}</div>
                    </td>
                    <td className="py-3.5 px-4 text-gray-600">
                      <div>{sku.category}</div>
                      <div className="text-xs text-gray-400">{sku.brand}</div>
                    </td>
                    <td className="py-3.5 px-4 font-medium text-gray-800">
                      ₹{sku.avg_unit_price.toFixed(2)}
                    </td>
                    <td className="py-3.5 px-4 font-mono font-bold text-gray-900">
                      {sku.price_elasticity}
                    </td>
                    <td className="py-3.5 px-4">
                      {sku.classification === "Elastic" && (
                        <span className="inline-flex items-center px-2.5 py-1 rounded-full text-xs font-semibold bg-emerald-100 text-emerald-800">
                          Elastic
                        </span>
                      )}
                      {sku.classification === "Inelastic" && (
                        <span className="inline-flex items-center px-2.5 py-1 rounded-full text-xs font-semibold bg-blue-100 text-blue-800">
                          Inelastic
                        </span>
                      )}
                      {sku.classification === "Anomalous" && (
                        <span className="inline-flex items-center px-2.5 py-1 rounded-full text-xs font-semibold bg-amber-100 text-amber-800">
                          Anomalous
                        </span>
                      )}
                    </td>
                    <td className="py-3.5 px-4 font-semibold text-indigo-600">
                      {sku.recommended_discount_pct}%
                    </td>
                    <td className="py-3.5 px-4 font-bold text-gray-900">
                      ₹{sku.optimal_price.toFixed(2)}
                    </td>
                    <td className="py-3.5 px-4 font-semibold text-emerald-600">
                      +{sku.projected_revenue_impact_pct}%
                    </td>
                    <td className="py-3.5 px-4 text-xs text-gray-600 max-w-xs">
                      {sku.action_recommendation}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
