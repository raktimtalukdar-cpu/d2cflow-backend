from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime


class ProductVariant(BaseModel):
    sku: str
    barcode: Optional[str] = None
    weight_grams: Optional[float] = 500
    dimensions: Optional[dict] = None  # {l, b, h in cm}
    color: Optional[str] = None
    size: Optional[str] = None
    mrp: Optional[float] = None
    cost_price: Optional[float] = None
    selling_price: Optional[float] = None
    qty_on_hand: Optional[int] = 0


class Product(BaseModel):
    id: Optional[str] = None
    name: str
    description: Optional[str] = None
    brand: Optional[str] = None
    category: Optional[str] = None
    sub_category: Optional[str] = None
    hsn_code: Optional[str] = None
    gst_rate: Optional[float] = None
    images: List[str] = []
    tags: List[str] = []
    is_active: bool = True
    variants: List[ProductVariant] = []
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class ChannelListing(BaseModel):
    id: Optional[str] = None
    sku: str
    channel: str
    channel_sku_id: Optional[str] = None
    listing_id: Optional[str] = None
    channel_price: Optional[float] = None
    channel_mrp: Optional[float] = None
    is_active: bool = True
    is_deactivated_by_channel: bool = False
    last_synced_at: Optional[datetime] = None
