from pydantic import BaseModel
from typing import Optional, List


class Warehouse(BaseModel):
    id: Optional[str] = None
    name: str
    code: str  # e.g. "DEL1", "MUM1"
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    pincode: Optional[str] = None
    is_active: bool = True
    courier_account_ids: List[str] = []  # courier accounts linked to this warehouse
    channels: List[str] = []  # channels that route to this warehouse
    pickup_slot_rules: Optional[dict] = None  # {day_of_week: pickup_time}
    weight_rules: Optional[dict] = None  # fixed cardboard weight additions


class WarehouseRoutingRule(BaseModel):
    id: Optional[str] = None
    warehouse_id: str
    rule_type: str  # "channel", "pincode_range", "state", "product_category"
    rule_value: str
    priority: int = 0
