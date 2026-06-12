import axios from 'axios';

const BASE = import.meta.env.VITE_API_URL || 'http://localhost:8099';

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
      localStorage.removeItem('d2c_session');
      window.location.href = '/login';
    }
    return Promise.reject(err);
  }
);
