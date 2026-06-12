"""
APScheduler-based job scheduler.
All automation jobs run here on defined intervals.
Starts automatically when the FastAPI app starts.
"""
import logging
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

logger = logging.getLogger(__name__)

scheduler = BackgroundScheduler(timezone="Asia/Kolkata")


# ------------------------------------------------------------------ #
# Job Definitions
# ------------------------------------------------------------------ #

def job_ingest_all_channels():
    """Pull orders from all channels every 30 minutes."""
    from .ingestion.shopify import ShopifyIngester
    from .ingestion.amazon import AmazonIngester
    from .ingestion.flipkart import FlipkartIngester
    from .ingestion.meesho import MeeshoIngester
    from .ingestion.myntra import MyntraIngester

    for IngesterClass in [ShopifyIngester, AmazonIngester, FlipkartIngester, MeeshoIngester, MyntraIngester]:
        try:
            result = IngesterClass().upsert_orders(since_hours=1)
            logger.info(f"[{IngesterClass.channel}] Ingestion: {result}")
        except Exception as e:
            logger.error(f"[{IngesterClass.channel}] Ingestion failed: {e}")


def job_run_order_automations():
    """Run all order automation rules every 30 minutes (after ingestion)."""
    from .automation.order_engine import OrderAutomationEngine
    try:
        OrderAutomationEngine().run_all()
    except Exception as e:
        logger.error(f"Order automation failed: {e}")


def job_auto_ship_rtd():
    """Auto-create Shiprocket shipments for RTD orders every hour."""
    from .couriers.shiprocket import ShiprocketClient
    try:
        ShiprocketClient().auto_ship_rtd_orders()
    except Exception as e:
        logger.error(f"Auto-ship RTD failed: {e}")


def job_process_ndrs():
    """Check NDRs from Shiprocket every 4 hours."""
    from .couriers.shiprocket import ShiprocketClient
    try:
        ShiprocketClient().process_ndrs()
    except Exception as e:
        logger.error(f"NDR processing failed: {e}")


def job_inventory_sync():
    """Sync inventory across all channels every hour."""
    from .automation.inventory_engine import InventoryEngine
    try:
        InventoryEngine().run_all()
    except Exception as e:
        logger.error(f"Inventory sync failed: {e}")


def job_returns_engine():
    """Process returns and file claims every 6 hours."""
    from .automation.returns_engine import ReturnsEngine
    try:
        engine = ReturnsEngine()
        engine.run_all()
        engine.file_courier_claims()
    except Exception as e:
        logger.error(f"Returns engine failed: {e}")


def job_daily_summary():
    """Send founder daily WhatsApp summary at 9am IST."""
    from .database import get_db
    from .config import get_settings
    from .notifications.whatsapp import WhatsAppNotifier
    from datetime import date
    db = get_db()
    s = get_settings()

    today = date.today().isoformat()
    summary_res = db.table("daily_summary").select("*").eq("date", today).execute()

    totals = {"date": today, "total_orders": 0, "gmv": 0, "dispatched": 0, "rto": 0, "fulfillment_rate": 0}
    for row in summary_res.data:
        totals["total_orders"] += row.get("total_orders", 0)
        totals["gmv"] += float(row.get("gmv", 0) or 0)
        totals["dispatched"] += row.get("delivered", 0)
        totals["rto"] += row.get("rto", 0)

    pending_rtd = db.table("orders").select("id", count="exact").eq("status", "rtd").execute()
    totals["pending_rtd"] = pending_rtd.count or 0
    if totals["total_orders"]:
        totals["fulfillment_rate"] = round(totals["dispatched"] / totals["total_orders"] * 100, 1)

    WhatsAppNotifier().send_founder_daily_summary(s.founder_whatsapp, totals)


def job_daily_error_digest():
    """Email founder error digest at 10pm IST."""
    from .database import get_db
    from .config import get_settings
    from .notifications.email import EmailNotifier
    from datetime import datetime, timezone, timedelta
    db = get_db()
    s = get_settings()

    since = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
    errors = (
        db.table("automation_logs")
        .select("event_type, entity_id, message")
        .eq("status", "failed")
        .gt("created_at", since)
        .execute()
    )
    if errors.data:
        EmailNotifier().send_daily_error_digest(s.founder_email, errors.data)


def job_weekly_stocktake_reminder():
    """Send stock-take reminder every Monday 9am IST."""
    from .automation.inventory_engine import InventoryEngine
    try:
        InventoryEngine().send_stocktake_reminder()
    except Exception as e:
        logger.error(f"Stock-take reminder failed: {e}")


# ------------------------------------------------------------------ #
# Schedule Registration
# ------------------------------------------------------------------ #

def start_scheduler():
    # Order ingestion — every 30 min
    scheduler.add_job(job_ingest_all_channels, IntervalTrigger(minutes=30), id="ingest_channels", replace_existing=True)

    # Order automations — 5 min after ingestion
    scheduler.add_job(job_run_order_automations, IntervalTrigger(minutes=30), id="order_automations",
                      replace_existing=True)

    # Auto-ship RTD — every hour at :15
    scheduler.add_job(job_auto_ship_rtd, CronTrigger(minute=15), id="auto_ship_rtd", replace_existing=True)

    # NDR processing — 4x/day
    scheduler.add_job(job_process_ndrs, CronTrigger(hour="6,12,18,22"), id="process_ndrs", replace_existing=True)

    # Inventory sync — every hour
    scheduler.add_job(job_inventory_sync, IntervalTrigger(hours=1), id="inventory_sync", replace_existing=True)

    # Returns + claims — every 6 hours
    scheduler.add_job(job_returns_engine, CronTrigger(hour="0,6,12,18"), id="returns_engine", replace_existing=True)

    # Daily summary — 9am IST
    scheduler.add_job(job_daily_summary, CronTrigger(hour=9, minute=0, timezone="Asia/Kolkata"),
                      id="daily_summary", replace_existing=True)

    # Error digest — 10pm IST
    scheduler.add_job(job_daily_error_digest, CronTrigger(hour=22, minute=0, timezone="Asia/Kolkata"),
                      id="error_digest", replace_existing=True)

    # Weekly stock-take — Monday 9am IST
    scheduler.add_job(job_weekly_stocktake_reminder, CronTrigger(day_of_week="mon", hour=9, minute=0, timezone="Asia/Kolkata"),
                      id="stocktake_reminder", replace_existing=True)

    scheduler.start()
    logger.info("Scheduler started with all jobs registered")


def stop_scheduler():
    scheduler.shutdown()
