import { useState, useCallback, useEffect, createContext, useContext } from 'react';

const ToastContext = createContext(null);

let _addToast = null;

export function toast(message, type = 'info', duration = 3000) {
  _addToast?.({ message, type, duration, id: Date.now() + Math.random() });
}
toast.success = (msg, dur) => toast(msg, 'success', dur);
toast.error = (msg, dur) => toast(msg, 'error', dur);
toast.info = (msg, dur) => toast(msg, 'info', dur);
toast.warn = (msg, dur) => toast(msg, 'warn', dur);

export function ToastProvider({ children }) {
  const [toasts, setToasts] = useState([]);

  const addToast = useCallback((t) => {
    setToasts(prev => [...prev, t]);
    setTimeout(() => setToasts(prev => prev.filter(x => x.id !== t.id)), t.duration);
  }, []);

  useEffect(() => { _addToast = addToast; return () => { _addToast = null; }; }, [addToast]);

  const BG = { success: '#16A249', error: '#DC2626', warn: '#D97706', info: '#3395FF' };
  const ICON = { success: '✓', error: '✕', warn: '⚠', info: 'ℹ' };

  return (
    <ToastContext.Provider value={addToast}>
      {children}
      <div style={{ position: 'fixed', bottom: 24, right: 24, zIndex: 9999, display: 'flex', flexDirection: 'column', gap: 8, alignItems: 'flex-end' }}>
        {toasts.map(t => (
          <div key={t.id} style={{
            display: 'flex', alignItems: 'center', gap: 10,
            background: '#fff',
            borderTop: '1px solid var(--border)', borderRight: '1px solid var(--border)', borderBottom: '1px solid var(--border)',
            borderLeft: `4px solid ${BG[t.type]}`,
            borderRadius: 'var(--radius)', padding: '10px 14px',
            boxShadow: 'var(--shadow-md)',
            fontSize: 13, fontWeight: 500,
            animation: 'fadeIn 0.2s ease',
            maxWidth: 340,
          }}>
            <span style={{ width: 18, height: 18, borderRadius: '50%', background: BG[t.type], color: '#fff', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 10, fontWeight: 700, flexShrink: 0 }}>
              {ICON[t.type]}
            </span>
            {t.message}
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}
