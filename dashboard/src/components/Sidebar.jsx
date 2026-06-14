import { useState, useEffect, useMemo } from 'react';
import { getOrders } from '../data/orders';

function computeCounts() {
  let orders = [];
  try { orders = getOrders() || []; } catch { orders = []; }
  return {
    orders: orders.filter(o => o.status !== 'cancelled').length,
    new: orders.filter(o => o.status === 'new').length,
    rtd: orders.filter(o => o.status === 'rtd' || o.status === 'confirmed').length,
    shipped: orders.filter(o => o.status === 'shipped').length,
    rto: orders.filter(o => o.status === 'rto').length,
    delivered: orders.filter(o => o.status === 'delivered').length,
    byChannel: {
      amazon:  orders.filter(o => (o.channel || '').toLowerCase().includes('amazon')).length,
      flipkart: orders.filter(o => (o.channel || '').toLowerCase().includes('flipkart')).length,
      meesho:  orders.filter(o => (o.channel || '').toLowerCase().includes('meesho')).length,
      myntra:  orders.filter(o => (o.channel || '').toLowerCase().includes('myntra')).length,
      shopify: orders.filter(o => (o.channel || '').toLowerCase().includes('shopify')).length,
    },
  };
}

const NavIcon = ({ d }) => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d={d} />
  </svg>
);

const ICONS = {
  home: 'M3 9l9-7 9 7v11a2 2 0 01-2 2H5a2 2 0 01-2-2z M9 22V12h6v10',
  orders: 'M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2 M9 5a2 2 0 002 2h2a2 2 0 002-2 M9 5a2 2 0 012-2h2a2 2 0 012 2 M12 12h.01 M12 16h.01',
  products: 'M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4',
  shipping: 'M5 17H3a2 2 0 01-2-2V5a2 2 0 012-2h11a2 2 0 012 2v3 M18 18h-7a2 2 0 01-2-2V9 M23 11l-4.5-2.5L14 11l4.5 2.5z M18 18V11 M23 11v7',
  automation: 'M13 2L3 14h9l-1 8 10-12h-9l1-8',
  returns: 'M3 9l9-7 9 7 M9 22V12h6v10 M15 9H9',
  integrations: 'M10 13a5 5 0 007.54.54l3-3a5 5 0 00-7.07-7.07l-1.72 1.71 M14 11a5 5 0 00-7.54-.54l-3 3a5 5 0 007.07 7.07l1.71-1.71',
  analytics: 'M18 20V10 M12 20V4 M6 20v-6',
  whatsapp: 'M21 15a2 2 0 01-2 2H7l-4 4V5a2 2 0 012-2h14a2 2 0 012 2z',
  crm: 'M17 21v-2a4 4 0 00-4-4H5a4 4 0 00-4 4v2 M23 21v-2a4 4 0 00-3-3.87 M16 3.13a4 4 0 010 7.75 M9 7a4 4 0 100 8 4 4 0 000-8z',
  settings: 'M12 15a3 3 0 100-6 3 3 0 000 6z M19.4 15a1.65 1.65 0 00.33 1.82l.06.06a2 2 0 010 2.83 2 2 0 01-2.83 0l-.06-.06a1.65 1.65 0 00-1.82-.33 1.65 1.65 0 00-1 1.51V21a2 2 0 01-2 2 2 2 0 01-2-2v-.09A1.65 1.65 0 009 19.4a1.65 1.65 0 00-1.82.33l-.06.06a2 2 0 01-2.83 0 2 2 0 010-2.83l.06-.06A1.65 1.65 0 004.68 15a1.65 1.65 0 00-1.51-1H3a2 2 0 01-2-2 2 2 0 012-2h.09A1.65 1.65 0 004.6 9a1.65 1.65 0 00-.33-1.82l-.06-.06a2 2 0 010-2.83 2 2 0 012.83 0l.06.06A1.65 1.65 0 009 4.68a1.65 1.65 0 001-1.51V3a2 2 0 012-2 2 2 0 012 2v.09a1.65 1.65 0 001 1.51 1.65 1.65 0 001.82-.33l.06-.06a2 2 0 012.83 0 2 2 0 010 2.83l-.06.06A1.65 1.65 0 0019.4 9a1.65 1.65 0 001.51 1H21a2 2 0 012 2 2 2 0 01-2 2h-.09a1.65 1.65 0 00-1.51 1z',
};

function NavItem({ icon, label, badge, active, onClick, indent = 0 }) {
  return (
    <button onClick={onClick} style={{
      display: 'flex', alignItems: 'center', gap: '10px',
      width: '100%', padding: `8px 16px 8px ${16 + indent * 16}px`,
      background: active ? 'rgba(51,149,255,0.12)' : 'transparent',
      boxShadow: active ? 'inset 2px 0 0 #3395FF' : 'none',
      color: active ? '#E8ECF4' : '#7A8499',
      fontSize: '13px', fontWeight: active ? '500' : '400',
      transition: 'all 0.12s', cursor: 'pointer',
      textAlign: 'left', fontFamily: 'inherit',
    }}
    onMouseEnter={e => { if (!active) { e.currentTarget.style.background = 'rgba(255,255,255,0.04)'; e.currentTarget.style.color = '#C8D0E0'; }}}
    onMouseLeave={e => { if (!active) { e.currentTarget.style.background = 'transparent'; e.currentTarget.style.color = '#7A8499'; }}}
    >
      {icon && <span style={{ opacity: active ? 1 : 0.6, flexShrink: 0 }}><NavIcon d={ICONS[icon]} /></span>}
      {!icon && <span style={{ width: 6, height: 6, borderRadius: '50%', background: active ? '#3395FF' : '#3A4255', flexShrink: 0, marginLeft: 2 }} />}
      <span style={{ flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{label}</span>
      {badge !== undefined && badge > 0 && (
        <span style={{ background: '#3395FF', color: '#fff', borderRadius: '10px', padding: '1px 6px', fontSize: '10px', fontWeight: 700, minWidth: 18, textAlign: 'center' }}>{badge}</span>
      )}
      {badge === 0 && <span style={{ color: '#3A4255', fontSize: '11px' }}>0</span>}
    </button>
  );
}

function Section({ title, children, defaultOpen = false }) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div>
      <button onClick={() => setOpen(!open)} style={{
        display: 'flex', alignItems: 'center', gap: 6, width: '100%',
        padding: '6px 16px', color: '#4A5568', fontSize: '10px', fontWeight: 700,
        textTransform: 'uppercase', letterSpacing: '0.8px', background: 'none',
        border: 'none', cursor: 'pointer', fontFamily: 'inherit',
        marginTop: 4,
      }}>
        <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"
          style={{ transform: open ? 'rotate(90deg)' : 'rotate(0deg)', transition: 'transform 0.15s' }}>
          <path d="m9 18 6-6-6-6" />
        </svg>
        {title}
      </button>
      {open && <div>{children}</div>}
    </div>
  );
}

export default function Sidebar({ active, onNavigate }) {
  const [counts, setCounts] = useState(() => computeCounts());

  // Recompute on every navigation (active change) and on localStorage updates
  useEffect(() => {
    setCounts(computeCounts());
  }, [active]);

  useEffect(() => {
    const handler = () => setCounts(computeCounts());
    window.addEventListener('storage', handler);
    // Also poll every 3s to catch same-tab localStorage writes
    const interval = setInterval(handler, 3000);
    return () => { window.removeEventListener('storage', handler); clearInterval(interval); };
  }, []);

  return (
    <div style={{
      width: 'var(--sidebar-width)', minHeight: '100vh', background: 'var(--sidebar-bg)',
      display: 'flex', flexDirection: 'column', flexShrink: 0,
      borderRight: '1px solid var(--sidebar-border)', overflowY: 'auto',
    }}>
      {/* Logo */}
      <div style={{ padding: '18px 16px 12px', display: 'flex', alignItems: 'center', gap: 8 }}>
        <div style={{ width: 28, height: 28, background: '#3395FF', borderRadius: '8px', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="white"><path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z"/></svg>
        </div>
        <span style={{ color: '#E8ECF4', fontWeight: 700, fontSize: '16px', letterSpacing: '-0.3px' }}>d2c<span style={{ color: '#3395FF' }}>flow</span></span>
        <span style={{ marginLeft: 'auto', background: '#1E2640', color: '#3395FF', fontSize: '9px', fontWeight: 700, padding: '2px 6px', borderRadius: 4, letterSpacing: '0.5px' }}>BETA</span>
      </div>

      <div style={{ height: 1, background: 'var(--sidebar-border)', margin: '0 12px 8px' }} />

      {/* Main nav */}
      <NavItem icon="home" label="Home" active={active === 'home'} onClick={() => onNavigate('home')} />
      <NavItem icon="orders" label="Orders" badge={counts.orders} active={active === 'orders'} onClick={() => onNavigate('orders')} />
      <NavItem icon="whatsapp" label="WhatsApp Orders" active={active === 'whatsapp-orders'} onClick={() => onNavigate('whatsapp-orders')} />
      <NavItem icon="crm" label="CRM" active={active === 'crm'} onClick={() => onNavigate('crm')} />
      <NavItem icon="shipping" label="Shipping" badge={counts.rtd} active={active === 'shipping'} onClick={() => onNavigate('shipping')} />
      <NavItem icon="products" label="Products" active={active === 'products'} onClick={() => onNavigate('products')} />
      <NavItem icon="returns" label="Returns" badge={counts.rto} active={active === 'returns'} onClick={() => onNavigate('returns')} />
      <NavItem icon="automation" label="Automations" active={active === 'automations'} onClick={() => onNavigate('automations')} />
      <NavItem icon="analytics" label="Analytics" active={active === 'analytics'} onClick={() => onNavigate('analytics')} />
      <NavItem icon="integrations" label="Integrations" active={active === 'integrations'} onClick={() => onNavigate('integrations')} />

      <div style={{ height: 1, background: 'var(--sidebar-border)', margin: '8px 12px' }} />

      {/* Channel sections */}
      <Section title="Marketplaces" defaultOpen>
        <NavItem label="Amazon IN" badge={counts.byChannel.amazon} active={active === 'ch-amazon'} onClick={() => onNavigate('ch-amazon')} indent={0.5} />
        <NavItem label="Flipkart" badge={counts.byChannel.flipkart} active={active === 'ch-flipkart'} onClick={() => onNavigate('ch-flipkart')} indent={0.5} />
        <NavItem label="Meesho" badge={counts.byChannel.meesho} active={active === 'ch-meesho'} onClick={() => onNavigate('ch-meesho')} indent={0.5} />
        <NavItem label="Myntra" badge={counts.byChannel.myntra} active={active === 'ch-myntra'} onClick={() => onNavigate('ch-myntra')} indent={0.5} />
        <NavItem label="Shopify" badge={counts.byChannel.shopify} active={active === 'ch-shopify'} onClick={() => onNavigate('ch-shopify')} indent={0.5} />
      </Section>

      <Section title="Shipments">
        <NavItem label="In Transit" badge={counts.shipped} active={false} onClick={() => onNavigate('orders')} indent={0.5} />
        <NavItem label="Ready to Dispatch" badge={counts.rtd} active={false} onClick={() => onNavigate('shipping')} indent={0.5} />
        <NavItem label="RTO Initiated" badge={counts.rto} active={false} onClick={() => onNavigate('returns')} indent={0.5} />
        <NavItem label="Lost Shipment" badge={0} active={false} onClick={() => {}} indent={0.5} />
      </Section>

      {/* Bottom */}
      <div style={{ marginTop: 'auto', padding: '12px', borderTop: '1px solid var(--sidebar-border)' }}>
        <NavItem icon="settings" label="Settings" active={active === 'settings'} onClick={() => onNavigate('settings')} />
      </div>
    </div>
  );
}
