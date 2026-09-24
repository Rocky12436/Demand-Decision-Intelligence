import React, { useState, useEffect } from 'react';
import {
  Truck,
  MapPin,
  ArrowRight,
  ShieldCheck,
  CheckCircle2,
  RefreshCw,
} from 'lucide-react';
import {
  PageShell,
  PageHeader,
  Card,
  StatCard,
  StatusBadge,
  EmptyState,
} from '../../components/ui';

export default function TransfersPage() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [actionMessage, setActionMessage] = useState(null);

  const fetchTransfers = async () => {
    setLoading(true);
    try {
      const res = await fetch('/api/transfers/opportunities?dataset_id=1');
      if (res.ok) {
        const json = await res.json();
        setData(json);
      }
    } catch (err) {
      console.error('Failed to load transfers:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchTransfers();
  }, []);

  const handleConfirmTransfer = async (opp) => {
    try {
      const token = localStorage.getItem('token');
      const res = await fetch('/api/transfers/create', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { 'Authorization': `Bearer ${token}` } : {})
        },
        body: JSON.stringify({
          dataset_id: 1,
          from_city: opp.from_city,
          to_city: opp.to_city,
          lines: [
            { product_id: opp.product_id, quantity: opp.quantity, reason: 'Deficit Replenishment' }
          ]
        })
      });

      if (res.ok) {
        const result = await res.json();
        setActionMessage(`Transfer #${result.transfer_order_id} created: Moving ${opp.quantity} units from ${opp.from_city} → ${opp.to_city}.`);
        fetchTransfers();
      }
    } catch (err) {
      console.error('Failed to confirm transfer:', err);
    }
  };

  // SVG coordinate transformation helper for India Map Box
  const getSvgCoords = (lat, lng) => {
    const minLat = 8.0, maxLat = 32.0;
    const minLng = 68.0, maxLng = 88.0;
    const width = 500, height = 500;
    const x = ((lng - minLng) / (maxLng - minLng)) * width;
    const y = height - ((lat - minLat) / (maxLat - minLat)) * height;
    return { x: Math.max(30, Math.min(width - 30, x)), y: Math.max(30, Math.min(height - 30, y)) };
  };

  return (
    <PageShell>
      <PageHeader
        icon={Truck}
        title="Stock Transfers Between Cities"
        subtitle="Move excess stock from one city to another instead of buying new. Faster and cheaper."
        actions={
          <button onClick={fetchTransfers} disabled={loading} className="diq-btn diq-btn-secondary">
            <RefreshCw size={14} className={loading ? 'animate-spin' : ''} /> Refresh
          </button>
        }
      />

      {/* Success message */}
      {actionMessage && (
        <div style={{
          padding: '10px 14px', borderRadius: 'var(--border-radius-md)', marginBottom: '16px',
          backgroundColor: 'var(--status-success-bg)', border: '1px solid var(--status-success-border)',
          color: 'var(--status-success-text)', fontSize: '13px',
          display: 'flex', alignItems: 'center', gap: '6px',
        }}>
          <CheckCircle2 size={16} /> {actionMessage}
        </div>
      )}

      <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>

        {/* ── KPI Cards ── */}
        {data && (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: '12px' }}>
            <StatCard
              label="Stock Available to Move"
              value={`${data.total_units_movable?.toLocaleString('en-IN')} units`}
              subtext={`${data.total_opportunities} transfer option(s)`}
            />
            <StatCard
              label="Money Saved vs Buying New"
              value={`₹${data.total_cost_savings_rs?.toLocaleString('en-IN')}`}
              subtext="Compared to placing new orders"
            />
            <StatCard
              label="Source City Safety"
              value="100% Protected"
              subtext="No source city goes below minimum stock"
              icon={ShieldCheck}
            />
          </div>
        )}

        {/* ── Main content: List + Map ── */}
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '20px' }}>

          {/* Transfer Opportunities */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
            <div style={{ fontSize: '14px', fontWeight: 600, color: 'var(--text-primary)' }}>
              Recommended Transfers
            </div>

            {loading ? (
              <div style={{ padding: '48px', textAlign: 'center', color: 'var(--text-muted)', fontSize: '14px' }}>Finding transfer opportunities...</div>
            ) : !data?.opportunities || data.opportunities.length === 0 ? (
              <EmptyState
                icon={Truck}
                title="No transfers needed"
                description="All warehouses are balanced. No excess stock available to move."
              />
            ) : (
              data.opportunities.map((opp, idx) => (
                <Card key={idx}>
                  {/* Product + Savings */}
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '10px' }}>
                    <div>
                      <div style={{ fontWeight: 600, fontSize: '14px' }}>{opp.product_name}</div>
                      <div style={{ fontSize: '11px', color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>{opp.product_id}</div>
                    </div>
                    <div style={{ textAlign: 'right' }}>
                      <div className="tabular-nums" style={{ fontSize: '16px', fontWeight: 700, color: 'var(--status-success-text)' }}>
                        +₹{opp.cost_savings_rs?.toLocaleString('en-IN')}
                      </div>
                      <div style={{ fontSize: '10px', color: 'var(--text-muted)', textTransform: 'uppercase' }}>Savings</div>
                    </div>
                  </div>

                  {/* Route */}
                  <div style={{
                    display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                    padding: '10px 14px', backgroundColor: 'var(--bg-surface-subtle)',
                    borderRadius: 'var(--border-radius-md)', marginBottom: '10px', fontSize: '13px',
                  }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                      <strong>{opp.from_city}</strong>
                      <ArrowRight size={14} style={{ color: 'var(--accent-primary)' }} />
                      <strong style={{ color: 'var(--status-success-text)' }}>{opp.to_city}</strong>
                    </div>
                    <StatusBadge variant="info" label={`${opp.quantity} units`} size="sm" />
                  </div>

                  {/* Cost comparison */}
                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '8px', fontSize: '12px', marginBottom: '10px' }}>
                    <div>
                      <div style={{ color: 'var(--text-muted)', marginBottom: '2px' }}>Transfer Cost</div>
                      <div style={{ fontWeight: 600 }}>₹{opp.transfer_cost_rs?.toLocaleString('en-IN')}</div>
                    </div>
                    <div>
                      <div style={{ color: 'var(--text-muted)', marginBottom: '2px' }}>If We Buy Instead</div>
                      <div style={{ fontWeight: 600 }}>₹{opp.purchase_cost_rs?.toLocaleString('en-IN')}</div>
                    </div>
                    <div>
                      <div style={{ color: 'var(--text-muted)', marginBottom: '2px' }}>Speed Advantage</div>
                      <div style={{ fontWeight: 600, color: 'var(--status-success-text)' }}>{opp.time_advantage_days} days faster</div>
                    </div>
                  </div>

                  {/* Safety note + action */}
                  <div style={{
                    display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                    paddingTop: '10px', borderTop: '1px solid var(--border-subtle)',
                    fontSize: '12px', color: 'var(--text-muted)',
                  }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                      <ShieldCheck size={14} style={{ color: 'var(--status-success-icon)' }} />
                      {opp.from_city} keeps {opp.source_stock_after} units (min: {opp.source_rop})
                    </div>
                    <button onClick={() => handleConfirmTransfer(opp)} className="diq-btn diq-btn-primary diq-btn-sm">
                      Confirm Transfer
                    </button>
                  </div>
                </Card>
              ))
            )}
          </div>

          {/* ── Map ── */}
          <div>
            <div style={{ fontSize: '14px', fontWeight: 600, color: 'var(--text-primary)', marginBottom: '12px', display: 'flex', alignItems: 'center', gap: '6px' }}>
              <MapPin size={16} style={{ color: 'var(--accent-primary)' }} />
              Transfer Map
            </div>

            <Card>
              <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center' }}>
                <svg
                  viewBox="0 0 500 500"
                  style={{ width: '100%', maxWidth: '400px', height: 'auto', backgroundColor: 'var(--bg-surface-subtle)', borderRadius: 'var(--border-radius-lg)', border: '1px solid var(--border-subtle)' }}
                >
                  <defs>
                    <pattern id="grid" width="25" height="25" patternUnits="userSpaceOnUse">
                      <path d="M 25 0 L 0 0 0 25" fill="none" stroke="var(--border-subtle)" strokeWidth="0.5" />
                    </pattern>
                    <marker id="arrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
                      <path d="M 0 0 L 10 5 L 0 10 z" fill="var(--accent-primary)" />
                    </marker>
                  </defs>
                  <rect width="500" height="500" fill="url(#grid)" />

                  {/* Transfer lines */}
                  {data?.opportunities?.map((opp, i) => {
                    const fromP = getSvgCoords(opp.from_coords?.lat || 12.97, opp.from_coords?.lng || 77.59);
                    const toP = getSvgCoords(opp.to_coords?.lat || 28.70, opp.to_coords?.lng || 77.10);
                    const midX = (fromP.x + toP.x) / 2 + 20;
                    const midY = (fromP.y + toP.y) / 2 - 25;
                    const strokeW = Math.max(2, Math.min(6, (opp.quantity / 20)));

                    return (
                      <g key={`flow-${i}`}>
                        <path
                          d={`M ${fromP.x} ${fromP.y} Q ${midX} ${midY} ${toP.x} ${toP.y}`}
                          fill="none"
                          stroke="var(--accent-primary)"
                          strokeWidth={strokeW}
                          strokeDasharray="5,5"
                          markerEnd="url(#arrow)"
                          opacity="0.7"
                        />
                        <text x={midX} y={midY - 6} fill="var(--accent-primary)" fontSize="9" fontWeight="bold" textAnchor="middle">
                          {opp.quantity}u
                        </text>
                      </g>
                    );
                  })}

                  {/* Location nodes */}
                  {data?.map_locations?.map((loc) => {
                    const coords = getSvgCoords(loc.lat, loc.lng);
                    return (
                      <g key={`loc-${loc.id}`} transform={`translate(${coords.x}, ${coords.y})`}>
                        <circle r="7" fill="var(--accent-primary)" stroke="#ffffff" strokeWidth="2" />
                        <text x="11" y="4" fill="var(--text-primary)" fontSize="10" fontWeight="600">
                          {loc.city_name}
                        </text>
                      </g>
                    );
                  })}
                </svg>

                <div style={{ display: 'flex', gap: '16px', marginTop: '10px', fontSize: '11px', color: 'var(--text-muted)' }}>
                  <span style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                    <span style={{ width: '8px', height: '8px', borderRadius: '50%', backgroundColor: 'var(--accent-primary)' }} /> City
                  </span>
                  <span style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                    <span style={{ width: '16px', height: '0', borderTop: '2px dashed var(--accent-primary)' }} /> Transfer Route
                  </span>
                </div>
              </div>
            </Card>
          </div>
        </div>
      </div>
    </PageShell>
  );
}
