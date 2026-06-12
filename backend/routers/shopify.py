"""
Shopify real-time integration.

OAuth flow (recommended):
  1. GET  /api/shopify/oauth/start?shop=yourstore.myshopify.com
       → returns redirect_url to Shopify's authorization screen
  2. User authorizes → Shopify redirects to /api/shopify/oauth/callback?code=...
  3. Backend exchanges code for access_token, stores connection, syncs orders
  4. Backend redirects browser to frontend (/#shopify-connected)

Manual token flow (fallback):
  POST /api/shopify/connect  {shop_domain, access_token}
"""

import hashlib
import hmac
import json
import logging
import secrets
from datetime import datetime, timezone
from typing import List, Optional

import httpx
from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from ..config import get_settings

router = APIRouter(prefix="/api/shopify", tags=["shopify"])
logger = logging.getLogger(__name__)

# In-memory store
_synced_orders: dict[str, list] = {}   # shop_domain → [order, ...]
_connections: dict[str, dict] = {}     # shop_domain → {access_token, shop_name, connected_at}
_oauth_states: dict[str, str] = {}     # state → shop_domain  (CSRF protection)

SCOPES = "read_orders,write_orders,read_products,write_products"

# ─────────────────────────────────────────────────────────────────── #
# OAuth flow
# ─────────────────────────────────────────────────────────────────── #

@router.get("/oauth/start")
async def oauth_start(shop: str):
    """
    Step 1: Build the Shopify authorization URL and return it to the frontend.
    Frontend opens this URL in a popup or redirect.
    """
    settings = get_settings()
    if not settings.shopify_client_id:
        raise HTTPException(status_code=500, detail="SHOPIFY_CLIENT_ID not set in .env")

    shop = shop.strip().lower()
    if not shop.endswith(".myshopify.com"):
        shop = f"{shop}.myshopify.com"

    state = secrets.token_hex(16)
    _oauth_states[state] = shop

    redirect_uri = f"{settings.app_base_url}/api/shopify/oauth/callback"
    url = (
        f"https://{shop}/admin/oauth/authorize"
        f"?client_id={settings.shopify_client_id}"
        f"&scope={SCOPES}"
        f"&redirect_uri={redirect_uri}"
        f"&state={state}"
    )
    return {"redirect_url": url, "shop": shop}


@router.get("/oauth/callback")
async def oauth_callback(code: str, shop: str, state: str, background_tasks: BackgroundTasks):
    """
    Step 2: Shopify redirects here after the user authorizes.
    Exchange code → access token, store connection, sync orders, redirect to frontend.
    """
    settings = get_settings()

    # CSRF check
    expected_shop = _oauth_states.pop(state, None)
    # Allow in dev if state not found (e.g. restarted server)
    if expected_shop and expected_shop != shop:
        raise HTTPException(status_code=400, detail="State mismatch — possible CSRF")

    # Exchange code for token
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            f"https://{shop}/admin/oauth/access_token",
            json={
                "client_id": settings.shopify_client_id,
                "client_secret": settings.shopify_client_secret,
                "code": code,
            },
        )
        if resp.status_code != 200:
            logger.error(f"Token exchange failed: {resp.text}")
            raise HTTPException(status_code=400, detail=f"Token exchange failed: {resp.status_code}")
        token_data = resp.json()

    access_token = token_data.get("access_token")
    if not access_token:
        raise HTTPException(status_code=400, detail="No access_token in Shopify response")

    # Fetch shop info
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(
            f"https://{shop}/admin/api/2024-01/shop.json",
            headers={"X-Shopify-Access-Token": access_token},
        )
        shop_info = r.json().get("shop", {}) if r.status_code == 200 else {}

    # Store connection
    _connections[shop] = {
        "shop_domain": shop,
        "access_token": access_token,
        "shop_name": shop_info.get("name", shop),
        "email": shop_info.get("email", ""),
        "currency": shop_info.get("currency", "INR"),
        "connected_at": datetime.now(timezone.utc).isoformat(),
    }

    # Background: register webhooks + sync orders
    background_tasks.add_task(_register_webhooks, shop, access_token, settings.app_base_url)
    background_tasks.add_task(_sync_orders_bg, shop, access_token)

    logger.info(f"Shopify OAuth complete for {shop} ({shop_info.get('name', '')})")

    # Redirect browser to frontend success page
    frontend = "http://localhost:5173"
    return RedirectResponse(url=f"{frontend}/#shopify-connected?shop={shop}&name={shop_info.get('name', shop)}")


# ─────────────────────────────────────────────────────────────────── #
# Helpers
# ─────────────────────────────────────────────────────────────────── #

def _shopify_headers(token: str) -> dict:
    return {"X-Shopify-Access-Token": token, "Content-Type": "application/json"}


def _normalise_order(raw: dict, shop_domain: str) -> dict:
    """Convert a raw Shopify order to our internal format."""
    customer = raw.get("billing_address") or raw.get("shipping_address") or {}
    name = raw.get("customer", {})
    customer_name = (
        f"{name.get('first_name', '')} {name.get('last_name', '')}".strip()
        or customer.get("name", "Unknown")
    )

    items = []
    for li in raw.get("line_items", []):
        items.append({
            "name": li.get("title", ""),
            "sku": li.get("sku") or "—",
            "ean": "—",
            "qty": li.get("quantity", 1),
            "price": float(li.get("price", 0)),
            "variant": li.get("variant_title") or "",
        })

    shipping_addr = raw.get("shipping_address") or {}

    return {
        "id": f"SHP-{raw['id']}",
        "shopify_id": str(raw["id"]),
        "shop_domain": shop_domain,
        "date": raw.get("created_at", "")[:10],
        "customer": customer_name,
        "phone": (raw.get("customer", {}) or {}).get("phone") or shipping_addr.get("phone") or "—",
        "city": shipping_addr.get("city", "—"),
        "state": shipping_addr.get("province", ""),
        "pincode": shipping_addr.get("zip", "—"),
        "channel": "shopify",
        "payment": "cod" if raw.get("payment_gateway", "").lower() == "cash on delivery" else "prepaid",
        "items": items,
        "total": float(raw.get("total_price", 0)),
        "status": _map_status(raw.get("fulfillment_status"), raw.get("financial_status")),
        "courier": None,
        "awb": None,
        "createdAt": raw.get("created_at", ""),
        "source": "shopify",
    }


def _map_status(fulfillment_status: Optional[str], financial_status: Optional[str]) -> str:
    if fulfillment_status == "fulfilled":
        return "shipped"
    if fulfillment_status == "partial":
        return "rtd"
    if financial_status == "refunded":
        return "cancelled"
    return "new"


async def _fetch_all_orders(shop_domain: str, access_token: str) -> List[dict]:
    """Pull last 250 orders from Shopify."""
    url = f"https://{shop_domain}/admin/api/2024-01/orders.json?limit=250&status=any"
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(url, headers=_shopify_headers(access_token))
        resp.raise_for_status()
        return resp.json().get("orders", [])


async def _register_webhooks(shop_domain: str, access_token: str, base_url: str):
    """Register Shopify webhooks for order events."""
    topics = [
        ("orders/create", f"{base_url}/api/shopify/webhook/orders/create"),
        ("orders/updated", f"{base_url}/api/shopify/webhook/orders/updated"),
        ("orders/cancelled", f"{base_url}/api/shopify/webhook/orders/cancelled"),
    ]
    url = f"https://{shop_domain}/admin/api/2024-01/webhooks.json"

    # List existing webhooks to avoid duplicates
    async with httpx.AsyncClient(timeout=15) as client:
        existing_resp = await client.get(url, headers=_shopify_headers(access_token))
        existing = {w["address"] for w in existing_resp.json().get("webhooks", [])}

        for topic, address in topics:
            if address in existing:
                logger.info(f"Webhook already exists: {topic}")
                continue
            payload = {"webhook": {"topic": topic, "address": address, "format": "json"}}
            r = await client.post(url, headers=_shopify_headers(access_token), json=payload)
            if r.status_code in (200, 201):
                logger.info(f"Registered webhook: {topic} → {address}")
            else:
                logger.warning(f"Failed to register webhook {topic}: {r.text}")


# ─────────────────────────────────────────────────────────────────── #
# Connect + sync
# ─────────────────────────────────────────────────────────────────── #

class ConnectPayload(BaseModel):
    shop_domain: str   # e.g. yourstore.myshopify.com
    access_token: str  # Admin API token from Shopify Partners / Custom App


@router.post("/connect")
async def connect_shopify(payload: ConnectPayload, background_tasks: BackgroundTasks):
    """
    Verify Shopify credentials, register webhooks, and kick off an initial order sync.
    No auth required — works in demo mode.
    """
    shop = payload.shop_domain.strip().lower()
    if not shop.endswith(".myshopify.com"):
        shop = f"{shop}.myshopify.com"

    # 1. Verify credentials
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(
                f"https://{shop}/admin/api/2024-01/shop.json",
                headers=_shopify_headers(payload.access_token),
            )
            r.raise_for_status()
            shop_info = r.json().get("shop", {})
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=400, detail=f"Shopify rejected credentials: {e.response.status_code}")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Could not reach Shopify: {str(e)}")

    # 2. Store connection
    _connections[shop] = {
        "shop_domain": shop,
        "access_token": payload.access_token,
        "shop_name": shop_info.get("name", shop),
        "email": shop_info.get("email", ""),
        "currency": shop_info.get("currency", "INR"),
        "connected_at": datetime.now(timezone.utc).isoformat(),
    }

    # 3. Register webhooks + pull existing orders in the background
    settings = get_settings()
    background_tasks.add_task(_register_webhooks, shop, payload.access_token, settings.app_base_url)
    background_tasks.add_task(_sync_orders_bg, shop, payload.access_token)

    return {
        "status": "connected",
        "shop_name": shop_info.get("name", shop),
        "shop_domain": shop,
        "email": shop_info.get("email"),
        "currency": shop_info.get("currency", "INR"),
        "plan": shop_info.get("plan_display_name", ""),
        "message": f"Connected to {shop_info.get('name', shop)}. Syncing orders in background…",
    }


async def _sync_orders_bg(shop: str, access_token: str):
    """Background task: fetch all orders and store in memory."""
    try:
        raw_orders = await _fetch_all_orders(shop, access_token)
        normalised = [_normalise_order(o, shop) for o in raw_orders]
        # Merge: keep existing webhook-delivered orders, add fetched ones (dedup by shopify_id)
        existing_ids = {o["shopify_id"] for o in _synced_orders.get(shop, [])}
        new_ones = [o for o in normalised if o["shopify_id"] not in existing_ids]
        _synced_orders.setdefault(shop, [])
        _synced_orders[shop] = normalised  # full replace on initial sync
        logger.info(f"Synced {len(normalised)} orders from {shop}")
    except Exception as e:
        logger.error(f"Order sync failed for {shop}: {e}")


# ─────────────────────────────────────────────────────────────────── #
# Manual sync + status
# ─────────────────────────────────────────────────────────────────── #

@router.post("/sync")
async def manual_sync(shop_domain: str):
    """Pull latest orders on demand."""
    shop = shop_domain.strip().lower()
    if shop not in _connections:
        raise HTTPException(status_code=404, detail="Shop not connected. Call /connect first.")
    conn = _connections[shop]
    raw_orders = await _fetch_all_orders(shop, conn["access_token"])
    normalised = [_normalise_order(o, shop) for o in raw_orders]
    _synced_orders[shop] = normalised
    return {"synced": len(normalised), "shop": shop}


@router.get("/status")
async def connection_status(shop_domain: str):
    """Check if a shop is connected and return stats."""
    shop = shop_domain.strip().lower()
    if shop not in _connections:
        return {"connected": False}
    conn = _connections[shop]
    orders = _synced_orders.get(shop, [])
    return {
        "connected": True,
        "shop_name": conn["shop_name"],
        "shop_domain": shop,
        "connected_at": conn["connected_at"],
        "order_count": len(orders),
        "new_count": sum(1 for o in orders if o["status"] == "new"),
    }


@router.get("/orders")
async def get_orders(shop_domain: str, status: Optional[str] = None, limit: int = 200):
    """Return all synced orders for a shop."""
    shop = shop_domain.strip().lower()
    if shop not in _connections:
        raise HTTPException(status_code=404, detail="Shop not connected.")
    orders = _synced_orders.get(shop, [])
    if status:
        orders = [o for o in orders if o["status"] == status]
    return {"orders": orders[:limit], "total": len(orders)}


@router.delete("/disconnect")
async def disconnect(shop_domain: str):
    shop = shop_domain.strip().lower()
    _connections.pop(shop, None)
    _synced_orders.pop(shop, None)
    return {"status": "disconnected", "shop": shop}


# ─────────────────────────────────────────────────────────────────── #
# Webhooks (Shopify → d2cflow)
# ─────────────────────────────────────────────────────────────────── #

def _verify_shopify_hmac(raw_body: bytes, hmac_header: str, secret: str) -> bool:
    """Verify that the webhook came from Shopify."""
    if not secret or not hmac_header:
        return True  # Skip verification in dev if secret not set
    digest = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).digest()
    import base64
    expected = base64.b64encode(digest).decode()
    return hmac.compare_digest(expected, hmac_header)


@router.post("/webhook/orders/create")
async def webhook_order_create(
    request: Request,
    x_shopify_shop_domain: str = Header(None),
    x_shopify_hmac_sha256: str = Header(None),
):
    raw_body = await request.body()
    settings = get_settings()

    if not _verify_shopify_hmac(raw_body, x_shopify_hmac_sha256 or "", settings.shopify_client_secret):
        raise HTTPException(status_code=401, detail="Invalid webhook signature")

    shop = (x_shopify_shop_domain or "").lower()
    try:
        order_data = json.loads(raw_body)
        normalised = _normalise_order(order_data, shop)

        _synced_orders.setdefault(shop, [])
        # Prepend new order (most recent first)
        existing_ids = {o["shopify_id"] for o in _synced_orders[shop]}
        if normalised["shopify_id"] not in existing_ids:
            _synced_orders[shop].insert(0, normalised)
            logger.info(f"New order from Shopify webhook: {normalised['id']} ({shop})")
    except Exception as e:
        logger.error(f"Webhook order/create processing error: {e}")

    return {"ok": True}


@router.post("/webhook/orders/updated")
async def webhook_order_updated(
    request: Request,
    x_shopify_shop_domain: str = Header(None),
    x_shopify_hmac_sha256: str = Header(None),
):
    raw_body = await request.body()
    settings = get_settings()

    if not _verify_shopify_hmac(raw_body, x_shopify_hmac_sha256 or "", settings.shopify_client_secret):
        raise HTTPException(status_code=401, detail="Invalid webhook signature")

    shop = (x_shopify_shop_domain or "").lower()
    try:
        order_data = json.loads(raw_body)
        updated = _normalise_order(order_data, shop)
        orders = _synced_orders.get(shop, [])
        for i, o in enumerate(orders):
            if o["shopify_id"] == updated["shopify_id"]:
                orders[i] = updated
                break
        else:
            _synced_orders.setdefault(shop, []).insert(0, updated)
        logger.info(f"Updated order from Shopify webhook: {updated['id']} ({shop})")
    except Exception as e:
        logger.error(f"Webhook order/updated processing error: {e}")

    return {"ok": True}


@router.post("/webhook/orders/cancelled")
async def webhook_order_cancelled(
    request: Request,
    x_shopify_shop_domain: str = Header(None),
):
    raw_body = await request.body()
    shop = (x_shopify_shop_domain or "").lower()
    try:
        order_data = json.loads(raw_body)
        shopify_id = str(order_data.get("id", ""))
        for o in _synced_orders.get(shop, []):
            if o["shopify_id"] == shopify_id:
                o["status"] = "cancelled"
                break
    except Exception as e:
        logger.error(f"Webhook order/cancelled processing error: {e}")
    return {"ok": True}
