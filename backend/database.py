import ssl
import truststore
from supabase import create_client, Client
from .config import get_settings
from functools import lru_cache

# Use macOS system keychain for SSL — fixes uv-installed Python cert issues
truststore.inject_into_ssl()


@lru_cache
def get_db() -> Client:
    s = get_settings()
    return create_client(s.supabase_url, s.supabase_service_key)
