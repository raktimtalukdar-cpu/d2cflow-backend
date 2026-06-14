/**
 * Orders data — persisted in localStorage.
 * No mock data. Orders are created manually or synced from channels.
 */

const KEY = 'd2cflow_orders';

export function getOrders() {
  try {
    return JSON.parse(localStorage.getItem(KEY) || '[]');
  } catch {
    return [];
  }
}

export function saveOrders(orders) {
  localStorage.setItem(KEY, JSON.stringify(orders));
}

export function addOrder(order) {
  const orders = getOrders();
  const now = new Date();
  const dateStr = now.toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' });

  // Normalise items so every item has { name, sku, ean, qty, price }
  const items = (order.items || []).map(item => ({
    name: item.name || 'Unknown product',
    sku: item.sku || item.product_id || '—',
    ean: item.ean || '—',
    qty: Number(item.qty) || 1,
    price: Number(item.price ?? item.unit_price ?? 0),
  }));

  // Normalise top-level fields — WhatsApp uses `price`, manual orders use `total`
  const total = Number(order.total ?? order.price ?? items.reduce((s, i) => s + i.price * i.qty, 0));

  const newOrder = {
    customer: order.customer || 'Unknown',
    phone: order.phone || '—',
    city: order.city || '—',
    state: order.state || '—',
    pincode: order.pincode || '—',
    channel: order.channel || 'manual',
    payment: order.payment || 'prepaid',
    courier: order.courier || null,
    awb: order.awb || null,
    ...order,
    items,
    total,
    id: `ORD-${Date.now()}`,
    date: dateStr,
    status: order.status || 'new',
    createdAt: now.toISOString(),
  };
  orders.unshift(newOrder);
  saveOrders(orders);
  return newOrder;
}

export function updateOrder(id, updates) {
  const orders = getOrders();
  const idx = orders.findIndex(o => o.id === id);
  if (idx === -1) return null;
  orders[idx] = { ...orders[idx], ...updates };
  saveOrders(orders);
  return orders[idx];
}

export function deleteOrder(id) {
  const orders = getOrders().filter(o => o.id !== id);
  saveOrders(orders);
}
