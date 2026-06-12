from typing import Optional
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import logging
import os

from .scheduler import start_scheduler, stop_scheduler
from .database import get_db
from .config import get_settings
from .routers import auth as auth_router
from .routers import integrations as integrations_router
from .routers import invite as invite_router
from .routers import shopify as shopify_router

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting D2C Automation Engine...")
    start_scheduler()
    yield
    logger.info("Shutting down...")
    stop_scheduler()


app = FastAPI(
    title="D2C Automation Engine",
    description="End-to-end automation for Indian D2C brands",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"], allow_credentials=True)

app.include_router(auth_router.router)
app.include_router(integrations_router.router)
app.include_router(invite_router.router)
app.include_router(shopify_router.router)

# ------------------------------------------------------------------ #
# Health
# ------------------------------------------------------------------ #

@app.get("/health")
def health():
    return {"status": "ok", "version": "1.0.0"}


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

    ingesters = {
        "shopify": ShopifyIngester,
        "amazon": AmazonIngester,
        "flipkart": FlipkartIngester,
        "meesho": MeeshoIngester,
        "myntra": MyntraIngester,
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


# ------------------------------------------------------------------ #
# Dashboard API
# ------------------------------------------------------------------ #

@app.get("/api/dashboard/summary")
def dashboard_summary():
    db = get_db()
    summary = db.table("daily_summary").select("*").order("date", desc=True).limit(30).execute()
    pending_rtd = db.table("orders").select("id", count="exact").eq("status", "rtd").execute()
    rto_hotspots = db.table("rto_hotspots").select("*").limit(10).execute()
    return {
        "daily": summary.data,
        "pending_rtd": pending_rtd.count,
        "rto_hotspots": rto_hotspots.data,
    }


@app.get("/api/dashboard/profit")
def dashboard_profit():
    db = get_db()
    profit = db.table("profit_per_sku").select("*").order("estimated_profit", desc=True).execute()
    return profit.data


@app.get("/api/orders")
def list_orders(status: Optional[str] = None, channel: Optional[str] = None, limit: int = 50):
    db = get_db()
    q = db.table("orders").select("*").order("created_at", desc=True).limit(limit)
    if status:
        q = q.eq("status", status)
    if channel:
        q = q.eq("channel", channel)
    return q.execute().data


@app.get("/api/inventory")
def list_inventory():
    db = get_db()
    return db.table("inventory").select("*, skus(name, category)").execute().data


@app.get("/api/logs")
def list_logs(limit: int = 100, status: Optional[str] = None):
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
frontend_path = os.path.join(os.path.dirname(__file__), "..", "frontend")
if os.path.exists(frontend_path):
    app.mount("/", StaticFiles(directory=frontend_path, html=True), name="frontend")
