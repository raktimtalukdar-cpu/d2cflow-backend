import { useState, useEffect } from 'react';
import { getOrders, updateOrder } from '../data/orders';
import { decrementStock, getProducts } from '../data/products';
import { toast } from '../components/Toast';

const BACKEND = import.meta.env.VITE_API_URL || '';

async function apiFetch(path, options = {}) {
  const res = await fetch(`${BACKEND}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || `HTTP ${res.status}`);
  return data;
}

// rtdOrders computed inside component from state

// ── Create Shipment Modal (calls real Shiprocket API) ─────────────────────────
function CreateShipmentModal({ order, onClose, onShipped }) {
  const [step, setStep] = useState('confirm');
  const [result, setResult] = useState(null);
  const [errorMsg, setErrorMsg] = useState('');
  const [weight, setWeight] = useState(0.5);
  const [pickupLocation, setPickupLocation] = useState('Home');
  const [addr, setAddrState] = useState({
    name:    order.customer || '',
    phone:   String(order.phone || '').replace(/\D/g, ''),
    address: order.address || '',
    city:    order.city !== '—' ? (order.city || '') : '',
    state:   order.state !== '—' ? (order.state || '') : '',
    pincode: order.pincode !== '—' ? (order.pincode || '') : '',
  });
  const setAddr = k => e => setAddrState(a => ({ ...a, [k]: e.target.value }));

  const totalAmount = order.total ?? order.items?.reduce((s, i) => s + (i.price ?? 0) * (i.qty ?? 1), 0) ?? 0;

  const handleCreate = async () => {
    if (!addr.address.trim()) { toast.error('Address line required'); return; }
    if (!addr.city.trim())    { toast.error('City required'); return; }
    if (!addr.state.trim())   { toast.error('State required'); return; }
    if (!addr.pincode.trim()) { toast.error('Pincode required'); return; }

    setStep('loading');
    try {
      const srOrderId = `${order.id}-${Date.now()}`;
      const payload = {
        order_id: srOrderId,
        order_date: order.date || new Date().toISOString().split('T')[0],
        customer_name: addr.name || order.customer || 'Customer',
        customer_phone: addr.phone.replace(/\D/g, '') || '9999999999',
        customer_email: order.email || '',
        address: addr.address,
        city: addr.city,
        state: addr.state,
        pincode: addr.pincode,
        payment_method: order.payment === 'cod' ? 'COD' : 'Prepaid',
        sub_total: totalAmount,
        weight,
        pickup_location: pickupLocation,
        items: (order.items || []).map(item => ({
          name: item.name || 'Product',
          sku: item.sku || '',
          qty: item.qty || 1,
          price: item.price ?? item.unit_price ?? 0,
        })),
      };

      const data = await apiFetch('/api/shiprocket/shipment/create', {
        method: 'POST',
        body: JSON.stringify(payload),
      });

      setResult(data);
      setStep('done');
      if (onShipped) onShipped(order.id, data);
      toast.success(`Shipment created! AWB: ${data.awb || 'pending'}`);
    } catch (e) {
      setErrorMsg(e.message || 'Shipment creation failed');
      setStep('error');
    }
  };

  return (
    <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.45)', zIndex: 200, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
      <div onClick={e => e.stopPropagation()} className="animate-in"
        style={{ width: 520, background: '#fff', borderRadius: 'var(--radius-lg)', boxShadow: 'var(--shadow-lg)', overflow: 'hidden' }}>

        {/* Header */}
        <div style={{ padding: '16px 20px', borderBottom: '1px solid var(--border)', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <div>
            <div style={{ fontWeight: 700, fontSize: '15px' }}>Create Shipment via Shiprocket</div>
            <div style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>{order.id} · {order.customer}</div>
          </div>
          <button onClick={onClose} className="btn btn-ghost btn-icon">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M18 6L6 18M6 6l12 12"/></svg>
          </button>
        </div>

        {/* Loading */}
        {step === 'loading' && (
          <div style={{ padding: 48, textAlign: 'center' }}>
            <div style={{ width: 48, height: 48, border: '4px solid var(--border)', borderTop: '4px solid var(--blue)', borderRadius: '50%', animation: 'spin 0.8s linear infinite', margin: '0 auto 20px' }} />
            <div style={{ fontWeight: 600, color: 'var(--text-primary)', marginBottom: 6 }}>Creating shipment…</div>
            <div style={{ fontSize: 12, color: 'var(--text-secondary)' }}>Connecting to Shiprocket, assigning courier & generating AWB</div>
            <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
          </div>
        )}

        {/* Done */}
        {step === 'done' && result && (
          <div style={{ padding: 32, textAlign: 'center' }}>
            <div style={{ width: 64, height: 64, background: 'var(--green-light)', borderRadius: '50%', display: 'flex', alignItems: 'center', justifyContent: 'center', margin: '0 auto 16px', fontSize: '28px' }}>✅</div>
            <div style={{ fontWeight: 700, fontSize: '17px', marginBottom: 12 }}>Shipment Created!</div>

            <div style={{ background: '#f8fafc', borderRadius: 10, padding: '14px 20px', marginBottom: 20, textAlign: 'left' }}>
              {result.awb && (
                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8 }}>
                  <span style={{ fontSize: 12, color: '#64748b' }}>AWB Number</span>
                  <span style={{ fontFamily: 'monospace', fontWeight: 700, fontSize: 13, color: '#1e293b' }}>{result.awb}</span>
                </div>
              )}
              {result.courier && (
                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8 }}>
                  <span style={{ fontSize: 12, color: '#64748b' }}>Courier</span>
                  <span style={{ fontSize: 13, fontWeight: 600 }}>{result.courier}</span>
                </div>
              )}
              {result.shiprocket_order_id && (
                <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                  <span style={{ fontSize: 12, color: '#64748b' }}>Shiprocket Order ID</span>
                  <span style={{ fontSize: 13, fontFamily: 'monospace' }}>{result.shiprocket_order_id}</span>
                </div>
              )}
            </div>

            <div style={{ display: 'flex', gap: 8, justifyContent: 'center' }}>
              {result.label_url && (
                <a href={result.label_url} target="_blank" rel="noreferrer"
                  style={{ padding: '8px 16px', background: 'var(--blue)', color: '#fff', borderRadius: 8, fontSize: 13, fontWeight: 600, textDecoration: 'none', display: 'flex', alignItems: 'center', gap: 5 }}>
                  🖨️ Print Label
                </a>
              )}
              <button className="btn btn-primary" onClick={onClose}>Done</button>
            </div>
          </div>
        )}

        {/* Error */}
        {step === 'error' && (
          <div style={{ padding: 32, textAlign: 'center' }}>
            <div style={{ fontSize: 48, marginBottom: 12 }}>❌</div>
            <div style={{ fontWeight: 700, fontSize: '16px', marginBottom: 8 }}>Shipment Failed</div>
            <div style={{ fontSize: 12, color: '#dc2626', background: '#fee2e2', border: '1px solid rgba(220,38,38,0.2)', borderRadius: 8, padding: '10px 16px', marginBottom: 20, textAlign: 'left', lineHeight: 1.6 }}>
              {errorMsg}
            </div>
            <div style={{ display: 'flex', gap: 8, justifyContent: 'center' }}>
              <button className="btn btn-secondary" onClick={onClose}>Cancel</button>
              <button className="btn btn-primary" onClick={() => setStep('confirm')}>Try Again</button>
            </div>
          </div>
        )}

        {/* Confirm */}
        {step === 'confirm' && (
          <>
            <div style={{ padding: 20, display: 'flex', flexDirection: 'column', gap: 12, overflowY: 'auto', flex: 1 }}>
              {/* Order summary strip */}
              <div style={{ background: 'var(--surface-2)', borderRadius: 'var(--radius)', padding: '10px 14px', border: '1px solid var(--border)', display: 'flex', justifyContent: 'space-between', fontSize: 13 }}>
                <span style={{ color: 'var(--text-secondary)' }}>{(order.items || []).map(i => i.name).join(', ') || '—'}</span>
                <span style={{ fontWeight: 700, color: 'var(--blue)' }}>₹{totalAmount.toLocaleString('en-IN')} · {order.payment?.toUpperCase()}</span>
              </div>

              {/* Delivery Address */}
              <div style={{ fontSize: 11, fontWeight: 700, color: 'var(--text-secondary)', textTransform: 'uppercase', letterSpacing: '0.5px' }}>Delivery Address</div>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
                <div style={{ gridColumn: '1/-1' }}>
                  <label style={{ fontSize: 11, fontWeight: 600, color: 'var(--text-secondary)', display: 'block', marginBottom: 3 }}>Customer Name</label>
                  <input value={addr.name} onChange={setAddr('name')} className="form-input" style={{ width: '100%', boxSizing: 'border-box' }} placeholder="Full name" />
                </div>
                <div>
                  <label style={{ fontSize: 11, fontWeight: 600, color: 'var(--text-secondary)', display: 'block', marginBottom: 3 }}>Phone <span style={{ color: '#dc2626' }}>*</span></label>
                  <input value={addr.phone} onChange={setAddr('phone')} className="form-input" style={{ width: '100%', boxSizing: 'border-box' }} placeholder="10-digit mobile" />
                </div>
                <div style={{ gridColumn: '1/-1' }}>
                  <label style={{ fontSize: 11, fontWeight: 600, color: 'var(--text-secondary)', display: 'block', marginBottom: 3 }}>Address Line <span style={{ color: '#dc2626' }}>*</span></label>
                  <input value={addr.address} onChange={setAddr('address')} className="form-input" style={{ width: '100%', boxSizing: 'border-box' }} placeholder="House no, street, locality" />
                </div>
                <div>
                  <label style={{ fontSize: 11, fontWeight: 600, color: 'var(--text-secondary)', display: 'block', marginBottom: 3 }}>City <span style={{ color: '#dc2626' }}>*</span></label>
                  <input value={addr.city} onChange={setAddr('city')} className="form-input" style={{ width: '100%', boxSizing: 'border-box' }} placeholder="City" />
                </div>
                <div>
                  <label style={{ fontSize: 11, fontWeight: 600, color: 'var(--text-secondary)', display: 'block', marginBottom: 3 }}>State <span style={{ color: '#dc2626' }}>*</span></label>
                  <input value={addr.state} onChange={setAddr('state')} className="form-input" style={{ width: '100%', boxSizing: 'border-box' }} placeholder="State" />
                </div>
                <div>
                  <label style={{ fontSize: 11, fontWeight: 600, color: 'var(--text-secondary)', display: 'block', marginBottom: 3 }}>Pincode <span style={{ color: '#dc2626' }}>*</span></label>
                  <input value={addr.pincode} onChange={setAddr('pincode')} className="form-input" style={{ width: '100%', boxSizing: 'border-box' }} placeholder="6-digit" maxLength={6} />
                </div>
              </div>

              {/* Package */}
              <div style={{ height: 1, background: 'var(--border)' }} />
              <div style={{ fontSize: 11, fontWeight: 700, color: 'var(--text-secondary)', textTransform: 'uppercase', letterSpacing: '0.5px' }}>Package</div>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
                <div>
                  <label style={{ fontSize: 11, fontWeight: 600, color: 'var(--text-secondary)', display: 'block', marginBottom: 3 }}>Weight (kg)</label>
                  <input type="number" min="0.1" step="0.1" value={weight} onChange={e => setWeight(parseFloat(e.target.value) || 0.5)} className="form-input" style={{ width: '100%', boxSizing: 'border-box' }} />
                </div>
                <div>
                  <label style={{ fontSize: 11, fontWeight: 600, color: 'var(--text-secondary)', display: 'block', marginBottom: 3 }}>Pickup Location</label>
                  <input type="text" value={pickupLocation} onChange={e => setPickupLocation(e.target.value)} className="form-input" style={{ width: '100%', boxSizing: 'border-box' }} placeholder="Primary" />
                </div>
              </div>

              <div style={{ padding: '8px 12px', background: '#eff6ff', border: '1px solid #bfdbfe', borderRadius: 8, fontSize: 12, color: '#1d4ed8' }}>
                ℹ️ Best courier auto-assigned · AWB + label generated instantly · Stock deducted on confirm
              </div>
            </div>

            <div style={{ padding: '12px 20px', borderTop: '1px solid var(--border)', display: 'flex', gap: 8, justifyContent: 'flex-end', flexShrink: 0 }}>
              <button className="btn btn-secondary" onClick={onClose}>Cancel</button>
              <button className="btn btn-primary" onClick={handleCreate} style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                🚀 Create Shipment
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}

// ── Track AWB Modal ───────────────────────────────────────────────────────────
function TrackModal({ awb, onClose }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    apiFetch(`/api/shiprocket/track/${awb}`)
      .then(d => { setData(d); setLoading(false); })
      .catch(e => { setError(e.message); setLoading(false); });
  }, [awb]);

  const tracking = data?.tracking_data;
  const shipmentTrack = tracking?.shipment_track?.[0];
  const activities = tracking?.shipment_track_activities || [];

  return (
    <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.45)', zIndex: 200, display: 'flex', alignItems: 'center', justifyContent: 'center' }} onClick={onClose}>
      <div onClick={e => e.stopPropagation()} style={{ width: 500, maxHeight: '80vh', background: '#fff', borderRadius: 'var(--radius-lg)', boxShadow: 'var(--shadow-lg)', overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
        <div style={{ padding: '16px 20px', borderBottom: '1px solid var(--border)', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <div>
            <div style={{ fontWeight: 700, fontSize: 15 }}>Track Shipment</div>
            <div style={{ fontSize: 12, color: 'var(--text-secondary)', fontFamily: 'monospace' }}>{awb}</div>
          </div>
          <button onClick={onClose} className="btn btn-ghost btn-icon">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M18 6L6 18M6 6l12 12"/></svg>
          </button>
        </div>
        <div style={{ flex: 1, overflow: 'auto', padding: 20 }}>
          {loading && <div style={{ textAlign: 'center', padding: 40, color: 'var(--text-secondary)' }}>Loading tracking info…</div>}
          {error && <div style={{ color: '#dc2626', fontSize: 13 }}>{error}</div>}
          {shipmentTrack && (
            <>
              <div style={{ background: '#f0fdf4', border: '1px solid #bbf7d0', borderRadius: 10, padding: '12px 16px', marginBottom: 16 }}>
                <div style={{ fontWeight: 700, fontSize: 14, color: '#166534', marginBottom: 4 }}>{shipmentTrack.current_status}</div>
                <div style={{ fontSize: 12, color: '#64748b' }}>
                  {shipmentTrack.courier} · EDD: {shipmentTrack.etd || '—'}
                </div>
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 0 }}>
                {activities.slice(0, 10).map((a, i) => (
                  <div key={i} style={{ display: 'flex', gap: 12, paddingBottom: 14, position: 'relative' }}>
                    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', flexShrink: 0 }}>
                      <div style={{ width: 10, height: 10, borderRadius: '50%', background: i === 0 ? 'var(--green)' : 'var(--border)', border: '2px solid', borderColor: i === 0 ? 'var(--green)' : '#cbd5e1', marginTop: 3 }} />
                      {i < activities.length - 1 && <div style={{ width: 2, flex: 1, background: 'var(--border)', marginTop: 2 }} />}
                    </div>
                    <div style={{ flex: 1 }}>
                      <div style={{ fontSize: 13, fontWeight: i === 0 ? 600 : 400 }}>{a.activity}</div>
                      <div style={{ fontSize: 11, color: '#94a3b8', marginTop: 1 }}>{a.date} · {a.location}</div>
                    </div>
                  </div>
                ))}
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

// ── Main ShippingPage ─────────────────────────────────────────────────────────
export default function ShippingPage() {
  const [orders, setOrders] = useState(() => getOrders());
  const [shippingOrder, setShippingOrder] = useState(null);
  const [trackingAwb, setTrackingAwb] = useState(null);
  const [tab, setTab] = useState('rtd');
  const [srStatus, setSrStatus] = useState(null);

  // Refresh orders from localStorage every time page mounts (catches orders shipped elsewhere)
  useEffect(() => {
    const fresh = getOrders();
    setOrders(fresh);
    // Auto-switch to In Transit tab if no RTD orders but there are shipped ones
    const hasRtd = fresh.some(o => o.status !== 'shipped' && o.status !== 'delivered' && o.status !== 'cancelled' && (o.status === 'rtd' || o.status === 'new' || o.status === 'confirmed'));
    const hasTransit = fresh.some(o => o.status === 'shipped');
    if (!hasRtd && hasTransit) setTab('transit');
  }, []);

  // Check Shiprocket connection on mount
  useEffect(() => {
    apiFetch('/api/shiprocket/status')
      .then(d => setSrStatus(d))
      .catch(() => setSrStatus({ connected: false, error: 'Backend not reachable' }));
  }, []);

  // Update order in localStorage + local state when shipped, and deduct stock
  const handleShipped = (orderId, result) => {
    // Deduct stock for each item
    const order = orders.find(o => o.id === orderId);
    if (order) {
      const products = getProducts();
      for (const item of (order.items || [])) {
        const nameLower = (item.name || '').toLowerCase().trim();
        const prod = products.find(p =>
          (item.product_id && (p.id === item.product_id || p.sku === item.product_id)) ||
          (item.sku && item.sku !== '—' && p.sku === item.sku) ||
          (nameLower && p.name.toLowerCase().trim() === nameLower) ||
          (nameLower && p.name.toLowerCase().includes(nameLower)) ||
          (nameLower && nameLower.includes(p.name.toLowerCase().trim()))
        );
        if (prod) decrementStock(prod.id, item.qty || 1);
      }
    }
    // Persist to localStorage
    updateOrder(orderId, {
      awb: result.awb,
      courier: result.courier,
      shiprocket_order_id: result.shiprocket_order_id,
      label_url: result.label_url,
      status: 'shipped',
    });
    // Refresh from localStorage
    setOrders(getOrders());
  };

  const currentRtd = orders.filter(o => o.status !== 'shipped' && o.status !== 'delivered' && o.status !== 'cancelled' && (o.status === 'rtd' || o.status === 'new' || o.status === 'confirmed'));

  const inTransit = orders.filter(o => o.status === 'shipped');
  const delivered = orders.filter(o => o.status === 'delivered');

  const tabs = [
    { key: 'rtd', label: 'Ready to Dispatch', count: currentRtd.length },
    { key: 'transit', label: 'In Transit', count: inTransit.length },
    { key: 'delivered', label: 'Delivered', count: delivered.length },
    { key: 'ndr', label: 'NDR', count: 0 },
  ];

  const displayOrders = tab === 'rtd' ? currentRtd
    : tab === 'transit' ? inTransit
    : tab === 'delivered' ? delivered
    : [];

  return (
    <div style={{ padding: 24 }}>
      {/* Page header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 20 }}>
        <div>
          <h1 style={{ fontSize: '20px', fontWeight: 700, letterSpacing: '-0.3px' }}>Shipping</h1>
          <p style={{ fontSize: '13px', color: 'var(--text-secondary)', marginTop: 2 }}>Manage shipments via Shiprocket · Delhivery · BlueDart · Xpressbees</p>
        </div>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          {/* Shiprocket connection badge */}
          {srStatus !== null && (
            <div style={{
              display: 'flex', alignItems: 'center', gap: 6, padding: '5px 12px',
              background: srStatus.connected ? '#f0fdf4' : '#fff7ed',
              border: `1px solid ${srStatus.connected ? '#bbf7d0' : '#fed7aa'}`,
              borderRadius: 20, fontSize: 12, fontWeight: 600,
              color: srStatus.connected ? '#166534' : '#9a3412',
            }}>
              <span style={{ width: 7, height: 7, borderRadius: '50%', background: srStatus.connected ? '#22c55e' : '#f97316', display: 'inline-block' }} />
              {srStatus.connected ? 'Shiprocket Connected' : 'Shiprocket Not Connected'}
            </div>
          )}
          <button className="btn btn-secondary" onClick={() => toast.success(`Printing labels for ${currentRtd.length} RTD orders`)}>
            🖨️ Bulk Print Labels
          </button>
          <button className="btn btn-primary" onClick={() => currentRtd[0] && setShippingOrder(currentRtd[0])}>
            🚀 Ship Next Order
          </button>
        </div>
      </div>

      {/* Shiprocket not connected banner */}
      {srStatus && !srStatus.connected && (
        <div style={{ marginBottom: 16, padding: '12px 16px', background: '#fff7ed', border: '1px solid #fed7aa', borderRadius: 10, fontSize: 13, color: '#9a3412', display: 'flex', alignItems: 'center', gap: 10 }}>
          <span style={{ fontSize: 18 }}>⚠️</span>
          <div>
            <strong>Shiprocket not connected.</strong> Add your credentials to the <code style={{ background: 'rgba(0,0,0,0.06)', padding: '1px 5px', borderRadius: 3 }}>.env</code> file:
            <code style={{ display: 'block', marginTop: 4, background: 'rgba(0,0,0,0.06)', padding: '4px 8px', borderRadius: 4, fontFamily: 'monospace', fontSize: 12 }}>
              SHIPROCKET_EMAIL=your@email.com<br/>SHIPROCKET_PASSWORD=your_api_password
            </code>
          </div>
        </div>
      )}

      {/* Stats row */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 12, marginBottom: 20 }}>
        {[
          { label: 'Ready to Dispatch', value: currentRtd.length, color: 'var(--purple)', bg: 'var(--purple-light)', icon: '📦' },
          { label: 'In Transit', value: inTransit.length, color: 'var(--blue)', bg: 'var(--blue-light)', icon: '🚚' },
          { label: 'Delivered', value: delivered.length, color: 'var(--green)', bg: 'var(--green-light)', icon: '✅' },
          { label: 'NDR Pending', value: 0, color: 'var(--red)', bg: 'var(--red-light)', icon: '⚠️' },
        ].map((s, i) => (
          <div key={i} className="card" style={{ padding: 16 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
              <div style={{ width: 40, height: 40, background: s.bg, borderRadius: 10, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '18px' }}>{s.icon}</div>
              <div>
                <div style={{ fontSize: '22px', fontWeight: 700, color: s.color }}>{s.value}</div>
                <div style={{ fontSize: '11px', color: 'var(--text-secondary)' }}>{s.label}</div>
              </div>
            </div>
          </div>
        ))}
      </div>

      {/* Tabs */}
      <div style={{ display: 'flex', gap: 0, borderBottom: '1px solid var(--border)', marginBottom: 16 }}>
        {tabs.map(t => (
          <button key={t.key} onClick={() => setTab(t.key)} style={{
            padding: '9px 16px', background: 'none', border: 'none', cursor: 'pointer',
            fontSize: '13px', fontWeight: tab === t.key ? 600 : 400,
            color: tab === t.key ? 'var(--blue)' : 'var(--text-secondary)',
            borderBottom: tab === t.key ? '2px solid var(--blue)' : '2px solid transparent',
            fontFamily: 'inherit', display: 'flex', alignItems: 'center', gap: 6,
          }}>
            {t.label}
            {t.count > 0 && <span style={{ background: tab === t.key ? 'var(--blue)' : 'var(--border)', color: tab === t.key ? '#fff' : 'var(--text-secondary)', borderRadius: 10, padding: '1px 6px', fontSize: '10px', fontWeight: 700 }}>{t.count}</span>}
          </button>
        ))}
      </div>

      {/* Orders table */}
      <div className="card" style={{ overflow: 'hidden' }}>
        <table className="table">
          <thead>
            <tr>
              <th><input type="checkbox" style={{ accentColor: 'var(--blue)' }} /></th>
              <th>Order</th>
              <th>Customer & Address</th>
              <th>Items</th>
              <th>Payment</th>
              <th>Weight</th>
              <th>Courier / AWB</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {displayOrders.map(order => (
              <tr key={order.id}>
                <td style={{ padding: '10px 12px', width: 36 }}>
                  <input type="checkbox" style={{ accentColor: 'var(--blue)' }} />
                </td>
                <td style={{ padding: '10px 12px' }}>
                  <div style={{ fontWeight: 600, fontSize: '13px', color: 'var(--blue)', fontFamily: 'monospace' }}>{order.id.replace('ORD-', '')}</div>
                  <div style={{ fontSize: '11px', color: 'var(--text-secondary)' }}>{order.date}</div>
                </td>
                <td style={{ padding: '10px 12px' }}>
                  <div style={{ fontWeight: 500 }}>{order.customer}</div>
                  <div style={{ fontSize: '11px', color: 'var(--text-secondary)' }}>{order.city || '—'}, {order.state || '—'} — {order.pincode || '—'}</div>
                </td>
                <td style={{ padding: '10px 12px' }}>
                  <div style={{ fontSize: '12px' }}>{order.items?.[0]?.name || '—'}</div>
                  {(order.items?.length || 0) > 1 && <div style={{ fontSize: '11px', color: 'var(--text-secondary)' }}>+{order.items.length - 1} more</div>}
                </td>
                <td style={{ padding: '10px 12px' }}>
                  <span className={`badge ${order.payment === 'cod' ? 'badge-cod' : 'badge-prepaid'}`}>{order.payment?.toUpperCase()}</span>
                </td>
                <td style={{ padding: '10px 12px', fontSize: '13px' }}>~0.5 kg</td>
                <td style={{ padding: '10px 12px' }}>
                  {order.courier ? (
                    <div>
                      <div style={{ fontWeight: 500, fontSize: '12px' }}>{order.courier}</div>
                      {order.awb && <div style={{ fontSize: '10px', color: 'var(--text-secondary)', fontFamily: 'monospace' }}>{order.awb}</div>}
                    </div>
                  ) : (
                    <span style={{ fontSize: '12px', color: 'var(--text-disabled)' }}>—</span>
                  )}
                </td>
                <td style={{ padding: '10px 12px' }}>
                  <div style={{ display: 'flex', gap: 6 }}>
                    {order.status !== 'shipped' && order.status !== 'delivered' ? (
                      <button
                        className="btn btn-primary"
                        style={{ fontSize: '11px', padding: '5px 10px', display: 'flex', alignItems: 'center', gap: 4 }}
                        onClick={() => setShippingOrder(order)}
                      >
                        🚀 Ship Now
                      </button>
                    ) : (
                      <>
                        {order.awb && (
                          <button
                            className="btn btn-secondary"
                            style={{ fontSize: '11px', padding: '5px 10px' }}
                            onClick={() => setTrackingAwb(order.awb)}
                          >
                            📍 Track
                          </button>
                        )}
                        <button
                          className="btn btn-secondary"
                          style={{ fontSize: '11px', padding: '5px 10px' }}
                          onClick={() => updateOrder(order.id, { status: 'delivered' }) && setOrders(getOrders())}
                        >
                          ✅ Mark Delivered
                        </button>
                        {order.label_url && (
                          <a href={order.label_url} target="_blank" rel="noreferrer"
                            style={{ fontSize: '11px', padding: '5px 10px', background: 'var(--surface-2)', border: '1px solid var(--border)', borderRadius: 6, color: 'var(--text-primary)', textDecoration: 'none', display: 'flex', alignItems: 'center' }}>
                            🖨️
                          </a>
                        )}
                      </>
                    )}
                  </div>
                </td>
              </tr>
            ))}
            {displayOrders.length === 0 && (
              <tr>
                <td colSpan={8} style={{ padding: '40px', textAlign: 'center', color: 'var(--text-secondary)', fontSize: 14 }}>
                  No orders in this category.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {shippingOrder && (
        <CreateShipmentModal
          order={shippingOrder}
          onClose={() => setShippingOrder(null)}
          onShipped={handleShipped}
        />
      )}
      {trackingAwb && (
        <TrackModal awb={trackingAwb} onClose={() => setTrackingAwb(null)} />
      )}
    </div>
  );
}
