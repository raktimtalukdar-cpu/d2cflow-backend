"""
Delhivery API wrapper — direct integration (alternative to Shiprocket aggregator).
"""
import httpx
import logging
from datetime import datetime, timezone
from ..config import get_settings
from ..database import get_db
from ..automation.logger import log_event

logger = logging.getLogger(__name__)

DELHIVERY_BASE = "https://track.delhivery.com/api"


class DelhiveryClient:

    def _headers(self):
        s = get_settings()
        return {
            "Authorization": f"Token {s.delhivery_api_token}",
            "Content-Type": "application/json",
        }

    def create_shipment(self, order: dict, items: list[dict], weight_kg: float = 0.5) -> dict:
        s = get_settings()
        addr = order.get("shipping_address") or {}

        shipment_data = {
            "format": "json",
            "data": {
                "shipments": [{
                    "waybill": "",  # auto-assigned
                    "name": order.get("customer_name", ""),
                    "add": addr.get("address1") or addr.get("AddressLine1") or addr.get("address", ""),
                    "city": addr.get("city", ""),
                    "state": addr.get("state", ""),
                    "country": "India",
                    "pin": order.get("pincode", ""),
                    "phone": order.get("customer_phone", ""),
                    "order": order["channel_order_id"],
                    "payment_mode": "COD" if order.get("payment_mode") == "cod" else "Pre-paid",
                    "cod_amount": order.get("total_amount", 0) if order.get("payment_mode") == "cod" else 0,
                    "total_amount": order.get("total_amount", 0),
                    "weight": weight_kg,
                    "seller_name": s.delhivery_seller_name,
                    "seller_add": s.delhivery_pickup_address,
                    "seller_city": s.delhivery_pickup_city,
                    "seller_pin": s.delhivery_pickup_pincode,
                    "seller_state": s.delhivery_pickup_state,
                    "products_desc": ", ".join(i.get("name", i.get("sku", "")) for i in items[:3]),
                }],
                "pickup_location": {
                    "name": s.delhivery_pickup_location,
                },
            },
        }

        resp = httpx.post(
            f"{DELHIVERY_BASE}/cmu/create.json",
            headers=self._headers(),
            data={"format": "json", "data": str(shipment_data["data"])},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()

        packages = data.get("packages", [])
        if not packages:
            raise ValueError(f"Delhivery returned no package: {data}")

        pkg = packages[0]
        awb = pkg.get("waybill", "")
        log_event("shipment_created", "order", order["channel_order_id"], "success",
                  f"AWB={awb} Courier=Delhivery")

        return {
            "awb": awb,
            "courier": "Delhivery",
            "label_url": pkg.get("label_url", ""),
            "delhivery_ref": pkg.get("refnum", ""),
        }

    def track_awb(self, awb: str) -> dict:
        resp = httpx.get(
            f"{DELHIVERY_BASE}/v1/packages/json/",
            headers=self._headers(),
            params={"waybill": awb},
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        shipments = data.get("ShipmentData", [])
        if shipments:
            s = shipments[0].get("Shipment", {})
            return {
                "awb": awb,
                "status": s.get("Status", ""),
                "city": s.get("City", ""),
                "updated_at": s.get("StatusDateTime", ""),
            }
        return {"awb": awb, "status": "unknown"}

    def schedule_pickup(self, awbs: list[str], pickup_date: str) -> bool:
        s = get_settings()
        resp = httpx.post(
            f"{DELHIVERY_BASE}/p/edit",
            headers=self._headers(),
            json={
                "pickup_time": f"{pickup_date}T11:00:00",
                "pickup_location": s.delhivery_pickup_location,
                "expected_package_count": len(awbs),
                "awbs": awbs,
            },
            timeout=30,
        )
        resp.raise_for_status()
        log_event("pickup_scheduled", "shipment", str(awbs), "success",
                  f"Delhivery pickup on {pickup_date}")
        return True

    def get_ndr_list(self) -> list[dict]:
        resp = httpx.get(
            f"{DELHIVERY_BASE}/p/ndr/v2/list",
            headers=self._headers(),
            params={"filter_by": "Action Required", "limit": 100},
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json().get("results", [])

    def cancel_shipment(self, waybills: list[str]) -> bool:
        resp = httpx.post(
            f"{DELHIVERY_BASE}/p/edit",
            headers=self._headers(),
            json={"waybill": ",".join(waybills), "cancellation": True},
            timeout=30,
        )
        resp.raise_for_status()
        return True
