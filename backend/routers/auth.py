"""
Auth router — user profile and tenant management.
Actual signup/login is handled client-side via Supabase JS SDK.
This router provides server-side helpers.
"""
from typing import Optional
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ..database import get_db
from ..middleware.auth import get_current_user, get_tenant_id

router = APIRouter(prefix="/api/auth", tags=["auth"])


class ProfileUpdate(BaseModel):
    brand_name: Optional[str] = None
    phone: Optional[str] = None
    gstin: Optional[str] = None
    pickup_address: Optional[dict] = None


@router.get("/me")
async def get_me(user=Depends(get_current_user)):
    """Return current user profile + tenant metadata."""
    db = get_db()
    tenant_id = get_tenant_id(user)
    row = db.table("tenants").select("*").eq("id", tenant_id).maybe_single().execute()
    integrations = db.table("channel_credentials").select("channel,connected,display_name").eq("tenant_id", tenant_id).execute()
    return {
        "user": {"id": tenant_id, "email": user.get("email")},
        "tenant": row.data,
        "integrations": integrations.data,
    }


@router.patch("/me")
async def update_profile(payload: ProfileUpdate, user=Depends(get_current_user)):
    db = get_db()
    tenant_id = get_tenant_id(user)
    updates = {k: v for k, v in payload.model_dump().items() if v is not None}
    if updates:
        db.table("tenants").update(updates).eq("id", tenant_id).execute()
    return {"status": "updated"}
