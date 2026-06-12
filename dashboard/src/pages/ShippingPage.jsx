import { useState } from 'react';
import { ORDERS } from '../data/mockData';
import { toast } from '../components/Toast';

const COURIERS = [
  { id: 'delhivery', name: 'Delhivery', logo: '🔵', rating: 4.2, etd: '2-3 days', cod: true, zones: 'Pan India' },
  { id: 'bluedart', name: 'BlueDart DHL', logo: '🔴', rating: 4.5, etd: '1-2 days', cod: true, zones: 'Pan India' },
  { id: 'xpressbees', name: 'Xpressbees', logo: '🟡', rating: 4.0, etd: '3-4 days', cod: true, zones: 'Pan India' },
  { id: 'ecom', name: 'Ecom Express', logo: '🟢', rating: 3.9, etd: '3-5 days', cod: true, zones: 'Pan India' },
  { id: 'shadowfax', name: 'Shadowfax', logo: '⚫', rating: 3.8, etd: '2-4 days', cod: true, zones: 'Tier 1-2' },
  { id: 'dtdc', name: 'DTDC', logo: '🟠', rating: 3.7, etd: '3-5 days', cod: true, zones: 'Pan India' },
];

const rtdOrders = ORDERS.filter(o => o.status === 'rtd' || o.status === 'new');

function CreateShipmentModal({ order, onClose }) {
  const [selectedCourier, setSelectedCourier] = useState('delhivery');
  const [step, setStep] = useState(1); // 1=courier select, 2=confirm, 3=done
  const [awb, setAwb] = useState('');

  const handleCreate = () => {
    setAwb('DEL' + Math.random().toString().slice(2,12));
    setStep(3);
  };

  return (
    <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.4)', zIndex: 200, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
      <div onClick={e => e.stopPropagation()} className="animate-in"
        style={{ width: 560, background: '#fff', borderRadius: 'var(--radius-lg)', boxShadow: 'var(--shadow-lg)', overflow: 'hidden' }}>
        {/* Header */}
        <div style={{ padding: '16px 20px', borderBottom: '1px solid var(--border)', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <div>
            <div style={{ fontWeight: 700, fontSize: '15px' }}>Create Shipment</div>
            <div style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>{order.id} · {order.customer}</div>
          </div>
          <button onClick={onClose} className="btn btn-ghost btn-icon">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M18 6L6 18M6 6l12 12"/></svg>
          </button>
        </div>

        {step === 3 ? (
          <div style={{ padding: 32, textAlign: 'center' }}>
            <div style={{ width: 64, height: 64, background: 'var(--green-light)', borderRadius: '50%', display: 'flex', alignItems: 'center', justifyContent: 'center', margin: '0 auto 16px', fontSize: '28px' }}>✓</div>
            <div style={{ fontWeight: 700, fontSize: '16px', marginBottom: 8 }}>Shipment Created!</div>
            <div style={{ color: 'var(--text-secondary)', fontSize: '13px', marginBottom: 16 }}>AWB: <span style={{ fontFamily: 'monospace', fontWeight: 600, color: 'var(--text-primary)' }}>{awb}</span></div>
            <div style={{ display: 'flex', gap: 8, justifyContent: 'center' }}>
              <button className="btn btn-secondary">Print Label</button>
              <button className="btn btn-primary" onClick={onClose}>Done</button>
            </div>
          </div>
        ) : (
          <>
            <div style={{ padding: 20 }}>
              {/* Order summary */}
              <div style={{ background: 'var(--surface-2)', borderRadius: 'var(--radius)', padding: 12, marginBottom: 16, border: '1px solid var(--border)' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '13px' }}>
                  <span style={{ color: 'var(--text-secondary)' }}>Delivering to</span>
                  <span style={{ fontWeight: 500 }}>{order.city}, {order.state} {order.pincode}</span>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '13px', marginTop: 6 }}>
                  <span style={{ color: 'var(--text-secondary)' }}>Weight</span>
                  <span style={{ fontWeight: 500 }}>~0.5 kg</span>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '13px', marginTop: 6 }}>
                  <span style={{ color: 'var(--text-secondary)' }}>Payment</span>
                  <span className={`badge ${order.payment === 'cod' ? 'badge-cod' : 'badge-prepaid'}`}>{order.payment?.toUpperCase()}</span>
                </div>
              </div>

              {/* Courier options */}
              <div style={{ fontSize: '12px', fontWeight: 600, color: 'var(--text-secondary)', textTransform: 'uppercase', letterSpacing: '0.5px', marginBottom: 10 }}>Select Courier</div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                {COURIERS.map(c => (
                  <label key={c.id} style={{ display: 'flex', alignItems: 'center', gap: 12, padding: 12, border: `1.5px solid ${selectedCourier === c.id ? 'var(--blue)' : 'var(--border)'}`, borderRadius: 'var(--radius)', cursor: 'pointer', background: selectedCourier === c.id ? 'var(--blue-light)' : '#fff', transition: 'all 0.12s' }}>
                    <input type="radio" name="courier" value={c.id} checked={selectedCourier === c.id} onChange={() => setSelectedCourier(c.id)} style={{ accentColor: 'var(--blue)' }} />
                    <span style={{ fontSize: '18px' }}>{c.logo}</span>
                    <div style={{ flex: 1 }}>
                      <div style={{ fontWeight: 600, fontSize: '13px' }}>{c.name}</div>
                      <div style={{ fontSize: '11px', color: 'var(--text-secondary)' }}>ETA: {c.etd} · {c.zones}</div>
                    </div>
                    <div style={{ textAlign: 'right' }}>
                      <div style={{ fontWeight: 700, fontSize: '13px' }}>₹{(Math.random()*50+40).toFixed(0)}</div>
                      <div style={{ fontSize: '11px', color: '#16A249' }}>⭐ {c.rating}</div>
                    </div>
                  </label>
                ))}
              </div>
            </div>

            <div style={{ padding: '12px 20px', borderTop: '1px solid var(--border)', display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
              <button className="btn btn-secondary" onClick={onClose}>Cancel</button>
              <button className="btn btn-primary" onClick={handleCreate}>Create Shipment & Print Label</button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}

export default function ShippingPage() {
  const [shippingOrder, setShippingOrder] = useState(null);
  const [tab, setTab] = useState('rtd');

  const tabs = [
    { key: 'rtd', label: 'Ready to Dispatch', count: rtdOrders.length },
    { key: 'transit', label: 'In Transit', count: ORDERS.filter(o => o.status === 'shipped').length },
    { key: 'delivered', label: 'Delivered', count: ORDERS.filter(o => o.status === 'delivered').length },
    { key: 'ndr', label: 'NDR', count: 2 },
  ];

  const displayOrders = tab === 'rtd' ? rtdOrders
    : tab === 'transit' ? ORDERS.filter(o => o.status === 'shipped')
    : tab === 'delivered' ? ORDERS.filter(o => o.status === 'delivered')
    : [];

  return (
    <div style={{ padding: 24 }}>
      {/* Page header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 20 }}>
        <div>
          <h1 style={{ fontSize: '20px', fontWeight: 700, letterSpacing: '-0.3px' }}>Shipping</h1>
          <p style={{ fontSize: '13px', color: 'var(--text-secondary)', marginTop: 2 }}>Manage shipments across all couriers and channels</p>
        </div>
        <div style={{ display: 'flex', gap: 8 }}>
          <button className="btn btn-secondary" onClick={() => toast.success(`Printing labels for ${rtdOrders.length} RTD orders`)}>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M17 17H17.01 M17 3H5a2 2 0 00-2 2v4a2 2 0 002 2h12a2 2 0 002-2V5a2 2 0 00-2-2z M3 11v6a2 2 0 002 2h12a2 2 0 002-2v-6"/></svg>
            Bulk Print Labels
          </button>
          <button className="btn btn-primary" onClick={() => setShippingOrder(rtdOrders[0])}>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><rect x="1" y="3" width="15" height="13"/><path d="M16 8h4l3 3v5h-7V8z M5.5 21a2.5 2.5 0 100-5 2.5 2.5 0 000 5z M18.5 21a2.5 2.5 0 100-5 2.5 2.5 0 000 5z"/></svg>
            Auto-Ship All RTD
          </button>
        </div>
      </div>

      {/* Stats row */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 12, marginBottom: 20 }}>
        {[
          { label: 'Ready to Dispatch', value: rtdOrders.length, color: 'var(--purple)', bg: 'var(--purple-light)', icon: '📦' },
          { label: 'In Transit', value: ORDERS.filter(o => o.status === 'shipped').length, color: 'var(--blue)', bg: 'var(--blue-light)', icon: '🚚' },
          { label: 'Delivered Today', value: 3, color: 'var(--green)', bg: 'var(--green-light)', icon: '✅' },
          { label: 'NDR Pending', value: 2, color: 'var(--red)', bg: 'var(--red-light)', icon: '⚠️' },
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
              <th>Courier</th>
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
                  <div style={{ fontSize: '11px', color: 'var(--text-secondary)' }}>{order.city}, {order.state} — {order.pincode}</div>
                </td>
                <td style={{ padding: '10px 12px' }}>
                  <div style={{ fontSize: '12px' }}>{order.items[0]?.name}</div>
                  {order.items.length > 1 && <div style={{ fontSize: '11px', color: 'var(--text-secondary)' }}>+{order.items.length-1} more</div>}
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
                    <span style={{ fontSize: '12px', color: 'var(--text-disabled)' }}>Not assigned</span>
                  )}
                </td>
                <td style={{ padding: '10px 12px' }}>
                  <div style={{ display: 'flex', gap: 6 }}>
                    {!order.courier ? (
                      <button className="btn btn-primary" style={{ fontSize: '11px', padding: '5px 10px' }} onClick={() => setShippingOrder(order)}>
                        Ship Now
                      </button>
                    ) : (
                      <button className="btn btn-secondary" style={{ fontSize: '11px', padding: '5px 10px' }}
                        onClick={() => toast.info(`Tracking ${order.awb} on ${order.courier}`)}>
                        Track
                      </button>
                    )}
                    <button className="btn btn-ghost btn-icon" style={{ padding: '5px' }}
                      onClick={() => toast.success(`Label queued for order ${order.id.replace('ORD-','')}`)}>
                      <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M17 17H17.01 M17 3H5a2 2 0 00-2 2v4a2 2 0 002 2h12a2 2 0 002-2V5a2 2 0 00-2-2z M3 11v6a2 2 0 002 2h12a2 2 0 002-2v-6"/></svg>
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {shippingOrder && <CreateShipmentModal order={shippingOrder} onClose={() => setShippingOrder(null)} />}
    </div>
  );
}
