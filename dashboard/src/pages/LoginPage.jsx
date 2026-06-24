import { useState } from 'react';
import { useAuth } from '../context/AuthContext';

export default function LoginPage({ onNavigate }) {
  const { signIn, signInWithGoogle, signInWithMagicLink } = useAuth();
  const [mode, setMode] = useState('default'); // default | magic | password
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [magicSent, setMagicSent] = useState(false);

  const handleGoogle = async () => {
    setError('');
    setLoading(true);
    const { error } = await signInWithGoogle();
    setLoading(false);
    if (error) setError(error.message || JSON.stringify(error));
  };

  const handleMagicLink = async e => {
    e.preventDefault();
    if (!email) return;
    setError('');
    setLoading(true);
    const { error } = await signInWithMagicLink(email);
    setLoading(false);
    if (error) setError(error.message);
    else setMagicSent(true);
  };

  const handlePassword = async e => {
    e.preventDefault();
    setError('');
    setLoading(true);
    const { error } = await signIn({ email, password });
    setLoading(false);
    if (error) setError(error.message);
  };

  return (
    <div style={{
      minHeight: '100vh',
      background: 'var(--bg)',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      padding: 24,
    }}>
      <div style={{ width: '100%', maxWidth: 400 }}>

        {/* Logo */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, justifyContent: 'center', marginBottom: 40 }}>
          <div style={{
            width: 40, height: 40,
            background: 'linear-gradient(135deg, #3395FF 0%, #1A6FCC 100%)',
            borderRadius: 12,
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            color: '#fff', fontWeight: 800, fontSize: 20,
          }}>⚡</div>
          <span style={{ fontSize: 26, fontWeight: 800, letterSpacing: '-0.5px' }}>
            d2c<span style={{ color: 'var(--blue)' }}>flow</span>
          </span>
        </div>

        <div className="card" style={{ padding: '32px 32px 28px' }}>
          {magicSent ? (
            <div style={{ textAlign: 'center', padding: '16px 0' }}>
              <div style={{ fontSize: 44, marginBottom: 16 }}>📬</div>
              <h2 style={{ fontSize: 18, fontWeight: 700, marginBottom: 8 }}>Check your inbox</h2>
              <p style={{ fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.6, marginBottom: 24 }}>
                We sent a magic link to <strong>{email}</strong>.<br />
                Click it to sign in — no password needed.
              </p>
              <button
                onClick={() => { setMagicSent(false); setMode('default'); setEmail(''); }}
                className="btn btn-secondary"
                style={{ width: '100%', justifyContent: 'center' }}
              >
                Use a different email
              </button>
            </div>
          ) : (
            <>
              <h1 style={{ fontSize: 20, fontWeight: 700, marginBottom: 4, textAlign: 'center' }}>
                Sign in to d2cflow
              </h1>
              <p style={{ fontSize: 13, color: 'var(--text-secondary)', textAlign: 'center', marginBottom: 24 }}>
                Your D2C operations command centre
              </p>

              {/* Google — primary */}
              <button
                onClick={handleGoogle}
                disabled={loading}
                style={{
                  width: '100%', padding: '11px 16px',
                  display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 10,
                  background: '#fff', border: '1.5px solid var(--border)',
                  borderRadius: 'var(--radius)', cursor: loading ? 'default' : 'pointer',
                  fontFamily: 'inherit', fontSize: 14, fontWeight: 600,
                  color: 'var(--text-primary)', opacity: loading ? 0.7 : 1,
                  transition: 'all 0.15s',
                  boxShadow: '0 1px 3px rgba(0,0,0,0.08)',
                }}
                onMouseEnter={e => { if (!loading) e.currentTarget.style.background = '#f8faff'; }}
                onMouseLeave={e => { e.currentTarget.style.background = '#fff'; }}
              >
                <svg width="18" height="18" viewBox="0 0 24 24">
                  <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"/>
                  <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/>
                  <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"/>
                  <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"/>
                </svg>
                {loading ? 'Redirecting…' : 'Continue with Google'}
              </button>

              <div style={{ display: 'flex', alignItems: 'center', gap: 12, margin: '20px 0' }}>
                <div style={{ flex: 1, height: 1, background: 'var(--border)' }} />
                <span style={{ fontSize: 11, color: 'var(--text-disabled)', textTransform: 'uppercase', letterSpacing: '0.5px' }}>or</span>
                <div style={{ flex: 1, height: 1, background: 'var(--border)' }} />
              </div>

              {/* Magic link */}
              {(mode === 'default' || mode === 'magic') && (
                <form onSubmit={handleMagicLink}>
                  <div style={{ marginBottom: 10 }}>
                    <input
                      className="form-input"
                      type="email"
                      placeholder="Enter your work email"
                      value={email}
                      onChange={e => setEmail(e.target.value)}
                      required
                      style={{ width: '100%' }}
                      autoComplete="email"
                    />
                  </div>
                  <button
                    type="submit"
                    className="btn btn-primary"
                    disabled={loading || !email}
                    style={{ width: '100%', justifyContent: 'center', height: 40, fontSize: 14 }}
                  >
                    {loading ? 'Sending link…' : '✉ Send magic link'}
                  </button>
                </form>
              )}

              {/* Password fallback */}
              {mode === 'password' && (
                <form onSubmit={handlePassword}>
                  <div style={{ marginBottom: 10 }}>
                    <input
                      className="form-input"
                      type="email"
                      placeholder="Email address"
                      value={email}
                      onChange={e => setEmail(e.target.value)}
                      required
                      style={{ width: '100%', marginBottom: 8 }}
                    />
                    <input
                      className="form-input"
                      type="password"
                      placeholder="Password"
                      value={password}
                      onChange={e => setPassword(e.target.value)}
                      required
                      style={{ width: '100%' }}
                    />
                  </div>
                  <button
                    type="submit"
                    className="btn btn-primary"
                    disabled={loading}
                    style={{ width: '100%', justifyContent: 'center', height: 40, fontSize: 14 }}
                  >
                    {loading ? 'Signing in…' : 'Sign in with password'}
                  </button>
                  <div style={{ textAlign: 'center', marginTop: 10 }}>
                    <button type="button" onClick={() => setMode('default')}
                      style={{ background: 'none', border: 'none', fontSize: 12, color: 'var(--text-secondary)', cursor: 'pointer' }}>
                      ← Back
                    </button>
                  </div>
                </form>
              )}

              {error && (
                <div style={{ background: 'var(--red-light)', color: 'var(--red)', borderRadius: 'var(--radius)', padding: '10px 12px', fontSize: 12, marginTop: 12, lineHeight: 1.5 }}>
                  {error}
                </div>
              )}

              {mode !== 'password' && (
                <div style={{ textAlign: 'center', marginTop: 14 }}>
                  <button
                    onClick={() => { setMode('password'); setError(''); }}
                    style={{ background: 'none', border: 'none', fontSize: 12, color: 'var(--text-disabled)', cursor: 'pointer' }}
                  >
                    Sign in with password instead
                  </button>
                </div>
              )}
            </>
          )}
        </div>

        <p style={{ textAlign: 'center', marginTop: 20, fontSize: 13, color: 'var(--text-secondary)' }}>
          New to d2cflow?{' '}
          <button
            onClick={() => onNavigate('signup')}
            style={{ background: 'none', border: 'none', color: 'var(--blue)', fontWeight: 600, cursor: 'pointer', fontSize: 13 }}
          >
            Create free account →
          </button>
        </p>

        <p style={{ textAlign: 'center', fontSize: 11, color: 'var(--text-disabled)', marginTop: 8 }}>
          Secured by Supabase · Built for Indian D2C brands
        </p>
      </div>
    </div>
  );
}
