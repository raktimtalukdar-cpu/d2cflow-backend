import { useState, useMemo } from 'react';
import { getOrders } from '../data/orders';

// ── Helpers ───────────────────────────────────────────────────────────────────
function pct(a, b) { return b === 0 ? 0 : Math.round((a / b) * 100); }
function fmt(n) { return Number(n || 0).toLocaleString('en-IN'); }
function fmtCur(n) { return '₹' + fmt(n); }

const CHANNEL_COLORS = {
  shopify:  '#96bf48',
  whatsapp: '#25D366',
  amazon:   '#ff9900',
  flipkart: '#2874f0',
  meesho:   '#9b26af',
  myntra:   '#ff3f6c',
  manual:   '#64748b',
};
const CHANNEL_LABEL = {
  shopify: 'Shopify', whatsapp: 'WhatsApp', amazon: 'Amazon',
  flipkart: 'Flipkart', meesho: 'Meesho', myntra: 'Myntra', manual: 'Manual',
};

const STATUS_COLOR = {
  new: '#3b82f6', confirmed: '#8b5cf6', rtd: '#f59e0b',
  shipped: '#0ea5e9', delivered: '#22c55e', rto: '#ef4444', cancelled: '#94a3b8',
};

function StatCard({ label, value, sub, color, icon, trend }) {
  return (
    <div style={{ background: '#fff', borderRadius: 12, border: '1px solid #e2e8f0', padding: '16px 20px' }}>
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between' }}>
        <div>
          <div style={{ fontSize: 12, color: '#64748b', fontWeight: 500, marginBottom: 6 }}>{label}</div>
          <div style={{ fontSize: 26, fontWeight: 800, color: color || '#1e293b', lineHeight: 1 }}>{value}</div>
          {sub && <div style={{ fontSize: 11, color: '#94a3b8', marginTop: 5 }}>{sub}</div>}
        </div>
        <div style={{ fontSize: 24 }}>{icon}</div>
      </div>
      {trend !== undefined && (
        <div style={{ marginTop: 10, fontSize: 11, color: trend >= 0 ? '#16a34a' : '#dc2626', fontWeight: 600 }}>
          {trend >= 0 ? '↑' : '↓'} {Math.abs(trend)}% vs last period
        </div>
      )}
    </div>
  );
}

function BarChart({ data, maxVal, colorKey }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
      {data.map(row => (
        <div key={row.label} style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <div style={{ width: 90, fontSize: 12, color: '#475569', fontWeight: 500, textAlign: 'right', flexShrink: 0 }}>{row.label}</div>
          <div style={{ flex: 1, background: '#f1f5f9', borderRadius: 6, height: 22, overflow: 'hidden' }}>
            <div style={{
              width: `${maxVal > 0 ? (row.value / maxVal) * 100 : 0}%`,
              height: '100%',
              background: colorKey ? (CHANNEL_COLORS[colorKey(row)] || '#3b82f6') : (row.color || '#3b82f6'),
              borderRadius: 6,
              transition: 'width 0.4s ease',
              display: 'flex', alignItems: 'center', paddingLeft: 8,
            }}>
              {row.value > 0 && <span style={{ fontSize: 11, color: '#fff', fontWeight: 700, whiteSpace: 'nowrap' }}>{row.value}</span>}
            </div>
          </div>
          <div style={{ width: 60, fontSize: 12, color: '#1e293b', fontWeight: 600, textAlign: 'right', flexShrink: 0 }}>{row.displayVal || row.value}</div>
        </div>
      ))}
    </div>
  );
}

function DonutChart({ slices, size = 120 }) {
  const total = slices.reduce((s, x) => s + x.value, 0);
  if (total === 0) return <div style={{ width: size, height: size, borderRadius: '50%', background: '#f1f5f9', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 12, color: '#94a3b8' }}>No data</div>;

  let cumulative = 0;
  const r = 40, cx = 60, cy = 60, strokeW = 18;
  const circumference = 2 * Math.PI * r;

  return (
    <svg width={size} height={size} viewBox="0 0 120 120">
      {slices.map((slice, i) => {
        const ratio = slice.value / total;
        const dashArray = ratio * circumference;
        const dashOffset = circumference - cumulative * circumference / total;
        const result = (
          <circle key={i} cx={cx} cy={cy} r={r}
            fill="none" stroke={slice.color} strokeWidth={strokeW}
            strokeDasharray={`${dashArray} ${circumference - dashArray}`}
            strokeDashoffset={dashOffset}
            style={{ transition: 'stroke-dasharray 0.4s ease', transform: 'rotate(-90deg)', transformOrigin: '60px 60px' }}
          />
        );
        cumulative += slice.value;
        return result;
      })}
      <text x={cx} y={cy - 4} textAnchor="middle" fontSize="14" fontWeight="800" fill="#1e293b">{total}</text>
      <text x={cx} y={cy + 12} textAnchor="middle" fontSize="8" fill="#64748b">orders</text>
    </svg>
  );
}

function Section({ title, children, icon }) {
  return (
    <div style={{ background: '#fff', borderRadius: 12, border: '1px solid #e2e8f0', overflow: 'hidden' }}>
      <div style={{ padding: '14px 20px', borderBottom: '1px solid #f1f5f9', display: 'flex', alignItems: 'center', gap: 8 }}>
        {icon && <span style={{ fontSize: 16 }}>{icon}</span>}
        <div style={{ fontWeight: 700, fontSize: 14, color: '#1e293b' }}>{title}</div>
      </div>
      <div style={{ padding: 20 }}>{children}</div>
    </div>
  );
}

// ── Main ──────────────────────────────────────────────────────────────────────
export default function AnalyticsPage() {
  const [range, setRange] = useState('all'); // all | 7d | 30d
  const allOrders = getOrders();

  const orders = useMemo(() => {
    if (range === 'all') return allOrders;
    const days = range === '7d' ? 7 : 30;
    const cutoff = new Date(Date.now() - days * 86400000);
    return allOrders.filter(o => new Date(o.createdAt || o.date) >= cutoff);
  }, [range, allOrders.length]);

  // ── Core metrics ────────────────────────────────────────────────────────────
  const total = orders.length;
  const revenue = orders.reduce((s, o) => s + Number(o.total ?? o.price ?? 0), 0);
  const delivered = orders.filter(o => o.status === 'delivered').length;
  const shipped = orders.filter(o => o.status === 'shipped').length;
  const rto = orders.filter(o => o.status === 'rto').length;
  const cancelled = orders.filter(o => o.status === 'cancelled').length;
  const confirmed = orders.filter(o => ['confirmed', 'rtd', 'shipped', 'delivered'].includes(o.status)).length;
  const conversionRate = pct(confirmed, total);
  const deliveryRate = pct(delivered, shipped + delivered + rto);
  const rtoRate = pct(rto, shipped + delivered + rto);
  const avgOrderValue = total > 0 ? Math.round(revenue / total) : 0;

  // ── By channel ──────────────────────────────────────────────────────────────
  const channels = [...new Set(orders.map(o => o.channel || 'manual'))];
  const channelData = channels.map(ch => {
    const chOrders = orders.filter(o => (o.channel || 'manual') === ch);
    const chRevenue = chOrders.reduce((s, o) => s + Number(o.total ?? o.price ?? 0), 0);
    const chConverted = chOrders.filter(o => ['confirmed','rtd','shipped','delivered'].includes(o.status)).length;
    return {
      channel: ch,
      label: CHANNEL_LABEL[ch] || ch,
      orders: chOrders.length,
      revenue: chRevenue,
      conversion: pct(chConverted, chOrders.length),
      color: CHANNEL_COLORS[ch] || '#3b82f6',
    };
  }).sort((a, b) => b.orders - a.orders);

  // ── By status ───────────────────────────────────────────────────────────────
  const statusGroups = ['new','confirmed','rtd','shipped','delivered','rto','cancelled'].map(s => ({
    label: s.charAt(0).toUpperCase() + s.slice(1),
    value: orders.filter(o => o.status === s).length,
    color: STATUS_COLOR[s] || '#94a3b8',
  })).filter(s => s.value > 0);

  // ── Top products ─────────────────────────────────────────────────────────────
  const productMap = {};
  for (const o of orders) {
    for (const item of (o.items || [])) {
      const key = item.name || 'Unknown';
      if (!productMap[key]) productMap[key] = { name: key, qty: 0, revenue: 0, orders: 0 };
      productMap[key].qty += item.qty || 1;
      productMap[key].revenue += Number(item.price ?? 0) * (item.qty || 1);
      productMap[key].orders += 1;
    }
  }
  const topProducts = Object.values(productMap).sort((a, b) => b.revenue - a.revenue).slice(0, 8);

  // ── WhatsApp vs Shopify conversion funnel ───────────────────────────────────
  const funnelChannels = ['whatsapp', 'shopify'].map(ch => {
    const chO = orders.filter(o => (o.channel || 'manual') === ch);
    const conv = chO.filter(o => ['confirmed','rtd','shipped','delivered'].includes(o.status));
    const del = chO.filter(o => o.status === 'delivered');
    return {
      channel: ch,
      label: CHANNEL_LABEL[ch],
      color: CHANNEL_COLORS[ch],
      total: chO.length,
      converted: conv.length,
      delivered: del.length,
      convRate: pct(conv.length, chO.length),
      delRate: pct(del.length, conv.length),
    };
  }).filter(f => f.total > 0);

  // ── Daily trend (last 14 days) ───────────────────────────────────────────────
  const dailyTrend = [];
  for (let i = 13; i >= 0; i--) {
    const d = new Date(Date.now() - i * 86400000);
    const label = d.toLocaleDateString('en-IN', { day: '2-digit', month: 'short' });
    const dayOrders = allOrders.filter(o => {
      const od = new Date(o.createdAt || o.date);
      return od.toDateString() === d.toDateString();
    });
    dailyTrend.push({ label, count: dayOrders.length, revenue: dayOrders.reduce((s, o) => s + Number(o.total ?? 0), 0) });
  }
  const maxDayCount = Math.max(...dailyTrend.map(d => d.count), 1);

  // ── Payment split ────────────────────────────────────────────────────────────
  const prepaid = orders.filter(o => o.payment !== 'cod').length;
  const cod = orders.filter(o => o.payment === 'cod').length;

  if (allOrders.length === 0) {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', height: '100%', gap: 12, color: '#94a3b8' }}>
        <div style={{ fontSize: 48 }}>📊</div>
        <div style={{ fontSize: 18, fontWeight: 700, color: '#1e293b' }}>No data yet</div>
        <div style={{ fontSize: 13 }}>Add orders to see analytics here.</div>
      </div>
    );
  }

  return (
    <div style={{ padding: 24, background: '#f8f9fa', minHeight: '100%' }}>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 20 }}>
        <div>
          <h1 style={{ fontSize: 20, fontWeight: 800, color: '#1e293b', margin: 0 }}>Analytics</h1>
          <p style={{ fontSize: 13, color: '#64748b', margin: '2px 0 0' }}>Live data from your orders · {total} orders in view</p>
        </div>
        <div style={{ display: 'flex', gap: 4, background: '#fff', border: '1px solid #e2e8f0', borderRadius: 8, padding: 3 }}>
          {[['all','All time'], ['30d','30 days'], ['7d','7 days']].map(([v, l]) => (
            <button key={v} onClick={() => setRange(v)} style={{
              padding: '5px 14px', borderRadius: 6, border: 'none', cursor: 'pointer',
              background: range === v ? '#1e293b' : 'transparent',
              color: range === v ? '#fff' : '#64748b',
              fontSize: 12, fontWeight: 600, fontFamily: 'inherit',
            }}>{l}</button>
          ))}
        </div>
      </div>

      {/* KPI strip */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 12, marginBottom: 20 }}>
        <StatCard label="Total Orders" value={total} icon="📦" color="#1e293b" />
        <StatCard label="Total Revenue" value={fmtCur(revenue)} icon="💰" color="#16a34a" sub={`Avg ₹${fmt(avgOrderValue)} per order`} />
        <StatCard label="Conversion Rate" value={`${conversionRate}%`} icon="🎯" color="#7c3aed" sub={`${confirmed} of ${total} confirmed`} />
        <StatCard label="Delivery Rate" value={`${deliveryRate}%`} icon="✅" color="#0369a1" sub={`RTO: ${rtoRate}%`} />
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, marginBottom: 16 }}>

        {/* Orders by channel */}
        <Section title="Orders by Channel" icon="📢">
          <BarChart
            data={channelData.map(c => ({ label: c.label, value: c.orders, color: c.color }))}
            maxVal={Math.max(...channelData.map(c => c.orders), 1)}
          />
        </Section>

        {/* Order status breakdown */}
        <Section title="Order Status Breakdown" icon="📊">
          <div style={{ display: 'flex', alignItems: 'center', gap: 24 }}>
            <DonutChart slices={statusGroups} size={130} />
            <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 7 }}>
              {statusGroups.map(s => (
                <div key={s.label} style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                    <div style={{ width: 10, height: 10, borderRadius: 2, background: s.color, flexShrink: 0 }} />
                    <span style={{ fontSize: 12, color: '#475569' }}>{s.label}</span>
                  </div>
                  <span style={{ fontSize: 12, fontWeight: 700, color: '#1e293b' }}>{s.value} <span style={{ color: '#94a3b8', fontWeight: 400 }}>({pct(s.value, total)}%)</span></span>
                </div>
              ))}
            </div>
          </div>
        </Section>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, marginBottom: 16 }}>

        {/* Revenue by channel */}
        <Section title="Revenue by Channel" icon="💳">
          <BarChart
            data={channelData.map(c => ({ label: c.label, value: c.revenue, color: c.color, displayVal: fmtCur(c.revenue) }))}
            maxVal={Math.max(...channelData.map(c => c.revenue), 1)}
          />
        </Section>

        {/* Conversion by channel */}
        <Section title="Conversion Rate by Channel" icon="🎯">
          <BarChart
            data={channelData.map(c => ({ label: c.label, value: c.conversion, color: c.color, displayVal: `${c.conversion}%` }))}
            maxVal={100}
          />
        </Section>
      </div>

      {/* WhatsApp vs Shopify funnel */}
      {funnelChannels.length > 0 && (
        <Section title="WhatsApp vs Shopify — Conversion Funnel" icon="🔄">
          <div style={{ display: 'grid', gridTemplateColumns: `repeat(${funnelChannels.length}, 1fr)`, gap: 20 }}>
            {funnelChannels.map(f => (
              <div key={f.channel}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 14 }}>
                  <div style={{ width: 10, height: 10, borderRadius: '50%', background: f.color }} />
                  <span style={{ fontWeight: 700, fontSize: 14, color: '#1e293b' }}>{f.label}</span>
                </div>
                {[
                  { label: 'Total Enquiries', value: f.total, pct: 100, color: '#e2e8f0' },
                  { label: 'Converted to Order', value: f.converted, pct: pct(f.converted, f.total), color: f.color + '99' },
                  { label: 'Delivered', value: f.delivered, pct: pct(f.delivered, f.total), color: f.color },
                ].map((step, i) => (
                  <div key={i} style={{ marginBottom: 10 }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12, color: '#64748b', marginBottom: 4 }}>
                      <span>{step.label}</span>
                      <span style={{ fontWeight: 600, color: '#1e293b' }}>{step.value} ({step.pct}%)</span>
                    </div>
                    <div style={{ background: '#f1f5f9', borderRadius: 6, height: 10, overflow: 'hidden' }}>
                      <div style={{ width: `${step.pct}%`, height: '100%', background: step.color, borderRadius: 6, transition: 'width 0.4s' }} />
                    </div>
                  </div>
                ))}
                <div style={{ marginTop: 12, padding: '10px 14px', background: '#f8fafc', borderRadius: 8, border: '1px solid #e2e8f0' }}>
                  <div style={{ fontSize: 11, color: '#64748b' }}>Conversion Rate</div>
                  <div style={{ fontSize: 22, fontWeight: 800, color: f.color }}>{f.convRate}%</div>
                </div>
              </div>
            ))}
          </div>
        </Section>
      )}

      <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr', gap: 16, marginTop: 16 }}>

        {/* Top products */}
        <Section title="Top Products by Revenue" icon="🛍️">
          {topProducts.length === 0
            ? <div style={{ color: '#94a3b8', fontSize: 13 }}>No product data yet.</div>
            : <BarChart
                data={topProducts.map(p => ({ label: p.name.length > 20 ? p.name.slice(0, 18) + '…' : p.name, value: p.revenue, color: '#3b82f6', displayVal: fmtCur(p.revenue) }))}
                maxVal={Math.max(...topProducts.map(p => p.revenue), 1)}
              />
          }
        </Section>

        {/* Payment split + delivery stats */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          <Section title="Payment Split" icon="💳">
            <div style={{ display: 'flex', gap: 10 }}>
              {[
                { label: 'Prepaid', value: prepaid, color: '#22c55e' },
                { label: 'COD', value: cod, color: '#f59e0b' },
              ].map(p => (
                <div key={p.label} style={{ flex: 1, textAlign: 'center', padding: '12px 8px', background: '#f8fafc', borderRadius: 10, border: '1px solid #e2e8f0' }}>
                  <div style={{ fontSize: 22, fontWeight: 800, color: p.color }}>{p.value}</div>
                  <div style={{ fontSize: 11, color: '#64748b', marginTop: 2 }}>{p.label}</div>
                  <div style={{ fontSize: 11, fontWeight: 600, color: '#94a3b8' }}>{pct(p.value, total)}%</div>
                </div>
              ))}
            </div>
          </Section>

          <Section title="Delivery Health" icon="🚚">
            {[
              { label: 'Shipped', value: shipped, color: '#0ea5e9' },
              { label: 'Delivered', value: delivered, color: '#22c55e' },
              { label: 'RTO', value: rto, color: '#ef4444' },
              { label: 'Cancelled', value: cancelled, color: '#94a3b8' },
            ].map(s => (
              <div key={s.label} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8, fontSize: 13 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                  <div style={{ width: 8, height: 8, borderRadius: '50%', background: s.color }} />
                  <span style={{ color: '#475569' }}>{s.label}</span>
                </div>
                <span style={{ fontWeight: 700, color: s.color }}>{s.value}</span>
              </div>
            ))}
          </Section>
        </div>
      </div>

      {/* Daily trend */}
      <div style={{ marginTop: 16 }}>
        <Section title="Daily Order Trend (Last 14 Days)" icon="📈">
          <div style={{ display: 'flex', alignItems: 'flex-end', gap: 6, height: 80 }}>
            {dailyTrend.map((d, i) => (
              <div key={i} style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 4 }}>
                <div style={{ width: '100%', background: d.count > 0 ? '#3b82f6' : '#f1f5f9', borderRadius: '4px 4px 0 0', height: `${Math.max((d.count / maxDayCount) * 64, d.count > 0 ? 8 : 2)}px`, transition: 'height 0.3s', position: 'relative' }}>
                  {d.count > 0 && (
                    <div style={{ position: 'absolute', top: -18, left: '50%', transform: 'translateX(-50%)', fontSize: 10, fontWeight: 700, color: '#1e293b', whiteSpace: 'nowrap' }}>{d.count}</div>
                  )}
                </div>
                <div style={{ fontSize: 9, color: '#94a3b8', whiteSpace: 'nowrap', transform: 'rotate(-30deg)', transformOrigin: 'top center', marginTop: 4 }}>{d.label}</div>
              </div>
            ))}
          </div>
        </Section>
      </div>
    </div>
  );
}
