"""
Analytics API — fulfillment metrics, profit-per-SKU, shipping delays, RTO tracking.
"""
from fastapi import APIRouter, Depends
from typing import Optional
from datetime import datetime, timezone, timedelta

from ..database import get_db
from ..middleware.auth import get_current_user

router = APIRouter(prefix="/api/analytics", tags=["analytics"])


@router.get("/fulfillment")
def fulfillment_metrics(
    days: int = 30,
    warehouse_id: Optional[str] = None,
    channel: Optional[str] = None,
    user=Depends(get_current_user),
):
    db = get_db()
    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

    q = db.table("orders").select(
        "id, status, channel, created_at, dispatched_at, warehouse_id, payment_mode, total_amount"
    ).gt("created_at", since)
    if channel:
        q = q.eq("channel", channel)
    if warehouse_id:
        q = q.eq("warehouse_id", warehouse_id)
    orders = q.execute().data

    total = len(orders)
    if total == 0:
        return {"total": 0, "fulfillment_rate": 0, "avg_dispatch_hours": None}

    dispatched = [o for o in orders if o["status"] in ("dispatched", "delivered")]
    delivered = [o for o in orders if o["status"] == "delivered"]
    rto = [o for o in orders if o["status"] == "rto"]
    cancelled = [o for o in orders if o["status"] == "cancelled"]

    # Avg dispatch time
    dispatch_times = []
    for o in dispatched:
        if o.get("dispatched_at") and o.get("created_at"):
            try:
                created = datetime.fromisoformat(o["created_at"].replace("Z", "+00:00"))
                dispatched_at = datetime.fromisoformat(o["dispatched_at"].replace("Z", "+00:00"))
                hours = (dispatched_at - created).total_seconds() / 3600
                if 0 < hours < 168:
                    dispatch_times.append(hours)
            except Exception:
                pass

    avg_dispatch_hours = round(sum(dispatch_times) / len(dispatch_times), 1) if dispatch_times else None

    # GMV
    gmv = sum(float(o.get("total_amount") or 0) for o in orders)
    cod_orders = [o for o in orders if o.get("payment_mode") == "cod"]

    # By channel
    channels: dict = {}
    for o in orders:
        ch = o.get("channel", "unknown")
        if ch not in channels:
            channels[ch] = {"total": 0, "dispatched": 0, "rto": 0, "gmv": 0}
        channels[ch]["total"] += 1
        if o["status"] in ("dispatched", "delivered"):
            channels[ch]["dispatched"] += 1
        if o["status"] == "rto":
            channels[ch]["rto"] += 1
        channels[ch]["gmv"] += float(o.get("total_amount") or 0)

    return {
        "period_days": days,
        "total_orders": total,
        "dispatched": len(dispatched),
        "delivered": len(delivered),
        "rto": len(rto),
        "cancelled": len(cancelled),
        "fulfillment_rate": round(len(dispatched) / total * 100, 1),
        "rto_rate": round(len(rto) / total * 100, 1),
        "avg_dispatch_hours": avg_dispatch_hours,
        "gmv": round(gmv, 2),
        "cod_orders": len(cod_orders),
        "cod_pct": round(len(cod_orders) / total * 100, 1),
        "by_channel": channels,
    }


@router.get("/profit-per-sku")
def profit_per_sku(
    limit: int = 50,
    sort_by: str = "profit",
    user=Depends(get_current_user),
):
    db = get_db()
    return (
        db.table("profit_per_sku")
        .select("*")
        .order(sort_by if sort_by in ("estimated_profit", "units_sold", "revenue") else "estimated_profit", desc=True)
        .limit(limit)
        .execute()
        .data
    )


@router.get("/shipping-delays")
def shipping_delays(days: int = 14, user=Depends(get_current_user)):
    db = get_db()
    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

    # Orders dispatched but not delivered after 7 days
    delayed_cutoff = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
    delayed = (
        db.table("orders")
        .select("id, channel_order_id, awb, courier, dispatched_at, pincode, state, customer_name")
        .eq("status", "dispatched")
        .lt("dispatched_at", delayed_cutoff)
        .execute()
        .data
    )

    # By courier breakdown
    by_courier: dict = {}
    for o in delayed:
        c = o.get("courier", "unknown")
        by_courier[c] = by_courier.get(c, 0) + 1

    return {
        "delayed_count": len(delayed),
        "by_courier": by_courier,
        "orders": delayed[:50],
    }


@router.get("/inventory-health")
def inventory_health(user=Depends(get_current_user)):
    db = get_db()
    inventory = db.table("inventory").select("sku, qty_on_hand, qty_reserved, qty_available, skus(name, category, reorder_qty)").execute().data

    out_of_stock = [i for i in inventory if (i.get("qty_available") or 0) <= 0]
    low_stock = [i for i in inventory if 0 < (i.get("qty_available") or 0) <= 10]
    healthy = [i for i in inventory if (i.get("qty_available") or 0) > 10]

    # Dead stock (from app_settings flags)
    dead_keys = db.table("app_settings").select("key").ilike("key", "dead_stock_%").execute().data
    dead_count = len(dead_keys)

    return {
        "total_skus": len(inventory),
        "out_of_stock": len(out_of_stock),
        "low_stock": len(low_stock),
        "healthy": len(healthy),
        "dead_stock_skus": dead_count,
        "out_of_stock_skus": [{"sku": i["sku"], "name": (i.get("skus") or {}).get("name")} for i in out_of_stock[:20]],
        "low_stock_skus": [{"sku": i["sku"], "qty": i["qty_available"], "name": (i.get("skus") or {}).get("name")} for i in low_stock[:20]],
    }


@router.get("/rto-analysis")
def rto_analysis(days: int = 30, user=Depends(get_current_user)):
    db = get_db()
    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

    rto_orders = (
        db.table("orders")
        .select("channel, pincode, state, payment_mode, courier, total_amount")
        .eq("status", "rto")
        .gt("created_at", since)
        .execute()
        .data
    )

    total_rto = len(rto_orders)
    by_pincode: dict = {}
    by_state: dict = {}
    by_courier: dict = {}
    cod_rto = 0

    for o in rto_orders:
        pc = o.get("pincode", "unknown")
        by_pincode[pc] = by_pincode.get(pc, 0) + 1

        st = o.get("state", "unknown")
        by_state[st] = by_state.get(st, 0) + 1

        cr = o.get("courier", "unknown")
        by_courier[cr] = by_courier.get(cr, 0) + 1

        if o.get("payment_mode") == "cod":
            cod_rto += 1

    top_pincodes = sorted(by_pincode.items(), key=lambda x: x[1], reverse=True)[:10]
    top_states = sorted(by_state.items(), key=lambda x: x[1], reverse=True)[:10]

    return {
        "period_days": days,
        "total_rto": total_rto,
        "cod_rto": cod_rto,
        "cod_rto_pct": round(cod_rto / total_rto * 100, 1) if total_rto else 0,
        "by_courier": by_courier,
        "top_rto_pincodes": [{"pincode": p, "count": c} for p, c in top_pincodes],
        "top_rto_states": [{"state": s, "count": c} for s, c in top_states],
    }


@router.get("/daily-trend")
def daily_trend(days: int = 30, user=Depends(get_current_user)):
    db = get_db()
    summary = (
        db.table("daily_summary")
        .select("*")
        .order("date", desc=False)
        .limit(days)
        .execute()
        .data
    )
    return summary
