from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class NormalizedOrder(BaseModel):
    channel: str
    channel_order_id: str
    channel_suborder_id: Optional[str] = None
    status: str = "pending"
    payment_mode: Optional[str] = None  # prepaid/cod
    customer_name: Optional[str] = None
    customer_phone: Optional[str] = None
    customer_email: Optional[str] = None
    shipping_address: Optional[dict] = None
    pincode: Optional[str] = None
    state: Optional[str] = None
    total_amount: Optional[float] = None
    marketplace_fee: Optional[float] = None
    shipping_charge: Optional[float] = None
    items: list[dict] = []
    raw_payload: Optional[dict] = None
    created_at: Optional[datetime] = None
