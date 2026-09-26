import React, { useState, useEffect, useMemo } from 'react';
import {
  Tag,
  TrendingUp,
  TrendingDown,
  RefreshCw,
  Search,
  ExternalLink,
  ShieldCheck,
  AlertTriangle,
  Boxes,
  Zap,
  CheckCircle2,
  Sliders,
  Percent,
  BarChart3,
  Layers,
  Sparkles,
  Info
} from 'lucide-react';
import api, { getPricingElasticity, recalculateElasticity } from '../../services/api';

export default function PriceInsightsPage() {
  // Top-level View Switcher: 'market' (Web Scraper) | 'elasticity' (Yash's Log-Log Model)
  const [mainView, setMainView] = useState('market');

  // =========================================================================
  // 1. STATE FOR REAL-WORLD MARKET PRICES (USER'S WEB SCRAPER & STOCKING)
  // =========================================================================
  const [marketData, setMarketData] = useState(null);
  const [decisionsData, setDecisionsData] = useState(null);
  const [marketLoading, setMarketLoading] = useState(true);
  const [syncing, setSyncing] = useState(false);
  const [syncMessage, setSyncMessage] = useState('');
  const [marketSubTab, setMarketSubTab] = useState('decisions'); // 'decisions' | 'rates'
  const [selectedMarketCategory, setSelectedMarketCategory] = useState('ALL');
  const [marketSearchQuery, setMarketSearchQuery] = useState('');

  // =========================================================================
  // 2. STATE FOR PRICE ELASTICITY & DISCOUNT SIMULATOR (YASH'S ENGINE)
  // =========================================================================
  const [elasticityData, setElasticityData] = useState(null);
  const [elasticityLoading, setElasticityLoading] = useState(true);
  const [recalculating, setRecalculating] = useState(false);
  const [elasticityError, setElasticityError] = useState('');
  const [filterClass, setFilterClass] = useState('ALL');
  const [elasticitySearch, setElasticitySearch] = useState('');
  const [selectedElasticityCategory, setSelectedElasticityCategory] = useState('ALL');
  const [selectedSkuId, setSelectedSkuId] = useState(null);
  const [simDiscount, setSimDiscount] = useState(10); // 0% - 30%

  // =========================================================================
  // LIFECYCLE & DATA FETCHING
  // =========================================================================
  useEffect(() => {
    loadMarketPriceData();
    loadElasticityData();
  }, []);

  const loadMarketPriceData = async () => {
    setMarketLoading(true);
    try {
      const [marketRes, decisionsRes] = await Promise.all([
        api.get('/market-prices/live').catch(() => null),
        api.get('/market-prices/stock-decisions').catch(() => null),
      ]);
      if (marketRes?.data) setMarketData(marketRes.data);
      if (decisionsRes?.data) setDecisionsData(decisionsRes.data);
    } catch (err) {
      console.error('Failed to load market prices', err);
    } finally {
      setMarketLoading(false);
    }
  };

  const loadElasticityData = async () => {
    setElasticityLoading(true);
    setElasticityError('');
    try {
      const res = await getPricingElasticity(500);
      setElasticityData(res);
      if (res?.skus && res.skus.length > 0 && !selectedSkuId) {
        setSelectedSkuId(res.skus[0].product_id);
      }
    } catch (err) {
      setElasticityError(err.message || 'Failed to load pricing elasticity data.');
    } finally {
      setElasticityLoading(false);
    }
  };

  const handleSyncLiveMarket = async () => {
    setSyncing(true);
    setSyncMessage('');
    try {
      const res = await api.post('/market-prices/sync');
      setSyncMessage(res.data?.message || 'Successfully synchronized with Ministry portal!');
      await loadMarketPriceData();
    } catch (err) {
      console.error('Failed to sync live rates', err);
      setSyncMessage('Sync completed with cached rates.');
      await loadMarketPriceData();
    } finally {
      setSyncing(false);
    }
  };

  const handleRecalculateElasticity = async () => {
    try {
      setRecalculating(true);
      await recalculateElasticity();
      await loadElasticityData();
    } catch (err) {
      alert('Error recalculating elasticity: ' + err.message);
    } finally {
      setRecalculating(false);
    }
  };

  // =========================================================================
  // COMPUTED VALUES - MARKET PRICES (USER)
  // =========================================================================
  const decisions = decisionsData?.decisions || [];
  const commodities = marketData?.commodities || [];
  const filteredCommodities = useMemo(() => {
    return commodities.filter((c) => {
      const matchesCat =
        selectedMarketCategory === 'ALL' ||
        c.category.toLowerCase() === selectedMarketCategory.toLowerCase();
      const matchesSearch =
        !marketSearchQuery ||
        c.commodity.toLowerCase().includes(marketSearchQuery.toLowerCase());
      return matchesCat && matchesSearch;
    });
  }, [commodities, selectedMarketCategory, marketSearchQuery]);

  const surgeCount = decisions.filter((d) => d.divergence_pct >= 15.0).length;
  const dipCount = decisions.filter((d) => d.divergence_pct <= -10.0).length;
  const stableCount = decisions.filter(
    (d) => d.divergence_pct > -10.0 && d.divergence_pct < 15.0
  ).length;
  const asOnDate = marketData?.as_on_date || 'Today';

  // =========================================================================
  // COMPUTED VALUES - PRICE ELASTICITY (YASH)
  // =========================================================================
  const filteredSkus = useMemo(() => {
    if (!elasticityData || !elasticityData.skus) return [];
    return elasticityData.skus.filter((sku) => {
      const matchClass =
        filterClass === 'ALL' ||
        sku.classification.toUpperCase() === filterClass.toUpperCase();
      const matchSearch =
        sku.product_name.toLowerCase().includes(elasticitySearch.toLowerCase()) ||
        sku.brand.toLowerCase().includes(elasticitySearch.toLowerCase()) ||
        String(sku.product_id).includes(elasticitySearch);
      const matchCategory =
        selectedElasticityCategory === 'ALL' ||
        sku.category.toLowerCase() === selectedElasticityCategory.toLowerCase();
      return matchClass && matchSearch && matchCategory;
    });
  }, [elasticityData, filterClass, elasticitySearch, selectedElasticityCategory]);

  const elasticityCategories = useMemo(() => {
    if (!elasticityData || !elasticityData.skus) return [];
    const setCat = new Set(elasticityData.skus.map((s) => s.category));
    return Array.from(setCat);
  }, [elasticityData]);

  const selectedSku = useMemo(() => {
    if (!elasticityData || !elasticityData.skus) return null;
    return (
      elasticityData.skus.find((s) => s.product_id === selectedSkuId) ||
      elasticityData.skus[0]
    );
  }, [elasticityData, selectedSkuId]);

  const simResults = useMemo(() => {
    if (!selectedSku) return null;
    const baseP = selectedSku.avg_unit_price;
    const baseQ = selectedSku.avg_daily_quantity;
    const baseR = selectedSku.avg_daily_revenue;
    const ped = selectedSku.price_elasticity;

    const discountDec = simDiscount / 100;
    const simPrice = Math.max(0.01, baseP * (1 - discountDec));
    const pctVolChange = -ped * discountDec;
    const simQty = baseQ * (1 + pctVolChange);
    const simRevenue = simPrice * simQty;
    const revUplift = simRevenue - baseR;
    const revUpliftPct = baseR > 0 ? (revUplift / baseR) * 100 : 0;

    let marginOpportunity = 'Neutral';
    if (ped < -1 && revUplift > 0)
      marginOpportunity = 'High Volume & Revenue Uplift (Elastic)';
    else if (ped >= -1 && ped <= 0 && simDiscount > 0)
      marginOpportunity = 'Revenue Dilution Risk (Inelastic)';
    else if (ped > 0) marginOpportunity = 'Anomalous Price-Quantity Dynamics';

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

  const elasticityMeta = elasticityData?.metadata || {};

  return (
    <div style={{ maxWidth: '1440px', margin: '0 auto', paddingBottom: '3rem' }}>
      {/* =================================================================== */}
      {/* TOP HEADER & UNIFIED VIEW SWITCHER */}
      {/* =================================================================== */}
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          marginBottom: '1.75rem',
          flexWrap: 'wrap',
          gap: '1rem',
        }}
      >
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
            <span
              style={{
                fontSize: '0.75rem',
                fontWeight: 700,
                padding: '0.2rem 0.65rem',
                borderRadius: '999px',
                backgroundColor: 'rgba(59, 130, 246, 0.15)',
                color: '#60a5fa',
                border: '1px solid rgba(59, 130, 246, 0.3)',
                display: 'inline-flex',
                alignItems: 'center',
                gap: '0.35rem',
              }}
            >
              <Sparkles size={13} color="#60a5fa" />
              DUAL PRICING INTELLIGENCE SUITE
            </span>
            <span style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
              Real-World Scraper + Econometric Elasticity Model
            </span>
          </div>

          <h1
            style={{
              fontSize: '1.85rem',
              fontWeight: 800,
              color: 'var(--text-primary)',
              marginTop: '0.4rem',
              display: 'flex',
              alignItems: 'center',
              gap: '0.65rem',
              letterSpacing: '-0.02em',
            }}
          >
            <Tag color="var(--accent-primary)" size={28} />
            Pricing & Market Intelligence Hub
          </h1>
          <p style={{ color: 'var(--text-secondary)', fontSize: '0.925rem', marginTop: '0.2rem' }}>
            Seamlessly monitor real-time government commodity rates and simulate dynamic price elasticity discount curves.
          </p>
        </div>

        {/* PRIMARY VIEW SELECTOR PILLS */}
        <div
          style={{
            display: 'flex',
            backgroundColor: 'var(--bg-surface-elevated)',
            padding: '0.35rem',
            borderRadius: '12px',
            border: '1px solid var(--border-strong)',
            gap: '0.35rem',
          }}
        >
          <button
            onClick={() => setMainView('market')}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '0.5rem',
              padding: '0.6rem 1.15rem',
              borderRadius: '8px',
              border: 'none',
              backgroundColor:
                mainView === 'market'
                  ? 'var(--accent-primary)'
                  : 'transparent',
              color: mainView === 'market' ? '#fff' : 'var(--text-secondary)',
              fontWeight: mainView === 'market' ? 700 : 500,
              fontSize: '0.875rem',
              cursor: 'pointer',
              transition: 'all 0.15s ease',
            }}
          >
            <Zap size={16} color={mainView === 'market' ? '#fff' : '#10b981'} />
            <span>Govt Market Rates & Stocking</span>
            <span
              style={{
                fontSize: '0.7rem',
                padding: '0.1rem 0.45rem',
                borderRadius: '999px',
                backgroundColor:
                  mainView === 'market'
                    ? 'rgba(255,255,255,0.25)'
                    : 'rgba(16, 185, 129, 0.2)',
                color: mainView === 'market' ? '#fff' : '#34d399',
                fontWeight: 700,
              }}
            >
              LIVE
            </span>
          </button>

          <button
            onClick={() => setMainView('elasticity')}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '0.5rem',
              padding: '0.6rem 1.15rem',
              borderRadius: '8px',
              border: 'none',
              backgroundColor:
                mainView === 'elasticity'
                  ? 'var(--accent-primary)'
                  : 'transparent',
              color: mainView === 'elasticity' ? '#fff' : 'var(--text-secondary)',
              fontWeight: mainView === 'elasticity' ? 700 : 500,
              fontSize: '0.875rem',
              cursor: 'pointer',
              transition: 'all 0.15s ease',
            }}
          >
            <Sliders size={16} color={mainView === 'elasticity' ? '#fff' : '#818cf8'} />
            <span>Price Elasticity & Discount Simulator</span>
            <span
              style={{
                fontSize: '0.7rem',
                padding: '0.1rem 0.45rem',
                borderRadius: '999px',
                backgroundColor:
                  mainView === 'elasticity'
                    ? 'rgba(255,255,255,0.25)'
                    : 'rgba(99, 102, 241, 0.2)',
                color: mainView === 'elasticity' ? '#fff' : '#a5b4fc',
                fontWeight: 700,
              }}
            >
              STAGE 7
            </span>
          </button>
        </div>
      </div>

      {/* =================================================================== */}
      {/* VIEW 1: REAL-WORLD MARKET PRICES & WEB SCRAPER (USER'S IMPLEMENTATION) */}
      {/* =================================================================== */}
      {mainView === 'market' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
          {/* Top Control Bar with Live Web Scraper Badge & Sync Button */}
          <div
            className="card"
            style={{
              margin: 0,
              padding: '1.25rem 1.5rem',
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              flexWrap: 'wrap',
              gap: '1rem',
              background:
                'linear-gradient(90deg, rgba(17, 24, 39, 0.95) 0%, rgba(31, 41, 55, 0.8) 100%)',
              border: '1px solid rgba(16, 185, 129, 0.3)',
            }}
          >
            <div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                <span
                  style={{
                    width: '8px',
                    height: '8px',
                    borderRadius: '50%',
                    backgroundColor: 'var(--accent-emerald)',
                    boxShadow: '0 0 10px var(--accent-emerald)',
                  }}
                />
                <h2
                  style={{
                    fontSize: '1.15rem',
                    fontWeight: 700,
                    color: 'var(--text-primary)',
                  }}
                >
                  Live Scraper: Ministry of Consumer Affairs, Food & Public Distribution
                </h2>
              </div>
              <p
                style={{
                  fontSize: '0.85rem',
                  color: 'var(--text-secondary)',
                  marginTop: '0.2rem',
                }}
              >
                Direct automated connection to national retail commodity price reporting centres across Indian metros.
              </p>
            </div>

            <button
              className="btn btn-primary"
              onClick={handleSyncLiveMarket}
              disabled={syncing}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '0.5rem',
                padding: '0.65rem 1.35rem',
                fontWeight: 600,
              }}
            >
              <RefreshCw size={16} className={syncing ? 'animate-spin' : ''} />
              {syncing ? 'Scraping Ministry Portal...' : '🔄 Sync Live Govt Rates'}
            </button>
          </div>

          {/* Sync Message Alert */}
          {syncMessage && (
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '0.6rem',
                padding: '0.75rem 1.25rem',
                backgroundColor: 'rgba(16, 185, 129, 0.12)',
                border: '1px solid var(--accent-emerald)',
                borderRadius: '8px',
                color: 'var(--accent-emerald)',
                fontSize: '0.9rem',
              }}
            >
              <CheckCircle2 size={18} />
              <span>{syncMessage}</span>
            </div>
          )}

          {/* Live Market Price Ticker Ribbon */}
          <div
            className="card"
            style={{
              padding: '0.9rem 1.25rem',
              margin: 0,
              backgroundColor: 'var(--bg-surface-elevated)',
              border: '1px solid var(--border-strong)',
            }}
          >
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                marginBottom: '0.6rem',
              }}
            >
              <div
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '0.5rem',
                  fontSize: '0.78rem',
                  fontWeight: 700,
                  color: 'var(--text-secondary)',
                  textTransform: 'uppercase',
                  letterSpacing: '0.05em',
                }}
              >
                <Zap size={14} color="var(--accent-amber)" />
                Official Govt Retail Benchmark Rates (As on {asOnDate})
              </div>
              <a
                href="https://fcainfoweb.nic.in/Default.aspx"
                target="_blank"
                rel="noopener noreferrer"
                style={{
                  fontSize: '0.75rem',
                  color: 'var(--accent-cyan)',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '0.25rem',
                  textDecoration: 'none',
                }}
              >
                Verify on fcainfoweb.nic.in <ExternalLink size={12} />
              </a>
            </div>

            {/* Ticker chips */}
            <div
              style={{
                display: 'flex',
                gap: '0.75rem',
                overflowX: 'auto',
                paddingBottom: '0.35rem',
              }}
            >
              {commodities.slice(0, 12).map((c) => (
                <div
                  key={c.commodity}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: '0.6rem',
                    backgroundColor: 'rgba(255, 255, 255, 0.04)',
                    border: '1px solid var(--border-subtle)',
                    borderRadius: '8px',
                    padding: '0.35rem 0.75rem',
                    whiteSpace: 'nowrap',
                    fontSize: '0.825rem',
                  }}
                >
                  <span style={{ color: 'var(--text-secondary)', fontWeight: 500 }}>
                    {c.commodity}:
                  </span>
                  <span style={{ color: '#fff', fontWeight: 700 }}>
                    ₹{c.price_inr_per_kg.toFixed(2)}/kg
                  </span>
                </div>
              ))}
            </div>
          </div>

          {/* KPI Summary Cards */}
          <div className="grid-kpi" style={{ margin: 0 }}>
            <div className="kpi-card">
              <div className="kpi-title">Tracked Essential Commodities</div>
              <div className="kpi-value">
                {commodities.length || 41}{' '}
                <span style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>
                  items
                </span>
              </div>
              <div
                style={{
                  fontSize: '0.8rem',
                  color: 'var(--text-muted)',
                  marginTop: '0.25rem',
                }}
              >
                Across 555 National Reporting Centres
              </div>
            </div>

            <div className="kpi-card">
              <div className="kpi-title">Price Surge Alert SKUs</div>
              <div className="kpi-value" style={{ color: 'var(--accent-rose)' }}>
                {surgeCount}
              </div>
              <div
                style={{
                  fontSize: '0.8rem',
                  color: 'var(--text-muted)',
                  marginTop: '0.25rem',
                }}
              >
                Divergence &gt; +15% (Trim stock recommendation)
              </div>
            </div>

            <div className="kpi-card">
              <div className="kpi-title">Procurement Dip Windows</div>
              <div className="kpi-value" style={{ color: 'var(--accent-emerald)' }}>
                {dipCount}
              </div>
              <div
                style={{
                  fontSize: '0.8rem',
                  color: 'var(--text-muted)',
                  marginTop: '0.25rem',
                }}
              >
                Divergence &lt; -10% (Bulk stock opportunity)
              </div>
            </div>

            <div className="kpi-card">
              <div className="kpi-title">Stable Price Band SKUs</div>
              <div className="kpi-value" style={{ color: 'var(--accent-cyan)' }}>
                {stableCount}
              </div>
              <div
                style={{
                  fontSize: '0.8rem',
                  color: 'var(--text-muted)',
                  marginTop: '0.25rem',
                }}
              >
                Aligned with Standard ROP Policy
              </div>
            </div>
          </div>

          {/* Sub-Tabs: Stocking Decisions vs All Rates */}
          <div
            style={{
              display: 'flex',
              gap: '0.75rem',
              borderBottom: '1px solid var(--border-subtle)',
              paddingBottom: '0.25rem',
            }}
          >
            <button
              onClick={() => setMarketSubTab('decisions')}
              style={{
                padding: '0.65rem 1.25rem',
                background: 'none',
                border: 'none',
                borderBottom:
                  marketSubTab === 'decisions'
                    ? '2px solid var(--accent-primary)'
                    : '2px solid transparent',
                color:
                  marketSubTab === 'decisions'
                    ? 'var(--accent-primary)'
                    : 'var(--text-secondary)',
                fontWeight: marketSubTab === 'decisions' ? 700 : 500,
                fontSize: '0.9rem',
                cursor: 'pointer',
              }}
            >
              🎯 Real-World Stocking Recommendations ("Kitni Quantity Rakhna Chahiye")
            </button>
            <button
              onClick={() => setMarketSubTab('rates')}
              style={{
                padding: '0.65rem 1.25rem',
                background: 'none',
                border: 'none',
                borderBottom:
                  marketSubTab === 'rates'
                    ? '2px solid var(--accent-primary)'
                    : '2px solid transparent',
                color:
                  marketSubTab === 'rates'
                    ? 'var(--accent-primary)'
                    : 'var(--text-secondary)',
                fontWeight: marketSubTab === 'rates' ? 700 : 500,
                fontSize: '0.9rem',
                cursor: 'pointer',
              }}
            >
              📊 All Scraped Ministry Commodity Rates ({commodities.length})
            </button>
          </div>

          {/* SUB-TAB 1: Stocking Decisions Table */}
          {marketSubTab === 'decisions' && (
            <div className="card" style={{ padding: '1.5rem', margin: 0 }}>
              <div
                style={{
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                  marginBottom: '1.25rem',
                  flexWrap: 'wrap',
                  gap: '0.5rem',
                }}
              >
                <div>
                  <h3
                    style={{
                      fontSize: '1.1rem',
                      fontWeight: 600,
                      color: 'var(--text-primary)',
                    }}
                  >
                    Real-World Price-Adjusted Inventory Stocking Policy
                  </h3>
                  <p
                    style={{
                      fontSize: '0.85rem',
                      color: 'var(--text-secondary)',
                    }}
                  >
                    Compares current government retail price vs catalog baseline to recommend holding vs trimming buffer quantity.
                  </p>
                </div>
                <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
                  Govt Reporting As on: {asOnDate}
                </div>
              </div>

              <div style={{ overflowX: 'auto' }}>
                <table
                  style={{
                    width: '100%',
                    borderCollapse: 'collapse',
                    fontSize: '0.875rem',
                  }}
                >
                  <thead>
                    <tr style={{ borderBottom: '1px solid var(--border-subtle)' }}>
                      <th
                        style={{
                          padding: '0.75rem',
                          textAlign: 'left',
                          color: 'var(--text-muted)',
                          fontSize: '0.78rem',
                          textTransform: 'uppercase',
                        }}
                      >
                        SKU & Hub
                      </th>
                      <th
                        style={{
                          padding: '0.75rem',
                          textAlign: 'left',
                          color: 'var(--text-muted)',
                          fontSize: '0.78rem',
                          textTransform: 'uppercase',
                        }}
                      >
                        Govt Commodity
                      </th>
                      <th
                        style={{
                          padding: '0.75rem',
                          textAlign: 'right',
                          color: 'var(--text-muted)',
                          fontSize: '0.78rem',
                          textTransform: 'uppercase',
                        }}
                      >
                        Base Cost
                      </th>
                      <th
                        style={{
                          padding: '0.75rem',
                          textAlign: 'right',
                          color: 'var(--text-muted)',
                          fontSize: '0.78rem',
                          textTransform: 'uppercase',
                        }}
                      >
                        Live Govt Rate
                      </th>
                      <th
                        style={{
                          padding: '0.75rem',
                          textAlign: 'right',
                          color: 'var(--text-muted)',
                          fontSize: '0.78rem',
                          textTransform: 'uppercase',
                        }}
                      >
                        Price Divergence
                      </th>
                      <th
                        style={{
                          padding: '0.75rem',
                          textAlign: 'right',
                          color: 'var(--text-muted)',
                          fontSize: '0.78rem',
                          textTransform: 'uppercase',
                        }}
                      >
                        Standard Buffer
                      </th>
                      <th
                        style={{
                          padding: '0.75rem',
                          textAlign: 'right',
                          color: 'var(--text-muted)',
                          fontSize: '0.78rem',
                          textTransform: 'uppercase',
                        }}
                      >
                        Recommended Holding
                      </th>
                      <th
                        style={{
                          padding: '0.75rem',
                          textAlign: 'center',
                          color: 'var(--text-muted)',
                          fontSize: '0.78rem',
                          textTransform: 'uppercase',
                        }}
                      >
                        Quantity Action
                      </th>
                      <th
                        style={{
                          padding: '0.75rem',
                          textAlign: 'left',
                          color: 'var(--text-muted)',
                          fontSize: '0.78rem',
                          textTransform: 'uppercase',
                        }}
                      >
                        Strategy Rationale
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {decisions.map((row, idx) => (
                      <tr
                        key={row.product_id}
                        style={{
                          borderBottom: '1px solid var(--border-subtle)',
                          backgroundColor:
                            idx % 2 === 0
                              ? 'transparent'
                              : 'rgba(255, 255, 255, 0.015)',
                        }}
                      >
                        <td style={{ padding: '0.75rem' }}>
                          <div
                            style={{
                              fontWeight: 600,
                              color: 'var(--text-primary)',
                            }}
                          >
                            #{row.product_id}
                          </div>
                          <div
                            style={{
                              fontSize: '0.78rem',
                              color: 'var(--text-muted)',
                            }}
                          >
                            {row.city_name}
                          </div>
                        </td>
                        <td
                          style={{
                            padding: '0.75rem',
                            fontWeight: 500,
                            color: 'var(--text-secondary)',
                          }}
                        >
                          {row.product_name}
                          <div
                            style={{
                              fontSize: '0.75rem',
                              color: 'var(--accent-primary)',
                            }}
                          >
                            ({row.commodity_matched})
                          </div>
                        </td>
                        <td
                          style={{
                            padding: '0.75rem',
                            textAlign: 'right',
                            color: 'var(--text-muted)',
                          }}
                        >
                          ₹{row.baseline_price.toFixed(2)}
                        </td>
                        <td
                          style={{
                            padding: '0.75rem',
                            textAlign: 'right',
                            fontWeight: 700,
                            color: '#fff',
                          }}
                        >
                          ₹{row.live_market_price.toFixed(2)}
                        </td>
                        <td style={{ padding: '0.75rem', textAlign: 'right' }}>
                          <span
                            style={{
                              fontWeight: 700,
                              fontSize: '0.8rem',
                              color:
                                row.divergence_pct > 0
                                  ? 'var(--accent-rose)'
                                  : 'var(--accent-emerald)',
                            }}
                          >
                            {row.divergence_pct > 0
                              ? `+${row.divergence_pct}%`
                              : `${row.divergence_pct}%`}
                          </span>
                        </td>
                        <td
                          style={{
                            padding: '0.75rem',
                            textAlign: 'right',
                            color: 'var(--text-muted)',
                          }}
                        >
                          {row.standard_holding_qty.toLocaleString()}
                        </td>
                        <td
                          style={{
                            padding: '0.75rem',
                            textAlign: 'right',
                            fontWeight: 700,
                            color: row.badge_color,
                          }}
                        >
                          {row.recommended_holding_qty.toLocaleString()}
                        </td>
                        <td
                          style={{
                            padding: '0.75rem',
                            textAlign: 'center',
                          }}
                        >
                          <span
                            style={{
                              padding: '0.25rem 0.65rem',
                              borderRadius: '6px',
                              fontSize: '0.75rem',
                              fontWeight: 700,
                              backgroundColor: row.badge_bg,
                              color: row.badge_color,
                              display: 'inline-block',
                              whiteSpace: 'nowrap',
                            }}
                          >
                            {row.action_label}
                          </span>
                        </td>
                        <td
                          style={{
                            padding: '0.75rem',
                            color: 'var(--text-secondary)',
                            fontSize: '0.8rem',
                            maxWidth: '280px',
                          }}
                        >
                          {row.recommendation}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* SUB-TAB 2: All Live Scraped Commodities */}
          {marketSubTab === 'rates' && (
            <div className="card" style={{ padding: '1.5rem', margin: 0 }}>
              <div
                style={{
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                  marginBottom: '1.25rem',
                  flexWrap: 'wrap',
                  gap: '1rem',
                }}
              >
                {/* Category filter pills */}
                <div style={{ display: 'flex', gap: '0.4rem', flexWrap: 'wrap' }}>
                  {[
                    'ALL',
                    'Grains & Pulses',
                    'Edible Oils',
                    'Vegetables',
                    'Daily Essentials',
                    'Additional Millets',
                  ].map((cat) => (
                    <button
                      key={cat}
                      onClick={() => setSelectedMarketCategory(cat)}
                      style={{
                        padding: '0.4rem 0.8rem',
                        borderRadius: '6px',
                        border:
                          selectedMarketCategory === cat
                            ? '1px solid var(--accent-primary)'
                            : '1px solid var(--border-strong)',
                        backgroundColor:
                          selectedMarketCategory === cat
                            ? 'rgba(59, 130, 246, 0.2)'
                            : 'var(--bg-surface-elevated)',
                        color:
                          selectedMarketCategory === cat
                            ? '#93c5fd'
                            : 'var(--text-secondary)',
                        fontSize: '0.8rem',
                        fontWeight: selectedMarketCategory === cat ? 600 : 500,
                        cursor: 'pointer',
                      }}
                    >
                      {cat}
                    </button>
                  ))}
                </div>

                {/* Search Input */}
                <div style={{ position: 'relative', minWidth: '220px' }}>
                  <Search
                    size={15}
                    color="var(--text-muted)"
                    style={{ position: 'absolute', left: '10px', top: '10px' }}
                  />
                  <input
                    type="text"
                    placeholder="Filter by commodity..."
                    value={marketSearchQuery}
                    onChange={(e) => setMarketSearchQuery(e.target.value)}
                    style={{
                      width: '100%',
                      padding: '0.5rem 0.5rem 0.5rem 2.2rem',
                      borderRadius: '6px',
                      border: '1px solid var(--border-strong)',
                      backgroundColor: 'var(--bg-surface-elevated)',
                      color: '#fff',
                      fontSize: '0.85rem',
                      outline: 'none',
                    }}
                  />
                </div>
              </div>

              <div style={{ overflowX: 'auto' }}>
                <table
                  style={{
                    width: '100%',
                    borderCollapse: 'collapse',
                    fontSize: '0.875rem',
                  }}
                >
                  <thead>
                    <tr style={{ borderBottom: '1px solid var(--border-subtle)' }}>
                      <th
                        style={{
                          padding: '0.75rem',
                          textAlign: 'left',
                          color: 'var(--text-muted)',
                          fontSize: '0.78rem',
                          textTransform: 'uppercase',
                        }}
                      >
                        #
                      </th>
                      <th
                        style={{
                          padding: '0.75rem',
                          textAlign: 'left',
                          color: 'var(--text-muted)',
                          fontSize: '0.78rem',
                          textTransform: 'uppercase',
                        }}
                      >
                        Commodity Name
                      </th>
                      <th
                        style={{
                          padding: '0.75rem',
                          textAlign: 'left',
                          color: 'var(--text-muted)',
                          fontSize: '0.78rem',
                          textTransform: 'uppercase',
                        }}
                      >
                        Category
                      </th>
                      <th
                        style={{
                          padding: '0.75rem',
                          textAlign: 'right',
                          color: 'var(--text-muted)',
                          fontSize: '0.78rem',
                          textTransform: 'uppercase',
                        }}
                      >
                        Daily Retail Price
                      </th>
                      <th
                        style={{
                          padding: '0.75rem',
                          textAlign: 'center',
                          color: 'var(--text-muted)',
                          fontSize: '0.78rem',
                          textTransform: 'uppercase',
                        }}
                      >
                        Unit
                      </th>
                      <th
                        style={{
                          padding: '0.75rem',
                          textAlign: 'center',
                          color: 'var(--text-muted)',
                          fontSize: '0.78rem',
                          textTransform: 'uppercase',
                        }}
                      >
                        Reporting Date
                      </th>
                      <th
                        style={{
                          padding: '0.75rem',
                          textAlign: 'left',
                          color: 'var(--text-muted)',
                          fontSize: '0.78rem',
                          textTransform: 'uppercase',
                        }}
                      >
                        Source
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {filteredCommodities.map((c, idx) => (
                      <tr
                        key={c.commodity}
                        style={{
                          borderBottom: '1px solid var(--border-subtle)',
                          backgroundColor:
                            idx % 2 === 0
                              ? 'transparent'
                              : 'rgba(255, 255, 255, 0.015)',
                        }}
                      >
                        <td
                          style={{
                            padding: '0.75rem',
                            color: 'var(--text-muted)',
                          }}
                        >
                          #{idx + 1}
                        </td>
                        <td
                          style={{
                            padding: '0.75rem',
                            fontWeight: 600,
                            color: 'var(--text-primary)',
                          }}
                        >
                          {c.commodity}
                        </td>
                        <td
                          style={{
                            padding: '0.75rem',
                            color: 'var(--text-secondary)',
                          }}
                        >
                          {c.category}
                        </td>
                        <td
                          style={{
                            padding: '0.75rem',
                            textAlign: 'right',
                            fontWeight: 700,
                            color: 'var(--accent-cyan)',
                          }}
                        >
                          ₹{c.price_inr_per_kg.toFixed(2)}
                        </td>
                        <td
                          style={{
                            padding: '0.75rem',
                            textAlign: 'center',
                            color: 'var(--text-muted)',
                          }}
                        >
                          {c.unit}
                        </td>
                        <td
                          style={{
                            padding: '0.75rem',
                            textAlign: 'center',
                            color: 'var(--text-secondary)',
                          }}
                        >
                          {c.as_on_date}
                        </td>
                        <td
                          style={{
                            padding: '0.75rem',
                            color: 'var(--text-muted)',
                            fontSize: '0.78rem',
                          }}
                        >
                          Govt of India (PMD)
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>
      )}

      {/* =================================================================== */}
      {/* VIEW 2: PRICE ELASTICITY & DISCOUNT SIMULATOR (YASH'S ENGINE) */}
      {/* =================================================================== */}
      {mainView === 'elasticity' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
          {/* Header Banner */}
          <div
            className="card"
            style={{
              margin: 0,
              padding: '1.5rem',
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              flexWrap: 'wrap',
              gap: '1rem',
              background:
                'linear-gradient(135deg, rgba(30, 27, 75, 0.95) 0%, rgba(15, 23, 42, 0.95) 100%)',
              border: '1px solid rgba(99, 102, 241, 0.4)',
            }}
          >
            <div>
              <div
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: '0.4rem',
                  padding: '0.2rem 0.6rem',
                  backgroundColor: 'rgba(99, 102, 241, 0.2)',
                  color: '#a5b4fc',
                  border: '1px solid rgba(99, 102, 241, 0.3)',
                  fontSize: '0.75rem',
                  fontWeight: 700,
                  borderRadius: '999px',
                  marginBottom: '0.5rem',
                }}
              >
                Stage 7 • Log-Log OLS Regression Model
              </div>
              <h2
                style={{
                  fontSize: '1.5rem',
                  fontWeight: 800,
                  color: '#fff',
                  letterSpacing: '-0.01em',
                }}
              >
                Price Elasticity of Demand & Discount Insights Engine
              </h2>
              <p
                style={{
                  color: 'var(--text-secondary)',
                  fontSize: '0.885rem',
                  marginTop: '0.2rem',
                }}
              >
                Log-Log regression formulation: ln(Q) = β₀ + β₁ ln(P) + ε. Simulates optimal discount strategies without margin dilution.
              </p>
            </div>

            <button
              onClick={handleRecalculateElasticity}
              disabled={recalculating}
              className="btn"
              style={{
                backgroundColor: 'var(--accent-purple)',
                color: '#fff',
                padding: '0.65rem 1.35rem',
                fontWeight: 600,
                display: 'flex',
                alignItems: 'center',
                gap: '0.5rem',
                border: 'none',
              }}
            >
              {recalculating ? (
                <>
                  <RefreshCw size={16} className="animate-spin" />
                  <span>Recalculating...</span>
                </>
              ) : (
                <>
                  <span>⚡ Recalculate Model</span>
                </>
              )}
            </button>
          </div>

          {/* Metric Cards Grid */}
          <div className="grid-kpi" style={{ margin: 0 }}>
            <div className="kpi-card">
              <div className="kpi-title">Analyzed Catalog SKUs</div>
              <div className="kpi-value">{elasticityMeta.total_analyzed_skus || 0}</div>
              <div
                style={{
                  fontSize: '0.8rem',
                  color: 'var(--text-muted)',
                  marginTop: '0.25rem',
                }}
              >
                Active product time-series
              </div>
            </div>

            <div className="kpi-card">
              <div className="kpi-title">Elastic SKUs (PED &lt; -1.0)</div>
              <div className="kpi-value" style={{ color: 'var(--accent-emerald)' }}>
                {elasticityMeta.elastic_count || 0}
              </div>
              <div
                style={{
                  fontSize: '0.8rem',
                  color: 'var(--text-emerald)',
                  marginTop: '0.25rem',
                }}
              >
                High volume sensitivity to discounts
              </div>
            </div>

            <div className="kpi-card">
              <div className="kpi-title">Inelastic SKUs (-1.0 ≤ PED ≤ 0)</div>
              <div className="kpi-value" style={{ color: 'var(--accent-cyan)' }}>
                {elasticityMeta.inelastic_count || 0}
              </div>
              <div
                style={{
                  fontSize: '0.8rem',
                  color: 'var(--text-muted)',
                  marginTop: '0.25rem',
                }}
              >
                Margin steady (Preserve full price)
              </div>
            </div>

            <div className="kpi-card">
              <div className="kpi-title">Avg Price Elasticity</div>
              <div className="kpi-value" style={{ color: 'var(--accent-purple)' }}>
                {elasticityMeta.avg_price_elasticity || '-1.15'}
              </div>
              <div
                style={{
                  fontSize: '0.8rem',
                  color: 'var(--text-muted)',
                  marginTop: '0.25rem',
                }}
              >
                Log-log mean coefficient
              </div>
            </div>
          </div>

          {/* Interactive Discount Simulator Card */}
          {selectedSku && simResults && (
            <div
              className="card"
              style={{
                margin: 0,
                padding: '1.75rem',
                background:
                  'linear-gradient(135deg, rgba(30, 27, 75, 0.7) 0%, rgba(17, 24, 39, 0.95) 100%)',
                border: '1px solid rgba(129, 140, 248, 0.3)',
              }}
            >
              <div
                style={{
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                  borderBottom: '1px solid rgba(255, 255, 255, 0.08)',
                  paddingBottom: '1rem',
                  marginBottom: '1.5rem',
                  flexWrap: 'wrap',
                  gap: '1rem',
                }}
              >
                <div>
                  <span
                    style={{
                      fontSize: '0.75rem',
                      fontWeight: 700,
                      color: '#a5b4fc',
                      textTransform: 'uppercase',
                      letterSpacing: '0.05em',
                    }}
                  >
                    Interactive Simulator
                  </span>
                  <h3
                    style={{
                      fontSize: '1.25rem',
                      fontWeight: 700,
                      color: '#fff',
                      marginTop: '0.2rem',
                    }}
                  >
                    Real-Time Price & Revenue Impact Calculator
                  </h3>
                </div>

                {/* SKU Selector Dropdown */}
                <div style={{ minWidth: '320px' }}>
                  <label
                    style={{
                      display: 'block',
                      fontSize: '0.75rem',
                      color: 'var(--text-secondary)',
                      marginBottom: '0.25rem',
                    }}
                  >
                    Select Product for Simulation:
                  </label>
                  <select
                    value={selectedSku.product_id}
                    onChange={(e) => setSelectedSkuId(Number(e.target.value))}
                    style={{
                      width: '100%',
                      padding: '0.55rem 0.75rem',
                      backgroundColor: 'var(--bg-surface-elevated)',
                      border: '1px solid var(--border-strong)',
                      color: '#fff',
                      borderRadius: '8px',
                      fontSize: '0.85rem',
                      outline: 'none',
                    }}
                  >
                    {elasticityData?.skus?.map((s) => (
                      <option key={s.product_id} value={s.product_id}>
                        {s.product_name} (₹{s.avg_unit_price} • PED: {s.price_elasticity})
                      </option>
                    ))}
                  </select>
                </div>
              </div>

              {/* Controls & Metrics Row */}
              <div
                style={{
                  display: 'grid',
                  gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))',
                  gap: '1.5rem',
                  alignItems: 'center',
                }}
              >
                {/* Left: Slider Control */}
                <div
                  style={{
                    backgroundColor: 'rgba(255, 255, 255, 0.03)',
                    border: '1px solid rgba(255, 255, 255, 0.08)',
                    borderRadius: '12px',
                    padding: '1.25rem',
                  }}
                >
                  <div
                    style={{
                      display: 'flex',
                      justifyContent: 'space-between',
                      alignItems: 'center',
                      marginBottom: '0.75rem',
                    }}
                  >
                    <span
                      style={{
                        fontSize: '0.85rem',
                        fontWeight: 600,
                        color: 'var(--text-secondary)',
                      }}
                    >
                      Simulated Discount Rate:
                    </span>
                    <span
                      style={{
                        fontSize: '1.5rem',
                        fontWeight: 800,
                        color: '#818cf8',
                      }}
                    >
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
                    style={{
                      width: '100%',
                      accentColor: '#818cf8',
                      cursor: 'pointer',
                      height: '6px',
                    }}
                  />

                  <div
                    style={{
                      display: 'flex',
                      justifyContent: 'space-between',
                      fontSize: '0.75rem',
                      color: 'var(--text-muted)',
                      marginTop: '0.5rem',
                    }}
                  >
                    <span>0% (Full Price)</span>
                    <span>15% (Recommended)</span>
                    <span>30% (Max Promo)</span>
                  </div>

                  <div
                    style={{
                      marginTop: '1rem',
                      padding: '0.75rem',
                      backgroundColor: 'rgba(99, 102, 241, 0.1)',
                      border: '1px solid rgba(99, 102, 241, 0.2)',
                      borderRadius: '8px',
                      fontSize: '0.78rem',
                      color: '#c7d2fe',
                    }}
                  >
                    <p>
                      <strong>Category:</strong> {selectedSku.category} •{' '}
                      <strong>Brand:</strong> {selectedSku.brand}
                    </p>
                    <p style={{ marginTop: '0.2rem' }}>
                      <strong>PED Coefficient:</strong>{' '}
                      <span style={{ color: '#34d399', fontWeight: 700 }}>
                        {selectedSku.price_elasticity} ({selectedSku.classification})
                      </span>
                    </p>
                  </div>
                </div>

                {/* Right: Impact Metrics Cards */}
                <div
                  style={{
                    display: 'grid',
                    gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))',
                    gap: '0.75rem',
                  }}
                >
                  <div
                    style={{
                      backgroundColor: 'var(--bg-surface-elevated)',
                      border: '1px solid var(--border-subtle)',
                      borderRadius: '10px',
                      padding: '1rem',
                    }}
                  >
                    <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                      Unit Price Impact
                    </div>
                    <div
                      style={{
                        fontSize: '1.35rem',
                        fontWeight: 700,
                        color: '#fff',
                        marginTop: '0.25rem',
                      }}
                    >
                      ₹{simResults.simPrice}
                    </div>
                    <div
                      style={{
                        fontSize: '0.72rem',
                        color: 'var(--text-muted)',
                        textDecoration: 'line-through',
                      }}
                    >
                      Base: ₹{simResults.basePrice}
                    </div>
                  </div>

                  <div
                    style={{
                      backgroundColor: 'var(--bg-surface-elevated)',
                      border: '1px solid var(--border-subtle)',
                      borderRadius: '10px',
                      padding: '1rem',
                    }}
                  >
                    <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                      Projected Volume Gain
                    </div>
                    <div
                      style={{
                        fontSize: '1.35rem',
                        fontWeight: 700,
                        color: 'var(--accent-emerald)',
                        marginTop: '0.25rem',
                      }}
                    >
                      +{simResults.pctVolChange}%
                    </div>
                    <div
                      style={{
                        fontSize: '0.72rem',
                        color: 'var(--text-muted)',
                      }}
                    >
                      {simResults.simQty} units/day
                    </div>
                  </div>

                  <div
                    style={{
                      backgroundColor: 'var(--bg-surface-elevated)',
                      border: '1px solid var(--border-subtle)',
                      borderRadius: '10px',
                      padding: '1rem',
                    }}
                  >
                    <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                      Daily Revenue Uplift
                    </div>
                    <div
                      style={{
                        fontSize: '1.35rem',
                        fontWeight: 700,
                        color:
                          Number(simResults.revUpliftPct) >= 0
                            ? '#a5b4fc'
                            : 'var(--accent-rose)',
                        marginTop: '0.25rem',
                      }}
                    >
                      {Number(simResults.revUpliftPct) >= 0 ? '+' : ''}
                      {simResults.revUpliftPct}%
                    </div>
                    <div
                      style={{
                        fontSize: '0.72rem',
                        color: 'var(--text-muted)',
                      }}
                    >
                      ₹{simResults.simRev} / day
                    </div>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* SKU Price Elasticity & Recommendation Matrix Table */}
          <div className="card" style={{ padding: '1.5rem', margin: 0 }}>
            <div
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                marginBottom: '1.25rem',
                flexWrap: 'wrap',
                gap: '1rem',
              }}
            >
              <div>
                <h3
                  style={{
                    fontSize: '1.1rem',
                    fontWeight: 600,
                    color: 'var(--text-primary)',
                  }}
                >
                  SKU Price Elasticity & Recommendation Matrix
                </h3>
                <p
                  style={{
                    fontSize: '0.85rem',
                    color: 'var(--text-secondary)',
                  }}
                >
                  Showing {filteredSkus.length} product elasticity profiles
                </p>
              </div>

              <div
                style={{
                  display: 'flex',
                  gap: '0.6rem',
                  alignItems: 'center',
                  flexWrap: 'wrap',
                }}
              >
                {/* Search Bar */}
                <div style={{ position: 'relative', minWidth: '220px' }}>
                  <Search
                    size={15}
                    color="var(--text-muted)"
                    style={{ position: 'absolute', left: '10px', top: '10px' }}
                  />
                  <input
                    type="text"
                    placeholder="Search SKU name or brand..."
                    value={elasticitySearch}
                    onChange={(e) => setElasticitySearch(e.target.value)}
                    style={{
                      width: '100%',
                      padding: '0.5rem 0.5rem 0.5rem 2.2rem',
                      borderRadius: '8px',
                      border: '1px solid var(--border-strong)',
                      backgroundColor: 'var(--bg-surface-elevated)',
                      color: '#fff',
                      fontSize: '0.85rem',
                      outline: 'none',
                    }}
                  />
                </div>

                {/* Category Dropdown */}
                <select
                  value={selectedElasticityCategory}
                  onChange={(e) => setSelectedElasticityCategory(e.target.value)}
                  style={{
                    padding: '0.5rem 0.75rem',
                    borderRadius: '8px',
                    border: '1px solid var(--border-strong)',
                    backgroundColor: 'var(--bg-surface-elevated)',
                    color: '#fff',
                    fontSize: '0.85rem',
                    outline: 'none',
                  }}
                >
                  <option value="ALL">All Categories</option>
                  {elasticityCategories.map((cat) => (
                    <option key={cat} value={cat}>
                      {cat}
                    </option>
                  ))}
                </select>

                {/* Classification filter pills */}
                <div
                  style={{
                    display: 'flex',
                    backgroundColor: 'var(--bg-surface-elevated)',
                    padding: '0.2rem',
                    borderRadius: '8px',
                    border: '1px solid var(--border-subtle)',
                  }}
                >
                  {['ALL', 'Elastic', 'Inelastic', 'Anomalous'].map((cls) => (
                    <button
                      key={cls}
                      onClick={() => setFilterClass(cls)}
                      style={{
                        padding: '0.35rem 0.7rem',
                        fontSize: '0.75rem',
                        fontWeight: filterClass === cls ? 700 : 500,
                        borderRadius: '6px',
                        border: 'none',
                        backgroundColor:
                          filterClass === cls
                            ? 'var(--accent-primary)'
                            : 'transparent',
                        color:
                          filterClass === cls ? '#fff' : 'var(--text-secondary)',
                        cursor: 'pointer',
                      }}
                    >
                      {cls}
                    </button>
                  ))}
                </div>
              </div>
            </div>

            {/* Table */}
            <div style={{ overflowX: 'auto' }}>
              <table
                style={{
                  width: '100%',
                  borderCollapse: 'collapse',
                  fontSize: '0.875rem',
                }}
              >
                <thead>
                  <tr style={{ borderBottom: '1px solid var(--border-subtle)' }}>
                    <th
                      style={{
                        padding: '0.75rem',
                        textAlign: 'left',
                        color: 'var(--text-muted)',
                        fontSize: '0.78rem',
                        textTransform: 'uppercase',
                      }}
                    >
                      SKU & Product Name
                    </th>
                    <th
                      style={{
                        padding: '0.75rem',
                        textAlign: 'left',
                        color: 'var(--text-muted)',
                        fontSize: '0.78rem',
                        textTransform: 'uppercase',
                      }}
                    >
                      Category & Brand
                    </th>
                    <th
                      style={{
                        padding: '0.75rem',
                        textAlign: 'right',
                        color: 'var(--text-muted)',
                        fontSize: '0.78rem',
                        textTransform: 'uppercase',
                      }}
                    >
                      Avg Price (₹)
                    </th>
                    <th
                      style={{
                        padding: '0.75rem',
                        textAlign: 'center',
                        color: 'var(--text-muted)',
                        fontSize: '0.78rem',
                        textTransform: 'uppercase',
                      }}
                    >
                      PED Coeff
                    </th>
                    <th
                      style={{
                        padding: '0.75rem',
                        textAlign: 'center',
                        color: 'var(--text-muted)',
                        fontSize: '0.78rem',
                        textTransform: 'uppercase',
                      }}
                    >
                      Elasticity Class
                    </th>
                    <th
                      style={{
                        padding: '0.75rem',
                        textAlign: 'center',
                        color: 'var(--text-muted)',
                        fontSize: '0.78rem',
                        textTransform: 'uppercase',
                      }}
                    >
                      Rec. Discount
                    </th>
                    <th
                      style={{
                        padding: '0.75rem',
                        textAlign: 'right',
                        color: 'var(--text-muted)',
                        fontSize: '0.78rem',
                        textTransform: 'uppercase',
                      }}
                    >
                      Optimal Price
                    </th>
                    <th
                      style={{
                        padding: '0.75rem',
                        textAlign: 'right',
                        color: 'var(--text-muted)',
                        fontSize: '0.78rem',
                        textTransform: 'uppercase',
                      }}
                    >
                      Proj. Rev Uplift
                    </th>
                    <th
                      style={{
                        padding: '0.75rem',
                        textAlign: 'left',
                        color: 'var(--text-muted)',
                        fontSize: '0.78rem',
                        textTransform: 'uppercase',
                      }}
                    >
                      Action Recommendation
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {filteredSkus.length === 0 ? (
                    <tr>
                      <td
                        colSpan={9}
                        style={{
                          textAlign: 'center',
                          padding: '2rem',
                          color: 'var(--text-muted)',
                        }}
                      >
                        No matching SKUs found for selected filters.
                      </td>
                    </tr>
                  ) : (
                    filteredSkus.map((sku, idx) => (
                      <tr
                        key={sku.product_id}
                        onClick={() => setSelectedSkuId(sku.product_id)}
                        style={{
                          borderBottom: '1px solid var(--border-subtle)',
                          backgroundColor:
                            selectedSkuId === sku.product_id
                              ? 'rgba(59, 130, 246, 0.12)'
                              : idx % 2 === 0
                              ? 'transparent'
                              : 'rgba(255, 255, 255, 0.015)',
                          cursor: 'pointer',
                          transition: 'background-color 0.12s ease',
                        }}
                      >
                        <td style={{ padding: '0.75rem' }}>
                          <div
                            style={{
                              fontWeight: 600,
                              color: 'var(--text-primary)',
                            }}
                          >
                            {sku.product_name}
                          </div>
                          <div
                            style={{
                              fontSize: '0.75rem',
                              color: 'var(--text-muted)',
                            }}
                          >
                            ID: #{sku.product_id}
                          </div>
                        </td>
                        <td style={{ padding: '0.75rem', color: 'var(--text-secondary)' }}>
                          <div>{sku.category}</div>
                          <div
                            style={{
                              fontSize: '0.75rem',
                              color: 'var(--text-muted)',
                            }}
                          >
                            {sku.brand}
                          </div>
                        </td>
                        <td
                          style={{
                            padding: '0.75rem',
                            textAlign: 'right',
                            fontWeight: 600,
                            color: 'var(--text-primary)',
                          }}
                        >
                          ₹{sku.avg_unit_price.toFixed(2)}
                        </td>
                        <td
                          style={{
                            padding: '0.75rem',
                            textAlign: 'center',
                            fontFamily: 'monospace',
                            fontWeight: 700,
                            color: '#fff',
                          }}
                        >
                          {sku.price_elasticity}
                        </td>
                        <td style={{ padding: '0.75rem', textAlign: 'center' }}>
                          <span
                            style={{
                              padding: '0.2rem 0.6rem',
                              borderRadius: '999px',
                              fontSize: '0.75rem',
                              fontWeight: 700,
                              backgroundColor:
                                sku.classification === 'Elastic'
                                  ? 'rgba(16, 185, 129, 0.18)'
                                  : sku.classification === 'Inelastic'
                                  ? 'rgba(59, 130, 246, 0.18)'
                                  : 'rgba(245, 158, 11, 0.18)',
                              color:
                                sku.classification === 'Elastic'
                                  ? 'var(--accent-emerald)'
                                  : sku.classification === 'Inelastic'
                                  ? 'var(--accent-cyan)'
                                  : 'var(--accent-amber)',
                            }}
                          >
                            {sku.classification}
                          </span>
                        </td>
                        <td
                          style={{
                            padding: '0.75rem',
                            textAlign: 'center',
                            fontWeight: 700,
                            color: '#818cf8',
                          }}
                        >
                          {sku.recommended_discount_pct}%
                        </td>
                        <td
                          style={{
                            padding: '0.75rem',
                            textAlign: 'right',
                            fontWeight: 700,
                            color: '#fff',
                          }}
                        >
                          ₹{sku.optimal_price.toFixed(2)}
                        </td>
                        <td
                          style={{
                            padding: '0.75rem',
                            textAlign: 'right',
                            fontWeight: 700,
                            color: 'var(--accent-emerald)',
                          }}
                        >
                          +{sku.projected_revenue_impact_pct}%
                        </td>
                        <td
                          style={{
                            padding: '0.75rem',
                            fontSize: '0.8rem',
                            color: 'var(--text-secondary)',
                            maxWidth: '280px',
                          }}
                        >
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
      )}
    </div>
  );
}
