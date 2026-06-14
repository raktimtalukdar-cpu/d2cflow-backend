import { useState, useEffect, useCallback, useRef } from 'react';
import { toast } from '../components/Toast';
import { getProducts } from '../data/products';
import { addOrder, getOrders } from '../data/orders';

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

// ── localStorage persistence ──────────────────────────────────────────────────
const CRM_KEY = 'd2cflow_crm_contacts';

function loadContacts() {
  try { return JSON.parse(localStorage.getItem(CRM_KEY) || '[]'); } catch { return []; }
}
function saveContacts(list) {
  localStorage.setItem(CRM_KEY, JSON.stringify(list));
}

// ── Helpers ───────────────────────────────────────────────────────────────────
function fmt(iso) {
  if (!iso) return '—';
  return new Date(iso).toLocaleString('en-IN', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' });
}
function phoneFromJid(jid = '') {
  const raw = jid.replace('@s.whatsapp.net', '').replace('@g.us', '').replace('@lid', '').split('-')[0];
  if (raw.startsWith('91') && raw.length === 12) return `+91 ${raw.slice(2, 7)} ${raw.slice(7)}`;
  if (raw.length === 10 && /^\d+$/.test(raw)) return `+91 ${raw.slice(0, 5)} ${raw.slice(5)}`;
  return raw;
}
function isGroup(jid = '') { return jid.endsWith('@g.us'); }
function isLid(jid = '') { return jid.endsWith('@lid'); }

// Tag colours
const TAG_COLORS = {
  customer: ['#dcfce7', '#166534'],
  lead: ['#eff6ff', '#1d4ed8'],
  vip: ['#fef9c3', '#854d0e'],
  supplier: ['#f3e8ff', '#6b21a8'],
  prospect: ['#fff7ed', '#9a3412'],
};
function tagStyle(tag) {
  const [bg, color] = TAG_COLORS[tag] || ['#f1f5f9', '#475569'];
  return { background: bg, color, borderRadius: 20, padding: '2px 9px', fontSize: 11, fontWeight: 600, display: 'inline-block' };
}

// ── Draft templates per message type ─────────────────────────────────────────
const DRAFT_TEMPLATES = [
  {
    id: 'offer',
    label: '🔥 Limited Offer',
    build: (p) =>
      `Hi {name}! 👋\n\nWe have an exciting offer for you!\n\n🛍️ *${p.name}*${p.mrp && p.price && p.mrp > p.price ? `\n~~₹${p.mrp}~~ → *₹${p.price}*` : p.price ? `\n*₹${p.price}*` : ''}\n${p.description ? `\n${p.description}\n` : ''}\nOrder now and get it delivered to your doorstep! 🚀\n\nReply *YES* to place your order or let us know if you have any questions.`,
  },
  {
    id: 'restock',
    label: '📦 Back in Stock',
    build: (p) =>
      `Hi {name}! 😊\n\nGreat news — *${p.name}* is back in stock!\n${p.price ? `\nPrice: *₹${p.price}*` : ''}${p.stock ? `\nOnly *${p.stock} units* left — grab yours before it sells out!\n` : '\n'}\nReply *YES* to reserve yours right away. 📦`,
  },
  {
    id: 'followup',
    label: '💬 Follow-up',
    build: (p) =>
      `Hi {name}! 👋\n\nJust checking in — were you interested in *${p.name}*?${p.price ? ` It's available at *₹${p.price}*.` : ''}\n\nLet me know if you have any questions — happy to help! 😊`,
  },
  {
    id: 'new_launch',
    label: '🚀 New Launch',
    build: (p) =>
      `Hi {name}! 🎉\n\nExciting news! We just launched *${p.name}*!\n${p.description ? `\n${p.description}\n` : ''}${p.price ? `\nIntroductory price: *₹${p.price}*\n` : ''}\nBe among the first to try it — reply *BUY* to order now! 🛒`,
  },
  {
    id: 'custom',
    label: '✏️ Custom message',
    build: () => '',
  },
];

// ── Compose modal ─────────────────────────────────────────────────────────────
function ComposeModal({ contacts, onClose, presetContact }) {
  const [tab, setTab] = useState(presetContact ? 'individual' : 'broadcast');
  const [selectedJids, setSelectedJids] = useState(new Set());
  const [singleJid, setSingleJid] = useState(presetContact?.jid || '');
  const [message, setMessage] = useState('');
  const [sending, setSending] = useState(false);
  const [results, setResults] = useState(null);
  const [filterTag, setFilterTag] = useState('all');
  const [wasProductOffer, setWasProductOffer] = useState(false);

  // Product-draft state
  const [products] = useState(() => getProducts());
  const [selectedProductId, setSelectedProductId] = useState('');
  const [selectedTemplate, setSelectedTemplate] = useState('');
  const [draftApplied, setDraftApplied] = useState(false);

  const allTags = [...new Set(contacts.flatMap(c => c.tags || []))];

  const filteredContacts = contacts.filter(c => {
    if (isGroup(c.jid)) return false;
    if (filterTag !== 'all' && !(c.tags || []).includes(filterTag)) return false;
    return true;
  });

  const toggleJid = jid => {
    const s = new Set(selectedJids);
    s.has(jid) ? s.delete(jid) : s.add(jid);
    setSelectedJids(s);
  };

  const selectAll = () => setSelectedJids(new Set(filteredContacts.map(c => c.jid)));
  const clearAll = () => setSelectedJids(new Set());

  // Apply draft when product + template are both chosen
  const handleApplyDraft = () => {
    const product = products.find(p => p.id === selectedProductId);
    const tpl = DRAFT_TEMPLATES.find(t => t.id === selectedTemplate);
    if (!product || !tpl) return;
    const draft = tpl.build(product);
    setMessage(draft);
    setDraftApplied(true);
    // Auto-scroll textarea into view after a tick
    setTimeout(() => document.getElementById('crm-msg-textarea')?.focus(), 50);
  };

  const handleSend = async () => {
    const targets = tab === 'broadcast'
      ? contacts.filter(c => selectedJids.has(c.jid))
      : contacts.filter(c => c.jid === singleJid);

    if (!targets.length) { toast.error('Select at least one contact'); return; }
    if (!message.trim()) { toast.error('Write a message'); return; }

    setSending(true);
    const res = { sent: [], failed: [] };

    // Determine if this is a product offer — track YES replies if so
    const isProductOffer = !!selectedProductId && selectedTemplate !== 'custom';
    setWasProductOffer(isProductOffer);

    for (const contact of targets) {
      const personalised = message.replace(/\{name\}/gi, contact.name || phoneFromJid(contact.jid));
      try {
        await apiFetch('/api/whatsapp/send-direct', {
          method: 'POST',
          body: JSON.stringify({
            jid: contact.jid,
            message: personalised,
            // Product context — enables YES-reply → order creation
            track_reply: isProductOffer,
            product_name: isProductOffer ? selectedProduct?.name : undefined,
            product_id: isProductOffer ? selectedProductId : undefined,
            price: isProductOffer ? (selectedProduct?.price || 0) : undefined,
            qty: 1,
            customer_name: contact.name || phoneFromJid(contact.jid),
          }),
        });
        res.sent.push(contact.name || phoneFromJid(contact.jid));
      } catch {
        res.failed.push(contact.name || phoneFromJid(contact.jid));
      }
      if (targets.length > 1) await new Promise(r => setTimeout(r, 600));
    }
    setSending(false);
    setResults(res);
  };

  if (results) {
    return (
      <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.45)', zIndex: 600, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <div style={{ background: '#fff', borderRadius: 16, padding: 36, textAlign: 'center', width: 380, boxShadow: '0 20px 60px rgba(0,0,0,0.15)' }}>
          <div style={{ fontSize: 52, marginBottom: 12 }}>{results.failed.length === 0 ? '✅' : '⚠️'}</div>
          <div style={{ fontWeight: 700, fontSize: 17, marginBottom: 6 }}>
            {results.failed.length === 0 ? 'Messages queued!' : 'Partially sent'}
          </div>
          {results.sent.length > 0 && <div style={{ fontSize: 13, color: '#166534', marginBottom: 4 }}>✓ Sent to: {results.sent.join(', ')}</div>}
          {results.failed.length > 0 && <div style={{ fontSize: 13, color: '#dc2626', marginBottom: 4 }}>✗ Failed: {results.failed.join(', ')}</div>}
          <div style={{ fontSize: 12, color: '#64748b', marginTop: 8, marginBottom: 4 }}>
            Messages are delivered via your connected WhatsApp bridge.
          </div>
          {wasProductOffer && (
            <div style={{ fontSize: 12, background: '#f0fdf4', border: '1px solid #bbf7d0', borderRadius: 8, padding: '8px 12px', color: '#166534', marginBottom: 16, display: 'flex', gap: 6 }}>
              <span>🎯</span>
              <span><strong>YES tracking active</strong> — if any recipient replies YES, an order will be automatically created in your dashboard within 2 minutes.</span>
            </div>
          )}
          <button style={{ background: '#3b82f6', color: '#fff', border: 'none', borderRadius: 8, padding: '10px 28px', fontWeight: 600, cursor: 'pointer', fontFamily: 'inherit' }} onClick={onClose}>Done</button>
        </div>
      </div>
    );
  }

  const selectedProduct = products.find(p => p.id === selectedProductId);

  return (
    <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.45)', zIndex: 600, display: 'flex', alignItems: 'center', justifyContent: 'center' }} onClick={onClose}>
      <div onClick={e => e.stopPropagation()} style={{ width: 640, maxHeight: '92vh', background: '#fff', borderRadius: 16, boxShadow: '0 20px 60px rgba(0,0,0,0.15)', display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
        {/* Header */}
        <div style={{ padding: '16px 20px', borderBottom: '1px solid #e2e8f0', display: 'flex', alignItems: 'center', gap: 12 }}>
          <div style={{ width: 40, height: 40, borderRadius: 10, background: '#25D36618', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 20 }}>💬</div>
          <div>
            <div style={{ fontWeight: 700, fontSize: 15 }}>Send WhatsApp Message</div>
            <div style={{ fontSize: 12, color: '#64748b' }}>Via your connected WhatsApp</div>
          </div>
          <button onClick={onClose} style={{ marginLeft: 'auto', background: 'none', border: 'none', cursor: 'pointer', color: '#94a3b8', fontSize: 18 }}>✕</button>
        </div>

        {/* Tabs */}
        <div style={{ display: 'flex', borderBottom: '1px solid #e2e8f0' }}>
          {[['broadcast', '📢 Broadcast'], ['individual', '👤 Individual']].map(([t, label]) => (
            <button key={t} onClick={() => setTab(t)} style={{
              flex: 1, padding: '10px 0', fontSize: 13, fontWeight: tab === t ? 700 : 500,
              color: tab === t ? '#3b82f6' : '#64748b', background: 'none', border: 'none',
              borderBottom: tab === t ? '2px solid #3b82f6' : '2px solid transparent',
              cursor: 'pointer', fontFamily: 'inherit',
            }}>{label}</button>
          ))}
        </div>

        <div style={{ flex: 1, overflow: 'auto', padding: 20, display: 'flex', flexDirection: 'column', gap: 16 }}>
          {/* Recipient selection */}
          {tab === 'broadcast' ? (
            <div>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
                <div style={{ fontSize: 12, fontWeight: 700, color: '#1e293b' }}>
                  Select recipients <span style={{ color: '#64748b', fontWeight: 400 }}>({selectedJids.size} selected)</span>
                </div>
                <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                  {allTags.length > 0 && (
                    <select value={filterTag} onChange={e => setFilterTag(e.target.value)}
                      style={{ fontSize: 11, border: '1px solid #e2e8f0', borderRadius: 6, padding: '3px 8px', fontFamily: 'inherit', color: '#475569' }}>
                      <option value="all">All tags</option>
                      {allTags.map(t => <option key={t} value={t}>{t}</option>)}
                    </select>
                  )}
                  <button onClick={selectAll} style={{ fontSize: 11, color: '#3b82f6', background: 'none', border: 'none', cursor: 'pointer', fontFamily: 'inherit' }}>Select all</button>
                  <button onClick={clearAll} style={{ fontSize: 11, color: '#64748b', background: 'none', border: 'none', cursor: 'pointer', fontFamily: 'inherit' }}>Clear</button>
                </div>
              </div>
              <div style={{ border: '1px solid #e2e8f0', borderRadius: 10, maxHeight: 180, overflowY: 'auto' }}>
                {filteredContacts.length === 0 ? (
                  <div style={{ padding: '24px', textAlign: 'center', color: '#94a3b8', fontSize: 13 }}>
                    No contacts. Sync from WhatsApp first.
                  </div>
                ) : filteredContacts.map((c, i) => (
                  <label key={c.jid} style={{
                    display: 'flex', alignItems: 'center', gap: 10, padding: '9px 14px',
                    borderBottom: i < filteredContacts.length - 1 ? '1px solid #f1f5f9' : 'none',
                    cursor: 'pointer', background: selectedJids.has(c.jid) ? '#f0f7ff' : '',
                  }}>
                    <input type="checkbox" checked={selectedJids.has(c.jid)} onChange={() => toggleJid(c.jid)} style={{ accentColor: '#3b82f6' }} />
                    <div style={{ width: 32, height: 32, borderRadius: '50%', background: '#e0f2fe', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 14, fontWeight: 700, color: '#0369a1', flexShrink: 0 }}>
                      {(c.name || '?')[0].toUpperCase()}
                    </div>
                    <div style={{ flex: 1 }}>
                      <div style={{ fontSize: 13, fontWeight: 600 }}>{c.name || phoneFromJid(c.jid)}</div>
                      <div style={{ fontSize: 11, color: '#94a3b8' }}>{phoneFromJid(c.jid)}</div>
                    </div>
                    {(c.tags || []).map(t => <span key={t} style={tagStyle(t)}>{t}</span>)}
                  </label>
                ))}
              </div>
            </div>
          ) : (
            <div>
              <div style={{ fontSize: 12, fontWeight: 700, color: '#1e293b', marginBottom: 8 }}>Select contact</div>
              {presetContact ? (
                /* Pre-selected contact — show as a locked chip */
                <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '10px 14px', border: '1px solid #bbf7d0', borderRadius: 8, background: '#f0fdf4' }}>
                  <div style={{ width: 34, height: 34, borderRadius: '50%', background: '#dcfce7', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 15, fontWeight: 700, color: '#166534', flexShrink: 0 }}>
                    {(presetContact.name || '?')[0].toUpperCase()}
                  </div>
                  <div style={{ flex: 1 }}>
                    <div style={{ fontSize: 13, fontWeight: 600, color: '#166534' }}>{presetContact.name || phoneFromJid(presetContact.jid)}</div>
                    <div style={{ fontSize: 11, color: '#64748b' }}>{phoneFromJid(presetContact.jid)}</div>
                  </div>
                  <span style={{ fontSize: 11, background: '#dcfce7', color: '#166534', borderRadius: 20, padding: '2px 8px', fontWeight: 600 }}>Selected</span>
                </div>
              ) : (
                <select value={singleJid} onChange={e => setSingleJid(e.target.value)}
                  style={{ width: '100%', padding: '9px 12px', border: '1px solid #e2e8f0', borderRadius: 8, fontSize: 13, fontFamily: 'inherit' }}>
                  <option value="">— choose a contact —</option>
                  {contacts.filter(c => !isGroup(c.jid) && !isLid(c.jid)).map(c => {
                    const phone = c.phone || phoneFromJid(c.jid);
                    const name = c.name && c.name !== phone ? c.name : null;
                    return (
                      <option key={c.jid} value={c.jid}>
                        {name ? `${name} — ${phone}` : phone}
                      </option>
                    );
                  })}
                </select>
              )}
            </div>
          )}

          {/* ── Product + Draft suggestion ── */}
          <div style={{ background: '#f8fafc', border: '1px solid #e2e8f0', borderRadius: 10, padding: '14px 16px' }}>
            <div style={{ fontSize: 12, fontWeight: 700, color: '#1e293b', marginBottom: 10, display: 'flex', alignItems: 'center', gap: 6 }}>
              <span>🛍️</span> Product & Draft Suggestion
              <span style={{ fontWeight: 400, color: '#94a3b8', fontSize: 11 }}>(optional)</span>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
              {/* Product selector */}
              <div>
                <div style={{ fontSize: 11, color: '#64748b', fontWeight: 600, marginBottom: 4 }}>Choose product</div>
                <select
                  value={selectedProductId}
                  onChange={e => { setSelectedProductId(e.target.value); setSelectedTemplate(''); setDraftApplied(false); }}
                  style={{ width: '100%', padding: '8px 10px', border: '1px solid #e2e8f0', borderRadius: 7, fontSize: 12, fontFamily: 'inherit', background: '#fff' }}
                >
                  <option value="">— select a product —</option>
                  {products.length === 0
                    ? <option disabled>No products in catalog yet</option>
                    : products.map(p => (
                        <option key={p.id} value={p.id}>
                          {p.name}{p.sku ? ` (${p.sku})` : ''}{p.stock !== undefined ? ` · ${p.stock} in stock` : ''}
                        </option>
                      ))
                  }
                </select>
              </div>

              {/* Template selector */}
              <div>
                <div style={{ fontSize: 11, color: '#64748b', fontWeight: 600, marginBottom: 4 }}>Message type</div>
                <select
                  value={selectedTemplate}
                  onChange={e => { setSelectedTemplate(e.target.value); setDraftApplied(false); }}
                  disabled={!selectedProductId}
                  style={{ width: '100%', padding: '8px 10px', border: '1px solid #e2e8f0', borderRadius: 7, fontSize: 12, fontFamily: 'inherit', background: !selectedProductId ? '#f8fafc' : '#fff', color: !selectedProductId ? '#94a3b8' : '#1e293b' }}
                >
                  <option value="">— choose type —</option>
                  {DRAFT_TEMPLATES.map(t => <option key={t.id} value={t.id}>{t.label}</option>)}
                </select>
              </div>
            </div>

            {/* Product info chip + Apply button */}
            {selectedProduct && (
              <div style={{ marginTop: 10, display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, flex: 1, background: '#fff', border: '1px solid #e2e8f0', borderRadius: 7, padding: '7px 10px' }}>
                  <span style={{ fontSize: 18 }}>📦</span>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontSize: 12, fontWeight: 600, color: '#1e293b', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{selectedProduct.name}</div>
                    <div style={{ fontSize: 11, color: '#64748b', display: 'flex', gap: 8 }}>
                      {selectedProduct.price > 0 && <span>₹{selectedProduct.price}</span>}
                      {selectedProduct.mrp > 0 && selectedProduct.mrp !== selectedProduct.price && <span style={{ textDecoration: 'line-through', color: '#94a3b8' }}>₹{selectedProduct.mrp}</span>}
                      {selectedProduct.stock !== undefined && <span style={{ color: selectedProduct.stock > 0 ? '#166534' : '#dc2626' }}>{selectedProduct.stock > 0 ? `${selectedProduct.stock} in stock` : 'Out of stock'}</span>}
                      {selectedProduct.sku && <span style={{ color: '#94a3b8' }}>SKU: {selectedProduct.sku}</span>}
                    </div>
                  </div>
                </div>

                <button
                  onClick={handleApplyDraft}
                  disabled={!selectedTemplate}
                  style={{
                    padding: '8px 16px', borderRadius: 7, border: 'none', fontSize: 12, fontWeight: 700, fontFamily: 'inherit', cursor: selectedTemplate ? 'pointer' : 'default',
                    background: draftApplied ? '#dcfce7' : selectedTemplate ? '#3b82f6' : '#e2e8f0',
                    color: draftApplied ? '#166534' : selectedTemplate ? '#fff' : '#94a3b8',
                    display: 'flex', alignItems: 'center', gap: 5, whiteSpace: 'nowrap', transition: 'all 0.15s',
                  }}>
                  {draftApplied ? '✓ Applied' : '✨ Use draft'}
                </button>
              </div>
            )}
          </div>

          {/* Message textarea */}
          <div>
            <div style={{ fontSize: 12, fontWeight: 700, color: '#1e293b', marginBottom: 8, display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
              <span>Message</span>
              {message && <span style={{ fontSize: 11, color: '#94a3b8', fontWeight: 400 }}>{message.length} chars</span>}
            </div>
            <textarea
              id="crm-msg-textarea"
              value={message}
              onChange={e => { setMessage(e.target.value); setDraftApplied(false); }}
              placeholder="Hi {name}! 👋 We have an exciting offer for you…"
              style={{ width: '100%', boxSizing: 'border-box', minHeight: 120, padding: '10px 12px', border: '1px solid #e2e8f0', borderRadius: 8, fontSize: 13, fontFamily: 'inherit', resize: 'vertical', lineHeight: 1.7, outline: 'none' }}
            />
            <div style={{ fontSize: 11, color: '#94a3b8', marginTop: 4 }}>
              Use <code style={{ background: '#f1f5f9', padding: '1px 4px', borderRadius: 3 }}>{'{name}'}</code> to personalise with contact name.
            </div>
          </div>
        </div>

        {/* Footer */}
        <div style={{ padding: '14px 20px', borderTop: '1px solid #e2e8f0', display: 'flex', gap: 8, justifyContent: 'flex-end', background: '#fafafa' }}>
          <button onClick={onClose} style={{ padding: '8px 18px', border: '1px solid #e2e8f0', borderRadius: 8, background: '#fff', color: '#475569', cursor: 'pointer', fontFamily: 'inherit', fontSize: 13 }}>Cancel</button>
          <button onClick={handleSend} disabled={sending || !message.trim()}
            style={{ padding: '8px 20px', background: sending ? '#94a3b8' : '#25D366', color: '#fff', border: 'none', borderRadius: 8, fontWeight: 700, cursor: 'pointer', fontFamily: 'inherit', fontSize: 13, display: 'flex', alignItems: 'center', gap: 6 }}>
            {sending
              ? <><span style={{ width: 13, height: 13, border: '2px solid rgba(255,255,255,0.4)', borderTop: '2px solid #fff', borderRadius: '50%', animation: 'crm-spin 0.8s linear infinite', display: 'inline-block' }} />Sending…</>
              : `📤 Send to ${tab === 'broadcast' ? selectedJids.size : (singleJid ? 1 : 0)} contact${tab === 'broadcast' && selectedJids.size !== 1 ? 's' : ''}`}
          </button>
        </div>
      </div>
    </div>
  );
}

// ── Contact detail drawer ─────────────────────────────────────────────────────
function ContactDrawer({ contact, onClose, onUpdate, onSendMessage }) {
  const [note, setNote] = useState(contact.note || '');
  const [tag, setTag] = useState('');
  const tags = contact.tags || [];

  const addTag = () => {
    const t = tag.trim().toLowerCase();
    if (!t || tags.includes(t)) { setTag(''); return; }
    onUpdate({ ...contact, tags: [...tags, t] });
    setTag('');
  };

  const removeTag = (t) => onUpdate({ ...contact, tags: tags.filter(x => x !== t) });

  const saveNote = () => {
    onUpdate({ ...contact, note });
    toast.success('Note saved');
  };

  return (
    <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.3)', zIndex: 500, display: 'flex', alignItems: 'flex-start', justifyContent: 'flex-end' }} onClick={onClose}>
      <div onClick={e => e.stopPropagation()} style={{ width: 400, height: '100vh', background: '#fff', boxShadow: '-4px 0 24px rgba(0,0,0,0.08)', display: 'flex', flexDirection: 'column', overflow: 'auto' }}>
        {/* Header */}
        <div style={{ padding: '16px 20px', borderBottom: '1px solid #e2e8f0', display: 'flex', alignItems: 'center', gap: 14 }}>
          <div style={{ width: 48, height: 48, borderRadius: '50%', background: '#e0f2fe', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 22, fontWeight: 700, color: '#0369a1', flexShrink: 0 }}>
            {(contact.name || '?')[0].toUpperCase()}
          </div>
          <div style={{ flex: 1 }}>
            <div style={{ fontWeight: 700, fontSize: 16 }}>{contact.name || phoneFromJid(contact.jid)}</div>
            <div style={{ fontSize: 12, color: '#64748b' }}>{isGroup(contact.jid) ? '👥 Group' : `📱 ${phoneFromJid(contact.jid)}`}</div>
          </div>
          <button onClick={onClose} style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#94a3b8', fontSize: 18 }}>✕</button>
        </div>

        <div style={{ flex: 1, padding: 20, display: 'flex', flexDirection: 'column', gap: 20 }}>
          {/* Quick actions */}
          <div style={{ display: 'flex', gap: 8 }}>
            <button onClick={() => onSendMessage(contact)} style={{ flex: 1, padding: '9px 0', background: '#25D366', color: '#fff', border: 'none', borderRadius: 8, fontWeight: 600, cursor: 'pointer', fontFamily: 'inherit', fontSize: 13 }}>
              💬 Send Message
            </button>
          </div>

          {/* Tags */}
          <div>
            <div style={{ fontSize: 12, fontWeight: 700, color: '#1e293b', marginBottom: 8 }}>Tags</div>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginBottom: 8 }}>
              {tags.map(t => (
                <span key={t} style={{ ...tagStyle(t), display: 'flex', alignItems: 'center', gap: 4, cursor: 'default' }}>
                  {t}
                  <button onClick={() => removeTag(t)} style={{ background: 'none', border: 'none', cursor: 'pointer', padding: 0, fontSize: 12, lineHeight: 1, color: 'inherit', opacity: 0.7 }}>×</button>
                </span>
              ))}
              {tags.length === 0 && <span style={{ fontSize: 12, color: '#94a3b8' }}>No tags yet</span>}
            </div>
            <div style={{ display: 'flex', gap: 6 }}>
              <input value={tag} onChange={e => setTag(e.target.value)} onKeyDown={e => e.key === 'Enter' && addTag()}
                placeholder="customer, lead, vip…"
                style={{ flex: 1, padding: '6px 10px', border: '1px solid #e2e8f0', borderRadius: 6, fontSize: 12, fontFamily: 'inherit' }} />
              <button onClick={addTag} style={{ padding: '6px 12px', background: '#3b82f6', color: '#fff', border: 'none', borderRadius: 6, cursor: 'pointer', fontSize: 12, fontFamily: 'inherit' }}>Add</button>
            </div>
          </div>

          {/* Note */}
          <div>
            <div style={{ fontSize: 12, fontWeight: 700, color: '#1e293b', marginBottom: 8 }}>Note</div>
            <textarea value={note} onChange={e => setNote(e.target.value)}
              placeholder="Add a note about this contact…"
              style={{ width: '100%', boxSizing: 'border-box', minHeight: 90, padding: '8px 10px', border: '1px solid #e2e8f0', borderRadius: 8, fontSize: 12, fontFamily: 'inherit', resize: 'vertical' }} />
            <button onClick={saveNote} style={{ marginTop: 6, padding: '6px 14px', background: '#f1f5f9', color: '#475569', border: '1px solid #e2e8f0', borderRadius: 6, cursor: 'pointer', fontSize: 12, fontFamily: 'inherit' }}>Save note</button>
          </div>

          {/* Info */}
          <div style={{ background: '#f8fafc', borderRadius: 10, padding: '14px 16px', fontSize: 12, color: '#475569' }}>
            <div style={{ marginBottom: 6 }}><strong>JID:</strong> <span style={{ fontFamily: 'monospace', fontSize: 11 }}>{contact.jid}</span></div>
            {contact.last_message_time && <div><strong>Last seen:</strong> {fmt(contact.last_message_time)}</div>}
            {contact.source && <div style={{ marginTop: 4 }}><strong>Source:</strong> {contact.source}</div>}
          </div>
        </div>
      </div>
    </div>
  );
}

// ── Excel / CSV Import Modal ───────────────────────────────────────────────────
function parseCSV(text) {
  const lines = text.trim().split(/\r?\n/);
  if (lines.length < 2) return [];
  const headers = lines[0].split(',').map(h => h.trim().toLowerCase().replace(/[^a-z0-9]/g, ''));
  // Find name and phone columns flexibly
  const nameIdx = headers.findIndex(h => h.includes('name') || h === 'contact');
  const phoneIdx = headers.findIndex(h => h.includes('phone') || h.includes('mobile') || h.includes('number') || h.includes('whatsapp'));
  if (phoneIdx === -1) return null; // can't find phone column
  return lines.slice(1).map(line => {
    const cols = line.split(',').map(c => c.trim().replace(/^"|"$/g, ''));
    const phone = cols[phoneIdx]?.replace(/\D/g, '');
    if (!phone || phone.length < 10) return null;
    const fullPhone = phone.length === 10 ? '91' + phone : phone;
    const name = nameIdx >= 0 ? cols[nameIdx] : '';
    return { name, phone: fullPhone };
  }).filter(Boolean);
}

function ImportModal({ onClose, onImport }) {
  const [file, setFile] = useState(null);
  const [preview, setPreview] = useState(null); // [{name, phone}]
  const [error, setError] = useState('');
  const [importing, setImporting] = useState(false);
  const fileRef = useRef();

  const handleFile = (f) => {
    setFile(f);
    setError('');
    setPreview(null);
    if (!f) return;
    const ext = f.name.split('.').pop().toLowerCase();
    if (ext === 'csv' || ext === 'txt') {
      const reader = new FileReader();
      reader.onload = e => {
        const rows = parseCSV(e.target.result);
        if (rows === null) { setError('Could not find a "phone" or "mobile" column. Please check your CSV headers.'); return; }
        if (rows.length === 0) { setError('No valid rows found.'); return; }
        setPreview(rows);
      };
      reader.readAsText(f);
    } else if (ext === 'xlsx' || ext === 'xls') {
      // Read xlsx as binary and extract text cells
      const reader = new FileReader();
      reader.onload = e => {
        try {
          // Try to extract shared strings from xlsx (zip format)
          // For simplicity, use a basic approach: convert to text and parse
          const text = e.target.result;
          // xlsx files are zips — we can't parse without a library
          // Prompt user to save as CSV
          setError('Excel files (.xlsx) need to be saved as CSV first. In Excel: File → Save As → CSV (.csv).\n\nOr paste data directly.');
        } catch (err) { setError('Could not parse Excel file. Please save as CSV first.'); }
      };
      reader.readAsBinaryString(f);
    } else {
      setError('Please upload a .csv or .xlsx file.');
    }
  };

  const handleDrop = e => {
    e.preventDefault();
    const f = e.dataTransfer.files[0];
    if (f) handleFile(f);
  };

  const handleImport = async () => {
    if (!preview?.length) return;
    setImporting(true);
    onImport(preview);
    setImporting(false);
    onClose();
  };

  return (
    <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)', zIndex: 1000, display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 20 }}>
      <div style={{ background: '#fff', borderRadius: 16, width: '100%', maxWidth: 560, maxHeight: '90vh', display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
        {/* Header */}
        <div style={{ padding: '20px 24px', borderBottom: '1px solid #e2e8f0', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <div>
            <div style={{ fontWeight: 700, fontSize: 16, color: '#1e293b' }}>📥 Import Contacts from Excel / CSV</div>
            <div style={{ fontSize: 12, color: '#64748b', marginTop: 3 }}>Columns needed: <strong>Name</strong> (optional), <strong>Phone</strong> (required)</div>
          </div>
          <button onClick={onClose} style={{ background: 'none', border: 'none', fontSize: 20, cursor: 'pointer', color: '#94a3b8', padding: '0 4px' }}>✕</button>
        </div>

        <div style={{ flex: 1, overflowY: 'auto', padding: '20px 24px' }}>
          {/* Drop zone */}
          <div onDrop={handleDrop} onDragOver={e => e.preventDefault()}
            onClick={() => fileRef.current?.click()}
            style={{ border: '2px dashed #cbd5e1', borderRadius: 12, padding: '32px 24px', textAlign: 'center', cursor: 'pointer', marginBottom: 16, background: file ? '#f0fdf4' : '#f8fafc', transition: 'background 0.2s' }}>
            <div style={{ fontSize: 36, marginBottom: 8 }}>{file ? '✅' : '📂'}</div>
            <div style={{ fontWeight: 600, fontSize: 14, color: '#1e293b', marginBottom: 4 }}>
              {file ? file.name : 'Click to choose file or drag & drop'}
            </div>
            <div style={{ fontSize: 12, color: '#64748b' }}>CSV or Excel file • Columns: Name, Phone/Mobile</div>
            <input ref={fileRef} type="file" accept=".csv,.xlsx,.xls,.txt" style={{ display: 'none' }}
              onChange={e => handleFile(e.target.files[0])} />
          </div>

          {/* Format hint */}
          <div style={{ background: '#fffbeb', border: '1px solid #fde68a', borderRadius: 8, padding: '10px 14px', marginBottom: 16, fontSize: 12, color: '#92400e' }}>
            <strong>Expected format:</strong>
            <div style={{ fontFamily: 'monospace', marginTop: 4, background: '#fff8e1', padding: '6px 10px', borderRadius: 4 }}>
              Name, Phone<br />
              Priya Sharma, 9876543210<br />
              Rahul Verma, 91 98765 43211
            </div>
            <div style={{ marginTop: 6 }}>Phone numbers with or without country code. 10-digit numbers get +91 prefix automatically.</div>
          </div>

          {error && (
            <div style={{ background: '#fee2e2', border: '1px solid rgba(220,38,38,0.3)', borderRadius: 8, padding: '10px 14px', fontSize: 13, color: '#dc2626', marginBottom: 16, whiteSpace: 'pre-line' }}>
              {error}
            </div>
          )}

          {preview && (
            <div style={{ background: '#f8fafc', borderRadius: 10, border: '1px solid #e2e8f0', overflow: 'hidden' }}>
              <div style={{ padding: '10px 16px', borderBottom: '1px solid #e2e8f0', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <span style={{ fontWeight: 700, fontSize: 13, color: '#1e293b' }}>Preview — {preview.length} contacts</span>
                <span style={{ fontSize: 12, color: '#10b981', fontWeight: 600 }}>Ready to import</span>
              </div>
              <div style={{ maxHeight: 200, overflowY: 'auto' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
                  <thead>
                    <tr style={{ background: '#f1f5f9' }}>
                      <th style={{ padding: '7px 16px', textAlign: 'left', fontWeight: 600, color: '#475569' }}>Name</th>
                      <th style={{ padding: '7px 16px', textAlign: 'left', fontWeight: 600, color: '#475569' }}>WhatsApp JID</th>
                    </tr>
                  </thead>
                  <tbody>
                    {preview.slice(0, 50).map((r, i) => (
                      <tr key={i} style={{ borderTop: '1px solid #f1f5f9' }}>
                        <td style={{ padding: '7px 16px', color: '#1e293b' }}>{r.name || <span style={{ color: '#94a3b8' }}>—</span>}</td>
                        <td style={{ padding: '7px 16px', fontFamily: 'monospace', fontSize: 12, color: '#475569' }}>{r.phone}@s.whatsapp.net</td>
                      </tr>
                    ))}
                    {preview.length > 50 && (
                      <tr><td colSpan={2} style={{ padding: '7px 16px', color: '#94a3b8', fontSize: 12, textAlign: 'center' }}>…and {preview.length - 50} more</td></tr>
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>

        <div style={{ padding: '16px 24px', borderTop: '1px solid #e2e8f0', display: 'flex', gap: 10, justifyContent: 'flex-end' }}>
          <button onClick={onClose} style={{ padding: '9px 20px', border: '1px solid #e2e8f0', borderRadius: 8, background: '#fff', color: '#475569', cursor: 'pointer', fontFamily: 'inherit', fontSize: 13 }}>Cancel</button>
          <button onClick={handleImport} disabled={!preview?.length || importing}
            style={{ padding: '9px 20px', background: '#3b82f6', color: '#fff', border: 'none', borderRadius: 8, fontWeight: 700, cursor: preview?.length ? 'pointer' : 'not-allowed', fontFamily: 'inherit', fontSize: 13, opacity: preview?.length ? 1 : 0.5 }}>
            {importing ? 'Importing…' : `Import ${preview?.length || 0} Contacts`}
          </button>
        </div>
      </div>
    </div>
  );
}

// ── Funnel & Group Tracking Panel ─────────────────────────────────────────────
function FunnelPanel() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [tab, setTab] = useState('funnel'); // funnel | groups
  const [confirming, setConfirming] = useState(null); // jid being confirmed

  const load = async () => {
    setLoading(true);
    try {
      const d = await apiFetch('/api/whatsapp/crm-funnel');
      setData(d);
    } catch (e) {
      toast.error(e.message || 'Failed to load funnel data');
    }
    setLoading(false);
  };

  const syncConfirmedToLocalStorage = async () => {
    try {
      const res = await apiFetch('/api/whatsapp/detected-orders?status=confirmed');
      const confirmedOrders = res.orders || [];
      const existing = getOrders();
      const existingWaIds = new Set(existing.map(o => o.wa_order_id).filter(Boolean));
      let added = 0;
      for (const o of confirmedOrders) {
        // Skip if this exact backend order was already synced (by wa_order_id)
        if (existingWaIds.has(o.id)) continue;
        const items = (o.items || [{ name: o.product_hint || 'Product', qty: o.qty || 1, price: o.catalog_price || o.price || 0 }]).map(it => ({
          name: it.name || o.product_hint || 'Product',
          sku: it.product_id || o.product_id || '—',
          qty: it.qty || o.qty || 1,
          price: it.unit_price || o.catalog_price || o.price || 0,
        }));
        addOrder({
          customer: o.customer_name || 'Customer',
          phone: (o.chat_jid || '').replace('@s.whatsapp.net', '').replace('@g.us', '').split('-')[0],
          channel: 'whatsapp',
          payment: 'prepaid',
          status: 'confirmed',
          items,
          total: (o.catalog_price || o.price || 0) * (o.qty || 1),
          wa_order_id: o.id,
          source_jid: o.chat_jid,
        });
        added++;
      }
      if (added > 0) toast.success(`${added} confirmed order${added !== 1 ? 's' : ''} synced to Orders!`);
      else toast.info('All confirmed orders already in Orders section.');
    } catch (e) {
      toast.error(e.message || 'Sync failed');
    }
  };

  const handleManualConfirm = async (jid) => {
    setConfirming(jid);
    try {
      const res = await apiFetch('/api/whatsapp/crm-manual-confirm', {
        method: 'POST',
        body: JSON.stringify({ jid }),
      });

      // Save confirmed order to localStorage so it appears in Orders page
      const backendOrder = res.order || {};
      const alreadyExists = getOrders().some(o =>
        o.wa_order_id === backendOrder.id ||
        (o.channel === 'whatsapp' && o.customer === backendOrder.customer_name && o.createdAt?.startsWith(new Date().toISOString().slice(0, 10)))
      );
      if (!alreadyExists && (backendOrder.id || backendOrder.customer_name)) {
        const items = (backendOrder.items || []).map(it => ({
          name: it.name || backendOrder.product_hint || 'Product',
          sku: it.product_id || '—',
          qty: it.qty || 1,
          price: it.unit_price || backendOrder.price || 0,
        }));
        const rawPhone = jid.replace('@s.whatsapp.net', '').replace('@g.us', '').split('-')[0];
        addOrder({
          customer: backendOrder.customer_name || 'Customer',
          phone: rawPhone,
          channel: 'whatsapp',
          payment: 'prepaid',
          status: 'confirmed',
          items,
          total: backendOrder.price || 0,
          wa_order_id: backendOrder.id,
          source_jid: jid,
          source_group: jid.endsWith('@g.us') ? 'group' : 'direct',
        });
      }

      toast.success('✅ Order confirmed and added to Orders!');
      await load();
    } catch (e) {
      toast.error(e.message || 'Failed to confirm');
    }
    setConfirming(null);
  };

  useEffect(() => { load(); }, []);

  // Auto-sync confirmed WhatsApp orders to localStorage every 30 seconds
  useEffect(() => {
    const autoSync = async () => {
      try {
        const res = await apiFetch('/api/whatsapp/detected-orders?status=confirmed');
        const confirmedOrders = res.orders || [];
        const existing = getOrders();
        const existingWaIds = new Set(existing.map(o => o.wa_order_id).filter(Boolean));
        let added = 0;
        for (const o of confirmedOrders) {
          if (existingWaIds.has(o.id)) continue;
          const items = (o.items || [{ name: o.product_hint || 'Product', qty: o.qty || 1, price: o.catalog_price || o.price || 0 }]).map(it => ({
            name: it.name || o.product_hint || 'Product',
            sku: it.product_id || o.product_id || '—',
            qty: it.qty || o.qty || 1,
            price: it.unit_price || it.price || o.catalog_price || o.price || 0,
          }));
          addOrder({
            customer: o.customer_name || 'Customer',
            phone: (o.chat_jid || '').split('@')[0].split('-')[0],
            channel: 'whatsapp',
            payment: 'prepaid',
            status: 'confirmed',
            items,
            total: o.total || (o.catalog_price || o.price || 0) * (o.qty || 1),
            wa_order_id: o.id,
            source_jid: o.chat_jid,
          });
          added++;
        }
        if (added > 0) {
          toast.success(`${added} new WhatsApp order${added !== 1 ? 's' : ''} synced!`);
          load(); // refresh funnel display
        }
      } catch (e) {
        // silent — don't spam errors for background sync
      }
    };
    autoSync(); // run immediately on mount
    const interval = setInterval(async () => {
      // First trigger a confirmation check on the backend (picks up new YES messages)
      try { await apiFetch('/api/whatsapp/check-confirmations', { method: 'POST' }); } catch {}
      // Then sync new confirmed orders to localStorage
      await autoSync();
    }, 30000);
    return () => clearInterval(interval);
  }, []);

  const fmtTime = iso => {
    if (!iso) return '—';
    try {
      return new Date(iso).toLocaleString('en-IN', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' });
    } catch { return iso; }
  };

  if (loading) return (
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: 300, color: '#64748b', fontSize: 14 }}>
      <div style={{ width: 28, height: 28, border: '3px solid #e2e8f0', borderTop: '3px solid #3b82f6', borderRadius: '50%', animation: 'crm-spin 0.8s linear infinite', marginRight: 12 }} />
      Loading funnel data…
    </div>
  );

  if (!data) return null;

  const { funnel, broadcasts, groups } = data;
  const stepsData = [
    { label: 'Messages Sent', value: funnel.sent, color: '#3b82f6', bg: '#eff6ff', icon: '📤' },
    { label: 'Awaiting Reply', value: funnel.waiting, color: '#f59e0b', bg: '#fffbeb', icon: '⏳' },
    { label: 'Orders Confirmed', value: funnel.confirmed, color: '#10b981', bg: '#f0fdf4', icon: '✅' },
  ];

  return (
    <div style={{ padding: '20px 24px' }}>
      {/* Sub-tabs */}
      <div style={{ display: 'flex', gap: 4, marginBottom: 20, borderBottom: '1px solid #e2e8f0', paddingBottom: 0 }}>
        {[['funnel', '📊 Broadcast Funnel'], ['groups', '👥 Group Tracking']].map(([t, label]) => (
          <button key={t} onClick={() => setTab(t)}
            style={{ padding: '8px 16px', border: 'none', background: 'none', fontSize: 13, fontWeight: tab === t ? 700 : 500, color: tab === t ? '#3b82f6' : '#64748b', borderBottom: tab === t ? '2px solid #3b82f6' : '2px solid transparent', cursor: 'pointer', fontFamily: 'inherit', marginBottom: -1 }}>
            {label}
          </button>
        ))}
        <div style={{ marginLeft: 'auto', display: 'flex', gap: 8 }}>
          <button onClick={syncConfirmedToLocalStorage} style={{ padding: '6px 12px', border: '1px solid #bbf7d0', borderRadius: 7, background: '#f0fdf4', fontSize: 12, color: '#166534', cursor: 'pointer', fontFamily: 'inherit', fontWeight: 600 }}>
            📦 Sync Confirmed → Orders
          </button>
          <button onClick={load} style={{ padding: '6px 12px', border: '1px solid #e2e8f0', borderRadius: 7, background: '#fff', fontSize: 12, color: '#475569', cursor: 'pointer', fontFamily: 'inherit' }}>
            🔄 Refresh
          </button>
        </div>
      </div>

      {tab === 'funnel' && (
        <>
          {/* Funnel cards */}
          <div style={{ display: 'flex', gap: 12, marginBottom: 24 }}>
            {stepsData.map((s, i) => (
              <div key={s.label} style={{ flex: 1, background: s.bg, borderRadius: 12, padding: '16px 20px', border: `1px solid ${s.color}22` }}>
                <div style={{ fontSize: 24, marginBottom: 6 }}>{s.icon}</div>
                <div style={{ fontSize: 28, fontWeight: 800, color: s.color }}>{s.value}</div>
                <div style={{ fontSize: 12, color: '#475569', marginTop: 2 }}>{s.label}</div>
                {i === 2 && funnel.conversion_rate > 0 && (
                  <div style={{ marginTop: 6, fontSize: 11, color: '#10b981', fontWeight: 700 }}>{funnel.conversion_rate}% conversion</div>
                )}
              </div>
            ))}
            {/* Conversion bar */}
            <div style={{ flex: 1, background: '#fff', borderRadius: 12, padding: '16px 20px', border: '1px solid #e2e8f0', display: 'flex', flexDirection: 'column', justifyContent: 'center' }}>
              <div style={{ fontSize: 12, color: '#64748b', marginBottom: 10, fontWeight: 600 }}>CONVERSION FUNNEL</div>
              {stepsData.map((s, i) => {
                const pct = funnel.sent > 0 ? Math.round(s.value / funnel.sent * 100) : 0;
                return (
                  <div key={s.label} style={{ marginBottom: 8 }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11, color: '#64748b', marginBottom: 3 }}>
                      <span>{s.label}</span><span style={{ fontWeight: 700, color: s.color }}>{pct}%</span>
                    </div>
                    <div style={{ height: 6, background: '#f1f5f9', borderRadius: 3, overflow: 'hidden' }}>
                      <div style={{ height: '100%', width: `${pct}%`, background: s.color, borderRadius: 3, transition: 'width 0.6s ease' }} />
                    </div>
                  </div>
                );
              })}
            </div>
          </div>

          {/* Broadcast history table */}
          <div style={{ background: '#fff', borderRadius: 12, border: '1px solid #e2e8f0', overflow: 'hidden' }}>
            <div style={{ padding: '14px 20px', borderBottom: '1px solid #f1f5f9', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
              <div style={{ fontWeight: 700, fontSize: 14, color: '#1e293b' }}>Broadcast History</div>
              <div style={{ fontSize: 12, color: '#94a3b8' }}>{broadcasts.length} message{broadcasts.length !== 1 ? 's' : ''} tracked</div>
            </div>
            {broadcasts.length === 0 ? (
              <div style={{ padding: '48px 24px', textAlign: 'center', color: '#94a3b8', fontSize: 13 }}>
                No broadcasts tracked yet. Send a message with a product selected to start tracking.
              </div>
            ) : (
              <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                <thead>
                  <tr style={{ background: '#f8fafc' }}>
                    {['Contact', 'Product', 'Sent', 'Status', 'Confirmed At', 'Order'].map(h => (
                      <th key={h} style={{ padding: '9px 16px', textAlign: 'left', fontSize: 11, fontWeight: 700, color: '#64748b', textTransform: 'uppercase', letterSpacing: '0.5px', borderBottom: '1px solid #e2e8f0' }}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {broadcasts.map((b, i) => (
                    <tr key={b.jid + i} style={{ borderBottom: '1px solid #f1f5f9' }}
                      onMouseEnter={e => e.currentTarget.style.background = '#f8fafc'}
                      onMouseLeave={e => e.currentTarget.style.background = ''}>
                      <td style={{ padding: '10px 16px' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                          <div style={{ width: 32, height: 32, borderRadius: '50%', background: b.is_group ? '#f3e8ff' : '#e0f2fe', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 14, flexShrink: 0 }}>
                            {b.is_group ? '👥' : (b.name || '?')[0].toUpperCase()}
                          </div>
                          <div>
                            <div style={{ fontWeight: 600, fontSize: 13, color: '#1e293b' }}>{b.name || b.jid}</div>
                            <div style={{ fontSize: 10, color: '#94a3b8' }}>{b.is_group ? 'Group' : b.jid.replace('@s.whatsapp.net', '')}</div>
                          </div>
                        </div>
                      </td>
                      <td style={{ padding: '10px 16px', fontSize: 13, color: '#475569' }}>
                        {b.product_name || '—'}
                        {b.price > 0 && <div style={{ fontSize: 11, color: '#10b981', fontWeight: 600 }}>₹{b.price}</div>}
                      </td>
                      <td style={{ padding: '10px 16px', fontSize: 12, color: '#64748b', whiteSpace: 'nowrap' }}>{fmtTime(b.sent_at)}</td>
                      <td style={{ padding: '10px 16px' }}>
                        {b.confirmed ? (
                          <span style={{ fontSize: 11, background: '#f0fdf4', color: '#166534', border: '1px solid #bbf7d0', borderRadius: 20, padding: '2px 10px', fontWeight: 700 }}>✅ Confirmed</span>
                        ) : b.current_state === 'waiting_confirm' ? (
                          <div style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
                            <span style={{ fontSize: 11, background: '#fffbeb', color: '#92400e', border: '1px solid #fde68a', borderRadius: 20, padding: '2px 10px', fontWeight: 700 }}>⏳ Awaiting YES</span>
                            <button
                              onClick={() => handleManualConfirm(b.jid)}
                              disabled={confirming === b.jid}
                              style={{ fontSize: 11, padding: '3px 10px', background: '#3b82f6', color: '#fff', border: 'none', borderRadius: 6, cursor: 'pointer', fontFamily: 'inherit', fontWeight: 600, opacity: confirming === b.jid ? 0.6 : 1 }}>
                              {confirming === b.jid ? '…' : '✓ Mark Confirmed'}
                            </button>
                          </div>
                        ) : (
                          <span style={{ fontSize: 11, background: '#f8fafc', color: '#94a3b8', border: '1px solid #e2e8f0', borderRadius: 20, padding: '2px 10px', fontWeight: 600 }}>Sent</span>
                        )}
                      </td>
                      <td style={{ padding: '10px 16px', fontSize: 12, color: '#64748b', whiteSpace: 'nowrap' }}>{fmtTime(b.confirmed_at)}</td>
                      <td style={{ padding: '10px 16px', fontSize: 12, fontFamily: 'monospace', color: '#3b82f6' }}>
                        {b.order_id ? b.order_id.substring(0, 16) + '…' : '—'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </>
      )}

      {tab === 'groups' && (
        <div>
          <div style={{ marginBottom: 16, padding: '12px 16px', background: '#fffbeb', border: '1px solid #fde68a', borderRadius: 10, fontSize: 13, color: '#92400e' }}>
            <strong>💡 How group tracking works:</strong> When you send a product offer to a group, the system monitors the group for YES replies. Each YES from any member creates a confirmed order for them.
          </div>
          {groups.length === 0 ? (
            <div style={{ background: '#fff', borderRadius: 12, border: '1px solid #e2e8f0', padding: '60px 24px', textAlign: 'center', color: '#94a3b8', fontSize: 13 }}>
              <div style={{ fontSize: 48, marginBottom: 12 }}>👥</div>
              No groups tracked yet. Send a product offer to a WhatsApp group to start tracking.
            </div>
          ) : (
            <div style={{ display: 'grid', gap: 12 }}>
              {groups.map((g, i) => (
                <div key={g.jid + i} style={{ background: '#fff', borderRadius: 12, border: '1px solid #e2e8f0', padding: '16px 20px' }}>
                  <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                      <div style={{ width: 44, height: 44, borderRadius: '50%', background: '#f3e8ff', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 22, flexShrink: 0 }}>👥</div>
                      <div>
                        <div style={{ fontWeight: 700, fontSize: 14, color: '#1e293b', marginBottom: 2 }}>{g.name || g.jid}</div>
                        <div style={{ fontSize: 11, color: '#94a3b8', fontFamily: 'monospace' }}>{g.jid}</div>
                        <div style={{ marginTop: 6, display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                          <span style={{ fontSize: 11, background: '#eff6ff', color: '#1d4ed8', borderRadius: 20, padding: '2px 10px', fontWeight: 600 }}>
                            📦 {g.product_name || 'No product'}
                          </span>
                          {g.price > 0 && <span style={{ fontSize: 11, background: '#f0fdf4', color: '#166534', borderRadius: 20, padding: '2px 10px', fontWeight: 600 }}>₹{g.price}</span>}
                          <span style={{ fontSize: 11, background: '#f8fafc', color: '#64748b', borderRadius: 20, padding: '2px 10px' }}>Sent {fmtTime(g.sent_at)}</span>
                        </div>
                      </div>
                    </div>
                    <div style={{ textAlign: 'right' }}>
                      {g.confirmed ? (
                        <div style={{ background: '#f0fdf4', border: '1px solid #bbf7d0', borderRadius: 10, padding: '8px 14px', textAlign: 'center' }}>
                          <div style={{ fontSize: 20 }}>✅</div>
                          <div style={{ fontSize: 11, color: '#166534', fontWeight: 700, marginTop: 2 }}>Order Confirmed</div>
                          <div style={{ fontSize: 10, color: '#64748b' }}>{fmtTime(g.confirmed_at)}</div>
                        </div>
                      ) : g.current_state === 'waiting_confirm' ? (
                        <div style={{ background: '#fffbeb', border: '1px solid #fde68a', borderRadius: 10, padding: '8px 14px', textAlign: 'center' }}>
                          <div style={{ fontSize: 20 }}>⏳</div>
                          <div style={{ fontSize: 11, color: '#92400e', fontWeight: 700, marginTop: 2 }}>Awaiting YES</div>
                          <div style={{ fontSize: 10, color: '#64748b', marginBottom: 8 }}>Monitoring group</div>
                          <button
                            onClick={() => handleManualConfirm(g.jid)}
                            disabled={confirming === g.jid}
                            style={{ fontSize: 11, padding: '4px 12px', background: '#3b82f6', color: '#fff', border: 'none', borderRadius: 6, cursor: 'pointer', fontFamily: 'inherit', fontWeight: 600, width: '100%', opacity: confirming === g.jid ? 0.6 : 1 }}>
                            {confirming === g.jid ? '…' : '✓ Mark Confirmed'}
                          </button>
                        </div>
                      ) : (
                        <div style={{ background: '#f8fafc', border: '1px solid #e2e8f0', borderRadius: 10, padding: '8px 14px', textAlign: 'center' }}>
                          <div style={{ fontSize: 20 }}>📤</div>
                          <div style={{ fontSize: 11, color: '#64748b', fontWeight: 600, marginTop: 2 }}>Sent</div>
                        </div>
                      )}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ── Main CRM page ─────────────────────────────────────────────────────────────
export default function CRMPage() {
  const [contacts, setContacts] = useState(loadContacts);
  const [syncing, setSyncing] = useState(false);
  const [search, setSearch] = useState('');
  const [filterTag, setFilterTag] = useState('all');
  const [filterType, setFilterType] = useState('all'); // all | contacts | groups
  const [selected, setSelected] = useState(new Set());
  const [showCompose, setShowCompose] = useState(false);
  const [composePreset, setComposePreset] = useState(null); // single contact preset
  const [activeContact, setActiveContact] = useState(null);
  const [showImportModal, setShowImportModal] = useState(false);
  const [bulkTagInput, setBulkTagInput] = useState('');
  const [mainTab, setMainTab] = useState('contacts'); // contacts | funnel

  const persist = useCallback((list) => { setContacts(list); saveContacts(list); }, []);

  // ── Sync from WhatsApp DB ──────────────────────────────────────────────────
  const handleSync = async () => {
    setSyncing(true);
    try {
      const d = await apiFetch('/api/whatsapp/search-chats?limit=200');
      const raw = d.chats || [];
      const existing = loadContacts();
      const existingJids = new Set(existing.map(c => c.jid));
      let added = 0;
      const merged = [...existing];
      for (const c of raw) {
        // Skip LID JIDs (internal device identifiers, not real contacts)
        if ((c.jid || '').endsWith('@lid')) continue;
        if (!existingJids.has(c.jid)) {
          merged.push({
            jid: c.jid,
            name: c.name || '',        // backend now returns display name or formatted phone
            phone: c.phone || phoneFromJid(c.jid),
            last_message_time: c.last_message_time,
            is_group: c.is_group || false,
            tags: [],
            note: '',
            source: 'whatsapp_sync',
            addedAt: new Date().toISOString(),
          });
          added++;
        } else {
          // Update name/phone if backend has better info
          const idx = merged.findIndex(m => m.jid === c.jid);
          if (idx !== -1) {
            if (c.name && c.name !== c.phone) merged[idx].name = c.name; // real name
            if (c.phone) merged[idx].phone = c.phone;
          }
        }
      }
      persist(merged);
      toast.success(`Synced ${added} new contact(s) from WhatsApp (${merged.length} total)`);
    } catch (e) {
      toast.error(e.message || 'Sync failed — is the bridge running?');
    }
    setSyncing(false);
  };

  // ── Filtering ──────────────────────────────────────────────────────────────
  const allTags = [...new Set(contacts.flatMap(c => c.tags || []))].sort();

  const filtered = contacts.filter(c => {
    if (filterType === 'contacts' && isGroup(c.jid)) return false;
    if (filterType === 'groups' && !isGroup(c.jid)) return false;
    if (filterTag !== 'all' && !(c.tags || []).includes(filterTag)) return false;
    if (search) {
      const q = search.toLowerCase();
      return (c.name || '').toLowerCase().includes(q) || phoneFromJid(c.jid).includes(q);
    }
    return true;
  });

  // ── Selection ──────────────────────────────────────────────────────────────
  const toggle = jid => { const s = new Set(selected); s.has(jid) ? s.delete(jid) : s.add(jid); setSelected(s); };
  const toggleAll = () => setSelected(selected.size === filtered.length ? new Set() : new Set(filtered.map(c => c.jid)));

  // ── Bulk tag ───────────────────────────────────────────────────────────────
  const handleBulkTag = () => {
    const t = bulkTagInput.trim().toLowerCase();
    if (!t || selected.size === 0) return;
    const updated = contacts.map(c => selected.has(c.jid) && !(c.tags || []).includes(t) ? { ...c, tags: [...(c.tags || []), t] } : c);
    persist(updated);
    toast.success(`Tagged ${selected.size} contact(s) as "${t}"`);
    setBulkTagInput('');
    setSelected(new Set());
  };

  // ── Remove contact ─────────────────────────────────────────────────────────
  const handleRemove = jid => { persist(contacts.filter(c => c.jid !== jid)); toast.info('Contact removed'); };

  // ── Update contact ─────────────────────────────────────────────────────────
  const handleUpdate = updated => { persist(contacts.map(c => c.jid === updated.jid ? updated : c)); setActiveContact(updated); };

  // ── Import from Excel/CSV ──────────────────────────────────────────────────
  const handleImport = (rows) => {
    const existing = contacts;
    const existingJids = new Set(existing.map(c => c.jid));
    let added = 0;
    const merged = [...existing];
    for (const { name, phone } of rows) {
      const jid = `${phone}@s.whatsapp.net`;
      if (!existingJids.has(jid)) {
        merged.push({ jid, name: name || '', tags: [], note: '', source: 'excel_import', addedAt: new Date().toISOString() });
        existingJids.add(jid);
        added++;
      }
    }
    persist(merged);
    toast.success(`Imported ${added} new contact${added !== 1 ? 's' : ''} (${rows.length - added} already existed)`);
  };

  // ── Open compose for one contact ───────────────────────────────────────────
  const handleSendToOne = (contact) => {
    setComposePreset(contact);
    setShowCompose(true);
    setActiveContact(null);
  };

  const stats = {
    total: contacts.length,
    contacts: contacts.filter(c => !isGroup(c.jid)).length,
    groups: contacts.filter(c => isGroup(c.jid)).length,
    tagged: contacts.filter(c => (c.tags || []).length > 0).length,
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', background: '#f8f9fa' }}>
      {/* Header */}
      <div style={{ background: '#fff', borderBottom: '1px solid #e2e8f0', padding: '16px 24px', display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexShrink: 0 }}>
        <div>
          <h1 style={{ fontSize: 18, fontWeight: 700, color: '#1e293b', margin: 0 }}>WhatsApp CRM</h1>
          <p style={{ fontSize: 13, color: '#64748b', margin: '2px 0 0' }}>Manage contacts · Send notifications · Track broadcast funnel</p>
        </div>
        <div style={{ display: 'flex', gap: 8 }}>
          <button onClick={handleSync} disabled={syncing}
            style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '8px 16px', border: '1px solid #e2e8f0', borderRadius: 8, background: '#fff', color: '#475569', cursor: 'pointer', fontFamily: 'inherit', fontSize: 13, fontWeight: 500 }}>
            {syncing
              ? <><span style={{ width: 13, height: 13, border: '2px solid #94a3b8', borderTop: '2px solid #3b82f6', borderRadius: '50%', animation: 'crm-spin 0.8s linear infinite', display: 'inline-block' }} />Syncing…</>
              : <>🔄 Sync Contacts</>}
          </button>
          <button onClick={() => setShowImportModal(true)}
            style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '8px 16px', border: '1px solid #e2e8f0', borderRadius: 8, background: '#fff', color: '#475569', cursor: 'pointer', fontFamily: 'inherit', fontSize: 13, fontWeight: 500 }}>
            📥 Import Excel/CSV
          </button>
          <button onClick={() => { setComposePreset(null); setShowCompose(true); }}
            style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '8px 16px', background: '#25D366', color: '#fff', border: 'none', borderRadius: 8, fontWeight: 700, cursor: 'pointer', fontFamily: 'inherit', fontSize: 13 }}>
            💬 Send Message
          </button>
        </div>
      </div>

      {/* Main tab bar */}
      <div style={{ background: '#fff', borderBottom: '1px solid #e2e8f0', padding: '0 24px', display: 'flex', gap: 4, flexShrink: 0 }}>
        {[['contacts', '👤 Contacts'], ['funnel', '📊 Broadcast Funnel']].map(([t, label]) => (
          <button key={t} onClick={() => setMainTab(t)}
            style={{ padding: '10px 18px', border: 'none', background: 'none', fontSize: 13, fontWeight: mainTab === t ? 700 : 500, color: mainTab === t ? '#3b82f6' : '#64748b', borderBottom: mainTab === t ? '2px solid #3b82f6' : '2px solid transparent', cursor: 'pointer', fontFamily: 'inherit', marginBottom: -1 }}>
            {label}
          </button>
        ))}
      </div>

      {/* Funnel panel */}
      {mainTab === 'funnel' && (
        <div style={{ flex: 1, overflowY: 'auto' }}>
          <FunnelPanel />
        </div>
      )}

      {/* Stats strip — contacts tab only */}
      {mainTab === 'contacts' && <></> /* continue below */}
      {mainTab !== 'contacts' ? null : <>

      {/* Stats strip */}
      <div style={{ display: 'flex', gap: 1, background: '#e2e8f0', borderBottom: '1px solid #e2e8f0', flexShrink: 0 }}>
        {[
          { label: 'Total', value: stats.total, icon: '👥' },
          { label: 'Contacts', value: stats.contacts, icon: '👤' },
          { label: 'Groups', value: stats.groups, icon: '💬' },
          { label: 'Tagged', value: stats.tagged, icon: '🏷️' },
        ].map(s => (
          <div key={s.label} style={{ flex: 1, background: '#fff', padding: '10px 20px', display: 'flex', alignItems: 'center', gap: 10 }}>
            <span style={{ fontSize: 18 }}>{s.icon}</span>
            <div>
              <div style={{ fontSize: 18, fontWeight: 700, color: '#1e293b', lineHeight: 1 }}>{s.value}</div>
              <div style={{ fontSize: 11, color: '#64748b' }}>{s.label}</div>
            </div>
          </div>
        ))}
      </div>

      {/* Toolbar */}
      <div style={{ background: '#fff', borderBottom: '1px solid #e2e8f0', padding: '10px 20px', display: 'flex', alignItems: 'center', gap: 10, flexShrink: 0, flexWrap: 'wrap' }}>
        {/* Search */}
        <div style={{ position: 'relative', flex: '1 1 200px', maxWidth: 280 }}>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#94a3b8" strokeWidth="2" style={{ position: 'absolute', left: 10, top: '50%', transform: 'translateY(-50%)' }}>
            <circle cx="11" cy="11" r="8"/><path d="m21 21-4.35-4.35"/>
          </svg>
          <input value={search} onChange={e => setSearch(e.target.value)} placeholder="Search contacts…"
            style={{ width: '100%', boxSizing: 'border-box', padding: '7px 10px 7px 32px', border: '1px solid #e2e8f0', borderRadius: 8, fontSize: 13, fontFamily: 'inherit' }} />
        </div>

        {/* Type filter */}
        <select value={filterType} onChange={e => setFilterType(e.target.value)}
          style={{ padding: '7px 10px', border: '1px solid #e2e8f0', borderRadius: 8, fontSize: 12, fontFamily: 'inherit', color: '#475569' }}>
          <option value="all">All types</option>
          <option value="contacts">Contacts only</option>
          <option value="groups">Groups only</option>
        </select>

        {/* Tag filter */}
        <select value={filterTag} onChange={e => setFilterTag(e.target.value)}
          style={{ padding: '7px 10px', border: '1px solid #e2e8f0', borderRadius: 8, fontSize: 12, fontFamily: 'inherit', color: '#475569' }}>
          <option value="all">All tags</option>
          {allTags.map(t => <option key={t} value={t}>{t}</option>)}
        </select>

        {/* Bulk tag if selection */}
        {selected.size > 0 && (
          <div style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '5px 10px', background: '#eff6ff', borderRadius: 8, border: '1px solid #bfdbfe' }}>
            <span style={{ fontSize: 12, color: '#1d4ed8', fontWeight: 600 }}>{selected.size} selected</span>
            <input value={bulkTagInput} onChange={e => setBulkTagInput(e.target.value)} onKeyDown={e => e.key === 'Enter' && handleBulkTag()}
              placeholder="tag name…" style={{ padding: '3px 8px', border: '1px solid #bfdbfe', borderRadius: 5, fontSize: 12, width: 90, fontFamily: 'inherit' }} />
            <button onClick={handleBulkTag} style={{ padding: '3px 10px', background: '#3b82f6', color: '#fff', border: 'none', borderRadius: 5, fontSize: 12, cursor: 'pointer', fontFamily: 'inherit' }}>Tag</button>
            <button onClick={() => { setComposePreset(null); setShowCompose(true); }}
              style={{ padding: '3px 10px', background: '#25D366', color: '#fff', border: 'none', borderRadius: 5, fontSize: 12, cursor: 'pointer', fontFamily: 'inherit' }}>💬 Message</button>
            <button onClick={() => setSelected(new Set())} style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#64748b', fontSize: 14 }}>✕</button>
          </div>
        )}

        <div style={{ marginLeft: 'auto', fontSize: 12, color: '#94a3b8' }}>{filtered.length} contact{filtered.length !== 1 ? 's' : ''}</div>
      </div>

      {/* Contact list */}
      <div style={{ flex: 1, overflowY: 'auto' }}>
        {contacts.length === 0 ? (
          /* Empty state */
          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', height: '100%', padding: 60, textAlign: 'center' }}>
            <div style={{ fontSize: 56, marginBottom: 16 }}>👥</div>
            <div style={{ fontWeight: 700, fontSize: 18, color: '#1e293b', marginBottom: 8 }}>No contacts yet</div>
            <div style={{ fontSize: 13, color: '#64748b', maxWidth: 380, lineHeight: 1.7, marginBottom: 24 }}>
              Sync your WhatsApp contacts to start sending personalised messages and broadcast notifications to your customers.
            </div>
            <button onClick={handleSync} disabled={syncing}
              style={{ padding: '10px 24px', background: '#25D366', color: '#fff', border: 'none', borderRadius: 8, fontWeight: 700, cursor: 'pointer', fontFamily: 'inherit', fontSize: 14 }}>
              🔄 Sync WhatsApp Contacts
            </button>
          </div>
        ) : filtered.length === 0 ? (
          <div style={{ padding: '60px', textAlign: 'center', color: '#94a3b8', fontSize: 14 }}>
            No contacts match your filters.
          </div>
        ) : (
          <table style={{ width: '100%', borderCollapse: 'collapse' }}>
            <thead>
              <tr style={{ background: '#f8fafc', position: 'sticky', top: 0, zIndex: 1 }}>
                <th style={{ padding: '9px 16px', width: 36, borderBottom: '1px solid #e2e8f0' }}>
                  <input type="checkbox" checked={selected.size === filtered.length && filtered.length > 0}
                    onChange={toggleAll} style={{ accentColor: '#3b82f6' }} />
                </th>
                {['Contact', 'Type', 'Tags', 'Note', 'Last seen', ''].map(h => (
                  <th key={h} style={{ padding: '9px 14px', textAlign: 'left', fontSize: 11, fontWeight: 700, color: '#64748b', textTransform: 'uppercase', letterSpacing: '0.5px', borderBottom: '1px solid #e2e8f0', whiteSpace: 'nowrap' }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {filtered.map((contact, i) => (
                <tr key={contact.jid}
                  style={{ borderBottom: i < filtered.length - 1 ? '1px solid #f1f5f9' : 'none', background: selected.has(contact.jid) ? '#f0f7ff' : '' }}
                  onMouseEnter={e => { if (!selected.has(contact.jid)) e.currentTarget.style.background = '#f8fafc'; }}
                  onMouseLeave={e => { if (!selected.has(contact.jid)) e.currentTarget.style.background = ''; }}>
                  <td style={{ padding: '10px 16px' }}>
                    <input type="checkbox" checked={selected.has(contact.jid)} onChange={() => toggle(contact.jid)} style={{ accentColor: '#3b82f6' }} />
                  </td>
                  {/* Name + phone */}
                  <td style={{ padding: '10px 14px', cursor: 'pointer' }} onClick={() => setActiveContact(contact)}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                      <div style={{ width: 36, height: 36, borderRadius: '50%', background: isGroup(contact.jid) ? '#f3e8ff' : '#e0f2fe', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 16, color: isGroup(contact.jid) ? '#7c3aed' : '#0369a1', fontWeight: 700, flexShrink: 0 }}>
                        {isGroup(contact.jid) ? '👥' : (contact.name || '?')[0].toUpperCase()}
                      </div>
                      <div>
                        <div style={{ fontWeight: 600, fontSize: 13, color: '#1e293b' }}>{contact.name || <span style={{ color: '#94a3b8' }}>(no name)</span>}</div>
                        <div style={{ fontSize: 11, color: '#94a3b8', fontFamily: 'monospace' }}>{phoneFromJid(contact.jid)}</div>
                      </div>
                    </div>
                  </td>
                  {/* Type */}
                  <td style={{ padding: '10px 14px' }}>
                    <span style={{ fontSize: 11, background: isGroup(contact.jid) ? '#f3e8ff' : '#f0fdf4', color: isGroup(contact.jid) ? '#7c3aed' : '#166534', borderRadius: 20, padding: '2px 8px', fontWeight: 600 }}>
                      {isGroup(contact.jid) ? 'Group' : 'Contact'}
                    </span>
                  </td>
                  {/* Tags */}
                  <td style={{ padding: '10px 14px' }}>
                    <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
                      {(contact.tags || []).length === 0
                        ? <span style={{ fontSize: 11, color: '#cbd5e1' }}>—</span>
                        : (contact.tags || []).map(t => <span key={t} style={tagStyle(t)}>{t}</span>)}
                    </div>
                  </td>
                  {/* Note */}
                  <td style={{ padding: '10px 14px', maxWidth: 200 }}>
                    <span style={{ fontSize: 12, color: '#64748b', overflow: 'hidden', display: '-webkit-box', WebkitLineClamp: 1, WebkitBoxOrient: 'vertical' }}>
                      {contact.note || <span style={{ color: '#cbd5e1' }}>—</span>}
                    </span>
                  </td>
                  {/* Last seen */}
                  <td style={{ padding: '10px 14px', fontSize: 12, color: '#94a3b8', whiteSpace: 'nowrap' }}>
                    {fmt(contact.last_message_time)}
                  </td>
                  {/* Actions */}
                  <td style={{ padding: '10px 14px' }}>
                    <div style={{ display: 'flex', gap: 5 }}>
                      <button onClick={() => handleSendToOne(contact)}
                        style={{ fontSize: 11, padding: '4px 10px', background: '#dcfce7', color: '#166534', border: '1px solid #bbf7d0', borderRadius: 6, cursor: 'pointer', fontFamily: 'inherit', whiteSpace: 'nowrap' }}>
                        💬 Send
                      </button>
                      <button onClick={() => setActiveContact(contact)}
                        style={{ fontSize: 11, padding: '4px 8px', background: '#f1f5f9', color: '#475569', border: '1px solid #e2e8f0', borderRadius: 6, cursor: 'pointer', fontFamily: 'inherit' }}>
                        Edit
                      </button>
                      <button onClick={() => handleRemove(contact.jid)}
                        style={{ fontSize: 11, padding: '4px 8px', background: '#fee2e2', color: '#dc2626', border: '1px solid rgba(220,38,38,0.2)', borderRadius: 6, cursor: 'pointer', fontFamily: 'inherit' }}>
                        ✕
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      </>}

      {/* Modals */}
      {showCompose && (
        <ComposeModal
          contacts={contacts}
          presetContact={composePreset || null}
          onClose={() => { setShowCompose(false); setComposePreset(null); }}
        />
      )}

      {activeContact && (
        <ContactDrawer
          contact={activeContact}
          onClose={() => setActiveContact(null)}
          onUpdate={handleUpdate}
          onSendMessage={handleSendToOne}
        />
      )}

      {showImportModal && (
        <ImportModal
          onClose={() => setShowImportModal(false)}
          onImport={handleImport}
        />
      )}

      <style>{`@keyframes crm-spin { to { transform: rotate(360deg); } }`}</style>
    </div>
  );
}
