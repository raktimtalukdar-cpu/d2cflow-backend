import { useState } from 'react';
import { toast } from '../components/Toast';

function Section({ title, children }) {
  return (
    <div className="card" style={{ padding: 24, marginBottom: 20 }}>
      <div style={{ fontWeight: 700, fontSize: 14, marginBottom: 16, paddingBottom: 12, borderBottom: '1px solid var(--border)' }}>{title}</div>
      {children}
    </div>
  );
}

function Field({ label, hint, children }) {
  return (
    <div style={{ marginBottom: 16 }}>
      <label style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-secondary)', display: 'block', marginBottom: 4 }}>{label}</label>
      {hint && <div style={{ fontSize: 11, color: 'var(--text-disabled)', marginBottom: 5 }}>{hint}</div>}
      {children}
    </div>
  );
}

export default function SettingsPage() {
  const [brand, setBrand] = useState(() => {
    try { return JSON.parse(localStorage.getItem('d2c_brand_profile') || 'null') || { name: '', email: '', phone: '', gstin: '', pan: '' }; } catch { return { name: '', email: '', phone: '', gstin: '', pan: '' }; }
  });
  const [address, setAddress] = useState(() => {
    try { return JSON.parse(localStorage.getItem('d2c_brand_address') || 'null') || { line1: '', city: '', state: '', pincode: '', country: 'India' }; } catch { return { line1: '', city: '', state: '', pincode: '', country: 'India' }; }
  });
  const [notifications, setNotifications] = useState({ newOrder: true, dispatch: true, delivery: true, rto: true, lowStock: false, paymentFailed: true });
  const [saving, setSaving] = useState(false);
  const [tab, setTab] = useState('profile');

  const save = async () => {
    setSaving(true);
    localStorage.setItem('d2c_brand_profile', JSON.stringify(brand));
    localStorage.setItem('d2c_brand_address', JSON.stringify(address));
    await new Promise(r => setTimeout(r, 400));
    setSaving(false);
    toast.success('Settings saved');
  };

  const tabs = [
    { key: 'profile', label: 'Brand Profile' },
    { key: 'notifications', label: 'Notifications' },
    { key: 'team', label: 'Team & Roles' },
    { key: 'api', label: 'API Keys' },
  ];

  return (
    <div style={{ padding: 24, maxWidth: 760 }}>
      <h1 style={{ fontSize: 20, fontWeight: 700, marginBottom: 6 }}>Settings</h1>
      <p style={{ fontSize: 13, color: 'var(--text-secondary)', marginBottom: 24 }}>Manage your brand profile, notifications, and account preferences.</p>

      {/* Tabs */}
      <div style={{ display: 'flex', gap: 2, marginBottom: 24, background: 'var(--surface-2)', borderRadius: 'var(--radius)', padding: 3, width: 'fit-content', border: '1px solid var(--border)' }}>
        {tabs.map(t => (
          <button key={t.key} onClick={() => setTab(t.key)}
            style={{ padding: '6px 14px', borderRadius: 'var(--radius-sm)', border: 'none', cursor: 'pointer', fontSize: 12, fontWeight: 500, fontFamily: 'inherit', background: tab === t.key ? '#fff' : 'transparent', color: tab === t.key ? 'var(--text-primary)' : 'var(--text-secondary)', boxShadow: tab === t.key ? 'var(--shadow)' : 'none' }}>
            {t.label}
          </button>
        ))}
      </div>

      {tab === 'profile' && (
        <>
          <Section title="Brand Information">
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14 }}>
              <Field label="Brand name *">
                <input className="form-input" value={brand.name} onChange={e => setBrand(b => ({ ...b, name: e.target.value }))} />
              </Field>
              <Field label="Contact email *">
                <input className="form-input" type="email" value={brand.email} onChange={e => setBrand(b => ({ ...b, email: e.target.value }))} />
              </Field>
              <Field label="Phone number">
                <input className="form-input" value={brand.phone} onChange={e => setBrand(b => ({ ...b, phone: e.target.value }))} />
              </Field>
              <Field label="GSTIN" hint="Required for GST invoice generation">
                <input className="form-input" value={brand.gstin} onChange={e => setBrand(b => ({ ...b, gstin: e.target.value }))} placeholder="22AAAAA0000A1Z5" />
              </Field>
              <Field label="PAN">
                <input className="form-input" value={brand.pan} onChange={e => setBrand(b => ({ ...b, pan: e.target.value }))} />
              </Field>
            </div>
          </Section>

          <Section title="Pickup / Warehouse Address">
            <Field label="Address line 1">
              <input className="form-input" value={address.line1} onChange={e => setAddress(a => ({ ...a, line1: e.target.value }))} style={{ width: '100%', boxSizing: 'border-box' }} />
            </Field>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 14 }}>
              <Field label="City">
                <input className="form-input" value={address.city} onChange={e => setAddress(a => ({ ...a, city: e.target.value }))} />
              </Field>
              <Field label="State">
                <input className="form-input" value={address.state} onChange={e => setAddress(a => ({ ...a, state: e.target.value }))} />
              </Field>
              <Field label="Pincode">
                <input className="form-input" value={address.pincode} onChange={e => setAddress(a => ({ ...a, pincode: e.target.value }))} />
              </Field>
            </div>
          </Section>

          <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
            <button className="btn btn-primary" onClick={save} disabled={saving}>
              {saving ? 'Saving…' : 'Save changes'}
            </button>
          </div>
        </>
      )}

      {tab === 'notifications' && (
        <Section title="Notification Preferences">
          {[
            { key: 'newOrder', label: 'New order received', desc: 'Get notified when a new order comes in from any channel' },
            { key: 'dispatch', label: 'Order dispatched', desc: 'Notify when shipment is picked up by courier' },
            { key: 'delivery', label: 'Order delivered', desc: 'Confirmation when order is marked delivered' },
            { key: 'rto', label: 'RTO initiated', desc: 'Alert when a shipment is returned by courier' },
            { key: 'lowStock', label: 'Low stock alert', desc: 'Notify when SKU inventory drops below threshold' },
            { key: 'paymentFailed', label: 'Payment failure', desc: 'Alert on failed payment or COD non-collection' },
          ].map(item => (
            <div key={item.key} style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '12px 0', borderBottom: '1px solid var(--border)' }}>
              <div>
                <div style={{ fontSize: 13, fontWeight: 500 }}>{item.label}</div>
                <div style={{ fontSize: 11, color: 'var(--text-secondary)', marginTop: 2 }}>{item.desc}</div>
              </div>
              <div onClick={() => setNotifications(n => ({ ...n, [item.key]: !n[item.key] }))}
                style={{ width: 40, height: 22, borderRadius: 11, background: notifications[item.key] ? 'var(--blue)' : 'var(--border)', cursor: 'pointer', position: 'relative', transition: 'background 0.2s', flexShrink: 0 }}>
                <div style={{ position: 'absolute', top: 3, left: notifications[item.key] ? 21 : 3, width: 16, height: 16, borderRadius: '50%', background: '#fff', transition: 'left 0.2s', boxShadow: '0 1px 3px rgba(0,0,0,0.2)' }} />
              </div>
            </div>
          ))}
          <div style={{ marginTop: 16, display: 'flex', justifyContent: 'flex-end' }}>
            <button className="btn btn-primary" onClick={() => toast.success('Notification preferences saved')}>Save preferences</button>
          </div>
        </Section>
      )}

      {tab === 'team' && (
        <Section title="Team Members">
          <div style={{ marginBottom: 16, display: 'flex', justifyContent: 'flex-end' }}>
            <button className="btn btn-primary" style={{ gap: 6, fontSize: 12 }} onClick={() => toast.info('Use "Invite Team" from the profile menu to add members')}>
              + Invite member
            </button>
          </div>
          {(() => {
            const bp = (() => { try { return JSON.parse(localStorage.getItem('d2c_brand_profile') || 'null') || {}; } catch { return {}; } })();
            const name = bp.name || 'Workspace Admin';
            const email = bp.email || '—';
            const initials = name.split(' ').slice(0,2).map(w => w[0]).join('').toUpperCase() || 'A';
            return (
              <div style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '10px 0', borderBottom: '1px solid var(--border)' }}>
                <div style={{ width: 32, height: 32, borderRadius: '50%', background: 'linear-gradient(135deg, #3395FF, #7C3AED)', color: '#fff', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 11, fontWeight: 700 }}>{initials}</div>
                <div style={{ flex: 1 }}>
                  <div style={{ fontSize: 13, fontWeight: 500 }}>{name}</div>
                  <div style={{ fontSize: 11, color: 'var(--text-secondary)' }}>{email}</div>
                </div>
                <span style={{ fontSize: 11, background: 'var(--blue-light)', color: 'var(--blue)', padding: '3px 8px', borderRadius: 'var(--radius)', fontWeight: 600 }}>Owner</span>
              </div>
            );
          })()}
          <div style={{ marginTop: 16, padding: 16, background: 'var(--surface-2)', borderRadius: 'var(--radius)', border: '1px dashed var(--border)', textAlign: 'center', fontSize: 13, color: 'var(--text-secondary)' }}>
            Invite teammates to collaborate on orders, shipping, and returns.
          </div>
        </Section>
      )}

      {tab === 'api' && (
        <Section title="API Keys">
          <div style={{ padding: 16, background: '#FFF8E1', border: '1px solid #FFD54F', borderRadius: 'var(--radius)', marginBottom: 16, fontSize: 12, color: '#795548' }}>
            ⚠️ Keep your API keys secure. Never share them publicly or commit them to version control.
          </div>
          {[
            { label: 'Live API Key', value: 'd2c_live_xxxxxxxxxxxxxxxxxxxxxxxx', active: true },
            { label: 'Test API Key', value: 'd2c_test_xxxxxxxxxxxxxxxxxxxxxxxx', active: false },
          ].map(k => (
            <div key={k.label} style={{ marginBottom: 16 }}>
              <label style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-secondary)', display: 'block', marginBottom: 5 }}>{k.label}</label>
              <div style={{ display: 'flex', gap: 8 }}>
                <input className="form-input" value={k.value} readOnly style={{ flex: 1, fontFamily: 'monospace', fontSize: 12 }} />
                <button className="btn btn-secondary" style={{ fontSize: 12 }} onClick={() => { navigator.clipboard?.writeText(k.value); toast.success('API key copied to clipboard'); }}>Copy</button>
                <button className="btn btn-secondary" style={{ fontSize: 12 }} onClick={() => toast.warn('Regenerating will invalidate the current key. Confirm?')}>Regenerate</button>
              </div>
            </div>
          ))}
        </Section>
      )}
    </div>
  );
}
