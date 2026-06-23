"""
Manifest generation — auto-generate pickup manifests post-RTD marking.
Supports Shiprocket manifest + custom CSV export.
"""
import csv
import io
import logging
from datetime import datetime, timezone, date
from ..database import get_db
from ..config import get_settings
from ..automation.logger import log_event

logger = logging.getLogger(__name__)


class ManifestEngine:

    def generate_manifest(self, warehouse_id: str = None, courier: str = None) -> dict:
        db = get_db()
        q = (
            db.table("orders")
            .select("id, channel_order_id, channel, awb, courier, customer_name, customer_phone, pincode, state, total_amount, payment_mode, shiprocket_order_id, order_items(sku, name, qty)")
            .eq("status", "rtd")
            .not_.is_("awb", "null")
        )
        if warehouse_id:
            q = q.eq("warehouse_id", warehouse_id)
        if courier:
            q = q.eq("courier", courier)

        orders = q.execute().data

        if not orders:
            return {"status": "no_orders", "count": 0}

        manifest_id = f"MAN-{date.today().strftime('%Y%m%d')}-{len(orders)}"

        # Store manifest record
        manifest_data = {
            "manifest_id": manifest_id,
            "warehouse_id": warehouse_id,
            "courier": courier,
            "order_count": len(orders),
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "status": "generated",
        }
        db.table("manifests").insert(manifest_data).execute()

        # Try Shiprocket manifest generation
        sr_manifest_url = None
        sr_order_ids = [
            int(o["shiprocket_order_id"]) for o in orders
            if o.get("shiprocket_order_id") and o.get("courier", "").lower() != "delhivery"
        ]
        if sr_order_ids:
            try:
                sr_manifest_url = self._generate_shiprocket_manifest(sr_order_ids)
            except Exception as e:
                logger.warning(f"Shiprocket manifest generation failed: {e}")

        # Always generate CSV fallback
        csv_content = self._generate_csv_manifest(orders)

        log_event("manifest_generated", "system", manifest_id, "success",
                  f"{len(orders)} orders, courier={courier or 'all'}")

        return {
            "manifest_id": manifest_id,
            "order_count": len(orders),
            "shiprocket_manifest_url": sr_manifest_url,
            "csv_content": csv_content,
            "orders": [{"order_id": o["channel_order_id"], "awb": o["awb"], "courier": o["courier"]} for o in orders],
        }

    def _generate_shiprocket_manifest(self, order_ids: list[int]) -> str:
        from ..couriers.shiprocket import ShiprocketClient
        import httpx
        sr = ShiprocketClient()
        resp = httpx.post(
            "https://apiv2.shiprocket.in/v1/external/manifests/generate",
            headers=sr._headers(),
            json={"order_ids": order_ids},
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json().get("manifest_url", "")

    def _generate_csv_manifest(self, orders: list[dict]) -> str:
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow([
            "Manifest Date", "Order ID", "Channel", "AWB", "Courier",
            "Customer Name", "Phone", "Pincode", "State",
            "Amount", "Payment Mode", "Items"
        ])
        today = date.today().strftime("%d-%m-%Y")
        for o in orders:
            items_str = ", ".join(
                f"{i.get('name', i.get('sku', ''))} x{i.get('qty', 1)}"
                for i in (o.get("order_items") or [])
            )
            writer.writerow([
                today,
                o.get("channel_order_id", ""),
                o.get("channel", ""),
                o.get("awb", ""),
                o.get("courier", ""),
                o.get("customer_name", ""),
                o.get("customer_phone", ""),
                o.get("pincode", ""),
                o.get("state", ""),
                o.get("total_amount", 0),
                o.get("payment_mode", ""),
                items_str,
            ])
        return buf.getvalue()

    def list_manifests(self, warehouse_id: str = None) -> list:
        db = get_db()
        q = db.table("manifests").select("*").order("generated_at", desc=True).limit(50)
        if warehouse_id:
            q = q.eq("warehouse_id", warehouse_id)
        return q.execute().data
