import { ORDERS, CHANNEL_STATS } from '../data/mockData';

const today = new Date().toLocaleDateString('en-IN', { weekday: 'long', day: 'numeric', month: 'long' });

export default function HomePage({ onNavigate }) {
  const todayOrders = ORDERS.slice(0, 5);
  const pendingRTD = ORDERS.filter(o => o.status === 'rtd').length;
  const newOrders = ORDERS.filter(o => o.status === 'new').length;
  const rtoOrders = ORDERS.filter(o => o.status === 'rto').length;
  const totalGMV = ORDERS.reduce((s, o) => s + o.total, 0);

  return (
    <div style={{ padding: 24, maxWidth: 1200 }}>
      {/* Greeting */}
      <div style={{ marginBottom: 24 }}>
        <h1 style={{ fontSize: '22px', fontWeight: 700, letterSpacing: '-0.3px' }}>Good morning, Raktim 👋</h1>
        <p style={{ fontSize: '13px', color: 'var(--text-secondary)', marginTop: 2 }}>{today} · Your store is live across 5 channels</p>
      </div>

      {/* Alert banners */}
      {pendingRTD > 0 && (
        <div onClick={() => onNavigate('shipping')} style={{ background: 'linear-gradient(135deg, #7C3AED 0%, #5B21B6 100%)', borderRadius: 'var(--radius-lg)', padding: '14px 18px', marginBottom: 12, display: 'flex', alignItems: 'center', gap: 12, cursor: 'pointer', color: '#fff' }}>
          <span style={{ fontSize: '20px' }}>📦</span>
          <div style={{ flex: 1 }}>
            <div style={{ fontWeight: 600, fontSize: '14px' }}>{pendingRTD} orders ready to dispatch</div>
            <div style={{ fontSize: '12px', opacity: 0.8 }}>Tap to create shipments and print labels</div>
          </div>
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="m9 18 6-6-6-6"/></svg>
        </div>
      )}
      {newOrders > 0 && (
        <div onClick={() => onNavigate('orders')} style={{ background: 'var(--green-light)', border: '1px solid rgba(22,162,73,0.2)', borderRadius: 'var(--radius-lg)', padding: '12px 16px', marginBottom: 20, display: 'flex', alignItems: 'center', gap: 12, cursor: 'pointer' }}>
          <span style={{ fontSize: '18px' }}>🆕</span>
          <div style={{ flex: 1 }}>
            <div style={{ fontWeight: 600, fontSize: '13px', color: 'var(--green)' }}>{newOrders} new orders waiting for action</div>
          </div>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="var(--green)" strokeWidth="2"><path d="m9 18 6-6-6-6"/></svg>
        </div>
      )}

      {/* KPI Cards */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 12, marginBottom: 24 }}>
        {[
          { label: "Today's Orders", value: ORDERS.length, sub: '+12% vs yesterday', color: 'var(--blue)', icon: '🛒' },
          { label: 'GMV (Month)', value: `₹${(totalGMV/1000).toFixed(1)}k`, sub: 'Across all channels', color: 'var(--green)', icon: '💰' },
          { label: 'Pending Dispatch', value: pendingRTD, sub: 'Need shipping today', color: 'var(--purple)', icon: '⏳', alert: pendingRTD > 0 },
          { label: 'RTO Rate', value: `${((rtoOrders/ORDERS.length)*100).toFixed(1)}%`, sub: `${rtoOrders} orders returned`, color: rtoOrders > 2 ? 'var(--red)' : 'var(--green)', icon: '↩️' },
        ].map((kpi, i) => (
          <div key={i} className="card" style={{ padding: '16px 18px', boxShadow: `inset 3px 0 0 ${kpi.color}` }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
              <div>
                <div style={{ fontSize: '11px', color: 'var(--text-secondary)', fontWeight: 500, marginBottom: 6 }}>{kpi.label}</div>
                <div style={{ fontSize: '26px', fontWeight: 800, color: kpi.color, letterSpacing: '-1px' }}>{kpi.value}</div>
                <div style={{ fontSize: '11px', color: 'var(--text-secondary)', marginTop: 4 }}>{kpi.sub}</div>
              </div>
              <span style={{ fontSize: '22px' }}>{kpi.icon}</span>
            </div>
          </div>
        ))}
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
        {/* Channel breakdown */}
        <div className="card" style={{ padding: 18 }}>
          <div style={{ fontWeight: 600, fontSize: '14px', marginBottom: 14 }}>Orders by Channel</div>
          {Object.entries(CHANNEL_STATS).map(([ch, stats]) => {
            const total = Object.values(stats).reduce((a, b) => a + b, 0);
            const maxTotal = 76;
            return (
              <div key={ch} style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 10 }}>
                <span style={{ width: 64, fontSize: '12px', fontWeight: 500, textTransform: 'capitalize', color: 'var(--text-primary)' }}>{ch}</span>
                <div style={{ flex: 1, height: 6, background: 'var(--border)', borderRadius: 3, overflow: 'hidden' }}>
                  <div style={{ height: '100%', width: `${(total/maxTotal)*100}%`, background: 'var(--blue)', borderRadius: 3, transition: 'width 0.6s ease' }} />
                </div>
                <span style={{ fontSize: '12px', fontWeight: 600, width: 24, textAlign: 'right' }}>{total}</span>
                {stats.new > 0 && <span className="badge badge-new" style={{ fontSize: '10px', padding: '1px 5px' }}>+{stats.new}</span>}
              </div>
            );
          })}
        </div>

        {/* Recent orders */}
        <div className="card" style={{ padding: 18 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 14 }}>
            <div style={{ fontWeight: 600, fontSize: '14px' }}>Recent Orders</div>
            <button onClick={() => onNavigate('orders')} style={{ background: 'none', border: 'none', cursor: 'pointer', fontSize: '12px', color: 'var(--blue)', fontFamily: 'inherit' }}>View all →</button>
          </div>
          {todayOrders.map(o => {
            const STATUS_MAP = { new: 'badge-new', packed: 'badge-packed', rtd: 'badge-rtd', shipped: 'badge-shipped', delivered: 'badge-delivered', rto: 'badge-rto', cancelled: 'badge-cancelled' };
            return (
              <div key={o.id} style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '8px 0', borderBottom: '1px solid var(--border)' }}>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontSize: '13px', fontWeight: 500, display: 'flex', alignItems: 'center', gap: 6 }}>
                    <span style={{ fontFamily: 'monospace', color: 'var(--blue)' }}>{o.id.replace('ORD-','')}</span>
                    <span style={{ fontSize: '11px', color: 'var(--text-secondary)' }}>{o.customer}</span>
                  </div>
                  <div style={{ fontSize: '11px', color: 'var(--text-secondary)', marginTop: 1 }}>{o.items[0]?.name}</div>
                </div>
                <div style={{ textAlign: 'right' }}>
                  <div style={{ fontWeight: 700, fontSize: '13px' }}>₹{o.total.toLocaleString('en-IN')}</div>
                  <span className={`badge ${STATUS_MAP[o.status]}`} style={{ fontSize: '10px' }}>{o.status}</span>
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
