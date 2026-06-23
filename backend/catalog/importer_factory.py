"""
Credential-loading helper for catalog importers.
Reads per-tenant channel credentials from the channel_credentials table
so importers don't have to fall back on global env vars.
"""
import json
from ..database import get_db


def get_creds(db, tenant_id: str, channel: str) -> dict:
    """
    Load channel credentials for a tenant from channel_credentials table.
    Raises ValueError if the channel is not connected for that tenant.
    """
    row = (
        db.table("channel_credentials")
        .select("credentials, connected")
        .eq("tenant_id", tenant_id)
        .eq("channel", channel)
        .maybe_single()
        .execute()
    )
    if not row.data or not row.data.get("connected"):
        raise ValueError(f"{channel} is not connected for this tenant")

    raw = row.data.get("credentials") or "{}"
    return json.loads(raw) if isinstance(raw, str) else raw


def get_importer(channel: str, tenant_id: str):
    """
    Return a ready-to-use importer for the given channel, loaded with
    per-tenant credentials. Falls back to global env vars if no tenant_id given.
    """
    db = get_db()

    if channel == "shopify":
        from .shopify_importer import ShopifyCatalogImporter
        creds = get_creds(db, tenant_id, "shopify") if tenant_id else None
        return ShopifyCatalogImporter(creds=creds)

    if channel == "amazon":
        from .amazon_importer import AmazonCatalogImporter
        creds = get_creds(db, tenant_id, "amazon") if tenant_id else None
        return AmazonCatalogImporter(creds=creds)

    if channel == "flipkart":
        from .flipkart_importer import FlipkartCatalogImporter
        creds = get_creds(db, tenant_id, "flipkart") if tenant_id else None
        return FlipkartCatalogImporter(creds=creds)

    raise ValueError(f"No importer available for channel: {channel}")
