import { useState } from 'react';
import { useAuth } from '../context/AuthContext';

export default function LoginPage({ onNavigate }) {
  const { signIn } = useAuth();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const DEMO_EMAIL = 'admin@d2cflow.in';
  const DEMO_PASSWORD = 'demo1234';

  const handleSubmit = async e => {
    e.preventDefault();
    setError('');
    setLoading(true);

    // Demo mode — accept the demo credential or fall through to Supabase
    const skipAuth = !import.meta.env.VITE_SUPABASE_URL || import.meta.env.VITE_SUPABASE_URL.includes('placeholder');
    if (skipAuth || (email === DEMO_EMAIL && password === DEMO_PASSWORD)) {
      localStorage.removeItem('d2c_signed_out');
      window.location.reload();
      return;
    }

    const { error } = await signIn({ email, password });
    setLoading(false);
    if (error) setError(error.message);
  };

  return (
    <div style={{
      minHeight: '100vh', background: 'var(--bg)',
      display: 'flex', alignItems: 'center', justifyContent: 'center',
    }}>
      <div style={{ width: 400 }}>
        {/* Logo */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, justifyContent: 'center', marginBottom: 36 }}>
          <div style={{
            width: 36, height: 36, background: 'linear-gradient(135deg, #3395FF 0%, #1A6FCC 100%)',
            borderRadius: 10, display: 'flex', alignItems: 'center', justifyContent: 'center',
            color: '#fff', fontWeight: 800, fontSize: 18,
          }}>⚡</div>
          <span style={{ fontSize: 22, fontWeight: 800, letterSpacing: '-0.5px' }}>
            d2c<span style={{ color: 'var(--blue)' }}>flow</span>
          </span>
        </div>

        <div className="card" style={{ padding: 32 }}>
          <h1 style={{ fontSize: 20, fontWeight: 700, marginBottom: 4, letterSpacing: '-0.3px' }}>Welcome back</h1>
          <p style={{ fontSize: 13, color: 'var(--text-secondary)', marginBottom: 16 }}>
            Sign in to your store dashboard
          </p>
          <div style={{ background: 'var(--surface-2)', border: '1px solid var(--border)', borderRadius: 'var(--radius)', padding: '10px 12px', marginBottom: 20, fontSize: 12, color: 'var(--text-secondary)' }}>
            <strong style={{ color: 'var(--text-primary)' }}>Demo credentials</strong><br />
            Email: <code style={{ color: 'var(--blue)' }}>admin@d2cflow.in</code> &nbsp;·&nbsp; Password: <code style={{ color: 'var(--blue)' }}>demo1234</code>
          </div>

          <form onSubmit={handleSubmit}>
            <div style={{ marginBottom: 16 }}>
              <label style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-secondary)', display: 'block', marginBottom: 6 }}>
                Email address
              </label>
              <input
                className="form-input"
                type="email"
                placeholder="you@brand.com"
                value={email}
                onChange={e => setEmail(e.target.value)}
                required
                style={{ width: '100%' }}
              />
            </div>

            <div style={{ marginBottom: 8 }}>
              <label style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-secondary)', display: 'block', marginBottom: 6 }}>
                Password
              </label>
              <input
                className="form-input"
                type="password"
                placeholder="••••••••"
                value={password}
                onChange={e => setPassword(e.target.value)}
                required
                style={{ width: '100%' }}
              />
            </div>

            <div style={{ textAlign: 'right', marginBottom: 20 }}>
              <button type="button" style={{ background: 'none', border: 'none', fontSize: 12, color: 'var(--blue)', cursor: 'pointer' }}>
                Forgot password?
              </button>
            </div>

            {error && (
              <div style={{ background: 'var(--red-light)', color: 'var(--red)', borderRadius: 'var(--radius)', padding: '10px 12px', fontSize: 12, marginBottom: 16 }}>
                {error}
              </div>
            )}

            <button
              type="submit"
              className="btn btn-primary"
              disabled={loading}
              style={{ width: '100%', justifyContent: 'center', height: 40, fontSize: 14 }}
            >
              {loading ? 'Signing in…' : 'Sign in'}
            </button>
          </form>

          <div style={{ textAlign: 'center', marginTop: 20, fontSize: 13, color: 'var(--text-secondary)' }}>
            Don't have an account?{' '}
            <button
              onClick={() => onNavigate('signup')}
              style={{ background: 'none', border: 'none', color: 'var(--blue)', fontWeight: 600, cursor: 'pointer', fontSize: 13 }}
            >
              Create one free
            </button>
          </div>
        </div>

        <p style={{ textAlign: 'center', fontSize: 11, color: 'var(--text-disabled)', marginTop: 16 }}>
          Built for Indian D2C brands · Secured by Supabase
        </p>
      </div>
    </div>
  );
}
