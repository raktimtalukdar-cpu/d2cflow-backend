import { useState } from 'react';
import { toast } from '../components/Toast';

const PLANS = [
  { id: 'starter', name: 'Starter', price: 0, orders: 100, channels: 2, features: ['2 channels', '100 orders/month', 'Basic shipping', 'Email support'] },
  { id: 'growth', name: 'Growth', price: 2999, orders: 1000, channels: 5, features: ['5 channels', '1,000 orders/month', 'Multi-courier', 'WhatsApp alerts', 'Analytics', 'Priority support'], popular: true },
  { id: 'scale', name: 'Scale', price: 7999, orders: 10000, channels: 99, features: ['Unlimited channels', '10,000 orders/month', 'Dedicated courier rates', 'Custom automations', 'API access', '24/7 support'] },
];

export default function BillingPage() {
  const [currentPlan] = useState('growth');
  const [billing, setBilling] = useState('monthly');

  const usage = { orders: 312, limit: 1000, channels: 2, channelLimit: 5 };

  return (
    <div style={{ padding: 24, maxWidth: 860 }}>
      <h1 style={{ fontSize: 20, fontWeight: 700, marginBottom: 6 }}>Billing & Plan</h1>
      <p style={{ fontSize: 13, color: 'var(--text-secondary)', marginBottom: 24 }}>Manage your subscription and usage.</p>

      {/* Current usage */}
      <div className="card" style={{ padding: 20, marginBottom: 24 }}>
        <div style={{ fontWeight: 600, fontSize: 14, marginBottom: 14 }}>Current Usage — Growth Plan</div>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20 }}>
          {[
            { label: 'Orders this month', used: usage.orders, limit: usage.limit },
            { label: 'Active channels', used: usage.channels, limit: usage.channelLimit },
          ].map(u => (
            <div key={u.label}>
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12, color: 'var(--text-secondary)', marginBottom: 6 }}>
                <span>{u.label}</span>
                <span style={{ fontWeight: 600, color: 'var(--text-primary)' }}>{u.used} / {u.limit}</span>
              </div>
              <div style={{ height: 8, background: 'var(--border)', borderRadius: 4, overflow: 'hidden' }}>
                <div style={{ height: '100%', width: `${(u.used/u.limit)*100}%`, background: u.used/u.limit > 0.8 ? 'var(--red)' : 'var(--blue)', borderRadius: 4, transition: 'width 0.6s' }} />
              </div>
            </div>
          ))}
        </div>
        <div style={{ marginTop: 16, padding: '10px 14px', background: 'var(--green-light)', borderRadius: 'var(--radius)', fontSize: 12, color: 'var(--green)', fontWeight: 500 }}>
          ✓ Next billing date: July 12, 2026 · ₹2,999/month
        </div>
      </div>

      {/* Plan toggle */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
        <div style={{ fontWeight: 600, fontSize: 14 }}>Change Plan</div>
        <div style={{ display: 'flex', background: 'var(--surface-2)', border: '1px solid var(--border)', borderRadius: 'var(--radius)', padding: 3, gap: 2 }}>
          {['monthly', 'yearly'].map(b => (
            <button key={b} onClick={() => setBilling(b)}
              style={{ padding: '4px 12px', borderRadius: 'var(--radius-sm)', border: 'none', cursor: 'pointer', fontSize: 12, fontFamily: 'inherit', background: billing === b ? '#fff' : 'transparent', color: billing === b ? 'var(--text-primary)' : 'var(--text-secondary)', boxShadow: billing === b ? 'var(--shadow)' : 'none', fontWeight: billing === b ? 500 : 400 }}>
              {b === 'monthly' ? 'Monthly' : 'Yearly (save 20%)'}
            </button>
          ))}
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 16, marginBottom: 24 }}>
        {PLANS.map(plan => {
          const isActive = plan.id === currentPlan;
          const price = billing === 'yearly' ? Math.round(plan.price * 0.8) : plan.price;
          return (
            <div key={plan.id} className="card" style={{ padding: 20, position: 'relative', boxShadow: plan.popular ? '0 0 0 2px var(--blue)' : undefined }}>
              {plan.popular && (
                <div style={{ position: 'absolute', top: -1, left: '50%', transform: 'translateX(-50%)', background: 'var(--blue)', color: '#fff', fontSize: 10, fontWeight: 700, padding: '2px 10px', borderRadius: '0 0 6px 6px', letterSpacing: '0.5px' }}>MOST POPULAR</div>
              )}
              <div style={{ fontWeight: 700, fontSize: 16, marginBottom: 4 }}>{plan.name}</div>
              <div style={{ fontSize: 26, fontWeight: 800, color: 'var(--blue)', marginBottom: 2 }}>
                {price === 0 ? 'Free' : `₹${price.toLocaleString('en-IN')}`}
                {price > 0 && <span style={{ fontSize: 13, fontWeight: 400, color: 'var(--text-secondary)' }}>/mo</span>}
              </div>
              <div style={{ fontSize: 11, color: 'var(--text-secondary)', marginBottom: 16 }}>{plan.orders.toLocaleString()} orders/month</div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginBottom: 20 }}>
                {plan.features.map(f => (
                  <div key={f} style={{ display: 'flex', alignItems: 'center', gap: 7, fontSize: 12, color: 'var(--text-secondary)' }}>
                    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="var(--green)" strokeWidth="2.5"><path d="M20 6L9 17l-5-5"/></svg>
                    {f}
                  </div>
                ))}
              </div>
              {isActive ? (
                <div style={{ textAlign: 'center', fontSize: 12, fontWeight: 600, color: 'var(--green)', padding: '7px 0', background: 'var(--green-light)', borderRadius: 'var(--radius)' }}>Current plan</div>
              ) : (
                <button className={plan.popular ? 'btn btn-primary' : 'btn btn-secondary'} style={{ width: '100%', justifyContent: 'center', fontSize: 13 }}
                  onClick={() => toast.success(`Switching to ${plan.name} plan — contact support to upgrade`)}>
                  {plan.id === 'starter' ? 'Downgrade' : 'Upgrade'}
                </button>
              )}
            </div>
          );
        })}
      </div>

      {/* Invoice history */}
      <div className="card" style={{ padding: 20 }}>
        <div style={{ fontWeight: 600, fontSize: 14, marginBottom: 14 }}>Invoice History</div>
        {[
          { date: 'Jun 12, 2026', amount: '₹2,999', status: 'Paid', id: 'INV-2026-06' },
          { date: 'May 12, 2026', amount: '₹2,999', status: 'Paid', id: 'INV-2026-05' },
          { date: 'Apr 12, 2026', amount: '₹2,999', status: 'Paid', id: 'INV-2026-04' },
        ].map(inv => (
          <div key={inv.id} style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '10px 0', borderBottom: '1px solid var(--border)' }}>
            <div style={{ flex: 1 }}>
              <div style={{ fontSize: 13, fontWeight: 500 }}>{inv.date}</div>
              <div style={{ fontSize: 11, color: 'var(--text-secondary)' }}>{inv.id}</div>
            </div>
            <div style={{ fontWeight: 700, fontSize: 13 }}>{inv.amount}</div>
            <span style={{ fontSize: 11, background: 'var(--green-light)', color: 'var(--green)', padding: '2px 8px', borderRadius: 'var(--radius)', fontWeight: 600 }}>{inv.status}</span>
            <button className="btn btn-secondary" style={{ fontSize: 11 }} onClick={() => toast.success(`Downloading ${inv.id}.pdf`)}>Download</button>
          </div>
        ))}
      </div>
    </div>
  );
}
