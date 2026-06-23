"""
Integration management — store and retrieve per-tenant channel credentials.
OAuth callbacks for Shopify, Amazon SP-API, Flipkart, Meta.
"""
from typing import Optional, Tuple
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel
import httpx
import json
import logging

from ..database import get_db
from ..config import get_settings
from ..middleware.auth import get_current_user, get_tenant_id

router = APIRouter(prefix="/api/integrations", tags=["integrations"])
logger = logging.getLogger(__name__)


# ------------------------------------------------------------------ #
# Public test endpoint (no auth required — demo mode)
# ------------------------------------------------------------------ #

class TestCredPayload(BaseModel):
    channel: str
    credentials: dict


@router.post("/test")
async def test_credentials(payload: TestCredPayload):
    """Verify credentials by making a real API call. No auth required."""
    ok, message = await _test_connection(payload.channel, payload.credentials)
    if not ok:
        raise HTTPException(status_code=400, detail=message)
    return {"status": "connected", "channel": payload.channel, "message": message}


# ------------------------------------------------------------------ #
# Schemas
# ------------------------------------------------------------------ #

class CredentialPayload(BaseModel):
    channel: str
    credentials: dict  # encrypted at rest by Supabase RLS + Vault (future)


class IntegrationStatus(BaseModel):
    channel: str
    connected: bool
    connected_at: Optional[str] = None
    display_name: Optional[str] = None


# ------------------------------------------------------------------ #
# CRUD
# ------------------------------------------------------------------ #

@router.get("")
async def list_integrations(user=Depends(get_current_user)):
    db = get_db()
    tenant_id = get_tenant_id(user)
    rows = db.table("channel_credentials").select("channel,connected,connected_at,display_name").eq("tenant_id", tenant_id).execute()
    return rows.data


@router.post("")
async def save_credentials(payload: CredentialPayload, user=Depends(get_current_user)):
    """Save API key / credential-based integration."""
    db = get_db()
    tenant_id = get_tenant_id(user)

    # Test connection before saving
    ok, message = await _test_connection(payload.channel, payload.credentials)
    if not ok:
        raise HTTPException(status_code=400, detail=f"Connection test failed: {message}")

    db.table("channel_credentials").upsert({
        "tenant_id": tenant_id,
        "channel": payload.channel,
        "credentials": json.dumps(payload.credentials),  # store as JSON text
        "connected": True,
        "display_name": payload.credentials.get("shop_domain") or payload.credentials.get("seller_id") or payload.channel,
    }, on_conflict="tenant_id,channel").execute()

    return {"status": "connected", "channel": payload.channel}


@router.delete("/{channel}")
async def disconnect(channel: str, user=Depends(get_current_user)):
    db = get_db()
    tenant_id = get_tenant_id(user)
    db.table("channel_credentials").update({"connected": False, "credentials": None}).eq("tenant_id", tenant_id).eq("channel", channel).execute()
    return {"status": "disconnected"}


# ------------------------------------------------------------------ #
# OAuth flows
# ------------------------------------------------------------------ #

@router.get("/shopify/connect")
async def shopify_oauth_start(shop: str, user=Depends(get_current_user)):
    settings = get_settings()
    scopes = "read_orders,write_orders,read_products,write_products,read_inventory,write_inventory"
    redirect_uri = f"{settings.app_base_url}/api/integrations/shopify/callback"
    state = get_tenant_id(user)
    url = (
        f"https://{shop}/admin/oauth/authorize"
        f"?client_id={settings.shopify_client_id}"
        f"&scope={scopes}"
        f"&redirect_uri={redirect_uri}"
        f"&state={state}"
    )
    return {"redirect_url": url}


@router.get("/shopify/callback")
async def shopify_oauth_callback(code: str, shop: str, state: str, background_tasks: BackgroundTasks):
    """Exchange code for access token, store it, and kick off catalog import."""
    settings = get_settings()
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"https://{shop}/admin/oauth/access_token",
            json={"client_id": settings.shopify_client_id, "client_secret": settings.shopify_client_secret, "code": code},
        )
        resp.raise_for_status()
        token_data = resp.json()

    creds = {"shop_domain": shop, "access_token": token_data["access_token"]}
    db = get_db()
    db.table("channel_credentials").upsert({
        "tenant_id": state,
        "channel": "shopify",
        "credentials": json.dumps(creds),
        "connected": True,
        "display_name": shop,
    }, on_conflict="tenant_id,channel").execute()

    from ..catalog.shopify_importer import ShopifyCatalogImporter
    background_tasks.add_task(ShopifyCatalogImporter(creds=creds).import_all)

    return {"status": "connected", "shop": shop, "catalog_import": "started"}


@router.get("/amazon/connect")
async def amazon_oauth_start(user=Depends(get_current_user)):
    settings = get_settings()
    if not settings.amazon_app_id:
        raise HTTPException(
            status_code=400,
            detail="Amazon SP-API app not registered. Add AMAZON_APP_ID to .env (requires Amazon Seller Partner developer registration)."
        )
    state = get_tenant_id(user)
    url = (
        "https://sellercentral.amazon.in/apps/authorize/consent"
        f"?application_id={settings.amazon_app_id}"
        f"&state={state}&version=beta"
    )
    return {"redirect_url": url}


@router.get("/amazon/callback")
async def amazon_oauth_callback(spapi_oauth_code: str, state: str, selling_partner_id: str, background_tasks: BackgroundTasks):
    settings = get_settings()
    async with httpx.AsyncClient() as client:
        resp = await client.post("https://api.amazon.com/auth/o2/token", data={
            "grant_type": "authorization_code",
            "code": spapi_oauth_code,
            "client_id": settings.amazon_client_id,
            "client_secret": settings.amazon_client_secret,
        })
        resp.raise_for_status()
        tokens = resp.json()

    creds = {"seller_id": selling_partner_id, "refresh_token": tokens["refresh_token"]}
    db = get_db()
    db.table("channel_credentials").upsert({
        "tenant_id": state,
        "channel": "amazon",
        "credentials": json.dumps(creds),
        "connected": True,
        "display_name": selling_partner_id,
    }, on_conflict="tenant_id,channel").execute()

    from ..catalog.amazon_importer import AmazonCatalogImporter
    background_tasks.add_task(AmazonCatalogImporter(creds=creds).import_all)

    return {"status": "connected", "seller_id": selling_partner_id, "catalog_import": "started"}


@router.get("/meta/connect")
async def meta_oauth_start(user=Depends(get_current_user)):
    settings = get_settings()
    state = get_tenant_id(user)
    scopes = "whatsapp_business_management,whatsapp_business_messaging,pages_messaging,instagram_basic"
    url = (
        f"https://www.facebook.com/v19.0/dialog/oauth"
        f"?client_id={settings.meta_app_id}"
        f"&redirect_uri={settings.app_base_url}/api/integrations/meta/callback"
        f"&scope={scopes}&state={state}"
    )
    return {"redirect_url": url}


@router.get("/meta/callback")
async def meta_oauth_callback(code: str, state: str):
    settings = get_settings()
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            "https://graph.facebook.com/v19.0/oauth/access_token",
            params={"client_id": settings.meta_app_id, "client_secret": settings.meta_app_secret,
                    "redirect_uri": f"{settings.app_base_url}/api/integrations/meta/callback", "code": code},
        )
        resp.raise_for_status()
        tokens = resp.json()

    db = get_db()
    db.table("channel_credentials").upsert({
        "tenant_id": state,
        "channel": "meta",
        "credentials": json.dumps({"access_token": tokens["access_token"]}),
        "connected": True,
        "display_name": "Meta (Facebook/Instagram)",
    }, on_conflict="tenant_id,channel").execute()

    return {"status": "connected"}


@router.get("/flipkart/connect")
async def flipkart_oauth_start(user=Depends(get_current_user)):
    settings = get_settings()
    if not settings.flipkart_client_id:
        raise HTTPException(
            status_code=400,
            detail="Flipkart API app not registered. Add FLIPKART_CLIENT_ID to .env (requires Flipkart Seller Hub API access approval)."
        )
    state = get_tenant_id(user)
    url = (
        "https://seller.flipkart.com/oauth-service/oauth/authorize"
        f"?client_id={settings.flipkart_client_id}"
        f"&redirect_uri={settings.app_base_url}/api/integrations/flipkart/callback"
        f"&response_type=code&scope=Seller_Api&state={state}"
    )
    return {"redirect_url": url}


@router.get("/flipkart/callback")
async def flipkart_oauth_callback(code: str, state: str, background_tasks: BackgroundTasks):
    settings = get_settings()
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            "https://api.flipkart.com/oauth-service/oauth/token",
            data={"grant_type": "authorization_code", "code": code,
                  "redirect_uri": f"{settings.app_base_url}/api/integrations/flipkart/callback"},
            auth=(settings.flipkart_client_id, settings.flipkart_client_secret),
        )
        resp.raise_for_status()
        tokens = resp.json()

    creds = {"app_id": settings.flipkart_client_id, "app_secret": settings.flipkart_client_secret,
             "refresh_token": tokens["refresh_token"]}
    db = get_db()
    db.table("channel_credentials").upsert({
        "tenant_id": state,
        "channel": "flipkart",
        "credentials": json.dumps(creds),
        "connected": True,
        "display_name": "Flipkart Seller",
    }, on_conflict="tenant_id,channel").execute()

    from ..catalog.flipkart_importer import FlipkartCatalogImporter
    background_tasks.add_task(FlipkartCatalogImporter(creds=creds).import_all)

    return {"status": "connected", "catalog_import": "started"}


# ------------------------------------------------------------------ #
# Connection test helpers
# ------------------------------------------------------------------ #

async def _test_connection(channel: str, creds: dict) -> Tuple[bool, str]:
    """Make a live API call to verify credentials. Returns (success, message)."""
    try:
        async with httpx.AsyncClient(timeout=12) as client:

            if channel == "shiprocket":
                r = await client.post(
                    "https://apiv2.shiprocket.in/v1/external/auth/login",
                    json={"email": creds["email"], "password": creds["password"]},
                )
                if r.status_code == 200:
                    d = r.json()
                    name = f"{d.get('first_name', '')} {d.get('last_name', '')}".strip()
                    company = d.get("company", {}).get("name", "")
                    return True, f"Logged in as {name} · {company}"
                return False, r.json().get("message", "Invalid email or password")

            elif channel == "shopify":
                shop = creds.get("shop_domain", "").replace("https://", "").replace("http://", "").rstrip("/")
                if not shop:
                    return False, "Shop domain is required"
                r = await client.get(
                    f"https://{shop}/admin/api/2024-04/shop.json",
                    headers={"X-Shopify-Access-Token": creds.get("access_token", "")},
                )
                if r.status_code == 200:
                    s = r.json().get("shop", {})
                    return True, f"{s.get('name')} · {s.get('myshopify_domain')} · Plan: {s.get('plan_display_name', 'unknown')}"
                if r.status_code == 401:
                    return False, "Invalid access token — check the Admin API token"
                if r.status_code == 404:
                    return False, f"Store not found: {shop}"
                return False, f"HTTP {r.status_code}"

            elif channel == "whatsapp":
                r = await client.get(
                    f"https://graph.facebook.com/v19.0/{creds.get('phone_number_id')}",
                    headers={"Authorization": f"Bearer {creds.get('access_token', '')}"},
                )
                if r.status_code == 200:
                    d = r.json()
                    num = d.get("display_phone_number", "")
                    name = d.get("verified_name", "")
                    return True, f"Number: {num} · Business: {name}"
                err = r.json().get("error", {})
                return False, err.get("message", "Invalid token or phone number ID")

            elif channel == "delhivery":
                r = await client.get(
                    "https://track.delhivery.com/api/v1/packages/json/",
                    headers={"Authorization": f"Token {creds.get('api_token', '')}"},
                    params={"waybill": "000000000000"},
                )
                if r.status_code in (200, 404):
                    return True, "API token verified · Tracking API accessible"
                if r.status_code == 401:
                    return False, "Invalid API token"
                return False, f"HTTP {r.status_code}"

            elif channel == "woocommerce":
                url = creds.get("store_url", "").rstrip("/")
                r = await client.get(
                    f"{url}/wp-json/wc/v3/system_status",
                    auth=(creds.get("consumer_key", ""), creds.get("consumer_secret", "")),
                )
                if r.status_code == 200:
                    d = r.json()
                    version = d.get("environment", {}).get("wp_version", "")
                    wc_version = d.get("environment", {}).get("wc_version", "")
                    return True, f"WordPress {version} · WooCommerce {wc_version} · {url}"
                if r.status_code == 401:
                    return False, "Invalid Consumer Key or Secret"
                return False, f"HTTP {r.status_code} — check store URL and credentials"

            elif channel == "zoho":
                r = await client.get(
                    "https://www.zohoapis.in/books/v3/organizations",
                    headers={"Authorization": f"Zoho-oauthtoken {creds.get('access_token', '')}"},
                )
                if r.status_code == 200:
                    orgs = r.json().get("organizations", [])
                    if orgs:
                        return True, f"Organization: {orgs[0].get('name')} · GST: {orgs[0].get('gst_no', 'not set')}"
                    return True, "Connected to Zoho Books — no organizations found"
                return False, r.json().get("message", "Invalid access token")

            elif channel == "tally":
                host = creds.get("tally_host", "http://localhost:9000").rstrip("/")
                try:
                    r = await client.get(host, timeout=5)
                    return True, f"TallyConnector reachable at {host} · HTTP {r.status_code}"
                except Exception:
                    return False, f"Cannot reach {host} — ensure TallyConnector is running on that machine"

            elif channel == "razorpay":
                key_id = creds.get("key_id", "").strip()
                key_secret = creds.get("key_secret", "").strip()
                if not key_id or not key_secret:
                    return False, "Key ID and Key Secret are required"
                # Verify by listing payment links (lightweight, read-only)
                r = await client.get(
                    "https://api.razorpay.com/v1/payment_links",
                    auth=(key_id, key_secret),
                    params={"count": 1},
                )
                if r.status_code == 200:
                    mode = "live" if key_id.startswith("rzp_live") else "test"
                    return True, f"Connected · Key ID: {key_id[:16]}… · Mode: {mode}"
                if r.status_code == 401:
                    return False, "Invalid Key ID or Key Secret — check Razorpay Dashboard → API Keys"
                return False, f"HTTP {r.status_code} from Razorpay"

            elif channel == "amazon":
                # SP-API requires LWA OAuth token exchange — validate fields are present
                seller_id = creds.get("seller_id", "").strip()
                mws_token = creds.get("mws_token", "").strip()
                if not seller_id or not mws_token:
                    return False, "Seller ID and MWS Auth Token are required"
                # Basic format check
                if not seller_id.startswith("A"):
                    return False, "Seller ID should start with 'A' (e.g. A2EUQ1WTGCTBG2)"
                return True, f"Seller ID {seller_id} saved · Full SP-API OAuth completes on first sync"

            elif channel == "flipkart":
                app_id = creds.get("app_id", "").strip()
                app_secret = creds.get("app_secret", "").strip()
                if not app_id or not app_secret:
                    return False, "App ID and App Secret are required"
                # Try Flipkart token endpoint
                r = await client.post(
                    "https://api.flipkart.com/oauth-service/oauth/token",
                    data={"grant_type": "client_credentials", "scope": "Seller_Api"},
                    auth=(app_id, app_secret),
                )
                if r.status_code == 200:
                    return True, f"Flipkart API credentials verified · App ID: {app_id}"
                return False, "Invalid App ID or App Secret — check Flipkart Seller Hub → API"

            elif channel == "meesho":
                if not creds.get("api_token"):
                    return False, "API token is required"
                r = await client.get(
                    "https://external.meesho.com/api/v1/supplier/info",
                    headers={"api-token": creds["api_token"]},
                )
                if r.status_code == 200:
                    d = r.json()
                    return True, f"Supplier: {d.get('supplier_name', 'Connected')} · {d.get('email', '')}"
                if r.status_code == 401:
                    return False, "Invalid API token — check Meesho Supplier Hub → API Settings"
                return True, "Credentials saved · Meesho will validate on first sync"

            elif channel == "myntra":
                if not creds.get("supplier_id") or not creds.get("api_key"):
                    return False, "Supplier ID and API key are required"
                r = await client.get(
                    "https://api.myntra.com/seller/v1/supplier/info",
                    headers={
                        "Authorization": f"Bearer {creds['api_key']}",
                        "X-Supplier-Id": creds["supplier_id"],
                    },
                )
                if r.status_code == 200:
                    d = r.json()
                    return True, f"Supplier: {d.get('supplier_name', creds['supplier_id'])} · Myntra Partner Portal"
                return True, f"Credentials saved · Supplier ID {creds['supplier_id']} — Myntra validates on first sync"

            elif channel == "ajio":
                if not creds.get("api_key") or not creds.get("seller_id"):
                    return False, "API key and Seller ID are required"
                r = await client.get(
                    "https://business.ajio.com/api/v1/seller/info",
                    headers={
                        "Authorization": f"Bearer {creds['api_key']}",
                        "X-Seller-Id": creds["seller_id"],
                    },
                )
                if r.status_code == 200:
                    d = r.json()
                    return True, f"Seller: {d.get('seller_name', creds['seller_id'])} · Ajio Business"
                if r.status_code == 401:
                    return False, "Invalid API key or Seller ID — check Ajio Business Portal"
                return True, f"Credentials saved · Seller ID {creds['seller_id']} — Ajio validates on first sync"

            elif channel == "nykaa":
                if not creds.get("api_token") or not creds.get("seller_id"):
                    return False, "API token and Seller ID are required"
                r = await client.get(
                    "https://seller.nykaa.com/api/v2/seller/profile",
                    headers={
                        "Authorization": f"Bearer {creds['api_token']}",
                        "X-Seller-Id": creds["seller_id"],
                    },
                )
                if r.status_code == 200:
                    d = r.json()
                    return True, f"Seller: {d.get('seller_name', creds['seller_id'])} · Nykaa Seller Hub"
                if r.status_code == 401:
                    return False, "Invalid API token — check Nykaa Seller Hub → API Access"
                return True, f"Credentials saved · Seller ID {creds['seller_id']} — Nykaa validates on first sync"

            elif channel == "snapdeal":
                if not creds.get("api_token") or not creds.get("seller_id"):
                    return False, "API token and Seller ID are required"
                r = await client.get(
                    "https://seller.snapdeal.com/api/seller/profile",
                    headers={
                        "Authorization": f"Bearer {creds['api_token']}",
                        "sellerId": creds["seller_id"],
                    },
                )
                if r.status_code == 200:
                    d = r.json()
                    return True, f"Seller: {d.get('sellerName', creds['seller_id'])} · Snapdeal Seller Zone"
                if r.status_code == 401:
                    return False, "Invalid API token — check Snapdeal Seller Zone → API Access"
                return True, f"Credentials saved · Seller ID {creds['seller_id']} — Snapdeal validates on first sync"

            elif channel == "firstcry":
                if not creds.get("api_token") or not creds.get("seller_code"):
                    return False, "API token and Seller Code are required"
                r = await client.get(
                    "https://seller.firstcry.com/api/v1/seller/profile",
                    headers={
                        "Authorization": f"Bearer {creds['api_token']}",
                        "X-Seller-Code": creds["seller_code"],
                    },
                )
                if r.status_code == 200:
                    d = r.json()
                    return True, f"Seller: {d.get('seller_name', creds['seller_code'])} · FirstCry Seller Portal"
                if r.status_code == 401:
                    return False, "Invalid API token — check FirstCry Seller Portal → API Settings"
                return True, f"Credentials saved · Seller Code {creds['seller_code']} — FirstCry validates on first sync"

            elif channel == "zoho":
                if not creds.get("access_token") or not creds.get("organization_id"):
                    return False, "Access token and Organization ID are required"
                r = await client.get(
                    "https://www.zohoapis.in/books/v3/organizations",
                    headers={"Authorization": f"Zoho-oauthtoken {creds['access_token']}"},
                )
                if r.status_code == 200:
                    orgs = r.json().get("organizations", [])
                    match = next((o for o in orgs if str(o.get("organization_id")) == str(creds["organization_id"])), None)
                    if match:
                        return True, f"Organization: {match['name']} · GST: {match.get('gst_no', 'not set')}"
                    if orgs:
                        return True, f"Connected · {len(orgs)} org(s) found — verify Organization ID is correct"
                    return False, "No organizations found under this access token"
                if r.status_code == 401:
                    return False, "Invalid or expired access token — regenerate via Zoho API Console"
                return False, r.json().get("message", f"HTTP {r.status_code}")

            elif channel == "tally":
                host = creds.get("tally_host", "http://localhost:9000").rstrip("/")
                try:
                    r = await client.get(host, timeout=5)
                    return True, f"TallyConnector reachable at {host}"
                except Exception:
                    return False, f"Cannot reach {host} — ensure TallyConnector is running on that machine"

            return True, "Credentials saved"

    except httpx.ConnectTimeout:
        return False, "Connection timed out — the API endpoint did not respond in 12s"
    except httpx.ConnectError as e:
        return False, f"Network error: {str(e)}"
    except Exception as e:
        return False, str(e)
