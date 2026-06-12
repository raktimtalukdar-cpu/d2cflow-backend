import { useState, useRef, useEffect } from 'react';
import { toast } from './Toast';

export default function Topbar({ page, user, onSignOut, onNavigate, onInvite }) {
  const [search, setSearch] = useState('');
  const [showUserMenu, setShowUserMenu] = useState(false);
  const menuRef = useRef(null);

  const PAGE_LABELS = {
    home: 'Home', orders: 'Orders', shipping: 'Shipping',
    products: 'Products', returns: 'Returns', automations: 'Automations',
    analytics: 'Analytics', integrations: 'Integrations', settings: 'Settings',
    'ch-amazon': 'Amazon IN', 'ch-flipkart': 'Flipkart',
    'ch-meesho': 'Meesho', 'ch-myntra': 'Myntra', 'ch-shopify': 'Shopify',
  };

  // Close menu on outside click
  useEffect(() => {
    const handler = e => { if (menuRef.current && !menuRef.current.contains(e.target)) setShowUserMenu(false); };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, []);

  const displayName = user?.user_metadata?.brand_name || user?.email?.split('@')[0] || 'Raktim T.';
  const initials = displayName.split(' ').slice(0, 2).map(w => w[0]).join('').toUpperCase().slice(0, 2) || 'RT';

  return (
    <div style={{
      height: 52, background: '#fff', borderBottom: '1px solid var(--border)',
      display: 'flex', alignItems: 'center', gap: 12, padding: '0 20px',
      position: 'sticky', top: 0, zIndex: 50, flexShrink: 0,
    }}>
      {/* Breadcrumb */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 6, color: 'var(--text-secondary)', fontSize: '13px' }}>
        <span style={{ color: 'var(--text-disabled)' }}>Quick access</span>
        <span style={{ color: 'var(--border-strong)' }}>/</span>
        <span style={{ color: 'var(--text-primary)', fontWeight: 500 }}>{PAGE_LABELS[page] || page}</span>
      </div>

      {/* Search */}
      <div style={{ flex: 1, maxWidth: 400, position: 'relative', margin: '0 auto' }}>
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="var(--text-disabled)" strokeWidth="2"
          style={{ position: 'absolute', left: 10, top: '50%', transform: 'translateY(-50%)' }}>
          <circle cx="11" cy="11" r="8"/><path d="m21 21-4.35-4.35"/>
        </svg>
        <input
          className="form-input"
          style={{ paddingLeft: 32, fontSize: '13px', background: 'var(--surface-2)', border: '1px solid var(--border)' }}
          placeholder="Search orders, products, customers..."
          value={search}
          onChange={e => setSearch(e.target.value)}
        />
        <kbd style={{ position: 'absolute', right: 8, top: '50%', transform: 'translateY(-50%)', fontSize: '10px', color: 'var(--text-disabled)', background: 'var(--border)', padding: '1px 5px', borderRadius: 3 }}>⌘K</kbd>
      </div>

      {/* Right actions */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginLeft: 'auto' }}>
        <button className="btn btn-ghost btn-icon" style={{ position: 'relative' }}
          onClick={() => toast.info('No new notifications')}>
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M18 8A6 6 0 006 8c0 7-3 9-3 9h18s-3-2-3-9 M13.73 21a2 2 0 01-3.46 0"/>
          </svg>
          <span style={{ position: 'absolute', top: 4, right: 4, width: 7, height: 7, background: '#DC2626', borderRadius: '50%', border: '1.5px solid #fff' }} />
        </button>

        <button className="btn btn-ghost btn-icon"
          onClick={() => toast.info('Help docs coming soon')}>
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <circle cx="12" cy="12" r="10"/>
            <path d="M9.09 9a3 3 0 015.83 1c0 2-3 3-3 3 M12 17h.01"/>
          </svg>
        </button>

        {/* User dropdown */}
        <div ref={menuRef} style={{ position: 'relative' }}>
          <div onClick={() => setShowUserMenu(v => !v)}
            style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '4px 8px', borderRadius: 'var(--radius)', cursor: 'pointer', border: '1px solid var(--border)', background: showUserMenu ? 'var(--surface-2)' : 'transparent' }}
            onMouseEnter={e => { if (!showUserMenu) e.currentTarget.style.background = 'var(--surface-2)'; }}
            onMouseLeave={e => { if (!showUserMenu) e.currentTarget.style.background = 'transparent'; }}>
            <div style={{ width: 26, height: 26, borderRadius: '50%', background: 'linear-gradient(135deg, #3395FF, #7C3AED)', display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#fff', fontSize: '11px', fontWeight: 700 }}>
              {initials}
            </div>
            <span style={{ fontSize: '13px', fontWeight: 500, color: 'var(--text-primary)' }}>{displayName}</span>
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="var(--text-secondary)" strokeWidth="2">
              <path d={showUserMenu ? 'm18 15-6-6-6 6' : 'm6 9 6 6 6-6'}/>
            </svg>
          </div>

          {showUserMenu && (
            <div style={{
              position: 'absolute', top: 'calc(100% + 6px)', right: 0, width: 200,
              background: '#fff', border: '1px solid var(--border)', borderRadius: 'var(--radius)',
              boxShadow: 'var(--shadow-md)', overflow: 'hidden', zIndex: 300,
            }}>
              <div style={{ padding: '10px 14px', borderBottom: '1px solid var(--border)' }}>
                <div style={{ fontSize: 13, fontWeight: 600 }}>{displayName}</div>
                <div style={{ fontSize: 11, color: 'var(--text-secondary)', marginTop: 2 }}>{user?.email || 'demo@d2cflow.in'}</div>
              </div>
              {[
                { label: 'Account settings', icon: 'M12 15a3 3 0 100-6 3 3 0 000 6z', action: () => { setShowUserMenu(false); onNavigate?.('settings'); } },
                { label: 'Billing & plan', icon: 'M3 10h18M7 15h1m4 0h1m-7 4h12a3 3 0 003-3V8a3 3 0 00-3-3H6a3 3 0 00-3 3v8a3 3 0 003 3z', action: () => { setShowUserMenu(false); onNavigate?.('billing'); } },
                { label: 'Invite team', icon: 'M16 21v-2a4 4 0 00-4-4H6a4 4 0 00-4 4v2 M12 11a4 4 0 100-8 4 4 0 000 8z M19 8v6 M22 11h-6', action: () => { setShowUserMenu(false); onInvite?.(); } },
              ].map(item => (
                <button key={item.label} onClick={item.action}
                  style={{ display: 'flex', alignItems: 'center', gap: 10, width: '100%', padding: '9px 14px', background: 'none', border: 'none', cursor: 'pointer', fontSize: 13, color: 'var(--text-primary)', fontFamily: 'inherit', textAlign: 'left' }}
                  onMouseEnter={e => e.currentTarget.style.background = 'var(--surface-2)'}
                  onMouseLeave={e => e.currentTarget.style.background = 'none'}>
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d={item.icon}/></svg>
                  {item.label}
                </button>
              ))}
              <div style={{ borderTop: '1px solid var(--border)' }}>
                <button onClick={() => { setShowUserMenu(false); onSignOut?.(); }}
                  style={{ display: 'flex', alignItems: 'center', gap: 10, width: '100%', padding: '9px 14px', background: 'none', border: 'none', cursor: 'pointer', fontSize: 13, color: 'var(--red)', fontFamily: 'inherit', textAlign: 'left' }}
                  onMouseEnter={e => e.currentTarget.style.background = 'var(--red-light)'}
                  onMouseLeave={e => e.currentTarget.style.background = 'none'}>
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M9 21H5a2 2 0 01-2-2V5a2 2 0 012-2h4 M16 17l5-5-5-5 M21 12H9"/></svg>
                  Sign out
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
