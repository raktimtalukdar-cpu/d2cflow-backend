"""
Tally integration via TallyConnector (local bridge that speaks XML to Tally).
TallyConnector must be running on the seller's machine/server (default port 9000).
Docs: https://tallyconnector.com/
"""
import httpx
import logging
from datetime import datetime
from ..config import get_settings
from ..automation.logger import log_event

logger = logging.getLogger(__name__)

# TallyConnector wraps Tally's XML gateway and exposes a REST API.
# For sellers who run Tally on-prem, the bridge URL is typically http://localhost:9000.


class TallyConnector:

    def _base(self) -> str:
        s = get_settings()
        return s.tally_host.rstrip("/")

    def _headers(self):
        return {"Content-Type": "application/json"}

    def health(self) -> bool:
        try:
            resp = httpx.get(self._base(), timeout=5)
            return resp.status_code < 500
        except Exception:
            return False

    # ------------------------------------------------------------------ #
    # Create sales voucher from an order
    # ------------------------------------------------------------------ #
    def create_sales_voucher(self, order: dict) -> dict:
        items = order.get("order_items", [])
        ledger_entries = []

        # Debit: party ledger (customer)
        ledger_entries.append({
            "ledger": order.get("customer_name", "Cash"),
            "amount": float(order.get("total_amount", 0)),
            "isDebit": True,
        })

        # Credit: sales ledger per item
        for item in items:
            ledger_entries.append({
                "ledger": "Sales",
                "amount": float(item.get("unit_price", 0)) * int(item.get("qty", 1)),
                "isDebit": False,
            })

        payload = {
            "voucherType": "Sales",
            "date": datetime.now().strftime("%Y%m%d"),
            "narration": f"Order {order.get('channel_order_id')} via {order.get('channel')}",
            "reference": order.get("channel_order_id", ""),
            "ledgerEntries": ledger_entries,
            "inventoryEntries": [
                {
                    "stockItem": item.get("name", item.get("sku", "")),
                    "quantity": int(item.get("qty", 1)),
                    "rate": float(item.get("unit_price", 0)),
                    "amount": float(item.get("unit_price", 0)) * int(item.get("qty", 1)),
                    "godown": "Main Location",
                }
                for item in items
            ],
        }

        resp = httpx.post(
            f"{self._base()}/vouchers",
            headers=self._headers(),
            json=payload,
            timeout=15,
        )
        resp.raise_for_status()
        result = resp.json()
        log_event("tally_voucher_created", "order", order.get("channel_order_id", ""), "success",
                  f"Voucher ID: {result.get('voucherId', '')}")
        return result

    # ------------------------------------------------------------------ #
    # Sync stock items to Tally
    # ------------------------------------------------------------------ #
    def sync_stock_items(self, skus: list[dict]) -> list:
        results = []
        for sku in skus:
            try:
                payload = {
                    "name": sku.get("name", sku["sku"]),
                    "alias": sku["sku"],
                    "baseUnit": "Nos",
                    "openingBalance": {
                        "quantity": int(sku.get("qty_on_hand", 0)),
                        "rate": float(sku.get("cost_price", 0)),
                    },
                    "hsnCode": sku.get("hsn_code", ""),
                    "gstRate": float(sku.get("gst_rate", 18)),
                }
                resp = httpx.post(
                    f"{self._base()}/stockitems",
                    headers=self._headers(),
                    json=payload,
                    timeout=15,
                )
                resp.raise_for_status()
                results.append({"sku": sku["sku"], "status": "synced"})
            except Exception as e:
                results.append({"sku": sku["sku"], "status": "failed", "error": str(e)})
        return results

    # ------------------------------------------------------------------ #
    # Fetch ledger balance
    # ------------------------------------------------------------------ #
    def get_ledger_balance(self, ledger_name: str) -> dict:
        resp = httpx.get(
            f"{self._base()}/ledgers/{ledger_name}/balance",
            headers=self._headers(),
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()

    # ------------------------------------------------------------------ #
    # Pull recent vouchers
    # ------------------------------------------------------------------ #
    def get_vouchers(self, voucher_type: str = "Sales", limit: int = 50) -> list:
        resp = httpx.get(
            f"{self._base()}/vouchers",
            headers=self._headers(),
            params={"type": voucher_type, "limit": limit},
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json().get("vouchers", [])
