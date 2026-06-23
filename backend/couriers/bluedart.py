"""
BlueDart API wrapper — direct integration.
"""
import httpx
import logging
from datetime import datetime, timezone
from ..config import get_settings
from ..automation.logger import log_event

logger = logging.getLogger(__name__)

BLUEDART_TRACK_BASE = "https://apigateway.bluedart.com/in/transportation/track/v1"
BLUEDART_SHIP_BASE = "https://apigateway.bluedart.com/in/transportation/shipment/v1"


class BlueDartClient:

    def _headers(self):
        s = get_settings()
        return {
            "JWTToken": s.bluedart_jwt_token,
            "apikey": s.bluedart_api_key,
            "Content-Type": "application/json",
        }

    def create_shipment(self, order: dict, items: list[dict], weight_kg: float = 0.5) -> dict:
        s = get_settings()
        addr = order.get("shipping_address") or {}

        payload = {
            "Request": {
                "Consignee": {
                    "ConsigneeName": order.get("customer_name", ""),
                    "ConsigneeAddress1": addr.get("address1") or addr.get("address", ""),
                    "ConsigneeAddress2": addr.get("address2", ""),
                    "ConsigneeAddress3": addr.get("city", ""),
                    "ConsigneePincode": order.get("pincode", ""),
                    "ConsigneePhone": order.get("customer_phone", ""),
                    "ConsigneeMobile": order.get("customer_phone", ""),
                    "ConsigneeEmailID": order.get("customer_email", ""),
                },
                "Shipper": {
                    "OriginArea": s.bluedart_origin_area,
                    "Sender": s.bluedart_sender_name,
                    "SenderAddress1": s.bluedart_sender_address,
                    "SenderPincode": s.bluedart_sender_pincode,
                    "SenderMobile": s.bluedart_sender_mobile,
                    "CustomerCode": s.bluedart_customer_code,
                    "CustomerName": s.bluedart_sender_name,
                },
                "Services": {
                    "ProductCode": "A",  # Dart Apex (surface)
                    "SubProductCode": "",
                    "AWBNo": "",
                    "ActualWeight": str(weight_kg),
                    "CollectableAmount": str(order.get("total_amount", 0)) if order.get("payment_mode") == "cod" else "0",
                    "DeclaredValue": str(order.get("total_amount", 0)),
                    "Dimension": {"Dimensions": [{"Length": 15, "Breadth": 10, "Height": 5, "Count": 1}]},
                    "InvoiceNo": order["channel_order_id"],
                    "ItemCount": len(items),
                    "NoOfPieces": 1,
                    "PieceCount": "1",
                    "SpecialInstruction": "",
                    "IsDox": "N",
                    "PackType": "B",  # Box
                },
            }
        }

        resp = httpx.post(
            f"{BLUEDART_SHIP_BASE}/waybill",
            headers=self._headers(),
            json=payload,
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()

        awb_response = data.get("GenerateWaybillResult", {})
        awb = awb_response.get("AWBNo", "")

        if not awb:
            raise ValueError(f"BlueDart returned no AWB: {data}")

        log_event("shipment_created", "order", order["channel_order_id"], "success",
                  f"AWB={awb} Courier=BlueDart")

        return {
            "awb": awb,
            "courier": "BlueDart",
            "label_url": "",  # BlueDart label via separate call
        }

    def track_awb(self, awb: str) -> dict:
        resp = httpx.get(
            f"{BLUEDART_TRACK_BASE}/trackbyawbnumber/awb/{awb}",
            headers=self._headers(),
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        shipment = data.get("TrackByMultipleShipmentNumberResult", {}).get("ShipmentData", [{}])[0]
        status = shipment.get("StatusType", "")
        return {
            "awb": awb,
            "status": status,
            "location": shipment.get("ScannedLocation", ""),
            "updated_at": shipment.get("LocalActivityDate", ""),
        }

    def generate_label(self, awb: str) -> str:
        s = get_settings()
        resp = httpx.get(
            f"{BLUEDART_SHIP_BASE}/label",
            headers=self._headers(),
            params={"AWBNo": awb, "LabelType": "S"},
            timeout=30,
        )
        resp.raise_for_status()
        result = resp.json().get("GenerateLabelResult", {})
        return result.get("LabelPath", "")
