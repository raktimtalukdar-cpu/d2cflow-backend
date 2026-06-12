import { useState } from 'react';
import { AUTOMATIONS, TRIGGER_OPTIONS, ACTION_OPTIONS, CONDITION_FIELDS } from '../data/mockData';

function RuleEditor({ rule, onSave, onClose }) {
  const [trigger, setTrigger] = useState(rule?.trigger || '');
  const [conditions, setConditions] = useState(rule?.conditions || []);
  const [actions, setActions] = useState(rule?.actions?.map((a, i) => ({ id: i, type: a, config: '' })) || [{ id: 0, type: '', config: '' }]);
  const [description, setDescription] = useState('');
  const [group, setGroup] = useState(rule ? 'existing' : 'New Order');
  const [active, setActive] = useState(rule?.active ?? true);
  const [showTriggerSearch, setShowTriggerSearch] = useState(false);
  const [triggerSearch, setTriggerSearch] = useState('');

  const addCondition = () => setConditions([...conditions, { field: 'Source', op: 'is', value: '' }]);
  const removeCondition = (i) => setConditions(conditions.filter((_, idx) => idx !== i));
  const updateCondition = (i, key, val) => setConditions(conditions.map((c, idx) => idx === i ? { ...c, [key]: val } : c));
  const addAction = () => setActions([...actions, { id: Date.now(), type: '', config: '' }]);
  const removeAction = (id) => setActions(actions.filter(a => a.id !== id));
  const updateAction = (id, key, val) => setActions(actions.map(a => a.id === id ? { ...a, [key]: val } : a));

  const filteredTriggers = TRIGGER_OPTIONS.filter(t => t.toLowerCase().includes(triggerSearch.toLowerCase()));

  return (
    <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.4)', zIndex: 200, display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 24 }}>
      <div onClick={e => e.stopPropagation()} className="animate-in"
        style={{ width: '90%', maxWidth: 900, maxHeight: '90vh', background: '#fff', borderRadius: 'var(--radius-lg)', boxShadow: 'var(--shadow-lg)', display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
        {/* Header */}
        <div style={{ padding: '16px 20px', borderBottom: '1px solid var(--border)', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <div style={{ fontWeight: 700, fontSize: '15px' }}>{rule ? 'Edit Automation' : 'New Automation'}</div>
          <button onClick={onClose} className="btn btn-ghost btn-icon">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M18 6L6 18M6 6l12 12"/></svg>
          </button>
        </div>

        {/* Body — two columns */}
        <div style={{ display: 'flex', flex: 1, overflow: 'hidden' }}>
          {/* LEFT — trigger + conditions */}
          <div style={{ width: '50%', borderRight: '1px solid var(--border)', padding: 20, overflowY: 'auto' }}>
            <div style={{ fontSize: '11px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.5px', color: 'var(--text-secondary)', marginBottom: 12 }}>Trigger Event</div>

            {/* Trigger selector */}
            <div style={{ position: 'relative' }}>
              <div onClick={() => setShowTriggerSearch(!showTriggerSearch)}
                style={{ padding: '9px 12px', border: '1.5px solid ' + (trigger ? 'var(--blue)' : 'var(--border-strong)'), borderRadius: 'var(--radius)', cursor: 'pointer', fontSize: '13px', background: trigger ? 'var(--blue-light)' : '#fff', display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontWeight: trigger ? 500 : 400, color: trigger ? 'var(--blue)' : 'var(--text-secondary)' }}>
                <span>{trigger || 'Select trigger event...'}</span>
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="m6 9 6 6 6-6"/></svg>
              </div>
              {showTriggerSearch && (
                <div style={{ position: 'absolute', top: '100%', left: 0, right: 0, background: '#fff', border: '1px solid var(--border)', borderRadius: 'var(--radius)', boxShadow: 'var(--shadow-md)', zIndex: 50, marginTop: 2, overflow: 'hidden' }}>
                  <div style={{ padding: 8, borderBottom: '1px solid var(--border)' }}>
                    <input autoFocus className="form-input" placeholder="Search events..." value={triggerSearch} onChange={e => setTriggerSearch(e.target.value)} style={{ fontSize: '12px' }} />
                  </div>
                  <div style={{ maxHeight: 200, overflowY: 'auto' }}>
                    {filteredTriggers.map(t => (
                      <button key={t} onClick={() => { setTrigger(t); setShowTriggerSearch(false); setTriggerSearch(''); }}
                        style={{ display: 'block', width: '100%', padding: '8px 12px', background: trigger === t ? 'var(--blue-light)' : 'none', border: 'none', cursor: 'pointer', fontSize: '13px', textAlign: 'left', fontFamily: 'inherit', color: trigger === t ? 'var(--blue)' : 'var(--text-primary)', fontWeight: trigger === t ? 500 : 400 }}>
                        {t}
                      </button>
                    ))}
                  </div>
                </div>
              )}
            </div>

            {/* Conditions */}
            <div style={{ marginTop: 20 }}>
              <div style={{ fontSize: '11px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.5px', color: 'var(--text-secondary)', marginBottom: 12 }}>Conditions <span style={{ color: 'var(--text-disabled)', fontWeight: 400, textTransform: 'none', letterSpacing: 0 }}>(optional)</span></div>
              {conditions.map((c, i) => (
                <div key={i} style={{ display: 'flex', gap: 6, marginBottom: 8, alignItems: 'center' }}>
                  <select className="form-input form-select" value={c.field} onChange={e => updateCondition(i, 'field', e.target.value)} style={{ flex: 1.5, fontSize: '12px' }}>
                    {CONDITION_FIELDS.map(f => <option key={f}>{f}</option>)}
                  </select>
                  <select className="form-input form-select" value={c.op} onChange={e => updateCondition(i, 'op', e.target.value)} style={{ flex: 1, fontSize: '12px' }}>
                    <option>is</option><option>is not</option><option>contains</option><option>starts with</option>
                  </select>
                  <input className="form-input" value={c.value} onChange={e => updateCondition(i, 'value', e.target.value)} placeholder="Value..." style={{ flex: 2, fontSize: '12px' }} />
                  <button onClick={() => removeCondition(i)} className="btn btn-ghost btn-icon" style={{ flexShrink: 0, color: 'var(--red)' }}>
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M18 6L6 18M6 6l12 12"/></svg>
                  </button>
                </div>
              ))}
              <button onClick={addCondition} style={{ background: 'none', border: '1px dashed var(--border-strong)', borderRadius: 'var(--radius)', padding: '7px 12px', cursor: 'pointer', fontSize: '12px', color: 'var(--blue)', width: '100%', fontFamily: 'inherit', display: 'flex', alignItems: 'center', gap: 6, justifyContent: 'center' }}>
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
                Add condition
              </button>
            </div>

            {/* Metadata */}
            <div style={{ marginTop: 20, padding: '16px', background: 'var(--surface-2)', borderRadius: 'var(--radius)', border: '1px solid var(--border)' }}>
              <div style={{ marginBottom: 12 }}>
                <label style={{ fontSize: '12px', fontWeight: 500, color: 'var(--text-secondary)', display: 'block', marginBottom: 4 }}>Description (optional)</label>
                <input className="form-input" value={description} onChange={e => setDescription(e.target.value)} placeholder="e.g. Send WA when COD order placed" style={{ fontSize: '12px' }} />
              </div>
              <div style={{ marginBottom: 12 }}>
                <label style={{ fontSize: '12px', fontWeight: 500, color: 'var(--text-secondary)', display: 'block', marginBottom: 4 }}>Group</label>
                <select className="form-input form-select" value={group} onChange={e => setGroup(e.target.value)} style={{ fontSize: '12px' }}>
                  <option>New Order</option><option>Ordering a Package</option><option>Package Tracking</option><option>RTO & Returns</option><option>Inventory</option>
                </select>
              </div>
              <label style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer', fontSize: '13px' }}>
                <input type="checkbox" checked={active} onChange={e => setActive(e.target.checked)} style={{ accentColor: 'var(--blue)' }} />
                Active
              </label>
            </div>
          </div>

          {/* RIGHT — actions */}
          <div style={{ width: '50%', padding: 20, overflowY: 'auto' }}>
            <div style={{ fontSize: '11px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.5px', color: 'var(--text-secondary)', marginBottom: 12 }}>Actions to Perform</div>
            {actions.map((action, i) => (
              <div key={action.id} style={{ marginBottom: 12, padding: 14, background: 'var(--surface-2)', borderRadius: 'var(--radius)', border: '1px solid var(--border)' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
                  <div style={{ width: 22, height: 22, background: 'var(--blue)', color: '#fff', borderRadius: '50%', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '11px', fontWeight: 700, flexShrink: 0 }}>{i + 1}</div>
                  <select className="form-input form-select" value={action.type} onChange={e => updateAction(action.id, 'type', e.target.value)} style={{ flex: 1, fontSize: '12px', background: '#fff' }}>
                    <option value="">Select action...</option>
                    {ACTION_OPTIONS.map(a => <option key={a}>{a}</option>)}
                  </select>
                  <button onClick={() => removeAction(action.id)} className="btn btn-ghost btn-icon" style={{ color: 'var(--red)', flexShrink: 0 }}>
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M3 6h18 M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6 M8 6V4a2 2 0 012-2h4a2 2 0 012 2v2"/></svg>
                  </button>
                </div>
                {action.type && (
                  <input className="form-input" placeholder="Configuration (optional)..." value={action.config} onChange={e => updateAction(action.id, 'config', e.target.value)} style={{ fontSize: '12px', background: '#fff' }} />
                )}
                <div style={{ display: 'flex', gap: 8, marginTop: 8 }}>
                  <label style={{ fontSize: '11px', color: 'var(--text-secondary)', display: 'flex', alignItems: 'center', gap: 4 }}>
                    <input type="checkbox" style={{ accentColor: 'var(--blue)' }} /> Stop after failure
                  </label>
                </div>
              </div>
            ))}
            <button onClick={addAction} style={{ background: 'none', border: '1px dashed var(--border-strong)', borderRadius: 'var(--radius)', padding: '9px 12px', cursor: 'pointer', fontSize: '12px', color: 'var(--blue)', width: '100%', fontFamily: 'inherit', display: 'flex', alignItems: 'center', gap: 6, justifyContent: 'center' }}>
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
              Add task to perform
            </button>
          </div>
        </div>

        {/* Footer */}
        <div style={{ padding: '12px 20px', borderTop: '1px solid var(--border)', display: 'flex', justifyContent: 'flex-end', gap: 8, background: 'var(--surface-2)' }}>
          <button className="btn btn-secondary" onClick={onClose}>Cancel</button>
          <button className="btn btn-primary" onClick={() => { onSave && onSave({ trigger, conditions, actions: actions.map(a => a.type), active, group }); onClose(); }}>Save Automation</button>
        </div>
      </div>
    </div>
  );
}

export default function AutomationsPage() {
  const [automations, setAutomations] = useState(AUTOMATIONS);
  const [editing, setEditing] = useState(null);
  const [showNew, setShowNew] = useState(false);

  const toggleRule = (groupIdx, ruleIdx) => {
    setAutomations(prev => prev.map((g, gi) => gi !== groupIdx ? g : {
      ...g, rules: g.rules.map((r, ri) => ri !== ruleIdx ? r : { ...r, active: !r.active })
    }));
  };

  return (
    <div style={{ padding: 24 }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 20 }}>
        <div>
          <h1 style={{ fontSize: '20px', fontWeight: 700, letterSpacing: '-0.3px' }}>Automatic Actions</h1>
          <p style={{ fontSize: '13px', color: 'var(--text-secondary)', marginTop: 2 }}>Build rules to automate your entire D2C workflow without writing code</p>
        </div>
        <button className="btn btn-primary" onClick={() => setShowNew(true)}>
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
          Add Automation
        </button>
      </div>

      {/* Info banner */}
      <div style={{ background: 'var(--blue-light)', border: '1px solid rgba(51,149,255,0.2)', borderRadius: 'var(--radius)', padding: '12px 16px', marginBottom: 20, display: 'flex', alignItems: 'center', gap: 10 }}>
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="var(--blue)" strokeWidth="2"><circle cx="12" cy="12" r="10"/><path d="M12 16v-4 M12 8h.01"/></svg>
        <span style={{ fontSize: '13px', color: 'var(--blue-dark)' }}>
          <strong>{automations.reduce((s, g) => s + g.rules.filter(r => r.active).length, 0)} automations active</strong> · saving you ~6hrs/week on manual work
        </span>
      </div>

      {/* Groups */}
      {automations.map((group, gi) => (
        <div key={gi} className="card" style={{ marginBottom: 12, overflow: 'hidden' }}>
          <div style={{ padding: '12px 16px', background: 'var(--surface-2)', borderBottom: '1px solid var(--border)', display: 'flex', alignItems: 'center', gap: 8 }}>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="var(--text-secondary)" strokeWidth="2"><path d="m6 9 6 6 6-6"/></svg>
            <span style={{ fontWeight: 600, fontSize: '13px' }}>{group.group}</span>
            <span style={{ fontSize: '11px', color: 'var(--text-secondary)', background: 'var(--border)', padding: '1px 7px', borderRadius: 10 }}>{group.rules.length} rules</span>
            <button onClick={() => setEditing({ groupIdx: gi, ruleIdx: null, rule: null })} className="btn btn-secondary" style={{ marginLeft: 'auto', fontSize: '11px', padding: '4px 10px' }}>+ Add rule</button>
          </div>
          {group.rules.map((rule, ri) => (
            <div key={ri} style={{ padding: '12px 16px', borderBottom: ri < group.rules.length - 1 ? '1px solid var(--border)' : 'none', display: 'flex', alignItems: 'flex-start', gap: 12 }}>
              {/* Trigger */}
              <div style={{ flex: 1.5, minWidth: 0 }}>
                <div style={{ fontSize: '10px', fontWeight: 600, color: 'var(--text-secondary)', textTransform: 'uppercase', letterSpacing: '0.4px', marginBottom: 4 }}>Trigger</div>
                <div style={{ padding: '6px 10px', background: 'var(--blue-light)', borderRadius: 'var(--radius-sm)', fontSize: '12px', fontWeight: 500, color: 'var(--blue)', display: 'inline-block' }}>{rule.trigger}</div>
              </div>
              {/* Conditions */}
              <div style={{ flex: 1.5, minWidth: 0 }}>
                <div style={{ fontSize: '10px', fontWeight: 600, color: 'var(--text-secondary)', textTransform: 'uppercase', letterSpacing: '0.4px', marginBottom: 4 }}>Conditions</div>
                {rule.conditions.length === 0 ? <span style={{ fontSize: '12px', color: 'var(--text-disabled)' }}>Any order</span> : rule.conditions.map((c, ci) => (
                  <div key={ci} style={{ fontSize: '12px', display: 'flex', gap: 4, marginBottom: 3 }}>
                    <span style={{ background: '#F1F3F7', padding: '2px 6px', borderRadius: 3 }}>{c.field}</span>
                    <span style={{ color: 'var(--text-secondary)' }}>{c.op}</span>
                    <span style={{ background: '#F1F3F7', padding: '2px 6px', borderRadius: 3 }}>{c.value}</span>
                  </div>
                ))}
              </div>
              {/* Actions */}
              <div style={{ flex: 2, minWidth: 0 }}>
                <div style={{ fontSize: '10px', fontWeight: 600, color: 'var(--text-secondary)', textTransform: 'uppercase', letterSpacing: '0.4px', marginBottom: 4 }}>Actions</div>
                {rule.actions.map((a, ai) => (
                  <div key={ai} style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 3 }}>
                    <span style={{ width: 16, height: 16, background: 'var(--blue)', color: '#fff', borderRadius: '50%', fontSize: '9px', fontWeight: 700, display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>{ai+1}</span>
                    <span style={{ fontSize: '12px' }}>{a}</span>
                  </div>
                ))}
              </div>
              {/* Controls */}
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexShrink: 0 }}>
                {/* Toggle */}
                <button onClick={() => toggleRule(gi, ri)}
                  style={{ width: 36, height: 20, borderRadius: 10, background: rule.active ? 'var(--green)' : '#CBD5E0', border: 'none', cursor: 'pointer', position: 'relative', transition: 'background 0.2s', flexShrink: 0 }}>
                  <span style={{ position: 'absolute', top: 3, left: rule.active ? 19 : 3, width: 14, height: 14, background: '#fff', borderRadius: '50%', transition: 'left 0.2s' }} />
                </button>
                <button onClick={() => setEditing({ rule })} className="btn btn-ghost btn-icon" style={{ padding: '5px' }}>
                  <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M11 4H4a2 2 0 00-2 2v14a2 2 0 002 2h14a2 2 0 002-2v-7 M18.5 2.5a2.121 2.121 0 013 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>
                </button>
              </div>
            </div>
          ))}
        </div>
      ))}

      {/* Add button */}
      <button onClick={() => setShowNew(true)} style={{ width: '100%', padding: '14px', background: 'none', border: '2px dashed var(--border-strong)', borderRadius: 'var(--radius-lg)', cursor: 'pointer', fontSize: '13px', color: 'var(--blue)', fontFamily: 'inherit', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8, fontWeight: 500 }}>
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
        ADD AUTOMATIC ACTION
      </button>

      {(editing || showNew) && (
        <RuleEditor
          rule={editing?.rule}
          onSave={(data) => { console.log('Saved:', data); }}
          onClose={() => { setEditing(null); setShowNew(false); }}
        />
      )}
    </div>
  );
}
