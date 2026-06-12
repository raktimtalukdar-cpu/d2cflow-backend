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
  const newOrder = {
    ...order,
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
