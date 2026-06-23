from abc import ABC, abstractmethod
from typing import Generator
from ..models.order import NormalizedOrder
from ..database import get_db
from ..automation.logger import log_event
import logging

logger = logging.getLogger(__name__)

_sku_mapper = None

def _get_mapper():
    global _sku_mapper
    if _sku_mapper is None:
        from ..catalog.sku_mapper import SKUMapper
        _sku_mapper = SKUMapper()
    return _sku_mapper


class BaseIngester(ABC):
    channel: str

    @abstractmethod
    def fetch_orders(self, since_hours: int = 24) -> Generator[NormalizedOrder, None, None]:
        """Yield normalized orders from the channel."""
        ...

    def upsert_orders(self, since_hours: int = 24) -> dict:
        db = get_db()
        inserted, updated, errors = 0, 0, 0

        for order in self.fetch_orders(since_hours):
            try:
                # Check existing
                existing = (
                    db.table("orders")
                    .select("id, status")
                    .eq("channel", order.channel)
                    .eq("channel_order_id", order.channel_order_id)
                    .execute()
                )

                order_data = order.model_dump(exclude={"items"})
                order_data["raw_payload"] = order.raw_payload

                if existing.data:
                    existing_id = existing.data[0]["id"]
                    existing_status = existing.data[0]["status"]
                    # Don't overwrite terminal states
                    if existing_status in ("delivered", "rto", "cancelled"):
                        continue
                    db.table("orders").update(order_data).eq("id", existing_id).execute()
                    updated += 1
                else:
                    result = db.table("orders").insert(order_data).execute()
                    order_id = result.data[0]["id"]
                    # Resolve internal SKUs before inserting items
                    mapper = _get_mapper()
                    for item in order.items:
                        item["order_id"] = order_id
                        if not item.get("sku"):
                            resolved = mapper.resolve(
                                channel=order.channel,
                                channel_sku_id=item.get("channel_sku_id", ""),
                                product_name=item.get("name", ""),
                            )
                            if resolved:
                                item["sku"] = resolved
                    if order.items:
                        db.table("order_items").insert(order.items).execute()
                    inserted += 1

            except Exception as e:
                errors += 1
                logger.error(f"[{self.channel}] Failed to upsert order {order.channel_order_id}: {e}")
                log_event("ingestion_error", "order", order.channel_order_id, "failed", str(e))

        log_event("ingestion_complete", "order", self.channel, "success",
                  f"inserted={inserted} updated={updated} errors={errors}")
        return {"inserted": inserted, "updated": updated, "errors": errors}
