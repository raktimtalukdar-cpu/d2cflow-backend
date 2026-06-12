import { useState, useRef } from 'react';
import * as XLSX from 'xlsx';
import { toast } from '../components/Toast';
import { getProducts, saveProducts, addProduct, updateProduct, deleteProduct, EXCEL_COLUMNS } from '../data/products';

// ── Helpers ───────────────────────────────────────────────────────────────────

function StockBadge({ stock }) {
  if (stock === 0) return <span style={{ fontSize: 11, fontWeight: 600, color: '#DC2626', background: '#FEE2E2', padding: '2px 8px', borderRadius: 4 }}>Out of stock</span>;
  if (stock <= 5) return <span style={{ fontSize: 11, fontWeight: 600, color: '#D97706', background: '#FEF3C7', padding: '2px 8px', borderRadius: 4 }}>Low · {stock}</span>;
  return <span style={{ fontSize: 11, fontWeight: 600, color: '#065F46', background: '#D1FAE5', padding: '2px 8px', borderRadius: 4 }}>{stock} in stock</span>;
}

// ── Add / Edit Product Form ───────────────────────────────────────────────────

const EMPTY_FORM = { name: '', sku: '', ean: '', price: '', mrp: '', stock: '', category: '', weight: '' };

function FormField({ label, k, type = 'text', required, placeholder, hint, value, onChange }) {
  return (
    <div>
      <label style={{ fontSize: 11, fontWeight: 600, color: 'var(--text-secondary)', display: 'block', marginBottom: 3 }}>
        {label}{required && <span style={{ color: 'var(--red)' }}> *</span>}
      </label>
      {hint && <div style={{ fontSize: 10, color: 'var(--text-disabled)', marginBottom: 3 }}>{hint}</div>}
      <input className="form-input" type={type} value={value || ''} onChange={onChange} placeholder={placeholder} style={{ width: '100%', boxSizing: 'border-box' }} />
    </div>
  );
}

function ProductForm({ initial, onSave, onCancel }) {
  const [form, setForm] = useState(initial || EMPTY_FORM);
  const set = k => e => setForm(f => ({ ...f, [k]: e.target.value }));

  const handleSubmit = e => {
    e.preventDefault();
    if (!form.name.trim()) { toast.error('Product name is required'); return; }
    if (!form.sku.trim()) { toast.error('SKU is required'); return; }
    if (!form.price || isNaN(Number(form.price))) { toast.error('Valid selling price is required'); return; }
    if (!form.stock || isNaN(Number(form.stock))) { toast.error('Stock quantity is required'); return; }
    onSave(form);
  };

  return (
    <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
      <FormField label="Product Name" k="name" required placeholder="Handcrafted Brass Diya Set" value={form.name} onChange={set('name')} />
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
        <FormField label="SKU" k="sku" required placeholder="DIYA-BRASS-001" hint="Unique identifier for your inventory" value={form.sku} onChange={set('sku')} />
        <FormField label="EAN / Barcode" k="ean" placeholder="8901234567890" hint="13-digit barcode (optional)" value={form.ean} onChange={set('ean')} />
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 12 }}>
        <FormField label="Selling Price (₹)" k="price" type="number" required placeholder="1299" value={form.price} onChange={set('price')} />
        <FormField label="MRP (₹)" k="mrp" type="number" placeholder="1499" value={form.mrp} onChange={set('mrp')} />
        <FormField label="Stock Qty" k="stock" type="number" required placeholder="50" value={form.stock} onChange={set('stock')} />
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, alignItems: 'end' }}>
        <FormField label="Category" k="category" placeholder="Home Decor" value={form.category} onChange={set('category')} />
        <FormField label="Weight (grams)" k="weight" type="number" placeholder="350" hint="Used for shipping rate calculation" value={form.weight} onChange={set('weight')} />
      </div>
      <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end', paddingTop: 4 }}>
        <button type="button" className="btn btn-secondary" onClick={onCancel}>Cancel</button>
        <button type="submit" className="btn btn-primary">{initial ? 'Save changes' : 'Add product'}</button>
      </div>
    </form>
  );
}

// ── Excel Import ──────────────────────────────────────────────────────────────

function ImportModal({ onClose, onImported }) {
  const fileRef = useRef();
  const [preview, setPreview] = useState(null); // { rows, errors }
  const [importing, setImporting] = useState(false);

  const handleFile = e => {
    const file = e.target.files[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = evt => {
      try {
        const wb = XLSX.read(evt.target.result, { type: 'array' });
        const ws = wb.Sheets[wb.SheetNames[0]];
        const raw = XLSX.utils.sheet_to_json(ws, { defval: '' });

        if (raw.length === 0) { toast.error('Sheet is empty'); return; }

        // Map columns flexibly (case-insensitive)
        const colMap = {};
        const firstRow = raw[0];
        Object.keys(firstRow).forEach(col => {
          const lower = col.toLowerCase().replace(/[^a-z0-9]/g, '');
          if (lower.includes('name') || lower.includes('product')) colMap.name = col;
          else if (lower.includes('sku')) colMap.sku = col;
          else if (lower.includes('ean') || lower.includes('barcode')) colMap.ean = col;
          else if (lower.includes('sell') || lower.includes('price')) colMap.price = col;
          else if (lower.includes('mrp')) colMap.mrp = col;
          else if (lower.includes('stock') || lower.includes('qty') || lower.includes('quantity')) colMap.stock = col;
          else if (lower.includes('cat')) colMap.category = col;
          else if (lower.includes('weight')) colMap.weight = col;
        });

        const errors = [];
        if (!colMap.name) errors.push('Missing column: Product Name');
        if (!colMap.sku) errors.push('Missing column: SKU');
        if (!colMap.price) errors.push('Missing column: Selling Price');
        if (!colMap.stock) errors.push('Missing column: Stock Qty');

        const rows = raw.slice(0, 5).map((r, i) => ({
          name: r[colMap.name] || '',
          sku: r[colMap.sku] || '',
          ean: r[colMap.ean] || '',
          price: r[colMap.price] || '',
          mrp: r[colMap.mrp] || '',
          stock: r[colMap.stock] || '',
          category: r[colMap.category] || '',
          weight: r[colMap.weight] || '',
          _row: i + 2,
          _valid: !!(r[colMap.name] && r[colMap.sku] && r[colMap.price] && r[colMap.stock]),
        }));

        setPreview({ rows, errors, total: raw.length, colMap, allRows: raw });
      } catch (err) {
        toast.error('Could not read file: ' + err.message);
      }
    };
    reader.readAsArrayBuffer(file);
  };

  const handleImport = () => {
    if (!preview) return;
    setImporting(true);
    const { colMap, allRows } = preview;
    const products = getProducts();
    let added = 0, skipped = 0;

    allRows.forEach(r => {
      const name = String(r[colMap.name] || '').trim();
      const sku = String(r[colMap.sku] || '').trim();
      const price = Number(r[colMap.price] || 0);
      const stock = Number(r[colMap.stock] || 0);
      if (!name || !sku || !price) { skipped++; return; }
      // Skip duplicate SKUs
      if (products.find(p => p.sku === sku)) { skipped++; return; }
      products.unshift({
        id: `PRD-${Date.now()}-${added}`,
        name, sku,
        ean: String(r[colMap.ean] || ''),
        price,
        mrp: Number(r[colMap.mrp] || price),
        stock,
        category: String(r[colMap.category] || ''),
        weight: Number(r[colMap.weight] || 0),
        createdAt: new Date().toISOString(),
      });
      added++;
    });

    saveProducts(products);
    setImporting(false);
    toast.success(`Imported ${added} products${skipped ? `, skipped ${skipped} (missing fields or duplicate SKU)` : ''}`);
    onImported();
    onClose();
  };

  const downloadTemplate = () => {
    const ws = XLSX.utils.aoa_to_sheet([
      EXCEL_COLUMNS.map(c => c.label),
      ['Handcrafted Brass Diya Set', 'DIYA-BRASS-001', '8901234567890', '1299', '1499', '50', 'Home Decor', '350'],
      ['Organic Ashwagandha Capsules 60ct', 'ASHW-CAP-060', '8902345678901', '649', '799', '120', 'Health & Wellness', '180'],
    ]);
    const wb = XLSX.utils.book_new();
    XLSX.utils.book_append_sheet(wb, ws, 'Products');
    XLSX.writeFile(wb, 'd2cflow_products_template.xlsx');
  };

  return (
    <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.45)', zIndex: 500, display: 'flex', alignItems: 'center', justifyContent: 'center' }}
      onClick={onClose}>
      <div onClick={e => e.stopPropagation()} className="animate-in"
        style={{ width: 600, background: '#fff', borderRadius: 'var(--radius-lg)', boxShadow: 'var(--shadow-lg)', overflow: 'hidden', maxHeight: '90vh', display: 'flex', flexDirection: 'column' }}>

        <div style={{ padding: '16px 20px', borderBottom: '1px solid var(--border)', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <div>
            <div style={{ fontWeight: 700, fontSize: 15 }}>Import Products from Excel</div>
            <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginTop: 2 }}>Upload a .xlsx file to bulk-add your product catalog</div>
          </div>
          <button onClick={onClose} style={{ background: 'none', border: 'none', cursor: 'pointer', padding: 4 }}>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M18 6L6 18M6 6l12 12"/></svg>
          </button>
        </div>

        <div style={{ padding: 24, overflow: 'auto', flex: 1 }}>
          {/* Template download */}
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '12px 14px', background: 'var(--surface-2)', borderRadius: 'var(--radius)', border: '1px solid var(--border)', marginBottom: 20 }}>
            <div>
              <div style={{ fontSize: 13, fontWeight: 600 }}>Download template first</div>
              <div style={{ fontSize: 11, color: 'var(--text-secondary)', marginTop: 2 }}>
                Required columns: {EXCEL_COLUMNS.filter(c => c.required).map(c => c.label).join(', ')}
              </div>
            </div>
            <button className="btn btn-secondary" style={{ fontSize: 12 }} onClick={downloadTemplate}>
              ↓ Download .xlsx template
            </button>
          </div>

          {/* File upload */}
          <div
            onClick={() => fileRef.current?.click()}
            style={{ border: '2px dashed var(--border)', borderRadius: 'var(--radius)', padding: '32px 24px', textAlign: 'center', cursor: 'pointer', marginBottom: 20, transition: 'border-color 0.2s' }}
            onMouseEnter={e => e.currentTarget.style.borderColor = 'var(--blue)'}
            onMouseLeave={e => e.currentTarget.style.borderColor = 'var(--border)'}
          >
            <div style={{ fontSize: 32, marginBottom: 8 }}>📊</div>
            <div style={{ fontWeight: 600, fontSize: 14, marginBottom: 4 }}>Click to upload Excel file</div>
            <div style={{ fontSize: 12, color: 'var(--text-secondary)' }}>.xlsx or .xls — max 10,000 rows</div>
            <input ref={fileRef} type="file" accept=".xlsx,.xls" style={{ display: 'none' }} onChange={handleFile} />
          </div>

          {/* Preview */}
          {preview && (
            <div>
              {preview.errors.length > 0 && (
                <div style={{ padding: '10px 14px', background: 'var(--red-light)', borderRadius: 'var(--radius)', border: '1px solid rgba(220,38,38,0.2)', marginBottom: 16 }}>
                  {preview.errors.map((e, i) => <div key={i} style={{ fontSize: 12, color: 'var(--red)' }}>⚠ {e}</div>)}
                </div>
              )}

              <div style={{ fontSize: 12, fontWeight: 600, marginBottom: 8, color: 'var(--text-secondary)' }}>
                Preview — first 5 of {preview.total} rows
              </div>
              <div style={{ border: '1px solid var(--border)', borderRadius: 'var(--radius)', overflow: 'auto', marginBottom: 16 }}>
                <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 11 }}>
                  <thead>
                    <tr style={{ background: 'var(--surface-2)' }}>
                      {['Name', 'SKU', 'Price', 'Stock', 'Category'].map(h => (
                        <th key={h} style={{ padding: '6px 10px', textAlign: 'left', fontWeight: 600, color: 'var(--text-secondary)', borderBottom: '1px solid var(--border)' }}>{h}</th>
                      ))}
                      <th style={{ padding: '6px 10px', borderBottom: '1px solid var(--border)' }}></th>
                    </tr>
                  </thead>
                  <tbody>
                    {preview.rows.map((row, i) => (
                      <tr key={i} style={{ borderBottom: '1px solid var(--border)' }}>
                        <td style={{ padding: '6px 10px', maxWidth: 160, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{row.name || '—'}</td>
                        <td style={{ padding: '6px 10px', fontFamily: 'monospace', color: 'var(--blue)' }}>{row.sku || '—'}</td>
                        <td style={{ padding: '6px 10px' }}>₹{row.price || '—'}</td>
                        <td style={{ padding: '6px 10px' }}>{row.stock || '—'}</td>
                        <td style={{ padding: '6px 10px', color: 'var(--text-secondary)' }}>{row.category || '—'}</td>
                        <td style={{ padding: '6px 10px' }}>
                          {row._valid
                            ? <span style={{ color: 'var(--green)', fontWeight: 600 }}>✓</span>
                            : <span style={{ color: 'var(--red)', fontWeight: 600 }}>✗</span>}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              {preview.errors.length === 0 && (
                <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
                  <button className="btn btn-secondary" onClick={onClose}>Cancel</button>
                  <button className="btn btn-primary" onClick={handleImport} disabled={importing}>
                    {importing ? 'Importing…' : `Import all ${preview.total} products`}
                  </button>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

// ── Main Page ─────────────────────────────────────────────────────────────────

export default function ProductsPage() {
  const [products, setProducts] = useState(getProducts);
  const [search, setSearch] = useState('');
  const [showAdd, setShowAdd] = useState(false);
  const [showImport, setShowImport] = useState(false);
  const [editing, setEditing] = useState(null); // product being edited
  const [confirmDelete, setConfirmDelete] = useState(null);

  const refresh = () => setProducts(getProducts());

  const handleAdd = form => {
    addProduct(form);
    refresh();
    setShowAdd(false);
    toast.success('Product added to catalog');
  };

  const handleUpdate = form => {
    updateProduct(editing.id, {
      ...form,
      price: Number(form.price),
      mrp: Number(form.mrp),
      stock: Number(form.stock),
      weight: Number(form.weight),
    });
    refresh();
    setEditing(null);
    toast.success('Product updated');
  };

  const handleDelete = id => {
    deleteProduct(id);
    refresh();
    setConfirmDelete(null);
    toast.info('Product removed from catalog');
  };

  const filtered = products.filter(p =>
    !search || p.name.toLowerCase().includes(search.toLowerCase()) ||
    p.sku.toLowerCase().includes(search.toLowerCase()) ||
    (p.ean || '').includes(search) ||
    (p.category || '').toLowerCase().includes(search.toLowerCase())
  );

  // Empty state
  if (products.length === 0 && !showAdd) {
    return (
      <div style={{ padding: 40, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', minHeight: 'calc(100vh - 52px)' }}>
        <div style={{ fontSize: 56, marginBottom: 16 }}>📦</div>
        <div style={{ fontWeight: 700, fontSize: 20, marginBottom: 8 }}>No products yet</div>
        <div style={{ fontSize: 13, color: 'var(--text-secondary)', textAlign: 'center', maxWidth: 380, marginBottom: 32, lineHeight: 1.6 }}>
          Add your product catalog before creating orders. You can add products one by one or bulk-import from Excel.
        </div>
        <div style={{ display: 'flex', gap: 12 }}>
          <button className="btn btn-secondary" style={{ fontSize: 13, gap: 7 }} onClick={() => setShowImport(true)}>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4 M17 8l-5-5-5 5 M12 3v12"/></svg>
            Import from Excel
          </button>
          <button className="btn btn-primary" style={{ fontSize: 13, gap: 7 }} onClick={() => setShowAdd(true)}>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M12 5v14 M5 12h14"/></svg>
            Add product manually
          </button>
        </div>
        {showImport && <ImportModal onClose={() => setShowImport(false)} onImported={refresh} />}
      </div>
    );
  }

  return (
    <div style={{ padding: 24, maxWidth: 1100 }}>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 20 }}>
        <div>
          <h1 style={{ fontSize: 20, fontWeight: 700, letterSpacing: '-0.3px' }}>Products</h1>
          <p style={{ fontSize: 13, color: 'var(--text-secondary)', marginTop: 2 }}>
            {products.length} product{products.length !== 1 ? 's' : ''} in catalog
          </p>
        </div>
        <div style={{ display: 'flex', gap: 8 }}>
          <button className="btn btn-secondary" style={{ fontSize: 12, gap: 6 }} onClick={() => setShowImport(true)}>
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4 M17 8l-5-5-5 5 M12 3v12"/></svg>
            Import Excel
          </button>
          <button className="btn btn-primary" style={{ fontSize: 12, gap: 6 }} onClick={() => setShowAdd(true)}>
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M12 5v14 M5 12h14"/></svg>
            Add product
          </button>
        </div>
      </div>

      {/* Search */}
      <div style={{ position: 'relative', marginBottom: 16 }}>
        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="var(--text-secondary)" strokeWidth="2"
          style={{ position: 'absolute', left: 10, top: '50%', transform: 'translateY(-50%)' }}>
          <circle cx="11" cy="11" r="8"/><path d="m21 21-4.35-4.35"/>
        </svg>
        <input className="form-input" placeholder="Search by name, SKU, EAN…" value={search}
          onChange={e => setSearch(e.target.value)}
          style={{ paddingLeft: 30, width: 300 }} />
      </div>

      {/* Add product inline */}
      {showAdd && (
        <div className="card" style={{ padding: 20, marginBottom: 20, border: '1px solid var(--blue)', boxShadow: '0 0 0 3px rgba(51,149,255,0.1)' }}>
          <div style={{ fontWeight: 700, fontSize: 14, marginBottom: 16, color: 'var(--blue)' }}>+ New Product</div>
          <ProductForm onSave={handleAdd} onCancel={() => setShowAdd(false)} />
        </div>
      )}

      {/* Edit product inline */}
      {editing && (
        <div className="card" style={{ padding: 20, marginBottom: 20, border: '1px solid var(--blue)', boxShadow: '0 0 0 3px rgba(51,149,255,0.1)' }}>
          <div style={{ fontWeight: 700, fontSize: 14, marginBottom: 16 }}>Edit: {editing.name}</div>
          <ProductForm initial={editing} onSave={handleUpdate} onCancel={() => setEditing(null)} />
        </div>
      )}

      {/* Table */}
      <div className="card" style={{ overflow: 'hidden' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse' }}>
          <thead>
            <tr style={{ background: 'var(--surface-2)', borderBottom: '1px solid var(--border)' }}>
              {['Product', 'SKU', 'EAN', 'Price', 'MRP', 'Stock', 'Category', ''].map(h => (
                <th key={h} style={{ padding: '10px 14px', textAlign: 'left', fontSize: 11, fontWeight: 700, color: 'var(--text-secondary)', textTransform: 'uppercase', letterSpacing: '0.5px', whiteSpace: 'nowrap' }}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {filtered.length === 0 ? (
              <tr><td colSpan={8} style={{ padding: 32, textAlign: 'center', color: 'var(--text-secondary)', fontSize: 13 }}>No products match your search</td></tr>
            ) : filtered.map(p => (
              <tr key={p.id} style={{ borderBottom: '1px solid var(--border)' }}
                onMouseEnter={e => e.currentTarget.style.background = 'var(--surface-2)'}
                onMouseLeave={e => e.currentTarget.style.background = ''}>
                <td style={{ padding: '10px 14px' }}>
                  <div style={{ fontWeight: 500, fontSize: 13 }}>{p.name}</div>
                  {p.weight ? <div style={{ fontSize: 11, color: 'var(--text-secondary)', marginTop: 2 }}>{p.weight}g</div> : null}
                </td>
                <td style={{ padding: '10px 14px', fontFamily: 'monospace', fontSize: 12, color: 'var(--blue)' }}>{p.sku}</td>
                <td style={{ padding: '10px 14px', fontFamily: 'monospace', fontSize: 11, color: 'var(--text-secondary)' }}>{p.ean || '—'}</td>
                <td style={{ padding: '10px 14px', fontWeight: 700, fontSize: 13 }}>₹{Number(p.price).toLocaleString('en-IN')}</td>
                <td style={{ padding: '10px 14px', fontSize: 12, color: 'var(--text-secondary)' }}>{p.mrp ? `₹${Number(p.mrp).toLocaleString('en-IN')}` : '—'}</td>
                <td style={{ padding: '10px 14px' }}><StockBadge stock={Number(p.stock)} /></td>
                <td style={{ padding: '10px 14px', fontSize: 12, color: 'var(--text-secondary)' }}>{p.category || '—'}</td>
                <td style={{ padding: '10px 14px' }}>
                  <div style={{ display: 'flex', gap: 4 }}>
                    <button onClick={() => setEditing(p)} style={{ fontSize: 11, padding: '3px 8px', background: 'var(--surface-2)', border: '1px solid var(--border)', borderRadius: 'var(--radius)', cursor: 'pointer', fontFamily: 'inherit' }}>Edit</button>
                    <button onClick={() => setConfirmDelete(p)} style={{ fontSize: 11, padding: '3px 8px', background: 'var(--red-light)', color: 'var(--red)', border: '1px solid rgba(220,38,38,0.2)', borderRadius: 'var(--radius)', cursor: 'pointer', fontFamily: 'inherit' }}>Delete</button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Confirm delete */}
      {confirmDelete && (
        <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.4)', zIndex: 500, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          <div className="animate-in" style={{ width: 380, background: '#fff', borderRadius: 'var(--radius-lg)', padding: 24, boxShadow: 'var(--shadow-lg)' }}>
            <div style={{ fontWeight: 700, fontSize: 15, marginBottom: 8 }}>Delete product?</div>
            <div style={{ fontSize: 13, color: 'var(--text-secondary)', marginBottom: 20 }}>
              <strong>{confirmDelete.name}</strong> (SKU: {confirmDelete.sku}) will be permanently removed from your catalog. Orders using this product will not be affected.
            </div>
            <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
              <button className="btn btn-secondary" onClick={() => setConfirmDelete(null)}>Cancel</button>
              <button className="btn btn-primary" style={{ background: 'var(--red)', borderColor: 'var(--red)' }} onClick={() => handleDelete(confirmDelete.id)}>Delete</button>
            </div>
          </div>
        </div>
      )}

      {showImport && <ImportModal onClose={() => setShowImport(false)} onImported={refresh} />}
    </div>
  );
}
