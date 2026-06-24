from typing import Optional
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import logging
import os

from .scheduler import start_scheduler, stop_scheduler
from .database import get_db
from .config import get_settings
from .routers.whatsapp import start_wa_automation, stop_wa_automation
from .middleware import RequestIDMiddleware, RateLimitMiddleware
from .monitoring import metrics
from .routers import auth as auth_router
from .routers import integrations as integrations_router
from .routers import invite as invite_router
from .routers import shopify as shopify_router
from .routers import whatsapp as whatsapp_router
from .routers import shiprocket as shiprocket_router
from .routers import payments as payments_router
from .routers import catalog as catalog_router
from .routers import listings as listings_router
from .routers import warehouses as warehouses_router
from .routers import returns as returns_router
from .routers import analytics as analytics_router
from .routers import contacts as contacts_router
from .routers import product_page as product_page_router
from .routers import integration_guides as guides_router

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting D2C Automation Engine...")
    start_scheduler()
    start_wa_automation()
    yield
    logger.info("Shutting down...")
    stop_wa_automation()
    stop_scheduler()


app = FastAPI(
    title="D2C Automation Engine",
    description="End-to-end automation for Indian D2C brands",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"], allow_credentials=True)
app.add_middleware(RequestIDMiddleware)
app.add_middleware(RateLimitMiddleware)

app.include_router(auth_router.router)
app.include_router(integrations_router.router)
app.include_router(invite_router.router)
app.include_router(shopify_router.router)
app.include_router(whatsapp_router.router)
app.include_router(shiprocket_router.router)
app.include_router(payments_router.router)
app.include_router(catalog_router.router)
app.include_router(listings_router.router)
app.include_router(warehouses_router.router)
app.include_router(returns_router.router)
app.include_router(analytics_router.router)
app.include_router(contacts_router.router)
app.include_router(product_page_router.router)
app.include_router(guides_router.router)

# ------------------------------------------------------------------ #
# Health
# ------------------------------------------------------------------ #

@app.get("/health")
def health():
    return {"status": "ok", "version": "1.0.0"}


@app.get("/health/detailed")
def health_detailed():
    from .routers.whatsapp import _monitored_chats, _detected_orders, _pending_broadcasts
    return {
        "status": "ok",
        "version": "1.0.0",
        "metrics": metrics.summary(),
        "whatsapp": {
            "monitored_chats": len(_monitored_chats),
            "detected_orders": len(_detected_orders),
            "pending_broadcasts": len(_pending_broadcasts),
        },
    }


# ------------------------------------------------------------------ #
# Manual Triggers (for testing / one-off runs)
# ------------------------------------------------------------------ #

@app.post("/trigger/ingest")
def trigger_ingest(channel: str = "all"):
    from .ingestion.shopify import ShopifyIngester
    from .ingestion.amazon import AmazonIngester
    from .ingestion.flipkart import FlipkartIngester
    from .ingestion.meesho import MeeshoIngester
    from .ingestion.myntra import MyntraIngester

    from .ingestion.ajio import AjioIngester
    from .ingestion.nykaa import NykaaIngester
    from .ingestion.snapdeal import SnapdealIngester
    from .ingestion.firstcry import FirstcryIngester

    ingesters = {
        "shopify": ShopifyIngester,
        "amazon": AmazonIngester,
        "flipkart": FlipkartIngester,
        "meesho": MeeshoIngester,
        "myntra": MyntraIngester,
        "ajio": AjioIngester,
        "nykaa": NykaaIngester,
        "snapdeal": SnapdealIngester,
        "firstcry": FirstcryIngester,
    }
    results = {}
    targets = ingesters.items() if channel == "all" else [(channel, ingesters.get(channel))]
    for name, cls in targets:
        if cls:
            try:
                results[name] = cls().upsert_orders(since_hours=24)
            except Exception as e:
                results[name] = {"error": str(e)}
    return results


@app.post("/trigger/auto-ship")
def trigger_auto_ship():
    from .couriers.shiprocket import ShiprocketClient
    ShiprocketClient().auto_ship_rtd_orders()
    return {"status": "ok"}


@app.post("/trigger/inventory-sync")
def trigger_inventory_sync():
    from .automation.inventory_engine import InventoryEngine
    InventoryEngine().run_all()
    return {"status": "ok"}


@app.post("/trigger/order-automations")
def trigger_order_automations():
    from .automation.order_engine import OrderAutomationEngine
    OrderAutomationEngine().run_all()
    return {"status": "ok"}


@app.post("/trigger/repricing")
def trigger_repricing():
    from .automation.repricing_engine import RepricingEngine
    RepricingEngine().run_all()
    return {"status": "ok"}


@app.post("/trigger/cod-zones")
def trigger_cod_zones():
    from .automation.cod_zone_engine import CODZoneEngine
    CODZoneEngine().run_all()
    return {"status": "ok"}


@app.post("/trigger/listing-sync")
def trigger_listing_sync():
    from .listings.engine import ListingEngine
    engine = ListingEngine()
    engine.detect_deactivated_listings()
    engine.sync_prices_to_channels()
    return {"status": "ok"}


@app.post("/trigger/generate-manifest")
def trigger_generate_manifest(warehouse_id: Optional[str] = None):
    from .automation.manifest_engine import ManifestEngine
    return ManifestEngine().generate_manifest(warehouse_id=warehouse_id)


@app.post("/trigger/catalog-import")
def trigger_catalog_import(channel: str = "all"):
    from .catalog.shopify_importer import ShopifyCatalogImporter
    from .catalog.amazon_importer import AmazonCatalogImporter
    from .catalog.flipkart_importer import FlipkartCatalogImporter

    importers = {
        "shopify": ShopifyCatalogImporter,
        "amazon": AmazonCatalogImporter,
        "flipkart": FlipkartCatalogImporter,
    }
    results = {}
    targets = importers.items() if channel == "all" else [(channel, importers.get(channel))]
    for name, cls in targets:
        if cls:
            try:
                results[name] = cls().import_all()
            except Exception as e:
                results[name] = {"error": str(e)}
    return results


@app.post("/trigger/sku-mapping")
def trigger_sku_mapping():
    from .catalog.sku_mapper import SKUMapper
    return SKUMapper().bulk_map_unmapped_orders()


# ------------------------------------------------------------------ #
# Demo mode — active when SUPABASE_URL is not set
# ------------------------------------------------------------------ #

def _is_demo() -> bool:
    return not get_settings().supabase_url


_DEMO_CHANNELS = ["shopify", "amazon", "flipkart", "meesho", "myntra"]
_DEMO_SKUS = [
    {"sku": "KRT-BL-M", "name": "Blue Cotton Kurta (M)", "category": "Apparel"},
    {"sku": "KRT-RD-L", "name": "Red Silk Kurta (L)",   "category": "Apparel"},
    {"sku": "DUP-WH-F", "name": "White Cotton Dupatta", "category": "Accessories"},
    {"sku": "PLZ-GR-S", "name": "Green Palazzo (S)",    "category": "Apparel"},
    {"sku": "BAG-BK-1", "name": "Black Tote Bag",       "category": "Bags"},
]

def _demo_daily():
    from datetime import date, timedelta
    import random
    rows = []
    channels = _DEMO_CHANNELS
    for d in range(30):
        day = (date.today() - timedelta(days=d)).isoformat()
        for ch in channels:
            orders  = random.randint(8, 60)
            rto     = random.randint(1, max(1, orders // 8))
            delivered = random.randint(orders // 2, orders)
            rows.append({
                "date": day, "channel": ch,
                "total_orders": orders,
                "gmv": round(orders * random.uniform(400, 1200), 2),
                "rto": rto,
                "delivered": delivered,
            })
    return rows

def _demo_orders(status=None, channel=None, limit=50):
    import random, uuid
    from datetime import datetime, timedelta, timezone
    statuses = ["confirmed", "rtd", "dispatched", "delivered", "rto", "cancelled"]
    couriers = ["Delhivery", "Shiprocket", "BlueDart", "Ecom Express"]
    names    = ["Priya Sharma", "Rahul Gupta", "Anjali Patel", "Vikram Singh", "Nisha Reddy",
                "Arjun Kumar", "Sneha Joshi", "Rohan Mehta", "Kavya Nair", "Amit Verma"]
    pincodes = ["110001", "400001", "560001", "500001", "600001", "700001", "380001", "302001"]
    states   = ["Delhi", "Maharashtra", "Karnataka", "Telangana", "Tamil Nadu", "West Bengal", "Gujarat", "Rajasthan"]
    orders   = []
    for i in range(min(limit, 80)):
        ch  = channel or _DEMO_CHANNELS[i % len(_DEMO_CHANNELS)]
        st  = status or statuses[i % len(statuses)]
        idx = i % len(names)
        pc  = pincodes[i % len(pincodes)]
        created = (datetime.now(timezone.utc) - timedelta(hours=i * 3)).isoformat()
        orders.append({
            "id": str(uuid.uuid4()),
            "channel_order_id": f"{ch.upper()[:3]}-{100000 + i}",
            "channel": ch,
            "status": st,
            "payment_mode": "cod" if i % 3 == 0 else "prepaid",
            "customer_name": names[idx],
            "customer_phone": f"98{random.randint(10000000, 99999999)}",
            "pincode": pc,
            "state": states[i % len(states)],
            "total_amount": round(random.uniform(299, 2499), 2),
            "awb": f"DEL{random.randint(1000000, 9999999)}" if st in ("dispatched", "delivered") else None,
            "courier": couriers[i % len(couriers)] if st in ("dispatched", "delivered") else None,
            "created_at": created,
        })
    return orders

def _demo_inventory():
    import random
    rows = []
    for sku in _DEMO_SKUS:
        on_hand  = random.randint(5, 200)
        reserved = random.randint(0, min(on_hand, 30))
        rows.append({
            "sku": sku["sku"],
            "qty_on_hand": on_hand,
            "qty_reserved": reserved,
            "qty_available": on_hand - reserved,
            "skus": {"name": sku["name"], "category": sku["category"]},
        })
    return rows

def _demo_profit():
    import random
    rows = []
    for sku in _DEMO_SKUS:
        units = random.randint(30, 300)
        revenue = round(units * random.uniform(400, 1200), 2)
        cogs    = round(revenue * random.uniform(0.30, 0.50), 2)
        fees    = round(revenue * random.uniform(0.08, 0.18), 2)
        ship    = round(units * random.uniform(40, 80), 2)
        profit  = round(revenue - cogs - fees - ship, 2)
        rows.append({
            "sku": sku["sku"],
            "name": sku["name"],
            "units_sold": units,
            "gross_revenue": revenue,
            "total_cogs": cogs,
            "total_marketplace_fees": fees,
            "total_shipping": ship,
            "estimated_profit": profit,
        })
    return sorted(rows, key=lambda r: r["estimated_profit"], reverse=True)

def _demo_logs():
    from datetime import datetime, timedelta, timezone
    events = [
        ("ingestion_complete", "order",  "shopify",  "success", "inserted=12 updated=3 errors=0"),
        ("rtd_flagged",        "order",  "FK-100042", "success", "Order auto-flagged RTD after 24h"),
        ("shipment_created",   "order",  "AMZ-99871", "success", "AWB=DEL7654321 Courier=Delhivery"),
        ("low_stock_alert_sent","sku",   "KRT-BL-M",  "success", "qty=4"),
        ("po_generated",       "sku",    "KRT-RD-L",  "success", "PO PO-KRT-RD-L-20260622"),
        ("ingestion_complete", "order",  "amazon",    "success", "inserted=8 updated=1 errors=0"),
        ("awb_pushed",         "order",  "MSH-88231", "success", "AWB DEL123 pushed to meesho"),
        ("cod_confirmation_sent","order","FK-100039", "success", ""),
        ("ingestion_error",    "order",  "myntra",    "failed",  "ConnectionError: timeout after 30s"),
        ("rto_hotspot_alert",  "system", "pincode_analysis","success",""),
    ]
    rows = []
    for i, (ev, et, eid, st, msg) in enumerate(events):
        rows.append({
            "id": str(i + 1),
            "event_type": ev,
            "entity_type": et,
            "entity_id": eid,
            "status": st,
            "message": msg,
            "created_at": (datetime.now(timezone.utc) - timedelta(minutes=i * 18)).isoformat(),
        })
    return rows


# ------------------------------------------------------------------ #
# Dashboard API
# ------------------------------------------------------------------ #

@app.get("/api/dashboard/summary")
def dashboard_summary():
    if _is_demo():
        daily = _demo_daily()
        hotspots = [
            {"pincode": "110032", "state": "Delhi",       "total_orders": 28, "rto_rate_pct": 46},
            {"pincode": "400063", "state": "Maharashtra", "total_orders": 19, "rto_rate_pct": 37},
            {"pincode": "500072", "state": "Telangana",   "total_orders": 14, "rto_rate_pct": 31},
            {"pincode": "600091", "state": "Tamil Nadu",  "total_orders": 11, "rto_rate_pct": 28},
        ]
        return {"daily": daily, "pending_rtd": 7, "rto_hotspots": hotspots, "demo": True}

    db = get_db()
    summary     = db.table("daily_summary").select("*").order("date", desc=True).limit(30).execute()
    pending_rtd = db.table("orders").select("id", count="exact").eq("status", "rtd").execute()
    rto_hotspots = db.table("rto_hotspots").select("*").limit(10).execute()
    return {"daily": summary.data, "pending_rtd": pending_rtd.count, "rto_hotspots": rto_hotspots.data}


@app.get("/api/dashboard/profit")
def dashboard_profit():
    if _is_demo():
        return _demo_profit()
    db = get_db()
    return db.table("profit_per_sku").select("*").order("estimated_profit", desc=True).execute().data


@app.get("/api/orders")
def list_orders(status: Optional[str] = None, channel: Optional[str] = None, limit: int = 50):
    if _is_demo():
        orders = _demo_orders(status=status, channel=channel, limit=limit)
        return orders
    db = get_db()
    q = db.table("orders").select("*").order("created_at", desc=True).limit(limit)
    if status:
        q = q.eq("status", status)
    if channel:
        q = q.eq("channel", channel)
    return q.execute().data


@app.get("/api/inventory")
def list_inventory():
    if _is_demo():
        return _demo_inventory()
    db = get_db()
    return db.table("inventory").select("*, skus(name, category)").execute().data


@app.get("/api/logs")
def list_logs(limit: int = 100, status: Optional[str] = None):
    if _is_demo():
        logs = _demo_logs()
        if status:
            logs = [l for l in logs if l["status"] == status]
        return logs[:limit]
    db = get_db()
    q = db.table("automation_logs").select("*").order("created_at", desc=True).limit(limit)
    if status:
        q = q.eq("status", status)
    return q.execute().data


@app.get("/api/pos")
def list_pos(status: Optional[str] = None):
    db = get_db()
    q = db.table("purchase_orders").select("*").order("created_at", desc=True)
    if status:
        q = q.eq("status", status)
    return q.execute().data


@app.patch("/api/pos/{po_id}/status")
def update_po_status(po_id: str, status: str):
    db = get_db()
    db.table("purchase_orders").update({"status": status}).eq("id", po_id).execute()
    return {"status": "updated"}


# Serve frontend dashboard
frontend_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "frontend")
frontend_path = os.path.normpath(frontend_path)
if os.path.exists(frontend_path):
    logger.info(f"Serving frontend from {frontend_path}")
    app.mount("/", StaticFiles(directory=frontend_path, html=True), name="frontend")
else:
    logger.warning(f"Frontend directory not found at {frontend_path} — dashboard will not be served")
