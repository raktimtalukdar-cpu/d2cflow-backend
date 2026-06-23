"""
Contacts management API.
Handles contact CRUD, CSV import, WhatsApp verification, and named broadcast lists.
"""
import csv
import io
import sqlite3
import logging
from typing import Optional, List
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel

from ..database import get_db
from ..middleware.auth import get_current_user, get_tenant_id
from ..routers.whatsapp import WHATSAPP_DEVICE_DB

router = APIRouter(prefix="/api/contacts", tags=["contacts"])
logger = logging.getLogger(__name__)


# ------------------------------------------------------------------ #
# Schemas
# ------------------------------------------------------------------ #

class ContactPayload(BaseModel):
    name: str
    phone: Optional[str] = None
    email: Optional[str] = None
    business_name: Optional[str] = None
    tags: List[str] = []
    notes: Optional[str] = None
    source: str = "manual"


class ContactListPayload(BaseModel):
    name: str
    contact_ids: List[str] = []


class ContactListUpdatePayload(BaseModel):
    name: Optional[str] = None
    add_contact_ids: List[str] = []
    remove_contact_ids: List[str] = []


# ------------------------------------------------------------------ #
# Phone normalisation
# ------------------------------------------------------------------ #

def _normalize_phone(raw: str) -> str | None:
    """Normalize any Indian phone to E.164 without the + (e.g. 919876543210)."""
    if not raw:
        return None
    clean = raw.replace(" ", "").replace("-", "").replace("+", "").replace("(", "").replace(")", "")
    # Remove leading 0
    if clean.startswith("0"):
        clean = clean[1:]
    # 10-digit local number
    if len(clean) == 10 and clean.isdigit():
        return "91" + clean
    # Already has country code
    if clean.startswith("91") and len(clean) == 12 and clean.isdigit():
        return clean
    # International number with some other country code — store as-is
    if clean.isdigit() and 7 <= len(clean) <= 15:
        return clean
    return None


# ------------------------------------------------------------------ #
# CRUD
# ------------------------------------------------------------------ #

@router.get("")
def list_contacts(
    tag: Optional[str] = None,
    is_on_whatsapp: Optional[bool] = None,
    search: Optional[str] = None,
    limit: int = 200,
    user=Depends(get_current_user),
):
    db = get_db()
    tenant_id = get_tenant_id(user)
    q = db.table("contacts").select("*").eq("tenant_id", tenant_id).order("name").limit(limit)
    if tag:
        q = q.contains("tags", [tag])
    if is_on_whatsapp is not None:
        q = q.eq("is_on_whatsapp", is_on_whatsapp)
    if search:
        q = q.or_(f"name.ilike.%{search}%,phone.ilike.%{search}%,business_name.ilike.%{search}%")
    return q.execute().data


@router.post("")
def create_contact(payload: ContactPayload, user=Depends(get_current_user)):
    db = get_db()
    tenant_id = get_tenant_id(user)
    phone_e164 = _normalize_phone(payload.phone or "")
    result = db.table("contacts").upsert({
        "tenant_id": tenant_id,
        "name": payload.name,
        "phone": payload.phone,
        "phone_e164": phone_e164,
        "email": payload.email,
        "business_name": payload.business_name,
        "tags": payload.tags,
        "notes": payload.notes,
        "source": payload.source,
    }, on_conflict="tenant_id,phone_e164").execute()
    return result.data[0]


@router.put("/{contact_id}")
def update_contact(contact_id: str, payload: ContactPayload, user=Depends(get_current_user)):
    db = get_db()
    tenant_id = get_tenant_id(user)
    phone_e164 = _normalize_phone(payload.phone or "")
    db.table("contacts").update({
        "name": payload.name,
        "phone": payload.phone,
        "phone_e164": phone_e164,
        "email": payload.email,
        "business_name": payload.business_name,
        "tags": payload.tags,
        "notes": payload.notes,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }).eq("id", contact_id).eq("tenant_id", tenant_id).execute()
    return {"status": "updated"}


@router.delete("/{contact_id}")
def delete_contact(contact_id: str, user=Depends(get_current_user)):
    db = get_db()
    tenant_id = get_tenant_id(user)
    db.table("contacts").delete().eq("id", contact_id).eq("tenant_id", tenant_id).execute()
    return {"status": "deleted"}


# ------------------------------------------------------------------ #
# CSV import
# ------------------------------------------------------------------ #

# Flexible column name aliases
_PHONE_COLS = {"phone", "mobile", "phone_number", "contact", "whatsapp", "number", "mob"}
_NAME_COLS = {"name", "full_name", "customer_name", "contact_name", "client"}
_EMAIL_COLS = {"email", "email_address", "mail"}
_BIZ_COLS = {"business", "business_name", "company", "firm", "shop"}


def _pick(row: dict, candidates: set) -> str:
    for key in row:
        if key.lower().strip() in candidates:
            return str(row[key]).strip()
    return ""


@router.post("/import")
async def import_contacts(
    file: UploadFile = File(...),
    default_tag: Optional[str] = None,
    user=Depends(get_current_user),
):
    """
    CSV upload. Accepts flexible column names (name/Name/full_name, phone/mobile, etc.).
    Upserts on (tenant_id, phone_e164) so re-uploads don't create duplicates.
    """
    db = get_db()
    tenant_id = get_tenant_id(user)

    content = await file.read()
    try:
        text = content.decode("utf-8-sig")  # handles BOM from Excel exports
    except UnicodeDecodeError:
        text = content.decode("latin-1")

    reader = csv.DictReader(io.StringIO(text))
    inserted, updated, invalid = 0, 0, []

    rows_to_upsert = []
    for i, row in enumerate(reader, start=2):  # start=2 accounting for header row
        phone_raw = _pick(row, _PHONE_COLS)
        phone_e164 = _normalize_phone(phone_raw)
        name = _pick(row, _NAME_COLS) or phone_e164 or f"Contact {i}"

        if not phone_e164 and not _pick(row, _EMAIL_COLS):
            invalid.append({"row": i, "reason": "no valid phone or email", "data": dict(row)})
            continue

        tags = [default_tag] if default_tag else []
        rows_to_upsert.append({
            "tenant_id": tenant_id,
            "name": name,
            "phone": phone_raw,
            "phone_e164": phone_e164,
            "email": _pick(row, _EMAIL_COLS) or None,
            "business_name": _pick(row, _BIZ_COLS) or None,
            "tags": tags,
            "source": "csv_upload",
        })

    # Batch upsert in chunks of 100
    for i in range(0, len(rows_to_upsert), 100):
        chunk = rows_to_upsert[i:i + 100]
        result = db.table("contacts").upsert(chunk, on_conflict="tenant_id,phone_e164").execute()
        inserted += len(result.data)

    return {
        "total": len(rows_to_upsert) + len(invalid),
        "imported": inserted,
        "invalid": invalid,
        "invalid_count": len(invalid),
    }


# ------------------------------------------------------------------ #
# WhatsApp verification
# ------------------------------------------------------------------ #

@router.post("/check-whatsapp")
def check_whatsapp(
    contact_ids: Optional[List[str]] = None,
    user=Depends(get_current_user),
):
    """
    Cross-reference uploaded contacts against the local WhatsApp bridge DB.
    Marks is_on_whatsapp=true and records the WhatsApp JID for each matched contact.
    """
    db = get_db()
    tenant_id = get_tenant_id(user)
    now = datetime.now(timezone.utc).isoformat()

    # Load contacts to check
    q = db.table("contacts").select("id, phone_e164").eq("tenant_id", tenant_id)
    if contact_ids:
        q = q.in_("id", contact_ids)
    else:
        q = q.is_("wa_checked_at", "null")  # only unchecked by default
    contacts = q.execute().data

    if not contacts:
        return {"checked": 0, "on_whatsapp": 0, "not_on_whatsapp": 0}

    # Load known WhatsApp JIDs from whatsmeow_contacts
    wa_phones: set[str] = set()
    jid_map: dict[str, str] = {}
    try:
        conn = sqlite3.connect(WHATSAPP_DEVICE_DB)
        cur = conn.cursor()
        cur.execute("SELECT their_jid FROM whatsmeow_contacts WHERE their_jid LIKE '%@s.whatsapp.net'")
        for (jid,) in cur.fetchall():
            phone = jid.replace("@s.whatsapp.net", "")
            wa_phones.add(phone)
            jid_map[phone] = jid
        conn.close()
    except Exception as e:
        logger.warning(f"Could not read WhatsApp device DB: {e}")
        # Fall back: mark all as not verified
        for c in contacts:
            db.table("contacts").update({
                "is_on_whatsapp": False,
                "wa_checked_at": now,
            }).eq("id", c["id"]).execute()
        return {"checked": len(contacts), "on_whatsapp": 0, "not_on_whatsapp": len(contacts), "note": "bridge DB unavailable"}

    on_wa, not_on_wa = 0, 0
    for c in contacts:
        phone_e164 = c.get("phone_e164", "")
        if not phone_e164:
            continue

        if phone_e164 in wa_phones:
            db.table("contacts").update({
                "is_on_whatsapp": True,
                "whatsapp_jid": jid_map[phone_e164],
                "wa_checked_at": now,
            }).eq("id", c["id"]).execute()
            on_wa += 1
        else:
            db.table("contacts").update({
                "is_on_whatsapp": False,
                "wa_checked_at": now,
            }).eq("id", c["id"]).execute()
            not_on_wa += 1

    return {"checked": len(contacts), "on_whatsapp": on_wa, "not_on_whatsapp": not_on_wa}


# ------------------------------------------------------------------ #
# Named broadcast lists
# ------------------------------------------------------------------ #

@router.get("/lists")
def list_contact_lists(user=Depends(get_current_user)):
    db = get_db()
    tenant_id = get_tenant_id(user)
    lists = db.table("contact_lists").select("*").eq("tenant_id", tenant_id).order("name").execute().data
    # Attach member count
    for lst in lists:
        members = db.table("contact_list_members").select("id", count="exact").eq("list_id", lst["id"]).execute()
        lst["member_count"] = members.count or 0
    return lists


@router.post("/lists")
def create_contact_list(payload: ContactListPayload, user=Depends(get_current_user)):
    db = get_db()
    tenant_id = get_tenant_id(user)
    result = db.table("contact_lists").insert({"tenant_id": tenant_id, "name": payload.name}).execute()
    list_id = result.data[0]["id"]
    if payload.contact_ids:
        db.table("contact_list_members").insert(
            [{"list_id": list_id, "contact_id": cid} for cid in payload.contact_ids]
        ).execute()
    return {**result.data[0], "member_count": len(payload.contact_ids)}


@router.put("/lists/{list_id}")
def update_contact_list(list_id: str, payload: ContactListUpdatePayload, user=Depends(get_current_user)):
    db = get_db()
    tenant_id = get_tenant_id(user)
    # Verify ownership
    db.table("contact_lists").select("id").eq("id", list_id).eq("tenant_id", tenant_id).execute()
    if payload.name:
        db.table("contact_lists").update({"name": payload.name}).eq("id", list_id).execute()
    if payload.add_contact_ids:
        db.table("contact_list_members").upsert(
            [{"list_id": list_id, "contact_id": cid} for cid in payload.add_contact_ids],
            on_conflict="list_id,contact_id",
        ).execute()
    if payload.remove_contact_ids:
        for cid in payload.remove_contact_ids:
            db.table("contact_list_members").delete().eq("list_id", list_id).eq("contact_id", cid).execute()
    return {"status": "updated"}


@router.delete("/lists/{list_id}")
def delete_contact_list(list_id: str, user=Depends(get_current_user)):
    db = get_db()
    tenant_id = get_tenant_id(user)
    db.table("contact_list_members").delete().eq("list_id", list_id).execute()
    db.table("contact_lists").delete().eq("id", list_id).eq("tenant_id", tenant_id).execute()
    return {"status": "deleted"}


@router.get("/lists/{list_id}/members")
def list_members(list_id: str, user=Depends(get_current_user)):
    db = get_db()
    tenant_id = get_tenant_id(user)
    return (
        db.table("contact_list_members")
        .select("contacts(*)")
        .eq("list_id", list_id)
        .execute()
        .data
    )
