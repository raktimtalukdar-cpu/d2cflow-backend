import { createContext, useContext, useState, useEffect } from 'react';
import { supabase } from '../lib/supabase';

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [session, setSession] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    supabase.auth.getSession().then(({ data: { session } }) => {
      setSession(session);
      setUser(session?.user ?? null);
      if (session) localStorage.setItem('d2c_session', JSON.stringify(session));
      setLoading(false);
    });

    const { data: { subscription } } = supabase.auth.onAuthStateChange((_event, session) => {
      setSession(session);
      setUser(session?.user ?? null);
      if (session) {
        localStorage.setItem('d2c_session', JSON.stringify(session));
        localStorage.removeItem('d2c_signed_out');
      } else {
        localStorage.removeItem('d2c_session');
      }
    });

    return () => subscription.unsubscribe();
  }, []);

  const signUp = async ({ email, password, brandName, phone }) => {
    const { data, error } = await supabase.auth.signUp({
      email,
      password,
      options: { data: { brand_name: brandName, phone } },
    });
    return { data, error };
  };

  const signIn = async ({ email, password }) => {
    const { data, error } = await supabase.auth.signInWithPassword({ email, password });
    return { data, error };
  };

  const signInWithGoogle = async () => {
    const { data, error } = await supabase.auth.signInWithOAuth({
      provider: 'google',
      options: { redirectTo: window.location.origin },
    });
    console.log('[Google OAuth] data:', data, 'error:', error);
    if (error) return { data, error };
    if (!data?.url) return { data, error: { message: 'Google OAuth not configured in Supabase. Go to Supabase → Authentication → Providers → Google and enable it.' } };
    return { data, error };
  };

  const signInWithMagicLink = async (email) => {
    const { data, error } = await supabase.auth.signInWithOtp({
      email,
      options: { emailRedirectTo: window.location.origin },
    });
    return { data, error };
  };

  const signOut = async () => {
    try { await supabase.auth.signOut(); } catch (_) {}
    localStorage.removeItem('d2c_session');
    localStorage.removeItem('d2cflow_integrations');
    localStorage.setItem('d2c_signed_out', '1');
    window.location.reload();
  };

  return (
    <AuthContext.Provider value={{ user, session, loading, signUp, signIn, signInWithGoogle, signInWithMagicLink, signOut }}>
      {children}
    </AuthContext.Provider>
  );
}

export const useAuth = () => useContext(AuthContext);
