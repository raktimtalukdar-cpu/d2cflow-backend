import axios from 'axios';

// Empty string = relative URLs — works when frontend is served by the same FastAPI server
const BASE = import.meta.env.VITE_API_URL || '';

export const api = axios.create({ baseURL: BASE });

// Attach Supabase JWT to every request
api.interceptors.request.use(cfg => {
  const session = JSON.parse(localStorage.getItem('d2c_session') || 'null');
  if (session?.access_token) {
    cfg.headers.Authorization = `Bearer ${session.access_token}`;
  }
  return cfg;
});

// Auto-logout on 401
api.interceptors.response.use(
  r => r,
  err => {
    if (err.response?.status === 401) {
      // Only force re-login if there's no active Supabase session
      // Otherwise it's a backend JWT config issue — don't create an infinite loop
      const session = localStorage.getItem('d2c_session');
      if (!session) {
        window.location.href = '/';
      }
    }
    return Promise.reject(err);
  }
);
