import { useState, lazy, Suspense } from 'react';
import { AuthProvider, useAuth } from './context/AuthContext';
import Sidebar from './components/Sidebar';
import Topbar from './components/Topbar';

const HomePage = lazy(() => import('./pages/HomePage'));
const OrdersPage = lazy(() => import('./pages/OrdersPage'));
const ShippingPage = lazy(() => import('./pages/ShippingPage'));
const AutomationsPage = lazy(() => import('./pages/AutomationsPage'));
const IntegrationsPage = lazy(() => import('./pages/IntegrationsPage'));
const ProductsPage = lazy(() => import('./pages/ProductsPage'));
const SettingsPage = lazy(() => import('./pages/SettingsPage'));
const BillingPage = lazy(() => import('./pages/BillingPage'));
const LoginPage = lazy(() => import('./pages/LoginPage'));
const SignupPage = lazy(() => import('./pages/SignupPage'));
const WhatsAppOrdersPage = lazy(() => import('./pages/WhatsAppOrdersPage'));
const CRMPage = lazy(() => import('./pages/CRMPage'));
const AnalyticsPage = lazy(() => import('./pages/AnalyticsPage'));

function PlaceholderPage({ title, description }) {
  return (
    <div style={{ padding: 40, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', height: '100%', color: 'var(--text-secondary)' }}>
      <div style={{ fontSize: 48, marginBottom: 16 }}>🚧</div>
      <div style={{ fontWeight: 700, fontSize: '18px', color: 'var(--text-primary)', marginBottom: 8 }}>{title}</div>
      <div style={{ fontSize: '13px', textAlign: 'center', maxWidth: 300 }}>{description || 'Coming soon in the next build phase.'}</div>
    </div>
  );
}

function PageLoader() {
  return (
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%' }}>
      <div style={{ width: 32, height: 32, border: '3px solid var(--border)', borderTop: '3px solid var(--blue)', borderRadius: '50%', animation: 'spin 0.7s linear infinite' }} />
      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
    </div>
  );
}

function AuthGate() {
  const { user, loading } = useAuth();
  const [authPage, setAuthPage] = useState('login');

  if (loading) return (
    <div style={{ height: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
      <PageLoader />
    </div>
  );

  const skipAuth = !import.meta.env.VITE_SUPABASE_URL || import.meta.env.VITE_SUPABASE_URL.includes('placeholder');
  const signedOut = localStorage.getItem('d2c_signed_out') === '1';

  if (signedOut || (!skipAuth && !user)) {
    return (
      <Suspense fallback={<PageLoader />}>
        {authPage === 'login'
          ? <LoginPage onNavigate={p => { localStorage.removeItem('d2c_signed_out'); setAuthPage(p); }} />
          : <SignupPage onNavigate={p => { localStorage.removeItem('d2c_signed_out'); setAuthPage(p); }} />
        }
      </Suspense>
    );
  }

  return <Dashboard />;
}

const BACKEND = 'http://localhost:8000';

function InviteModal({ onClose, user }) {
  const [emails, setEmails] = useState('');
  const [role, setRole] = useState('member');
  const [sending, setSending] = useState(false);
  const [result, setResult] = useState(null); // { sent, failed, message } | null
  const [error, setError] = useState('');

  // Pull admin identity: Supabase user first, then brand profile saved in Settings
  const brandProfile = (() => { try { return JSON.parse(localStorage.getItem('d2c_brand_profile') || 'null') || {}; } catch { return {}; } })();
  const inviterEmail = user?.email || brandProfile.email || '';
  const inviterName = user?.user_metadata?.brand_name || brandProfile.name || inviterEmail.split('@')[0] || 'Admin';
  const workspaceName = user?.user_metadata?.brand_name || brandProfile.name || 'd2cflow';

  const handleSend = async () => {
    const list = emails.split(/[\n,;]+/).map(e => e.trim()).filter(Boolean);
    if (!list.length) return;
    setSending(true);
    setError('');
    try {
      const res = await fetch(`${BACKEND}/api/invite`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          emails: list,
          role,
          inviter_name: inviterName,
          inviter_email: inviterEmail,
          workspace_name: workspaceName,
        }),
      });
      const data = await res.json();
      if (!res.ok) {
        setError(data.detail || 'Failed to send invites');
        setSending(false);
        return;
      }
      setResult(data);
    } catch (e) {
      setError('Cannot reach backend. Make sure the server is running on port 8000.');
    }
    setSending(false);
  };

  return (
    <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.45)', zIndex: 500, display: 'flex', alignItems: 'center', justifyContent: 'center' }}
      onClick={onClose}>
      <div onClick={e => e.stopPropagation()} className="animate-in"
        style={{ width: 480, background: '#fff', borderRadius: 'var(--radius-lg)', boxShadow: 'var(--shadow-lg)', overflow: 'hidden' }}>
        <div style={{ padding: '16px 20px', borderBottom: '1px solid var(--border)', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <div style={{ fontWeight: 700, fontSize: 15 }}>Invite Team Members</div>
          <button onClick={onClose} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-secondary)', display: 'flex', padding: 4 }}>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M18 6L6 18M6 6l12 12"/></svg>
          </button>
        </div>

        {result ? (
          <div style={{ padding: 32, textAlign: 'center' }}>
            <div style={{ fontSize: 48, marginBottom: 12 }}>📨</div>
            <div style={{ fontWeight: 700, fontSize: 16, marginBottom: 6 }}>
              {result.failed?.length ? 'Partially sent' : 'Invites sent!'}
            </div>
            <div style={{ fontSize: 13, color: 'var(--text-secondary)', marginBottom: 8 }}>{result.message}</div>
            {result.sent?.length > 0 && (
              <div style={{ fontSize: 12, color: 'var(--green)', marginBottom: 4 }}>
                ✓ {result.sent.join(', ')}
              </div>
            )}
            {result.failed?.length > 0 && (
              <div style={{ fontSize: 12, color: 'var(--red)', marginBottom: 4 }}>
                ✗ {result.failed.map(f => `${f.email} (${f.reason})`).join(', ')}
              </div>
            )}
            <button className="btn btn-primary" style={{ marginTop: 16 }} onClick={onClose}>Done</button>
          </div>
        ) : (
          <div style={{ padding: 24 }}>
            <div style={{ marginBottom: 16 }}>
              <label style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-secondary)', display: 'block', marginBottom: 5 }}>
                Email addresses <span style={{ fontWeight: 400 }}>(one per line or comma-separated)</span>
              </label>
              <textarea
                className="form-input"
                rows={4}
                value={emails}
                onChange={e => setEmails(e.target.value)}
                placeholder="priya@yourbrand.in&#10;rahul@yourbrand.in"
                style={{ width: '100%', resize: 'vertical', boxSizing: 'border-box', fontFamily: 'inherit' }}
              />
            </div>
            <div style={{ marginBottom: 20 }}>
              <label style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-secondary)', display: 'block', marginBottom: 5 }}>Role</label>
              <select className="form-input form-select" value={role} onChange={e => setRole(e.target.value)} style={{ width: '100%' }}>
                <option value="admin">Admin — Full access including billing</option>
                <option value="member">Member — Orders, shipping, returns</option>
                <option value="viewer">Viewer — Read-only access</option>
                <option value="ops">Operations — Orders & shipping only</option>
              </select>
            </div>
            <div style={{ padding: '10px 14px', background: 'var(--surface-2)', borderRadius: 'var(--radius)', border: '1px solid var(--border)', fontSize: 12, color: 'var(--text-secondary)', marginBottom: 16 }}>
              Invites are valid for 7 days. Invited users will need to verify their email before accessing the workspace.
            </div>
            {error && (
              <div style={{ padding: '10px 14px', background: 'var(--red-light)', border: '1px solid rgba(220,38,38,0.25)', borderRadius: 'var(--radius)', fontSize: 12, color: 'var(--red)', marginBottom: 12 }}>
                {error}
              </div>
            )}
            <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
              <button className="btn btn-secondary" onClick={onClose}>Cancel</button>
              <button className="btn btn-primary" onClick={handleSend} disabled={sending || !emails.trim()}>
                {sending ? 'Sending invites…' : `Send ${emails.split(/[\n,;]+/).filter(e => e.trim()).length || ''} invite${emails.split(/[\n,;]+/).filter(e => e.trim()).length !== 1 ? 's' : ''}`}
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function Dashboard() {
  const { signOut, user } = useAuth();
  const [page, setPage] = useState('home');
  const [showInvite, setShowInvite] = useState(false);

  const renderPage = () => {
    if (page.startsWith('ch-')) {
      const channel = page.replace('ch-', '');
      return <OrdersPage filterChannel={channel} />;
    }
    switch (page) {
      case 'home': return <HomePage onNavigate={setPage} />;
      case 'orders': return <OrdersPage />;
      case 'whatsapp-orders': return <WhatsAppOrdersPage />;
      case 'crm': return <CRMPage />;
      case 'shipping': return <ShippingPage />;
      case 'automations': return <AutomationsPage />;
      case 'integrations': return <IntegrationsPage />;
      case 'settings': return <SettingsPage />;
      case 'billing': return <BillingPage />;
      case 'products': return <ProductsPage />;
      case 'returns': return <PlaceholderPage title="Returns & RTO" description="Return management, courier claims, and RTO analytics — Phase 2." />;
      case 'analytics': return <AnalyticsPage />;
      default: return <PlaceholderPage title={page} />;
    }
  };

  return (
    <div style={{ display: 'flex', height: '100vh', overflow: 'hidden' }}>
      <Sidebar active={page} onNavigate={setPage} />
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden', minWidth: 0 }}>
        <Topbar page={page} user={user} onSignOut={signOut} onNavigate={setPage} onInvite={() => setShowInvite(true)} />
        <div style={{ flex: 1, overflow: 'auto' }}>
          <Suspense fallback={<PageLoader />}>
            {renderPage()}
          </Suspense>
        </div>
      </div>
      {showInvite && <InviteModal onClose={() => setShowInvite(false)} user={user} />}
    </div>
  );
}

export default function App() {
  return (
    <AuthProvider>
      <AuthGate />
    </AuthProvider>
  );
}
