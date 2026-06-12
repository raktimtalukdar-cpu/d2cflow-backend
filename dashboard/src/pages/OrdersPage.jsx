import { useState, useCallback } from 'react';
import { getOrders, addOrder } from '../data/orders';
import { toast } from '../components/Toast';
import { getProducts, decrementStock } from '../data/products';

function buildStatusTree(orders) {
  return [
    { key: 'all', label: 'All orders', count: orders.length },
    { key: 'new', label: 'New orders', count: orders.filter(o => o.status === 'new').length, color: '#16A249' },
    { key: 'rtd', label: 'Ready to dispatch', count: orders.filter(o => o.status === 'rtd').length, color: '#7C3AED' },
    { key: 'shipped', label: 'In transit', count: orders.filter(o => o.status === 'shipped').length, color: '#3395FF' },
    { key: 'delivered', label: 'Delivered', count: orders.filter(o => o.status === 'delivered').length, color: '#065F46' },
    { key: 'rto', label: 'RTO', count: orders.filter(o => o.status === 'rto').length, color: '#DC2626' },
    { key: 'cancelled', label: 'Cancelled', count: orders.filter(o => o.status === 'cancelled').length, color: '#687385' },
  ];
}

const CHANNEL_SECTIONS = [
  { key: 'amazon', label: 'Amazon IN' },
  { key: 'flipkart', label: 'Flipkart' },
  { key: 'meesho', label: 'Meesho' },
  { key: 'myntra', label: 'Myntra' },
  { key: 'shopify', label: 'Shopify' },
];

const STATUS_BADGE = {
  new: { label: 'New', cls: 'badge-new' },
  packed: { label: 'Packed', cls: 'badge-packed' },
  rtd: { label: 'RTD', cls: 'badge-rtd' },
  shipped: { label: 'Shipped', cls: 'badge-shipped' },
  delivered: { label: 'Delivered', cls: 'badge-delivered' },
  rto: { label: 'RTO', cls: 'badge-rto' },
  cancelled: { label: 'Cancelled', cls: 'badge-cancelled' },
};

function ProductThumb({ name }) {
  const initials = name.split(' ').slice(0, 2).map(w => w[0]).join('').toUpperCase();
  const colors = ['#EBF4FF', '#E6F4EC', '#FEF3C7', '#FCE4EC', '#F3E5F5', '#FFF3E0'];
  const fg = ['#1A6FCC', '#16A249', '#92400E', '#880E4F', '#4A148C', '#E65100'];
  const idx = name.charCodeAt(0) % 6;
  return (
    <div style={{ width: 36, height: 36, borderRadius: 6, background: colors[idx], display: 'flex', alignItems: 'center', justifyContent: 'center', color: fg[idx], fontSize: '11px', fontWeight: 700, flexShrink: 0, border: '1px solid rgba(0,0,0,0.06)' }}>
      {initials}
    </div>
  );
}

function ChannelBadge({ ch }) {
  const map = { amazon: ['AMZ', 'ch-amazon'], flipkart: ['FK', 'ch-flipkart'], meesho: ['MS', 'ch-meesho'], myntra: ['MN', 'ch-myntra'], shopify: ['SHP', 'ch-shopify'] };
  const [label, cls] = map[ch] || ['?', ''];
  return <span className={`channel-badge ${cls}`}>{label}</span>;
}

function AddOrderModal({ onClose, onNavigate }) {
  const catalog = getProducts();
  const [form, setForm] = useState({ customer: '', phone: '', city: '', pincode: '', channel: 'shopify', payment: 'prepaid', qty: 1 });
  const [selectedProduct, setSelectedProduct] = useState(null);
  const [productSearch, setProductSearch] = useState('');
  const [showDropdown, setShowDropdown] = useState(false);

  const set = k => e => setForm(f => ({ ...f, [k]: e.target.value }));

  const filteredProducts = catalog.filter(p =>
    !productSearch || p.name.toLowerCase().includes(productSearch.toLowerCase()) || p.sku.toLowerCase().includes(productSearch.toLowerCase())
  );

  const handleProductSelect = p => {
    setSelectedProduct(p);
    setProductSearch(p.name);
    setShowDropdown(false);
  };

  const handleSave = () => {
    if (!form.customer.trim()) { toast.error('Customer name is required'); return; }
    if (!selectedProduct) { toast.error('Select a product from your catalog'); return; }
    const qty = Number(form.qty);
    if (!qty || qty < 1) { toast.error('Quantity must be at least 1'); return; }
    if (selectedProduct.stock < qty) {
      toast.error(`Only ${selectedProduct.stock} units in stock for "${selectedProduct.name}"`); return;
    }
    decrementStock(selectedProduct.id, qty);
    addOrder({
      customer: form.customer,
      phone: form.phone,
      city: form.city || '—',
      state: '',
      pincode: form.pincode || '—',
      channel: form.channel,
      payment: form.payment,
      items: [{ name: selectedProduct.name, sku: selectedProduct.sku, ean: selectedProduct.ean || '—', qty, price: Number(selectedProduct.price) }],
      total: Number(selectedProduct.price) * qty,
    });
    toast.success(`Order created for ${form.customer} — ${qty}× ${selectedProduct.name}`);
    onClose(true);
  };

  if (catalog.length === 0) {
    return (
      <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.4)', zIndex: 500, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <div className="animate-in" style={{ width: 420, background: '#fff', borderRadius: 'var(--radius-lg)', padding: 32, boxShadow: 'var(--shadow-lg)', textAlign: 'center' }}>
          <div style={{ fontSize: 40, marginBottom: 12 }}>📦</div>
          <div style={{ fontWeight: 700, fontSize: 16, marginBottom: 8 }}>No products in catalog</div>
          <div style={{ fontSize: 13, color: 'var(--text-secondary)', marginBottom: 20 }}>
            You need to add products before creating orders. Go to <strong>Products</strong> and add your catalog first.
          </div>
          <div style={{ display: 'flex', gap: 8, justifyContent: 'center' }}>
            <button className="btn btn-secondary" onClick={onClose}>Cancel</button>
            <button className="btn btn-primary" onClick={() => { onClose(); if (onNavigate) onNavigate('products'); }}>Go to Products →</button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.4)', zIndex: 500, display: 'flex', alignItems: 'center', justifyContent: 'center' }}
      onClick={() => { setShowDropdown(false); }}>
      <div onClick={e => e.stopPropagation()} className="animate-in"
        style={{ width: 520, background: '#fff', borderRadius: 'var(--radius-lg)', boxShadow: 'var(--shadow-lg)', overflow: 'visible' }}>
        <div style={{ padding: '16px 20px', borderBottom: '1px solid var(--border)', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <div style={{ fontWeight: 700, fontSize: 15 }}>Add Manual Order</div>
          <button onClick={onClose} className="btn btn-ghost btn-icon">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M18 6L6 18M6 6l12 12"/></svg>
          </button>
        </div>
        <div style={{ padding: 20, display: 'flex', flexDirection: 'column', gap: 12 }}>
          {/* Customer */}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
            <div>
              <label style={{ fontSize: 11, fontWeight: 600, color: 'var(--text-secondary)', display: 'block', marginBottom: 4 }}>Customer name *</label>
              <input className="form-input" value={form.customer} onChange={set('customer')} placeholder="Priya Sharma" />
            </div>
            <div>
              <label style={{ fontSize: 11, fontWeight: 600, color: 'var(--text-secondary)', display: 'block', marginBottom: 4 }}>Phone</label>
              <input className="form-input" value={form.phone} onChange={set('phone')} placeholder="+91 98765 43210" />
            </div>
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
            <div>
              <label style={{ fontSize: 11, fontWeight: 600, color: 'var(--text-secondary)', display: 'block', marginBottom: 4 }}>City</label>
              <input className="form-input" value={form.city} onChange={set('city')} placeholder="Mumbai" />
            </div>
            <div>
              <label style={{ fontSize: 11, fontWeight: 600, color: 'var(--text-secondary)', display: 'block', marginBottom: 4 }}>Pincode</label>
              <input className="form-input" value={form.pincode} onChange={set('pincode')} placeholder="400001" />
            </div>
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
            <div>
              <label style={{ fontSize: 11, fontWeight: 600, color: 'var(--text-secondary)', display: 'block', marginBottom: 4 }}>Channel</label>
              <select className="form-input form-select" value={form.channel} onChange={set('channel')}>
                <option value="shopify">Shopify</option><option value="amazon">Amazon</option>
                <option value="flipkart">Flipkart</option><option value="meesho">Meesho</option><option value="myntra">Myntra</option>
              </select>
            </div>
            <div>
              <label style={{ fontSize: 11, fontWeight: 600, color: 'var(--text-secondary)', display: 'block', marginBottom: 4 }}>Payment</label>
              <select className="form-input form-select" value={form.payment} onChange={set('payment')}>
                <option value="prepaid">Prepaid</option><option value="cod">COD</option>
              </select>
            </div>
          </div>

          {/* Product picker from catalog */}
          <div style={{ position: 'relative' }}>
            <label style={{ fontSize: 11, fontWeight: 600, color: 'var(--text-secondary)', display: 'block', marginBottom: 4 }}>
              Product * <span style={{ fontWeight: 400, color: 'var(--text-disabled)' }}>(from your catalog)</span>
            </label>
            <input className="form-input" value={productSearch}
              onChange={e => { setProductSearch(e.target.value); setSelectedProduct(null); setShowDropdown(true); }}
              onFocus={() => setShowDropdown(true)}
              placeholder="Search product name or SKU…" />
            {showDropdown && filteredProducts.length > 0 && (
              <div style={{ position: 'absolute', top: '100%', left: 0, right: 0, background: '#fff', border: '1px solid var(--border)', borderRadius: 'var(--radius)', boxShadow: 'var(--shadow-md)', zIndex: 600, maxHeight: 200, overflow: 'auto', marginTop: 2 }}>
                {filteredProducts.map(p => (
                  <div key={p.id} onClick={() => handleProductSelect(p)}
                    style={{ padding: '8px 12px', cursor: 'pointer', borderBottom: '1px solid var(--border)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}
                    onMouseEnter={e => e.currentTarget.style.background = 'var(--surface-2)'}
                    onMouseLeave={e => e.currentTarget.style.background = ''}>
                    <div>
                      <div style={{ fontSize: 13, fontWeight: 500 }}>{p.name}</div>
                      <div style={{ fontSize: 11, color: 'var(--text-secondary)' }}>SKU: {p.sku} · ₹{Number(p.price).toLocaleString('en-IN')}</div>
                    </div>
                    <div style={{ fontSize: 11, fontWeight: 600, color: p.stock === 0 ? 'var(--red)' : p.stock <= 5 ? '#D97706' : 'var(--green)', flexShrink: 0, marginLeft: 12 }}>
                      {p.stock === 0 ? 'Out of stock' : `${p.stock} left`}
                    </div>
                  </div>
                ))}
              </div>
            )}
            {selectedProduct && (
              <div style={{ marginTop: 6, padding: '8px 10px', background: 'var(--surface-2)', borderRadius: 'var(--radius)', border: '1px solid var(--border)', fontSize: 12 }}>
                ₹{Number(selectedProduct.price).toLocaleString('en-IN')} · SKU: {selectedProduct.sku} ·
                <span style={{ color: selectedProduct.stock <= 5 ? '#D97706' : 'var(--green)', fontWeight: 600 }}> {selectedProduct.stock} in stock</span>
              </div>
            )}
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '120px 1fr', gap: 12 }}>
            <div>
              <label style={{ fontSize: 11, fontWeight: 600, color: 'var(--text-secondary)', display: 'block', marginBottom: 4 }}>Qty *</label>
              <input className="form-input" type="number" min={1}
                max={selectedProduct?.stock || 999}
                value={form.qty} onChange={set('qty')} />
            </div>
            <div>
              <label style={{ fontSize: 11, fontWeight: 600, color: 'var(--text-secondary)', display: 'block', marginBottom: 4 }}>Unit Price (₹)</label>
              <input className="form-input" type="number" value={selectedProduct ? selectedProduct.price : ''} readOnly
                style={{ background: 'var(--surface-2)', color: 'var(--text-secondary)' }} placeholder="Auto-filled from catalog" />
            </div>
          </div>
        </div>
        <div style={{ padding: '12px 20px', borderTop: '1px solid var(--border)', display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
          <button className="btn btn-secondary" onClick={onClose}>Cancel</button>
          <button className="btn btn-primary" onClick={handleSave}>Create Order</button>
        </div>
      </div>
    </div>
  );
}

function OrderRow({ order, selected, onSelect, onClick }) {
  const sb = STATUS_BADGE[order.status] || { label: order.status, cls: '' };
  return (
    <tr onClick={onClick} style={{ cursor: 'pointer' }}>
      <td style={{ padding: '8px 12px', width: 36 }}>
        <input type="checkbox" checked={selected} onChange={onSelect} onClick={e => e.stopPropagation()} style={{ cursor: 'pointer', accentColor: 'var(--blue)' }} />
      </td>
      <td style={{ padding: '8px 4px', width: 20 }}>
        <button className="btn btn-ghost btn-icon" onClick={e => { e.stopPropagation(); toast.info(`Order ${order.id} starred`); }} style={{ padding: 4 }}>
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="#CBD5E0" strokeWidth="2"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/></svg>
        </button>
      </td>
      <td style={{ padding: '8px 12px', minWidth: 100 }}>
        <div style={{ fontWeight: 600, fontSize: '13px', color: 'var(--blue)', fontFamily: 'monospace' }}>{order.id.replace('ORD-', '')}</div>
        <div style={{ fontSize: '11px', color: 'var(--text-secondary)', marginTop: 2 }}>{order.date}</div>
      </td>
      <td style={{ padding: '8px 12px', minWidth: 140 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <ChannelBadge ch={order.channel} />
          <div>
            <div style={{ fontWeight: 500, fontSize: '13px' }}>{order.customer}</div>
            <div style={{ fontSize: '11px', color: 'var(--text-secondary)' }}>{order.city}, {order.pincode}</div>
          </div>
        </div>
      </td>
      <td style={{ padding: '8px 12px', maxWidth: 280 }}>
        {order.items.slice(0, 2).map((item, i) => (
          <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: i < order.items.length - 1 ? 6 : 0 }}>
            <ProductThumb name={item.name} />
            <div style={{ overflow: 'hidden' }}>
              <div style={{ fontSize: '12px', fontWeight: 500, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', maxWidth: 200 }}>{item.name}</div>
              <div style={{ fontSize: '10px', color: 'var(--text-secondary)', fontFamily: 'monospace' }}>SKU: {item.sku} · EAN: {item.ean}</div>
              <div style={{ fontSize: '11px', color: 'var(--text-secondary)' }}>{item.qty}× ₹{item.price.toLocaleString('en-IN')}</div>
            </div>
          </div>
        ))}
        {order.items.length > 2 && <div style={{ fontSize: '11px', color: 'var(--text-secondary)', marginTop: 4 }}>+{order.items.length - 2} more item(s)</div>}
      </td>
      <td style={{ padding: '8px 12px', width: 80 }}>
        <span className={`badge ${order.payment === 'cod' ? 'badge-cod' : 'badge-prepaid'}`}>{order.payment?.toUpperCase()}</span>
      </td>
      <td style={{ padding: '8px 12px', width: 100 }}>
        <div style={{ fontWeight: 700, fontSize: '14px' }}>₹{order.total.toLocaleString('en-IN')}</div>
        <span className={`badge ${sb.cls}`} style={{ marginTop: 3 }}>{sb.label}</span>
      </td>
      <td style={{ padding: '8px 12px', width: 120 }}>
        {order.courier ? (
          <div>
            <div style={{ fontSize: '12px', fontWeight: 500 }}>{order.courier}</div>
            {order.awb && <div style={{ fontSize: '10px', color: 'var(--text-secondary)', fontFamily: 'monospace' }}>{order.awb}</div>}
          </div>
        ) : <span style={{ fontSize: '11px', color: 'var(--text-disabled)' }}>—</span>}
      </td>
    </tr>
  );
}

function OrderDetail({ order, onClose }) {
  return (
    <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.35)', zIndex: 400, display: 'flex', alignItems: 'flex-start', justifyContent: 'flex-end' }}
      onClick={onClose}>
      <div onClick={e => e.stopPropagation()} className="animate-in"
        style={{ width: 520, height: '100vh', background: '#fff', boxShadow: 'var(--shadow-lg)', overflow: 'auto', display: 'flex', flexDirection: 'column' }}>
        <div style={{ padding: '16px 20px', borderBottom: '1px solid var(--border)', display: 'flex', alignItems: 'center', gap: 12 }}>
          <button onClick={onClose} className="btn btn-ghost btn-icon">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M18 6L6 18M6 6l12 12"/></svg>
          </button>
          <div>
            <div style={{ fontWeight: 700, fontSize: '15px' }}>Order {order.id}</div>
            <div style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>{order.date} · <ChannelBadge ch={order.channel} /></div>
          </div>
          <span className={`badge ${STATUS_BADGE[order.status]?.cls}`} style={{ marginLeft: 'auto' }}>{STATUS_BADGE[order.status]?.label}</span>
        </div>

        <div style={{ padding: '16px 20px', borderBottom: '1px solid var(--border)' }}>
          <div style={{ fontSize: '11px', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.5px', color: 'var(--text-secondary)', marginBottom: 10 }}>Customer</div>
          <div style={{ fontWeight: 600, fontSize: '14px' }}>{order.customer}</div>
          <div style={{ fontSize: '13px', color: 'var(--text-secondary)', marginTop: 2 }}>📞 {order.phone}</div>
          <div style={{ fontSize: '13px', color: 'var(--text-secondary)', marginTop: 2 }}>📍 {order.city}, {order.state} — {order.pincode}</div>
        </div>

        <div style={{ padding: '16px 20px', borderBottom: '1px solid var(--border)' }}>
          <div style={{ fontSize: '11px', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.5px', color: 'var(--text-secondary)', marginBottom: 10 }}>Items</div>
          {order.items.map((item, i) => (
            <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 12, padding: 10, background: 'var(--surface-2)', borderRadius: 'var(--radius)', border: '1px solid var(--border)' }}>
              <ProductThumb name={item.name} />
              <div style={{ flex: 1 }}>
                <div style={{ fontWeight: 500, fontSize: '13px' }}>{item.name}</div>
                <div style={{ fontSize: '11px', color: 'var(--text-secondary)', fontFamily: 'monospace', marginTop: 2 }}>SKU: {item.sku}</div>
              </div>
              <div style={{ textAlign: 'right' }}>
                <div style={{ fontWeight: 700 }}>₹{(item.price * item.qty).toLocaleString('en-IN')}</div>
                <div style={{ fontSize: '11px', color: 'var(--text-secondary)' }}>{item.qty} × ₹{item.price}</div>
              </div>
            </div>
          ))}
          <div style={{ display: 'flex', justifyContent: 'space-between', padding: '10px 0 0', borderTop: '1px solid var(--border)', fontWeight: 700, fontSize: '14px' }}>
            <span>Total</span>
            <span style={{ color: 'var(--blue)' }}>₹{order.total.toLocaleString('en-IN')}</span>
          </div>
        </div>

        <div style={{ padding: '16px 20px', borderBottom: '1px solid var(--border)' }}>
          <div style={{ fontSize: '11px', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.5px', color: 'var(--text-secondary)', marginBottom: 10 }}>Shipping</div>
          {order.courier ? (
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <div>
                <div style={{ fontWeight: 500 }}>{order.courier}</div>
                {order.awb && <div style={{ fontSize: '12px', color: 'var(--text-secondary)', fontFamily: 'monospace' }}>AWB: {order.awb}</div>}
              </div>
              <button className="btn btn-secondary" style={{ fontSize: '12px' }}
                onClick={() => toast.info(`Tracking ${order.awb} on ${order.courier}`)}>
                Track
              </button>
            </div>
          ) : (
            <button className="btn btn-primary" style={{ width: '100%', justifyContent: 'center' }}
              onClick={() => toast.info('Go to Shipping page to create shipment')}>
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><rect x="1" y="3" width="15" height="13"/><path d="M16 8h4l3 3v5h-7V8z M5.5 21a2.5 2.5 0 100-5 2.5 2.5 0 000 5z M18.5 21a2.5 2.5 0 100-5 2.5 2.5 0 000 5z"/></svg>
              Create Shipment
            </button>
          )}
        </div>

        <div style={{ padding: 16, display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          <button className="btn btn-secondary" style={{ fontSize: '12px' }}
            onClick={() => toast.success('Label sent to printer')}>
            🖨️ Print Label
          </button>
          <button className="btn btn-secondary" style={{ fontSize: '12px' }}
            onClick={() => toast.success(`WhatsApp sent to ${order.phone}`)}>
            💬 Send WA
          </button>
          <button className="btn btn-secondary" style={{ fontSize: '12px' }}
            onClick={() => toast.success('Invoice generated')}>
            🧾 Invoice
          </button>
          <button className="btn btn-danger" style={{ fontSize: '12px' }}
            onClick={() => { toast.warn(`Order ${order.id} cancellation requested`); onClose(); }}>
            Cancel
          </button>
        </div>
      </div>
    </div>
  );
}

export default function OrdersPage({ filterChannel }) {
  const [activeStatus, setActiveStatus] = useState('all');
  const [activeChannel, setActiveChannel] = useState(filterChannel || null);
  const [selected, setSelected] = useState(new Set());
  const [selectedOrder, setSelectedOrder] = useState(null);
  const [page, setPage] = useState(1);
  const [showAddOrder, setShowAddOrder] = useState(false);
  const [showFilter, setShowFilter] = useState(false);
  const [orders, setOrders] = useState(() => getOrders());
  const PER_PAGE = 20;

  const refreshOrders = useCallback(() => setOrders(getOrders()), []);

  const STATUS_TREE = buildStatusTree(orders);

  const filtered = orders.filter(o => {
    const chMatch = activeChannel ? o.channel === activeChannel : true;
    const stMatch = activeStatus === 'all' ? true : o.status === activeStatus;
    return chMatch && stMatch;
  });

  const paginated = filtered.slice((page - 1) * PER_PAGE, page * PER_PAGE);
  const totalPages = Math.ceil(filtered.length / PER_PAGE);

  const toggleSelect = (id) => {
    const s = new Set(selected);
    s.has(id) ? s.delete(id) : s.add(id);
    setSelected(s);
  };

  const handleBulkAction = (action) => {
    if (selected.size === 0) { toast.warn('Select orders first'); return; }
    if (action === 'print') toast.success(`Printing labels for ${selected.size} orders`);
    if (action === 'email') toast.success(`Confirmation emails sent to ${selected.size} customers`);
    if (action === 'delete') { toast.warn(`${selected.size} orders marked for cancellation`); setSelected(new Set()); }
    if (action === 'ship') toast.success(`Auto-shipping ${selected.size} orders via Shiprocket`);
  };

  return (
    <div style={{ display: 'flex', height: '100%', overflow: 'hidden' }}>
      {/* Left status panel */}
      <div style={{ width: 200, background: '#fff', borderRight: '1px solid var(--border)', flexShrink: 0, overflowY: 'auto', padding: '12px 0' }}>
        <div style={{ padding: '0 12px 8px', fontSize: '10px', fontWeight: 700, color: 'var(--text-secondary)', textTransform: 'uppercase', letterSpacing: '0.6px' }}>Status</div>
        {STATUS_TREE.map(s => (
          <button key={s.key} onClick={() => { setActiveStatus(s.key); setActiveChannel(null); setPage(1); }}
            style={{
              display: 'flex', alignItems: 'center', width: '100%', padding: '7px 12px',
              background: activeStatus === s.key && !activeChannel ? 'var(--blue-light)' : 'transparent',
              color: activeStatus === s.key && !activeChannel ? 'var(--blue)' : 'var(--text-primary)',
              boxShadow: activeStatus === s.key && !activeChannel ? 'inset 2px 0 0 var(--blue)' : 'none',
              cursor: 'pointer', fontSize: '13px', fontFamily: 'inherit', gap: 8,
              fontWeight: activeStatus === s.key && !activeChannel ? 500 : 400,
            }}>
            {s.color && <span style={{ width: 6, height: 6, borderRadius: '50%', background: s.color, flexShrink: 0 }} />}
            <span style={{ flex: 1, textAlign: 'left' }}>{s.label}</span>
            <span style={{ fontSize: '11px', color: activeStatus === s.key && !activeChannel ? 'var(--blue)' : 'var(--text-secondary)', fontWeight: 600 }}>{s.count}</span>
          </button>
        ))}

        {!filterChannel && (
          <>
            <div style={{ padding: '12px 12px 6px', fontSize: '10px', fontWeight: 700, color: 'var(--text-secondary)', textTransform: 'uppercase', letterSpacing: '0.6px', marginTop: 4, borderTop: '1px solid var(--border)' }}>By Channel</div>
            {CHANNEL_SECTIONS.map(ch => {
              const isActive = activeChannel === ch.key;
              return (
                <button key={ch.key} onClick={() => { setActiveChannel(isActive ? null : ch.key); setActiveStatus('all'); setPage(1); }}
                  style={{
                    display: 'flex', alignItems: 'center', width: '100%', padding: '6px 12px',
                    background: isActive ? 'var(--blue-light)' : 'transparent',
                    boxShadow: isActive ? 'inset 2px 0 0 var(--blue)' : 'none',
                    cursor: 'pointer', fontSize: '12px', fontFamily: 'inherit', gap: 8,
                    color: isActive ? 'var(--blue)' : 'var(--text-secondary)',
                    fontWeight: isActive ? 500 : 400,
                  }}>
                  <span style={{ flex: 1, textAlign: 'left', textTransform: 'capitalize' }}>{ch.label}</span>
                  <span style={{ fontSize: '11px', fontWeight: 600 }}>{orders.filter(o => o.channel === ch.key).length}</span>
                </button>
              );
            })}
          </>
        )}
      </div>

      {/* Main content */}
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
        {/* Toolbar */}
        <div style={{ padding: '12px 16px', background: '#fff', borderBottom: '1px solid var(--border)', display: 'flex', alignItems: 'center', gap: 8 }}>
          <button className="btn btn-primary" style={{ gap: 6 }} onClick={() => setShowAddOrder(true)}>
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
            Add order
          </button>

          <div style={{ width: 1, height: 24, background: 'var(--border)', margin: '0 4px' }} />

          {[
            { icon: 'M17 17H17.01 M17 3H5a2 2 0 00-2 2v4a2 2 0 002 2h12a2 2 0 002-2V5a2 2 0 00-2-2z M3 11v6a2 2 0 002 2h12a2 2 0 002-2v-6', tip: 'Print labels', action: () => handleBulkAction('print') },
            { icon: 'M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z M22 6l-10 7L2 6', tip: 'Send email', action: () => handleBulkAction('email') },
            { icon: 'M3 6h18 M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6m3 0V4a2 2 0 012-2h4a2 2 0 012 2v2', tip: 'Delete', action: () => handleBulkAction('delete') },
          ].map((item, i) => (
            <button key={i} onClick={item.action}
              style={{ display: 'flex', alignItems: 'center', gap: 5, border: '1px solid var(--border)', padding: '5px 10px', borderRadius: 'var(--radius-sm)', background: 'transparent', cursor: 'pointer', fontSize: '12px', color: 'var(--text-secondary)', fontFamily: 'inherit' }}
              onMouseEnter={e => { e.currentTarget.style.background = 'var(--surface-2)'; e.currentTarget.style.color = 'var(--text-primary)'; }}
              onMouseLeave={e => { e.currentTarget.style.background = 'transparent'; e.currentTarget.style.color = 'var(--text-secondary)'; }}>
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d={item.icon}/></svg>
              {item.tip}
            </button>
          ))}

          {selected.size > 0 && (
            <div style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '4px 10px', background: 'var(--blue-light)', borderRadius: 'var(--radius)', border: '1px solid rgba(51,149,255,0.2)' }}>
              <span style={{ fontSize: '12px', color: 'var(--blue)', fontWeight: 500 }}>{selected.size} selected</span>
              <button className="btn btn-primary" style={{ padding: '3px 10px', fontSize: '11px' }} onClick={() => handleBulkAction('ship')}>Bulk ship</button>
              <button onClick={() => setSelected(new Set())} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--blue)', fontSize: '12px' }}>✕</button>
            </div>
          )}

          <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 8 }}>
            <button className="btn btn-secondary" style={{ gap: 6, fontSize: '12px' }} onClick={() => { setShowFilter(v => !v); toast.info('Filter panel — connect backend for live filters'); }}>
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><polygon points="22 3 2 3 10 12.46 10 19 14 21 14 12.46 22 3"/></svg>
              {activeChannel ? `Channel: ${activeChannel}` : activeStatus !== 'all' ? `Status: ${activeStatus}` : 'Order filtering'}
            </button>
            <span style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>
              {Math.min((page-1)*PER_PAGE+1, filtered.length)}–{Math.min(page*PER_PAGE, filtered.length)} of {filtered.length} orders
            </span>
            <div style={{ display: 'flex', gap: 2 }}>
              <button className="btn btn-ghost btn-icon" onClick={() => setPage(p => Math.max(1,p-1))} disabled={page===1}
                style={{ border: '1px solid var(--border)', padding: '5px 8px' }}>
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="m15 18-6-6 6-6"/></svg>
              </button>
              <button className="btn btn-ghost btn-icon" onClick={() => setPage(p => Math.min(totalPages,p+1))} disabled={page===totalPages}
                style={{ border: '1px solid var(--border)', padding: '5px 8px' }}>
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="m9 18 6-6-6-6"/></svg>
              </button>
            </div>
          </div>
        </div>

        {/* Table */}
        <div style={{ flex: 1, overflowY: 'auto', overflowX: 'auto' }}>
          {orders.length === 0 ? (
            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', height: '100%', padding: 60, textAlign: 'center', color: 'var(--text-secondary)' }}>
              <div style={{ fontSize: 52, marginBottom: 16 }}>📋</div>
              <div style={{ fontWeight: 700, fontSize: 17, color: 'var(--text-primary)', marginBottom: 8 }}>No orders yet</div>
              <div style={{ fontSize: 13, maxWidth: 340, lineHeight: 1.6, marginBottom: 20 }}>
                Create orders manually using the <strong>Add order</strong> button above, or connect a sales channel in <strong>Integrations</strong> to sync orders automatically.
              </div>
              <button className="btn btn-primary" onClick={() => setShowAddOrder(true)}>
                + Add your first order
              </button>
            </div>
          ) : (
            <table className="table" style={{ minWidth: 900 }}>
              <thead>
                <tr>
                  <th style={{ width: 36 }}><input type="checkbox" style={{ accentColor: 'var(--blue)' }} onChange={e => setSelected(e.target.checked ? new Set(paginated.map(o => o.id)) : new Set())} /></th>
                  <th style={{ width: 20 }}></th>
                  <th>Order #</th>
                  <th>Customer</th>
                  <th>Items</th>
                  <th>Payment</th>
                  <th>Total / Status</th>
                  <th>Shipping</th>
                </tr>
              </thead>
              <tbody>
                {paginated.map(order => (
                  <OrderRow key={order.id} order={order}
                    selected={selected.has(order.id)}
                    onSelect={() => toggleSelect(order.id)}
                    onClick={() => setSelectedOrder(order)}
                  />
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>

      {selectedOrder && <OrderDetail order={selectedOrder} onClose={() => setSelectedOrder(null)} />}
      {showAddOrder && <AddOrderModal onClose={(didCreate) => { setShowAddOrder(false); if (didCreate) refreshOrders(); }} onNavigate={undefined} />}
    </div>
  );
}
