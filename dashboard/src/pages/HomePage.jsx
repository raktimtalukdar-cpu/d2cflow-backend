import { useState, useEffect } from 'react';
import { getOrders } from '../data/orders';

const today = new Date().toLocaleDateString('en-IN', { weekday: 'long', day: 'numeric', month: 'long' });

function getHour() { return new Date().getHours(); }
function greeting() {
  const h = getHour();
  if (h < 12) return 'Good morning';
  if (h < 17) return 'Good afternoon';
  return 'Good evening';
}

const CHANNELS = ['amazon', 'flipkart', 'meesho', 'myntra', 'shopify', 'whatsapp', 'manual'];
const CHANNEL_COLORS = {
  amazon: '#FF9900', flipkart: '#2874F0', meesho: '#F43397', myntra: '#FF3F6C',
  shopify: '#96BF48', whatsapp: '#25D366', manual: '#64748b',
};

function channelOf(o) {
  const ch = (o.channel || '').toLowerCase();
  for (const c of CHANNELS) if (ch.includes(c)) return c;
  return 'manual';
}

const STATUS_MAP = {
  new: 'badge-new', confirmed: 'badge-new', packed: 'badge-packed',
  rtd: 'badge-rtd', shipped: 'badge-shipped', delivered: 'badge-delivered',
  rto: 'badge-rto', cancelled: 'badge-cancelled',
};

export default function HomePage({ onNavigate }) {
  const [orders, setOrders] = useState(() => getOrders());

  useEffect(() => {
    setOrders(getOrders());
    const interval = setInterval(() => setOrders(getOrders()), 5000);
    return () => clearInterval(interval);
  }, []);

  const active = orders.filter(o => o.status !== 'cancelled');
  const totalGMV = active.reduce((s, o) => s + (Number(o.total) || 0), 0);
  const pendingRTD = active.filter(o => o.status === 'rtd' || o.status === 'confirmed').length;
  const newOrders = active.filter(o => o.status === 'new' || o.status === 'confirmed').length;
  const rtoOrders = active.filter(o => o.status === 'rto').length;
  const shippedOrders = active.filter(o => o.status === 'shipped').length;

  // Today's orders
  const todayStr = new Date().toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' });
  const todayOrders = orders.filter(o => o.date === todayStr || (o.createdAt || '').startsWith(new Date().toISOString().slice(0, 10)));
  const recentOrders = [...orders].sort((a, b) => (b.createdAt || '').localeCompare(a.createdAt || '')).slice(0, 6);

  // Channel breakdown from real orders
  const channelCounts = {};
  for (const c of CHANNELS) channelCounts[c] = { total: 0, new: 0 };
  for (const o of active) {
    const c = channelOf(o);
    if (!channelCounts[c]) channelCounts[c] = { total: 0, new: 0 };
    channelCounts[c].total++;
    if (o.status === 'new' || o.status === 'confirmed') channelCounts[c].new++;
  }
  const activeChannels = CHANNELS.filter(c => channelCounts[c]?.total > 0);
  const maxCount = Math.max(1, ...activeChannels.map(c => channelCounts[c].total));

  const rtoRate = active.length > 0 ? ((rtoOrders / active.length) * 100).toFixed(1) : '0.0';

  return (
    <div style={{ padding: 24, maxWidth: 1200 }}>
      {/* Greeting */}
      <div style={{ marginBottom: 24 }}>
        <h1 style={{ fontSize: '22px', fontWeight: 700, letterSpacing: '-0.3px' }}>{greeting()}, Raktim 👋</h1>
        <p style={{ fontSize: '13px', color: 'var(--text-secondary)', marginTop: 2 }}>
          {today} · {activeChannels.length > 0 ? `${activeChannels.length} active channel${activeChannels.length !== 1 ? 's' : ''}` : 'No orders yet'}
        </p>
      </div>

      {/* Alert banners */}
      {pendingRTD > 0 && (
        <div onClick={() => onNavigate('shipping')}
          style={{ background: 'linear-gradient(135deg, #7C3AED 0%, #5B21B6 100%)', borderRadius: 'var(--radius-lg)', padding: '14px 18px', marginBottom: 12, display: 'flex', alignItems: 'center', gap: 12, cursor: 'pointer', color: '#fff' }}>
          <span style={{ fontSize: '20px' }}>📦</span>
          <div style={{ flex: 1 }}>
            <div style={{ fontWeight: 600, fontSize: '14px' }}>{pendingRTD} order{pendingRTD !== 1 ? 's' : ''} ready to dispatch</div>
            <div style={{ fontSize: '12px', opacity: 0.8 }}>Tap to create shipments and print labels</div>
          </div>
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="m9 18 6-6-6-6"/></svg>
        </div>
      )}
      {newOrders > 0 && (
        <div onClick={() => onNavigate('orders')}
          style={{ background: 'var(--green-light)', border: '1px solid rgba(22,162,73,0.2)', borderRadius: 'var(--radius-lg)', padding: '12px 16px', marginBottom: 20, display: 'flex', alignItems: 'center', gap: 12, cursor: 'pointer' }}>
          <span style={{ fontSize: '18px' }}>🆕</span>
          <div style={{ flex: 1 }}>
            <div style={{ fontWeight: 600, fontSize: '13px', color: 'var(--green)' }}>{newOrders} new order{newOrders !== 1 ? 's' : ''} waiting for action</div>
          </div>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="var(--green)" strokeWidth="2"><path d="m9 18 6-6-6-6"/></svg>
        </div>
      )}
      {shippedOrders > 0 && (
        <div onClick={() => onNavigate('shipping')}
          style={{ background: '#eff6ff', border: '1px solid #bfdbfe', borderRadius: 'var(--radius-lg)', padding: '12px 16px', marginBottom: 20, display: 'flex', alignItems: 'center', gap: 12, cursor: 'pointer' }}>
          <span style={{ fontSize: '18px' }}>🚚</span>
          <div style={{ flex: 1 }}>
            <div style={{ fontWeight: 600, fontSize: '13px', color: 'var(--blue)' }}>{shippedOrders} order{shippedOrders !== 1 ? 's' : ''} in transit</div>
          </div>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="var(--blue)" strokeWidth="2"><path d="m9 18 6-6-6-6"/></svg>
        </div>
      )}

      {/* KPI Cards */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 12, marginBottom: 24 }}>
        {[
          { label: "Total Orders", value: active.length, sub: `${todayOrders.length} today`, color: 'var(--blue)', icon: '🛒', onClick: () => onNavigate('orders') },
          { label: 'GMV (All Time)', value: totalGMV >= 1000 ? `₹${(totalGMV/1000).toFixed(1)}k` : `₹${totalGMV}`, sub: 'Across all channels', color: 'var(--green)', icon: '💰' },
          { label: 'Pending Dispatch', value: pendingRTD, sub: 'Need shipping today', color: 'var(--purple)', icon: '⏳', alert: pendingRTD > 0, onClick: () => onNavigate('shipping') },
          { label: 'RTO Rate', value: `${rtoRate}%`, sub: `${rtoOrders} order${rtoOrders !== 1 ? 's' : ''} returned`, color: rtoOrders > 2 ? 'var(--red)' : 'var(--green)', icon: '↩️' },
        ].map((kpi, i) => (
          <div key={i} className="card" onClick={kpi.onClick}
            style={{ padding: '16px 18px', boxShadow: `inset 3px 0 0 ${kpi.color}`, cursor: kpi.onClick ? 'pointer' : 'default' }}>
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

      {orders.length === 0 ? (
        /* Empty state */
        <div style={{ textAlign: 'center', padding: '60px 24px', color: 'var(--text-secondary)' }}>
          <div style={{ fontSize: 56, marginBottom: 16 }}>📭</div>
          <div style={{ fontWeight: 700, fontSize: 18, color: 'var(--text-primary)', marginBottom: 8 }}>No orders yet</div>
          <div style={{ fontSize: 13, maxWidth: 340, margin: '0 auto', lineHeight: 1.7 }}>
            Orders will appear here once you add them manually, sync from WhatsApp, or connect a marketplace.
          </div>
          <div style={{ display: 'flex', gap: 10, justifyContent: 'center', marginTop: 20 }}>
            <button onClick={() => onNavigate('orders')} className="btn btn-primary">+ Add Order</button>
            <button onClick={() => onNavigate('whatsapp-orders')} className="btn btn-secondary">📱 WhatsApp Orders</button>
          </div>
        </div>
      ) : (
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
          {/* Channel breakdown */}
          <div className="card" style={{ padding: 18 }}>
            <div style={{ fontWeight: 600, fontSize: '14px', marginBottom: 14 }}>Orders by Channel</div>
            {activeChannels.length === 0 ? (
              <div style={{ color: 'var(--text-secondary)', fontSize: 13 }}>No channel data yet.</div>
            ) : activeChannels.map(ch => {
              const stats = channelCounts[ch];
              return (
                <div key={ch} style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 10 }}>
                  <span style={{ width: 68, fontSize: '12px', fontWeight: 500, textTransform: 'capitalize', color: 'var(--text-primary)' }}>{ch}</span>
                  <div style={{ flex: 1, height: 6, background: 'var(--border)', borderRadius: 3, overflow: 'hidden' }}>
                    <div style={{ height: '100%', width: `${(stats.total / maxCount) * 100}%`, background: CHANNEL_COLORS[ch] || 'var(--blue)', borderRadius: 3, transition: 'width 0.6s ease' }} />
                  </div>
                  <span style={{ fontSize: '12px', fontWeight: 600, width: 28, textAlign: 'right' }}>{stats.total}</span>
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
            {recentOrders.length === 0 ? (
              <div style={{ color: 'var(--text-secondary)', fontSize: 13 }}>No orders yet.</div>
            ) : recentOrders.map(o => (
              <div key={o.id} style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '8px 0', borderBottom: '1px solid var(--border)' }}>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontSize: '13px', fontWeight: 500, display: 'flex', alignItems: 'center', gap: 6 }}>
                    <span style={{ fontFamily: 'monospace', color: 'var(--blue)', fontSize: 12 }}>{String(o.id).replace('ORD-', '').slice(-7)}</span>
                    <span style={{ fontSize: '11px', color: 'var(--text-secondary)' }}>{o.customer}</span>
                  </div>
                  <div style={{ fontSize: '11px', color: 'var(--text-secondary)', marginTop: 1 }}>{o.items?.[0]?.name || '—'}</div>
                </div>
                <div style={{ textAlign: 'right', flexShrink: 0 }}>
                  <div style={{ fontWeight: 700, fontSize: '13px' }}>₹{Number(o.total || 0).toLocaleString('en-IN')}</div>
                  <span className={`badge ${STATUS_MAP[o.status] || 'badge-new'}`} style={{ fontSize: '10px' }}>{o.status}</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
