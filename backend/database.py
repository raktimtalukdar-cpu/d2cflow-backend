from supabase import create_client, Client
from .config import get_settings
from functools import lru_cache

# Fix SSL on macOS with uv-installed Python (no-op on Linux/Vercel)
try:
    import truststore
    truststore.inject_into_ssl()
except ImportError:
    pass


@lru_cache
def get_db() -> Client:
    s = get_settings()
    return create_client(s.supabase_url, s.supabase_service_key)
