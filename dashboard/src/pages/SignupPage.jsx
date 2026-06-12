import { useState } from 'react';
import { useAuth } from '../context/AuthContext';

export default function SignupPage({ onNavigate }) {
  const { signUp } = useAuth();
  const [form, setForm] = useState({ brandName: '', email: '', phone: '', password: '', confirm: '' });
  const [error, setError] = useState('');
  const [success, setSuccess] = useState(false);
  const [loading, setLoading] = useState(false);

  const set = k => e => setForm(f => ({ ...f, [k]: e.target.value }));

  const handleSubmit = async e => {
    e.preventDefault();
    setError('');
    if (form.password !== form.confirm) { setError('Passwords do not match'); return; }
    if (form.password.length < 8) { setError('Password must be at least 8 characters'); return; }
    setLoading(true);
    const { error } = await signUp({ email: form.email, password: form.password, brandName: form.brandName, phone: form.phone });
    setLoading(false);
    if (error) setError(error.message);
    else setSuccess(true);
  };

  if (success) return (
    <div style={{ minHeight: '100vh', background: 'var(--bg)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
      <div style={{ width: 400, textAlign: 'center' }}>
        <div style={{ fontSize: 48, marginBottom: 16 }}>🎉</div>
        <h2 style={{ fontWeight: 700, fontSize: 20, marginBottom: 8 }}>Check your email</h2>
        <p style={{ fontSize: 13, color: 'var(--text-secondary)', marginBottom: 24 }}>
          We sent a confirmation link to <strong>{form.email}</strong>. Click it to activate your account.
        </p>
        <button onClick={() => onNavigate('login')} className="btn btn-primary" style={{ justifyContent: 'center' }}>
          Back to sign in
        </button>
      </div>
    </div>
  );

  return (
    <div style={{ minHeight: '100vh', background: 'var(--bg)', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 24 }}>
      <div style={{ width: 440 }}>
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
          <h1 style={{ fontSize: 20, fontWeight: 700, marginBottom: 4, letterSpacing: '-0.3px' }}>Start automating your D2C ops</h1>
          <p style={{ fontSize: 13, color: 'var(--text-secondary)', marginBottom: 24 }}>
            Free to try · No credit card needed
          </p>

          <form onSubmit={handleSubmit}>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginBottom: 12 }}>
              <div>
                <label style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-secondary)', display: 'block', marginBottom: 6 }}>Brand name</label>
                <input className="form-input" placeholder="Raktim's Store" value={form.brandName} onChange={set('brandName')} required style={{ width: '100%' }} />
              </div>
              <div>
                <label style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-secondary)', display: 'block', marginBottom: 6 }}>Phone (WhatsApp)</label>
                <input className="form-input" type="tel" placeholder="+91 98765 43210" value={form.phone} onChange={set('phone')} style={{ width: '100%' }} />
              </div>
            </div>

            <div style={{ marginBottom: 12 }}>
              <label style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-secondary)', display: 'block', marginBottom: 6 }}>Work email</label>
              <input className="form-input" type="email" placeholder="you@brand.com" value={form.email} onChange={set('email')} required style={{ width: '100%' }} />
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginBottom: 20 }}>
              <div>
                <label style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-secondary)', display: 'block', marginBottom: 6 }}>Password</label>
                <input className="form-input" type="password" placeholder="Min 8 chars" value={form.password} onChange={set('password')} required style={{ width: '100%' }} />
              </div>
              <div>
                <label style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-secondary)', display: 'block', marginBottom: 6 }}>Confirm password</label>
                <input className="form-input" type="password" placeholder="Repeat" value={form.confirm} onChange={set('confirm')} required style={{ width: '100%' }} />
              </div>
            </div>

            {error && (
              <div style={{ background: 'var(--red-light)', color: 'var(--red)', borderRadius: 'var(--radius)', padding: '10px 12px', fontSize: 12, marginBottom: 16 }}>
                {error}
              </div>
            )}

            <button type="submit" className="btn btn-primary" disabled={loading} style={{ width: '100%', justifyContent: 'center', height: 40, fontSize: 14 }}>
              {loading ? 'Creating account…' : 'Create free account'}
            </button>
          </form>

          <div style={{ textAlign: 'center', marginTop: 20, fontSize: 13, color: 'var(--text-secondary)' }}>
            Already have an account?{' '}
            <button onClick={() => onNavigate('login')} style={{ background: 'none', border: 'none', color: 'var(--blue)', fontWeight: 600, cursor: 'pointer', fontSize: 13 }}>
              Sign in
            </button>
          </div>
        </div>

        <p style={{ textAlign: 'center', fontSize: 11, color: 'var(--text-disabled)', marginTop: 16 }}>
          By signing up you agree to our Terms & Privacy Policy
        </p>
      </div>
    </div>
  );
}
