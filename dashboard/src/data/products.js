/**
 * Products catalog — persisted in localStorage.
 * No mock data. Users add products manually or via Excel import.
 */

const KEY = 'd2cflow_products';

export function getProducts() {
  try {
    return JSON.parse(localStorage.getItem(KEY) || '[]');
  } catch {
    return [];
  }
}

export function saveProducts(products) {
  localStorage.setItem(KEY, JSON.stringify(products));
}

export function addProduct(product) {
  const products = getProducts();
  const newProduct = {
    ...product,
    id: `PRD-${Date.now()}`,
    createdAt: new Date().toISOString(),
    stock: Number(product.stock) || 0,
    price: Number(product.price) || 0,
    mrp: Number(product.mrp) || 0,
  };
  products.unshift(newProduct);
  saveProducts(products);
  return newProduct;
}

export function updateProduct(id, updates) {
  const products = getProducts();
  const idx = products.findIndex(p => p.id === id);
  if (idx === -1) return null;
  products[idx] = { ...products[idx], ...updates };
  saveProducts(products);
  return products[idx];
}

export function deleteProduct(id) {
  const products = getProducts().filter(p => p.id !== id);
  saveProducts(products);
}

export function decrementStock(productId, qty = 1) {
  const products = getProducts();
  const idx = products.findIndex(p => p.id === productId);
  if (idx === -1) return false;
  if (products[idx].stock < qty) return false;
  products[idx].stock -= qty;
  saveProducts(products);
  return true;
}

// Required columns for Excel import
export const EXCEL_COLUMNS = [
  { key: 'name', label: 'Product Name', required: true },
  { key: 'sku', label: 'SKU', required: true },
  { key: 'ean', label: 'EAN / Barcode', required: false },
  { key: 'price', label: 'Selling Price (₹)', required: true },
  { key: 'mrp', label: 'MRP (₹)', required: false },
  { key: 'stock', label: 'Stock Qty', required: true },
  { key: 'category', label: 'Category', required: false },
  { key: 'weight', label: 'Weight (grams)', required: false },
];
