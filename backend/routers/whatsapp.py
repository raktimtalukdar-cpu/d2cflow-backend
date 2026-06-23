"""
WhatsApp Order Intake router.

All bridge paths are configurable via environment variables so the backend
can run in production (Render) without hardcoded local paths.

Environment variables (all optional, have local-dev defaults):
  WHATSAPP_BRIDGE_BINARY  — path to the whatsapp-bridge binary
  WHATSAPP_BRIDGE_DIR     — working directory for the bridge process
  WHATSAPP_BRIDGE_API     — base URL of the bridge HTTP API  (default: http://localhost:8080)
  WHATSAPP_DB_PATH        — path to messages.db
  WHATSAPP_DEVICE_DB      — path to whatsapp.db (device auth)
  D2CFLOW_STORE_DIR       — directory for persisted JSON state (default: ~/.d2cflow)
"""

import base64
import io
import json
import logging
import os
import re
import sqlite3
import subprocess
import threading
import uuid
from datetime import datetime, timedelta, timezone
from typing import List, Optional

import httpx
from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

# ── Config (all overridable via env vars) ─────────────────────────────────────

_DEFAULT_BRIDGE_DIR = os.path.expanduser(
    "~/Documents/whatsapp-mcp/whatsapp-bridge"
)
BRIDGE_BINARY: str = os.environ.get(
    "WHATSAPP_BRIDGE_BINARY",
    os.path.join(_DEFAULT_BRIDGE_DIR, "whatsapp-bridge"),
)
BRIDGE_DIR: str = os.environ.get("WHATSAPP_BRIDGE_DIR", _DEFAULT_BRIDGE_DIR)
BRIDGE_API: str = os.environ.get("WHATSAPP_BRIDGE_API", "http://localhost:8080")
WHATSAPP_DB_PATH: str = os.environ.get(
    "WHATSAPP_DB_PATH",
    os.path.join(BRIDGE_DIR, "store", "messages.db"),
)
WHATSAPP_DEVICE_DB: str = os.environ.get(
    "WHATSAPP_DEVICE_DB",
    os.path.join(BRIDGE_DIR, "store", "whatsapp.db"),
)
_STORE_DIR: str = os.environ.get(
    "D2CFLOW_STORE_DIR", os.path.expanduser("~/.d2cflow")
)
_CHATS_FILE         = os.path.join(_STORE_DIR, "wa_monitored_chats.json")
_ORDERS_FILE        = os.path.join(_STORE_DIR, "wa_detected_orders.json")
_REPLIES_FILE       = os.path.join(_STORE_DIR, "wa_drafted_replies.json")
_CONFIRMATIONS_FILE = os.path.join(_STORE_DIR, "wa_confirmations.json")
_CONV_STATES_FILE   = os.path.join(_STORE_DIR, "wa_conv_states.json")
_BROADCASTS_FILE    = os.path.join(_STORE_DIR, "wa_broadcasts.json")

router = APIRouter(prefix="/api/whatsapp", tags=["whatsapp"])
logger = logging.getLogger(__name__)


# ── SQLite Setup ──────────────────────────────────────────────────────────────

def _init_sqlite_db():
    try:
        db_dir = os.path.dirname(WHATSAPP_DB_PATH)
        if db_dir:
            os.makedirs(db_dir, exist_ok=True)
        conn = sqlite3.connect(WHATSAPP_DB_PATH)
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id TEXT PRIMARY KEY,
                chat_jid TEXT,
                sender TEXT,
                content TEXT,
                timestamp TEXT,
                is_from_me INTEGER DEFAULT 0
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS chats (
                jid TEXT PRIMARY KEY,
                name TEXT,
                last_message_time TEXT
            )
        """)
        conn.commit()
        conn.close()
    except Exception as e:
        logger.warning("Could not initialize local SQLite tables: %s", e)

_init_sqlite_db()



# ── Persistent JSON helpers ───────────────────────────────────────────────────

def _load_json(path: str, default):
    try:
        os.makedirs(_STORE_DIR, exist_ok=True)
        if os.path.exists(path):
            with open(path) as f:
                return json.load(f)
    except Exception:
        pass
    return default


def _save_json(path: str, data) -> None:
    try:
        os.makedirs(_STORE_DIR, exist_ok=True)
        with open(path, "w") as f:
            json.dump(data, f)
    except Exception as e:
        logger.warning("Could not save %s: %s", path, e)


# ── In-memory stores (all seeded from disk — survive restarts) ────────────────

_monitored_chats: List[dict]      = _load_json(_CHATS_FILE, [])
_detected_orders: List[dict]      = _load_json(_ORDERS_FILE, [])
_drafted_replies: List[dict]      = _load_json(_REPLIES_FILE, [])
_pending_confirmations: List[dict] = _load_json(_CONFIRMATIONS_FILE, [])
_conversation_states: dict        = _load_json(_CONV_STATES_FILE, {})
# _pending_broadcasts: one entry per CRM send, never overwritten — supports multiple orders per contact
_pending_broadcasts: List[dict]   = _load_json(_BROADCASTS_FILE, [])
_synced_products: List[dict]      = []


def _persist_all() -> None:
    """Flush all mutable state to disk at once."""
    _save_json(_ORDERS_FILE, _detected_orders)
    _save_json(_REPLIES_FILE, _drafted_replies)
    _save_json(_CONFIRMATIONS_FILE, _pending_confirmations)
    _save_json(_BROADCASTS_FILE, _pending_broadcasts)
    _save_json(_CONV_STATES_FILE, _conversation_states)


# ── Bridge process state ──────────────────────────────────────────────────────

_bridge_process: Optional[subprocess.Popen] = None  # type: ignore[type-arg]
_qr_code_b64: Optional[str] = None
_wa_connected: bool = False
_bridge_lock = threading.Lock()


# ── Bridge helpers ────────────────────────────────────────────────────────────

def _is_bridge_running() -> bool:
    try:
        httpx.post(f"{BRIDGE_API}/api/send", json={}, timeout=1.0)
        return True
    except httpx.ConnectError:
        return False
    except Exception:
        return True  # non-connect error means it's up


def _is_bridge_authenticated() -> bool:
    for path in [WHATSAPP_DEVICE_DB, os.path.join(BRIDGE_DIR, "whatsapp.db")]:
        try:
            conn = sqlite3.connect(path)
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM whatsmeow_device")
            count = cur.fetchone()[0]
            conn.close()
            if count > 0:
                return True
        except Exception:
            pass
    return False


def _qr_data_to_b64(qr_data: str) -> Optional[str]:
    try:
        import qrcode  # type: ignore[import]
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=8,
            border=4,
        )
        qr.add_data(qr_data)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return base64.b64encode(buf.getvalue()).decode()
    except Exception as e:
        logger.warning("Could not generate QR PNG: %s", e)
        return None


def _parse_qr_from_output(line: str) -> Optional[str]:
    line = line.strip()
    line_lower = line.lower()
    for prefix in ("qr code:", "scan this qr code:", "qr:"):
        if line_lower.startswith(prefix):
            data = line[len(prefix):].strip()
            if data:
                return _qr_data_to_b64(data)
    # whatsmeow emits raw QR payload — detect by structure
    if "," in line and "@" in line and len(line) > 20 and not line.startswith("{"):
        return _qr_data_to_b64(line)
    return None


def _bridge_stdout_reader(proc: subprocess.Popen) -> None:  # type: ignore[type-arg]
    global _qr_code_b64, _wa_connected
    try:
        for raw_line in proc.stdout:  # type: ignore[union-attr]
            line = raw_line.decode("utf-8", errors="replace").rstrip()
            logger.debug("[bridge] %s", line)
            if any(kw in line.lower() for kw in ("logged in", "connected", "already logged in", "client is logged in")):
                _wa_connected = True
                _qr_code_b64 = None
            qr = _parse_qr_from_output(line)
            if qr:
                _qr_code_b64 = qr
                _wa_connected = False
    except Exception as e:
        logger.debug("Bridge stdout reader exited: %s", e)


def _start_bridge() -> bool:
    global _bridge_process, _wa_connected
    if not os.path.exists(BRIDGE_BINARY):
        logger.warning("Bridge binary not found at %s", BRIDGE_BINARY)
        return False
    if _is_bridge_running():
        if _is_bridge_authenticated():
            _wa_connected = True
        return True
    with _bridge_lock:
        if _is_bridge_running():
            return True
        try:
            proc = subprocess.Popen(
                [BRIDGE_BINARY],
                cwd=BRIDGE_DIR,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
            )
            _bridge_process = proc
            t = threading.Thread(target=_bridge_stdout_reader, args=(proc,), daemon=True)
            t.start()
            if _is_bridge_authenticated():
                _wa_connected = True
            return True
        except Exception as e:
            logger.error("Failed to start bridge: %s", e)
            return False


# ── SQLite DB helpers ─────────────────────────────────────────────────────────

def _resolve_jid_aliases(phone_jid: str) -> List[str]:
    """
    WhatsApp now stores many contacts under a LID (Linked Device ID) like
    '187758807122129@lid' rather than the phone JID '918337064381@s.whatsapp.net'.
    This function returns ALL JIDs we should scan for a given phone JID.
    """
    jids = [phone_jid]
    phone_number = phone_jid.split("@")[0]
    for db_path in [WHATSAPP_DEVICE_DB, os.path.join(BRIDGE_DIR, "whatsapp.db")]:
        try:
            conn = sqlite3.connect(db_path)
            cur = conn.cursor()
            cur.execute("SELECT lid FROM whatsmeow_lid_map WHERE pn = ?", (phone_number,))
            row = cur.fetchone()
            conn.close()
            if row:
                lid_jid = f"{row[0]}@lid"
                if lid_jid not in jids:
                    jids.append(lid_jid)
                break
        except Exception:
            pass
    return jids


def _wa_list_chats(query: Optional[str] = None, limit: int = 50) -> List[dict]:
    """
    Return chats with real contact names from whatsmeow_contacts (device DB).
    Falls back to messages DB `chats` table if device DB unavailable.
    Filters: no @lid, no @broadcast, no @newsletter.
    Formats Indian phone numbers as +91 XXXXX XXXXX.
    """

    def _fmt_phone(raw: str) -> str:
        raw = raw.split("-")[0]  # strip group timestamp suffix
        if raw.startswith("91") and len(raw) == 12:
            return f"+91 {raw[2:7]} {raw[7:]}"
        if len(raw) == 10 and raw.isdigit():
            return f"+91 {raw[:5]} {raw[5:]}"
        return raw

    # 1. Load contact name map from whatsmeow_contacts (device DB)
    contact_names: dict = {}
    try:
        device_conn = sqlite3.connect(WHATSAPP_DEVICE_DB)
        device_conn.row_factory = sqlite3.Row
        dc = device_conn.cursor()
        dc.execute("SELECT their_jid, full_name, push_name, first_name FROM whatsmeow_contacts")
        for r in dc.fetchall():
            jid = r["their_jid"]
            name = r["full_name"] or r["push_name"] or r["first_name"] or ""
            if name:
                contact_names[jid] = name
        device_conn.close()
    except Exception as e:
        logger.warning("Could not load contact names from device DB: %s", e)

    # 2. Build rows from contact_names (whatsmeow_contacts) — these are real contacts
    rows = []
    seen_jids: set = set()

    # First: individual contacts (DMs) from the contacts table
    for jid, name in contact_names.items():
        if not jid.endswith("@s.whatsapp.net"):
            continue
        seen_jids.add(jid)
        phone_raw = jid.replace("@s.whatsapp.net", "")
        phone_display = _fmt_phone(phone_raw)
        display_name = name or phone_display

        if query:
            q_lower = query.lower()
            if q_lower not in display_name.lower() and q_lower not in phone_display.lower():
                continue

        rows.append({
            "jid": jid,
            "name": display_name,
            "phone": phone_display,
            "is_group": False,
            "last_message_time": None,
        })

    # Sort DMs alphabetically by name
    rows.sort(key=lambda r: r["name"].lower())

    # Then: groups from messages DB chats table
    try:
        conn = sqlite3.connect(WHATSAPP_DB_PATH)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute(
            """SELECT jid, name, last_message_time FROM chats
               WHERE jid LIKE '%@g.us'
               ORDER BY last_message_time DESC LIMIT ?""",
            (100,),
        )
        for r in cur.fetchall():
            row = dict(r)
            jid = row.get("jid", "")
            if jid in seen_jids:
                continue
            seen_jids.add(jid)
            chat_name = row.get("name") or f"Group {jid.split('@')[0][:12]}"

            if query:
                q_lower = query.lower()
                if q_lower not in chat_name.lower():
                    continue

            rows.append({
                "jid": jid,
                "name": chat_name,
                "phone": "",
                "is_group": True,
                "last_message_time": row.get("last_message_time"),
            })
        conn.close()
    except Exception as e:
        logger.error("WhatsApp DB groups error: %s", e)

    return rows[:limit]


def _wa_list_messages(chat_jid: str, limit: int = 100, after_iso: Optional[str] = None, include_sent: bool = False) -> List[dict]:
    """
    Fetch messages for a chat.
    For DMs: only customer messages (is_from_me=0) unless include_sent=True.
    For groups (@g.us): always include all messages since confirmations come from Raktim himself (is_from_me=1).
    """
    is_group = chat_jid.endswith("@g.us")
    try:
        conn = sqlite3.connect(WHATSAPP_DB_PATH)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        if after_iso:
            if is_group or include_sent:
                cur.execute(
                    """SELECT id, chat_jid, sender, content AS text, timestamp, is_from_me
                       FROM messages WHERE chat_jid = ? AND timestamp > ?
                       ORDER BY timestamp DESC LIMIT ?""",
                    (chat_jid, after_iso, limit),
                )
            else:
                cur.execute(
                    """SELECT id, chat_jid, sender, content AS text, timestamp, is_from_me
                       FROM messages WHERE chat_jid = ? AND timestamp > ? AND is_from_me = 0
                       ORDER BY timestamp DESC LIMIT ?""",
                    (chat_jid, after_iso, limit),
                )
        else:
            if is_group or include_sent:
                cur.execute(
                    """SELECT id, chat_jid, sender, content AS text, timestamp, is_from_me
                       FROM messages WHERE chat_jid = ?
                       ORDER BY timestamp DESC LIMIT ?""",
                    (chat_jid, limit),
                )
            else:
                cur.execute(
                    """SELECT id, chat_jid, sender, content AS text, timestamp, is_from_me
                       FROM messages WHERE chat_jid = ? AND is_from_me = 0
                       ORDER BY timestamp DESC LIMIT ?""",
                    (chat_jid, limit),
                )
        rows = [dict(r) for r in cur.fetchall()]
        conn.close()
        return rows
    except Exception as e:
        logger.error("WhatsApp DB messages error (%s): %s", chat_jid, e)
        return []


def _wa_list_all_messages(chat_jid: str, limit: int = 10) -> List[dict]:
    """Read last N messages (both directions) across all JID aliases for confirmation detection."""
    all_rows: List[dict] = []
    for jid in _resolve_jid_aliases(chat_jid):
        try:
            conn = sqlite3.connect(WHATSAPP_DB_PATH)
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            cur.execute(
                """SELECT id, chat_jid, sender, content AS text, timestamp, is_from_me
                   FROM messages WHERE chat_jid = ? ORDER BY timestamp DESC LIMIT ?""",
                (jid, limit),
            )
            all_rows.extend(dict(r) for r in cur.fetchall())
            conn.close()
        except Exception as e:
            logger.error("WhatsApp DB all-messages error (%s): %s", jid, e)
    # Sort by timestamp descending and return top N
    all_rows.sort(key=lambda r: r.get("timestamp", ""), reverse=True)
    return all_rows[:limit]


# ── Intent detection ──────────────────────────────────────────────────────────

INTENT_KEYWORDS = [
    "want", "need", "interested", "can i get", "send me", "order", "book",
    "how much", "price", "available", "stock", "buy", "purchase", "do you have",
    "i'll take", "i want", "looking for", "get me", "want to buy",
]

CONFIRMATION_KEYWORDS = [
    "yes", "confirm", "ok", "confirmed", "yeah", "yep", "sure", "proceed",
    "हाँ", "हा", "हां", "ji", "ji han", "ji ha", "okay", "buy", "order",
    "place order", "i'll take", "i want", "done", "agreed", "go ahead",
]

_QTY_PATTERNS = [
    r'(\d+)\s*(?:pieces?|pcs?|units?|qty|nos?|x)',
    r'[×xX]\s*(\d+)',
    r'(?:qty|quantity)\s*[:\-]?\s*(\d+)',
    r'\b(\d+)\s+(?:pieces?|pcs?|units?)\b',
]
_PRICE_PATTERN = r'(?:₹|Rs\.?|INR)\s*(\d[\d,]*(?:\.\d{1,2})?)'


def _match_product(text_lower: str, products: List[dict]) -> Optional[dict]:
    best: Optional[dict] = None
    best_score = 0.0
    for p in products:
        name_lower = p.get("name", "").lower()
        sku = p.get("sku", "").lower()
        if name_lower and name_lower in text_lower:
            return p
        if sku and sku in text_lower:
            return p
        words = [w for w in name_lower.split() if len(w) > 3]
        if not words:
            continue
        score = sum(1 for w in words if w in text_lower) / len(words)
        if score > 0.5 and score > best_score:
            best_score = score
            best = p
    return best


def _guess_product_name(text: str) -> Optional[str]:
    clean = text
    for kw in ("i want to order", "i want", "i need", "can i get", "send me", "order", "book", "buy", "purchase"):
        clean = re.sub(re.escape(kw), "", clean, flags=re.IGNORECASE).strip()
    clean = re.sub(r"^(a|an|the|one|1)\s+", "", clean, flags=re.IGNORECASE).strip()
    chunk = re.split(r"[,.\?!]", clean)[0].strip()
    chunk = re.sub(r"\s*(please|pls|kindly|asap)$", "", chunk, flags=re.IGNORECASE).strip()
    return chunk if len(chunk) > 2 else None


def _detect_order_intent(message_text: str, products: List[dict]) -> Optional[dict]:
    text_lower = message_text.strip().lower()
    found_kw = [kw for kw in INTENT_KEYWORDS if kw in text_lower]
    
    # Try line-by-line parsing for structured cart checkout text
    lines = [l.strip() for l in message_text.split('\n') if l.strip()]
    matched_items = []
    
    if len(lines) > 1:
        for line in lines:
            line_lower = line.lower()
            matched = _match_product(line_lower, products)
            if matched:
                qty = 1
                for pattern in _QTY_PATTERNS:
                    m = re.search(pattern, line_lower, re.IGNORECASE)
                    if m:
                        try:
                            qty = int(m.group(1))
                        except (ValueError, IndexError):
                            pass
                        break
                matched_items.append({
                    "product": matched,
                    "qty": qty
                })
                
    # If no line-by-line matches, search for multiple product mentions in a single message
    if not matched_items:
        for p in products:
            p_name = p.get("name", "").lower()
            p_sku = p.get("sku", "").lower()
            if (p_name and p_name in text_lower) or (p_sku and p_sku in text_lower):
                start_idx = text_lower.find(p_name) if p_name in text_lower else text_lower.find(p_sku)
                window = text_lower[max(0, start_idx-15):min(len(text_lower), start_idx+len(p_name)+15)]
                qty = 1
                for pattern in _QTY_PATTERNS:
                    m = re.search(pattern, window, re.IGNORECASE)
                    if m:
                        try:
                            qty = int(m.group(1))
                        except (ValueError, IndexError):
                            pass
                        break
                if not any(item["product"]["id"] == p["id"] for item in matched_items):
                    matched_items.append({
                        "product": p,
                        "qty": qty
                    })

    if not matched_items:
        # Product name alone counts as enquiry
        matched = _match_product(text_lower, products)
        if not found_kw and matched:
            found_kw = ["product_name_match"]
            
        if not found_kw:
            return None
            
        if not matched:
            guessed = _guess_product_name(message_text)
            if not guessed:
                return None
            matched = {"id": None, "name": guessed, "sku": None, "price": None, "stock": None}
            
        qty = 1
        for pattern in _QTY_PATTERNS:
            m = re.search(pattern, text_lower, re.IGNORECASE)
            if m:
                try:
                    qty = int(m.group(1))
                except (ValueError, IndexError):
                    pass
                break
                
        price_hint = matched.get("price")
        pm = re.search(_PRICE_PATTERN, message_text)
        if pm:
            price_hint = float(pm.group(1).replace(",", ""))
            
        confidence = min(0.4 + len(found_kw) * 0.1 + (0.4 if matched.get("id") else 0.1), 0.99)
        
        return {
            "matched_product": matched,
            "product_hint": matched.get("name"),
            "product_id": matched.get("id"),
            "product_sku": matched.get("sku"),
            "catalog_price": matched.get("price"),
            "in_catalog": matched.get("id") is not None,
            "qty": qty,
            "price_hint": price_hint,
            "confidence": round(confidence, 2),
            "items": [{"name": matched.get("name"), "product_id": matched.get("id"), "qty": qty, "price": matched.get("price") or 0.0}]
        }

    # Aggregate matched items
    items_list = []
    total_price = 0.0
    for item in matched_items:
        p = item["product"]
        qty = item["qty"]
        price = float(p.get("price") or 0.0)
        items_list.append({
            "name": p.get("name"),
            "product_id": p.get("id"),
            "qty": qty,
            "price": price
        })
        total_price += price * qty
        
    first_item = matched_items[0]
    confidence = min(0.5 + len(matched_items) * 0.15 + (0.2 if found_kw else 0.0), 0.99)
    
    return {
        "matched_product": first_item["product"],
        "product_hint": first_item["product"].get("name"),
        "product_id": first_item["product"].get("id"),
        "product_sku": first_item["product"].get("sku"),
        "catalog_price": first_item["product"].get("price"),
        "in_catalog": True,
        "qty": sum(item["qty"] for item in matched_items),
        "price_hint": first_item["product"].get("price"),
        "confidence": round(confidence, 2),
        "items": items_list,
        "total_price": total_price
    }



# ── Product catalog ───────────────────────────────────────────────────────────

def _get_products() -> List[dict]:
    if _synced_products:
        return _synced_products
    try:
        from ..database import get_db
        db = get_db()
        result = db.table("products").select("id, name, sku, price, stock").limit(200).execute()
        if result.data:
            return result.data
    except Exception:
        pass
    return []


def _get_product_by_id(product_id: str) -> Optional[dict]:
    return next((p for p in _get_products() if p.get("id") == product_id), None)


def _get_product_by_name(name: str) -> Optional[dict]:
    if not name:
        return None
    name_lower = name.lower()
    return next((p for p in _get_products() if p.get("name", "").lower() == name_lower), None)


def _deduct_stock(product_id: str, qty: int) -> None:
    try:
        from ..database import get_db
        db = get_db()
        result = db.table("products").select("stock").eq("id", product_id).single().execute()
        current = (result.data or {}).get("stock", 0)
        db.table("products").update({"stock": max(0, current - qty)}).eq("id", product_id).execute()
    except Exception as e:
        logger.warning("Could not deduct stock for %s: %s", product_id, e)


# ── Draft reply builder ───────────────────────────────────────────────────────

def _create_draft_reply(detection: dict) -> dict:
    items = detection.get("items")
    customer_name = detection.get("customer_name", "there")
    
    if items and len(items) > 1:
        # Multiple items
        item_lines = []
        total = 0.0
        available_count = 0
        
        for item in items:
            p_id = item.get("product_id")
            p = _get_product_by_id(p_id) if p_id else None
            stock = p.get("stock", 99) if p else 0
            qty = item.get("qty", 1)
            price = item.get("price") or 0.0
            
            if stock > 0:
                available_count += 1
                item_lines.append(f"• *{item['name']}* (Qty: {qty}) — ₹{price * qty}")
                total += price * qty
            else:
                item_lines.append(f"• *{item['name']}* (Qty: {qty}) — _Out of stock_ ❌")
                
        if available_count > 0:
            msg = (
                f"Hi {customer_name}! \U0001f44b\n\n"
                f"We noticed you're interested in these items:\n"
                f"{chr(10).join(item_lines)}\n\n"
                f"Reply *YES* to confirm your order.\n"
                f"Total: *₹{total}*"
            )
            _conversation_states[detection["chat_jid"]] = {
                "state": "waiting_confirm",
                "detection_id": detection["id"],
                "items": [item for item in items if _get_product_by_id(item.get("product_id")).get("stock", 0) > 0],
                "total": total,
                "sent_at": None,
                "qty": sum(item.get("qty", 1) for item in items),
                "price": total, # Legacy compat
                "product_name": ", ".join(item.get("name") for item in items)
            }
        else:
            msg = (
                f"Hi {customer_name}! \U0001f44b\n\n"
                f"Thank you for your interest.\n\n"
                f"❌ Unfortunately, the requested items are currently out of stock."
            )
            
        return {
            "id": str(uuid.uuid4()),
            "detection_id": detection["id"],
            "chat_jid": detection["chat_jid"],
            "customer_name": customer_name,
            "product_name": ", ".join(item.get("name") for item in items),
            "product_id": items[0].get("product_id") if items else None,
            "product_available": available_count > 0,
            "product_price": total,
            "stock_qty": available_count,
            "catalog_price": total,
            "qty": sum(item.get("qty", 1) for item in items),
            "draft_message": msg,
            "message_text": msg,
            "status": "draft",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
    else:
        # Legacy/Single product fallback
        product = (
            _get_product_by_id(detection.get("product_id") or "")
            or _get_product_by_name(detection.get("product_hint") or "")
        )
        stock = product.get("stock", product.get("quantity", 99)) if product else 0
        available = product is not None and stock > 0
        qty = detection.get("qty", 1)

        if available:
            price = product["price"]
            msg = (
                f"Hi {customer_name}! \U0001f44b\n\n"
                f"We noticed you're interested in *{product['name']}*.\n\n"
                f"✅ Good news! It's available at *₹{price}*.\n\n"
                f"Reply *YES* to confirm your order of {qty} unit(s).\n"
                f"Total: *₹{price * qty}*"
            )
            _conversation_states[detection["chat_jid"]] = {
                "state": "waiting_confirm",
                "detection_id": detection["id"],
                "product_name": product["name"],
                "product_id": product.get("id"),
                "qty": qty,
                "price": price,
                "total": price * qty,
                "items": [{"name": product["name"], "product_id": product.get("id"), "qty": qty, "price": price}],
                "sent_at": None,
            }
        else:
            product_name = detection.get("product_hint", "the product")
            msg = (
                f"Hi {customer_name}! \U0001f44b\n\n"
                f"Thank you for your interest in *{product_name}*.\n\n"
                f"❌ Unfortunately, this item is currently out of stock.\n\n"
                f"We'll notify you as soon as it's back!"
            )

        return {
            "id": str(uuid.uuid4()),
            "detection_id": detection["id"],
            "chat_jid": detection["chat_jid"],
            "customer_name": customer_name,
            "product_name": detection.get("product_hint", ""),
            "product_id": detection.get("product_id"),
            "product_available": available,
            "product_price": product.get("price") if product else None,
            "stock_qty": stock,
            "catalog_price": product.get("price") if product else None,
            "qty": qty,
            "draft_message": msg,
            "message_text": msg,
            "status": "draft",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }


# ── Automated Razorpay payment links ──────────────────────────────────────────

def _generate_and_send_payment_link(order: dict) -> None:
    try:
        from .payments import _rz_auth, RAZORPAY_BASE
        
        amount = float(order.get("total") or order.get("price", 0.0))
        if amount <= 0:
            return
            
        customer_name = order.get("customer_name", "Customer")
        chat_jid = order.get("chat_jid")
        phone = chat_jid.split("@")[0].split("-")[0] if chat_jid else ""
        order_id = order.get("id")
        
        # Fallback check for Razorpay credentials
        try:
            auth = _rz_auth()
            has_credentials = True
        except Exception:
            has_credentials = False

        if not has_credentials:
            # Demo mode / missing credentials fallback
            short_url = f"https://rzp.io/i/mock-{order_id}"
            order["payment_link"] = short_url
            _persist_all()
            
            wa_message = (
                f"Thank you for confirming your order, {customer_name.split()[0]}! 🎉\n\n"
                f"[Demo Mode - Razorpay Credentials Not Configured]\n\n"
                f"Here's your mock payment link:\n\n"
                f"💳 *Amount:* ₹{amount:,.0f}\n"
                f"🔗 *Pay here:* {short_url}\n\n"
                f"Once payment is completed, your order will be shipped. Thank you! 🙏"
            )
            
            if _is_bridge_running():
                httpx.post(
                    f"{BRIDGE_API}/api/send",
                    json={"recipient": chat_jid, "message": wa_message},
                    timeout=10,
                )
            return

        # Real Razorpay link generation
        amount_paise = int(amount * 100)
        norm_phone = phone.replace(" ", "").replace("-", "")
        if not norm_phone.startswith("+"):
            if norm_phone.startswith("91") and len(norm_phone) == 12:
                norm_phone = "+" + norm_phone
            elif len(norm_phone) == 10:
                norm_phone = "+91" + norm_phone
            else:
                norm_phone = "+91" + norm_phone

        payload = {
            "amount": amount_paise,
            "currency": "INR",
            "accept_partial": False,
            "description": f"Payment for order {order_id}",
            "customer": {
                "name": customer_name,
                "contact": norm_phone,
                "email": "noreply@d2cflow.in",
            },
            "notify": {
                "sms": True,
                "email": False,
            },
            "reminder_enable": True,
            "notes": {
                "order_id": order_id,
                "source": "whatsapp_bot",
            },
            "callback_url": f"{get_settings().app_base_url}/api/payments/webhook",
            "callback_method": "get",
        }

        with httpx.Client(timeout=20) as client:
            resp = client.post(
                f"{RAZORPAY_BASE}/payment_links",
                auth=auth,
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()

        short_url = data.get("short_url")
        if not short_url:
            return

        order["payment_link"] = short_url
        order["payment_link_id"] = data.get("id")
        _persist_all()

        wa_message = (
            f"Thank you for confirming your order, {customer_name.split()[0]}! 🎉\n\n"
            f"Here's your secure payment link powered by Razorpay:\n\n"
            f"💳 *Amount:* ₹{amount:,.0f}\n"
            f"🔗 *Pay here:* {short_url}\n\n"
            f"Once payment is completed, your order will be shipped. Thank you! 🙏"
        )

        if _is_bridge_running():
            httpx.post(
                f"{BRIDGE_API}/api/send",
                json={"recipient": chat_jid, "message": wa_message},
                timeout=10,
            )
            logger.info("Auto-sent Razorpay link to %s", chat_jid)

    except Exception as e:
        logger.error("Failed to auto-generate/send Razorpay payment link: %s", e)


# ── Confirmed order creator ───────────────────────────────────────────────────

def _create_confirmed_order(chat_jid: str) -> Optional[dict]:
    state = _conversation_states.get(chat_jid)
    if not state or state.get("state") != "waiting_confirm":
        return None

    chat = next((c for c in _monitored_chats if c["chat_jid"] == chat_jid), None)
    customer_name = (chat or {}).get("customer_name", "Customer")
    
    # Multiple items support
    items = state.get("items")
    if items:
        for item in items:
            p_id = item.get("product_id")
            if p_id:
                _deduct_stock(p_id, item.get("qty", 1))
        qty = sum(item.get("qty", 1) for item in items)
        price = state.get("price") or 0.0
        product_name = state.get("product_name", "WhatsApp Order")
    else:
        qty = state.get("qty", 1)
        price = state.get("price") or 0.0
        product_name = state.get("product_name", "WhatsApp Order")
        product_id = state.get("product_id")
        if product_id:
            _deduct_stock(product_id, qty)
        items = [{"name": product_name, "product_id": product_id, "qty": qty, "price": price}]

    order = {
        "id": f"WA-{uuid.uuid4().hex[:8].upper()}",
        "channel": "whatsapp",
        "chat_jid": chat_jid,
        "customer_name": customer_name,
        "customer_phone": chat_jid.split("@")[0].split("-")[0],
        "message_text": f"Customer confirmed order for {product_name}",
        "product_hint": product_name,
        "product_id": items[0].get("product_id") if items else None,
        "qty": qty,
        "price": price / qty if qty else price,
        "total": price,
        "catalog_price": price / qty if qty else price,
        "items": items,
        "confidence": 1.0,
        "status": "confirmed",
        "detected_at": datetime.now(timezone.utc).isoformat(),
        "confirmed_at": datetime.now(timezone.utc).isoformat(),
        "message_id": str(uuid.uuid4()),
        "source": "whatsapp_confirmation",
    }
    _detected_orders.append(order)
    _conversation_states[chat_jid]["state"] = "idle"
    _persist_all()

    # Generate and send Razorpay payment link automatically
    _generate_and_send_payment_link(order)

    return {
        "order": order,
        "localStorage_payload": {
            "customer": customer_name,
            "items": items,
            "price": price,
            "status": "new",
            "channel": "whatsapp",
            "chat_jid": chat_jid,
        },
    }


# ── Core scan logic ───────────────────────────────────────────────────────────

def _run_scan_and_draft(chat_jid: Optional[str] = None) -> dict:
    products = _get_products()
    new_detections = 0
    new_drafts = 0
    existing_msg_ids = {o.get("message_id") for o in _detected_orders if o.get("message_id")}
    existing_detection_ids = {r["detection_id"] for r in _drafted_replies}

    chats_to_scan = (
        [c for c in _monitored_chats if c["chat_jid"] == chat_jid]
        if chat_jid else list(_monitored_chats)
    )
    total_messages = 0

    for chat in chats_to_scan:
        jid = chat["chat_jid"]

        # Skip only if there's a confirmed order AFTER the current broadcast was sent
        # (allows same contact to place new orders after fresh broadcasts)
        state = _conversation_states.get(jid, {})
        sent_at_str = state.get("sent_at", "")
        if sent_at_str:
            try:
                sent_dt = datetime.fromisoformat(sent_at_str.replace("Z", "+00:00"))
                already_confirmed = any(
                    o.get("chat_jid") == jid and o.get("status") == "confirmed"
                    and datetime.fromisoformat(str(o.get("confirmed_at","")).replace("Z","+00:00")) >= sent_dt
                    for o in _detected_orders
                    if o.get("confirmed_at")
                )
                if already_confirmed:
                    continue
            except Exception:
                pass

        cutoff_24h = datetime.now(timezone.utc) - timedelta(hours=24)
        last_scanned_str = chat.get("last_scanned")

        # If we're waiting for a YES, look back to when we sent the offer (not just last scan)
        state_for_jid = _conversation_states.get(jid, {})
        waiting_sent_at = state_for_jid.get("sent_at") if state_for_jid.get("state") == "waiting_confirm" else None

        if last_scanned_str:
            try:
                last_dt = datetime.fromisoformat(last_scanned_str.replace("Z", "+00:00"))
                after_dt = min(last_dt, cutoff_24h)
            except Exception:
                after_dt = cutoff_24h
        else:
            after_dt = datetime.now(timezone.utc) - timedelta(days=7)

        # Also check from when we sent the offer if waiting — customer may have replied before last scan
        if waiting_sent_at:
            try:
                sent_dt = datetime.fromisoformat(waiting_sent_at.replace("Z", "+00:00"))
                after_dt = min(after_dt, sent_dt)  # go back as far as the sent time
            except Exception:
                pass

        # Resolve LID aliases — WhatsApp may store the contact under a different JID
        jids_to_scan = _resolve_jid_aliases(jid)

        messages = []
        for scan_jid in jids_to_scan:
            messages.extend(_wa_list_messages(scan_jid, limit=500, after_iso=after_dt.isoformat()))
        total_messages += len(messages)

        for msg in messages:
            msg_id = msg.get("id")
            if msg_id and msg_id in existing_msg_ids:
                continue
            text = msg.get("text") or ""
            if not text:
                continue

            text_lower = text.lower()
            if any(kw in text_lower for kw in CONFIRMATION_KEYWORDS):
                _check_for_customer_confirmation(jid, text, msg)

            intent = _detect_order_intent(text, products)
            if not intent:
                continue

            customer_name = chat.get("customer_name") or msg.get("sender") or "Unknown"
            detection = {
                "id": str(uuid.uuid4()),
                "chat_jid": jid,
                "customer_name": customer_name,
                "message_text": text,
                "product_hint": intent["product_hint"],
                "product_id": intent["product_id"],
                "product_sku": intent["product_sku"],
                "catalog_price": intent["catalog_price"],
                "in_catalog": intent["in_catalog"],
                "qty": intent["qty"],
                "price": intent["price_hint"],
                "confidence": intent["confidence"],
                "status": "pending",
                "detected_at": datetime.now(timezone.utc).isoformat(),
                "message_id": msg_id,
                "message_timestamp": msg.get("timestamp"),
                "sender": msg.get("sender"),
            }
            _detected_orders.append(detection)
            if msg_id:
                existing_msg_ids.add(msg_id)
            new_detections += 1
            chat["order_count"] = chat.get("order_count", 0) + 1

            if detection["id"] not in existing_detection_ids:
                draft = _create_draft_reply(detection)
                _drafted_replies.append(draft)
                existing_detection_ids.add(detection["id"])
                new_drafts += 1

    now = datetime.now(timezone.utc).isoformat()
    for c in chats_to_scan:
        c["last_scanned"] = now
    _save_json(_CHATS_FILE, _monitored_chats)
    _persist_all()

    return {
        "scanned_chats": len(chats_to_scan),
        "messages_read": total_messages,
        "new_detections": new_detections,
        "new_drafts": new_drafts,
        "total_pending": sum(1 for o in _detected_orders if o["status"] == "pending"),
        "source": "real_whatsapp_db",
    }


def _check_for_customer_confirmation(chat_jid: str, text: str, msg: dict) -> None:
    """
    Called whenever a YES/confirm message is detected in a monitored chat.
    Flow: customer asks for product → system offers it with price → customer says YES → order created.
    We look for a draft/sent reply for this chat (meaning we already offered the product),
    then directly create a confirmed order using the product info stored in _conversation_states.
    """
    state = _conversation_states.get(chat_jid, {})

    # Parse the message timestamp
    msg_ts_str = str(msg.get("timestamp", "")).replace(" ", "T")
    try:
        msg_dt = datetime.fromisoformat(msg_ts_str)
        if msg_dt.tzinfo is None:
            msg_dt = msg_dt.replace(tzinfo=timezone.utc)
    except Exception:
        msg_dt = datetime.now(timezone.utc)

    # Don't re-trigger if we already created a confirmed order for a message at this exact timestamp
    already_confirmed = any(
        o.get("chat_jid") == chat_jid
        and o.get("status") == "confirmed"
        and o.get("confirmation_msg_ts") == msg_dt.isoformat()
        for o in _detected_orders
    )
    if already_confirmed:
        return

    # Need either a draft/sent reply (inbound flow) or a waiting_confirm state (CRM flow)
    has_offered = (
        state.get("state") in ("waiting_confirm",)
        or any(r["chat_jid"] == chat_jid and r["status"] in ("draft", "sent") for r in _drafted_replies)
    )
    if not has_offered:
        return

    # Get product info from state (set when draft was created) or from latest sent reply
    product_name = state.get("product_name", "")
    product_id = state.get("product_id", "")
    price = state.get("price", 0.0)
    qty = state.get("qty", 1)
    items = state.get("items")

    # Fall back to latest draft/sent reply if state doesn't have product info
    if not product_name and not items:
        replies = [r for r in _drafted_replies if r["chat_jid"] == chat_jid]
        if replies:
            latest = sorted(replies, key=lambda r: r.get("created_at", ""), reverse=True)[0]
            product_name = latest.get("product_name", "")
            product_id = latest.get("product_id") or ""
            price = latest.get("catalog_price") or latest.get("product_price") or 0.0
            qty = latest.get("qty", 1)

    chat = next((c for c in _monitored_chats if c["chat_jid"] == chat_jid), None)
    customer_name = (chat or {}).get("customer_name", "Customer")

    if items:
        for item in items:
            p_id = item.get("product_id")
            if p_id:
                _deduct_stock(p_id, item.get("qty", 1))
        total = state.get("total") or price
        product_hint = product_name or ", ".join(item.get("name") for item in items)
    else:
        if product_id:
            _deduct_stock(product_id, qty)
        items = [{"name": product_name or "WhatsApp Order", "product_id": product_id, "qty": qty, "price": price}]
        total = price * qty
        product_hint = product_name or "WhatsApp Order"

    order = {
        "id": f"WA-{uuid.uuid4().hex[:8].upper()}",
        "channel": "whatsapp",
        "chat_jid": chat_jid,
        "customer_name": customer_name,
        "customer_phone": chat_jid.split("@")[0].split("-")[0],
        "message_text": text,
        "product_hint": product_hint,
        "product_id": product_id or (items[0].get("product_id") if items else None),
        "items": items,
        "qty": qty,
        "price": price / qty if qty and not items else price,
        "total": total,
        "catalog_price": price / qty if qty and not items else price,
        "confidence": 1.0,
        "status": "confirmed",
        "detected_at": datetime.now(timezone.utc).isoformat(),
        "confirmed_at": datetime.now(timezone.utc).isoformat(),
        "confirmation_msg_ts": msg_dt.isoformat(),
        "message_id": msg.get("id", str(uuid.uuid4())),
        "source": "whatsapp_inbound",
        "notes": f"Customer confirmed: '{text}'",
    }
    _detected_orders.append(order)

    # Reset conversation state
    if state:
        _conversation_states[chat_jid]["state"] = "idle"

    _persist_all()
    logger.info("Inbound confirmation: order %s created for %s product=%s", order["id"], customer_name, product_hint)
    
    # Auto-generate and send payment link
    _generate_and_send_payment_link(order)



def _run_check_confirmations() -> dict:
    """
    Check each pending broadcast for a YES reply with a NEW timestamp.
    Key insight: if msg timestamp > last_confirmed_message_ts (or > sent_at for first YES),
    it's a brand-new confirmation — create an order and record this timestamp.
    This way multiple broadcasts to the same contact are handled independently.
    """
    checked = 0
    confirmed_count = 0
    orders_created = []

    for broadcast in _pending_broadcasts:
        if broadcast.get("confirmed"):
            continue  # already confirmed

        jid = broadcast["jid"]
        sent_at_str = broadcast.get("sent_at", "")
        last_ts_str = broadcast.get("last_confirmed_message_ts")

        # Parse cutoff: use last_confirmed_message_ts if set, else sent_at
        cutoff_str = last_ts_str if last_ts_str else sent_at_str
        try:
            cutoff_dt = datetime.fromisoformat(cutoff_str.replace("Z", "+00:00")) if cutoff_str else None
        except Exception:
            cutoff_dt = None

        checked += 1
        is_group = jid.endswith("@g.us")

        for msg in _wa_list_all_messages(jid, limit=50):
            # Groups: YES is sent by Raktim himself (is_from_me=1); DMs: customer replies (is_from_me=0)
            if is_group:
                if msg.get("is_from_me", 0) != 1:
                    continue  # groups: only our own sent messages count as replies
            else:
                if msg.get("is_from_me", 1) == 1:
                    continue  # DMs: skip our own messages

            # Parse message timestamp
            try:
                raw_ts = str(msg.get("timestamp", "")).replace(" ", "T")
                msg_dt = datetime.fromisoformat(raw_ts)
                if msg_dt.tzinfo is None:
                    msg_dt = msg_dt.replace(tzinfo=timezone.utc)
            except Exception:
                continue

            # Must be strictly NEWER than cutoff to be a new order
            if cutoff_dt and msg_dt <= cutoff_dt:
                continue

            # Skip very old messages (>7 days) as safety
            if msg_dt < datetime.now(timezone.utc) - timedelta(days=7):
                continue

            text = (msg.get("text") or "").strip().lower()
            if any(kw in text for kw in CONFIRMATION_KEYWORDS):
                # This is a new YES — create order using broadcast product info
                result = _create_confirmed_order_from_broadcast(jid, broadcast)
                if result:
                    confirmed_count += 1
                    orders_created.append(result)
                    # Mark this broadcast confirmed and record the message timestamp
                    broadcast["confirmed"] = True
                    broadcast["last_confirmed_message_ts"] = msg_dt.isoformat()
                    broadcast["confirmed_at"] = datetime.now(timezone.utc).isoformat()
                    _persist_all()
                    logger.info("New YES detected for broadcast %s jid=%s msg_ts=%s", broadcast["id"], jid, msg_dt.isoformat())
                break

    return {"checked": checked, "confirmed": confirmed_count, "orders_created": orders_created}


def _create_confirmed_order_from_broadcast(jid: str, broadcast: dict) -> Optional[dict]:
    """Create a confirmed order from a pending broadcast entry."""
    chat = next((c for c in _monitored_chats if c["chat_jid"] == jid), None)
    customer_name = broadcast.get("customer_name") or (chat.get("customer_name") if chat else jid)
    product_name = broadcast.get("product_name", "Unknown Product")
    product_id = broadcast.get("product_id", "")
    price = broadcast.get("price", 0.0)
    qty = broadcast.get("qty", 1)

    now_iso = datetime.now(timezone.utc).isoformat()
    order = {
        "id": f"WA-{uuid.uuid4().hex[:8].upper()}",
        "channel": "whatsapp",
        "customer_name": customer_name,
        "customer_phone": jid.split("@")[0].split("-")[0],
        "chat_jid": jid,
        "product_hint": product_name,
        "product_id": product_id,
        "qty": qty,
        "price": price,
        "catalog_price": price,
        "items": [{"name": product_name, "product_id": product_id, "qty": qty, "price": price}],
        "total": price * qty,
        "confidence": 1.0,
        "status": "confirmed",
        "detected_at": now_iso,
        "confirmed_at": now_iso,
        "created_at": now_iso,
        "broadcast_id": broadcast.get("id", ""),
        "source": "crm_broadcast",
        "notes": "Auto-confirmed via WhatsApp YES reply",
    }
    _detected_orders.append(order)
    _persist_all()
    logger.info("Order created from broadcast: %s customer=%s product=%s", order["id"], customer_name, product_name)
    
    # Auto-generate and send payment link
    _generate_and_send_payment_link(order)
    
    return order


def _scan_self_sent_confirmations() -> dict:
    """
    Detect orders from broadcasts sent DIRECTLY via WhatsApp (not via CRM tool).
    Pattern: Raktim sends offer message (is_from_me=1) → then sends YES/BUY (is_from_me=1).
    Works for both groups and DMs. Extracts product+price from the offer message text.
    """
    created = 0
    orders_created = []

    # Get all confirmed orders timestamps per JID to avoid re-creating
    confirmed_ts_by_jid: dict = {}
    for o in _detected_orders:
        if o.get("status") == "confirmed":
            jid = o.get("chat_jid", "")
            ts = o.get("confirmation_msg_ts") or o.get("confirmed_at") or ""
            if jid not in confirmed_ts_by_jid or ts > confirmed_ts_by_jid[jid]:
                confirmed_ts_by_jid[jid] = ts

    for chat in _monitored_chats:
        jid = chat["chat_jid"]
        # Get recent messages from both directions — include sent messages
        msgs = []
        for alias_jid in _resolve_jid_aliases(jid):
            try:
                conn = sqlite3.connect(WHATSAPP_DB_PATH)
                conn.row_factory = sqlite3.Row
                cur = conn.cursor()
                # Look back 48 hours
                cutoff = (datetime.now(timezone.utc) - timedelta(hours=48)).isoformat().replace("+00:00", "")
                cur.execute(
                    """SELECT id, chat_jid, sender, content AS text, timestamp, is_from_me
                       FROM messages WHERE chat_jid = ? AND timestamp > ?
                       ORDER BY timestamp ASC""",
                    (alias_jid, cutoff),
                )
                msgs.extend(dict(r) for r in cur.fetchall())
                conn.close()
            except Exception as e:
                logger.error("_scan_self_sent_confirmations DB error (%s): %s", alias_jid, e)

        if not msgs:
            continue

        # Walk messages looking for: sent offer → sent YES (within next ~5 messages or 10 minutes)
        for i, msg in enumerate(msgs):
            if msg.get("is_from_me") != 1:
                continue
            text = (msg.get("text") or "").strip()
            if not text:
                continue

            # Is this an offer message? Look for price pattern (₹XXXX or Rs.XXXX)
            price_match = re.search(r'[₹Rs\.]+\s*(\d[\d,]*)', text)
            if not price_match:
                continue

            try:
                price = float(price_match.group(1).replace(",", ""))
            except Exception:
                continue

            # Parse offer timestamp
            try:
                offer_ts_raw = str(msg.get("timestamp", "")).replace(" ", "T")
                offer_dt = datetime.fromisoformat(offer_ts_raw)
                if offer_dt.tzinfo is None:
                    offer_dt = offer_dt.replace(tzinfo=timezone.utc)
            except Exception:
                continue

            # Look at next 10 messages or within 10 minutes for YES/BUY
            for j in range(i + 1, min(i + 15, len(msgs))):
                follow = msgs[j]
                if follow.get("is_from_me") != 1:
                    continue
                follow_text = (follow.get("text") or "").strip().lower()
                if not any(kw in follow_text for kw in CONFIRMATION_KEYWORDS):
                    continue

                # Parse YES timestamp
                try:
                    yes_ts_raw = str(follow.get("timestamp", "")).replace(" ", "T")
                    yes_dt = datetime.fromisoformat(yes_ts_raw)
                    if yes_dt.tzinfo is None:
                        yes_dt = yes_dt.replace(tzinfo=timezone.utc)
                except Exception:
                    continue

                # Must be within 30 minutes of offer
                if (yes_dt - offer_dt).total_seconds() > 1800:
                    break

                # Check not already confirmed at this timestamp
                already = any(
                    o.get("chat_jid") == jid and o.get("confirmation_msg_ts") == yes_dt.isoformat()
                    for o in _detected_orders
                )
                if already:
                    break

                # Also skip if confirmed_at for this JID is newer than this YES
                last_confirmed = confirmed_ts_by_jid.get(jid, "")
                if last_confirmed and yes_dt.isoformat() <= last_confirmed:
                    break

                # Extract product name — first bold word or product keyword in offer
                product_name = ""
                bold_match = re.search(r'\*([^*]+)\*', text)
                if bold_match:
                    product_name = bold_match.group(1).strip()
                # Try matching against catalog
                products = _get_products()
                matched_product = None
                if product_name:
                    matched_product = _get_product_by_name(product_name)
                if not matched_product:
                    # Try to match any product name found in the offer text
                    for p in products:
                        if p.get("name", "").lower() in text.lower():
                            matched_product = p
                            product_name = p["name"]
                            break

                product_id = matched_product.get("id", "") if matched_product else ""
                if not product_name:
                    product_name = "WhatsApp Order"

                customer_name = chat.get("customer_name", jid)
                now_iso = datetime.now(timezone.utc).isoformat()
                order = {
                    "id": f"WA-{uuid.uuid4().hex[:8].upper()}",
                    "channel": "whatsapp",
                    "chat_jid": jid,
                    "customer_name": customer_name,
                    "customer_phone": jid.split("@")[0].split("-")[0],
                    "product_hint": product_name,
                    "product_id": product_id,
                    "qty": 1,
                    "price": price,
                    "total": price,
                    "catalog_price": price,
                    "items": [{"name": product_name, "product_id": product_id, "qty": 1, "price": price}],
                    "confidence": 0.9,
                    "status": "confirmed",
                    "detected_at": now_iso,
                    "confirmed_at": now_iso,
                    "created_at": now_iso,
                    "confirmation_msg_ts": yes_dt.isoformat(),
                    "offer_msg_ts": offer_dt.isoformat(),
                    "source": "whatsapp_self_confirmed",
                    "notes": f"Offer: '{text[:80]}' → YES: '{follow_text}'",
                }
                _detected_orders.append(order)
                confirmed_ts_by_jid[jid] = yes_dt.isoformat()
                created += 1
                orders_created.append(order)
                logger.info("Self-sent confirmation detected: order %s jid=%s product=%s price=%.0f", order["id"], jid, product_name, price)
                _persist_all()
                break  # one YES per offer

    return {"created": created, "orders": orders_created}


# ── Auto-scanner ──────────────────────────────────────────────────────────────

_wa_scheduler = BackgroundScheduler(timezone="Asia/Kolkata")
_last_scan_time: Optional[datetime] = None


def _auto_scan_job() -> None:
    global _last_scan_time
    if not _monitored_chats:
        return
    try:
        result = _run_scan_and_draft()
        _last_scan_time = datetime.now(timezone.utc)
        logger.info("Auto-scan: %d detection(s), %d draft(s)", result["new_detections"], result["new_drafts"])
        _run_check_confirmations()
        self_result = _scan_self_sent_confirmations()
        if self_result["created"] > 0:
            logger.info("Self-sent confirmations: %d new order(s)", self_result["created"])
    except Exception as e:
        logger.error("Auto-scan failed: %s", e)


try:
    _wa_scheduler.add_job(_auto_scan_job, "interval", minutes=2, id="wa_auto_scan", replace_existing=True)
    _wa_scheduler.start()
    logger.info("WhatsApp auto-scanner started (every 2 min)")
except Exception as e:
    logger.warning("Could not start WhatsApp auto-scanner: %s", e)

# Auto-start bridge only if the binary exists (local dev only)
if os.path.exists(BRIDGE_BINARY):
    try:
        _start_bridge()
    except Exception as e:
        logger.warning("Could not auto-start WhatsApp bridge: %s", e)


# ── Pydantic models ───────────────────────────────────────────────────────────

class AddChatPayload(BaseModel):
    chat_name: str
    chat_jid: str
    customer_name: str


class BulkAddChatsEntry(BaseModel):
    chat_jid: str
    chat_name: str
    customer_name: str


class BulkAddChatsPayload(BaseModel):
    chats: List[BulkAddChatsEntry]


class ConfirmOrderPayload(BaseModel):
    order_id: str


class RejectOrderPayload(BaseModel):
    order_id: str


class IncomingMessage(BaseModel):
    chat_jid: str
    message_id: Optional[str] = None
    sender: Optional[str] = None
    text: str
    timestamp: Optional[str] = None


class IncomingMessageBatch(BaseModel):
    chat_jid: str
    messages: List[IncomingMessage]


class ReplyIdPayload(BaseModel):
    reply_id: str


class EditReplyPayload(BaseModel):
    reply_id: str
    message: str


class ConfirmFromWAPayload(BaseModel):
    confirmation_id: str


class SyncProductsPayload(BaseModel):
    products: List[dict]


class DirectMessagePayload(BaseModel):
    jid: str
    message: str
    # Optional — set these when the message is a product offer expecting a YES reply
    product_name: Optional[str] = None
    product_id: Optional[str] = None
    price: Optional[float] = None
    qty: Optional[int] = 1
    customer_name: Optional[str] = None  # resolved name of the recipient
    track_reply: bool = False            # set True to watch for YES reply


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/bridge-status")
async def bridge_status():
    running = _is_bridge_running()
    authenticated = _is_bridge_authenticated()
    connected = running and (authenticated or _wa_connected)
    qr_available = _qr_code_b64 is not None
    return {
        "connected": connected,
        "qr_available": qr_available,
        "qr_b64": _qr_code_b64 if qr_available else None,
        "status": "connected" if connected else ("qr_pending" if qr_available else "offline"),
        "bridge_running": running,
        "authenticated": authenticated,
    }


@router.get("/qr")
async def get_qr():
    if _is_bridge_authenticated() or _wa_connected:
        return {"status": "scanned", "qr_b64": None, "message": "Already authenticated."}
    if _qr_code_b64:
        return {"status": "pending", "qr_b64": _qr_code_b64}
    if not os.path.exists(BRIDGE_BINARY):
        return {"status": "unavailable", "qr_b64": None, "message": "Bridge binary not found."}
    _start_bridge()
    return {"status": "pending", "qr_b64": _qr_code_b64}


@router.post("/start-bridge")
async def start_bridge_endpoint():
    if _is_bridge_running():
        return {"started": False, "message": "Bridge already running", "authenticated": _is_bridge_authenticated()}
    if not os.path.exists(BRIDGE_BINARY):
        raise HTTPException(status_code=503, detail=f"Bridge binary not found at {BRIDGE_BINARY}.")
    started = _start_bridge()
    return {"started": started, "message": "Bridge started." if started else "Failed to start bridge."}


@router.post("/messages")
async def receive_messages(payload: IncomingMessageBatch):
    """
    Ingest a batch of incoming messages and write them to the local SQLite database.
    Required by wa_scanner.py to push messages from production/remote bridges.
    """
    buffered = 0
    try:
        conn = sqlite3.connect(WHATSAPP_DB_PATH)
        cur = conn.cursor()
        
        # Ensure chat exists in chats table
        cur.execute("SELECT COUNT(*) FROM chats WHERE jid = ?", (payload.chat_jid,))
        if cur.fetchone()[0] == 0:
            cur.execute(
                "INSERT INTO chats (jid, name, last_message_time) VALUES (?, ?, ?)",
                (payload.chat_jid, payload.chat_jid.split("@")[0], datetime.now(timezone.utc).isoformat())
            )
            
        for msg in payload.messages:
            msg_id = msg.message_id or str(uuid.uuid4())
            # Use INSERT OR IGNORE to prevent duplicates
            cur.execute(
                """INSERT OR IGNORE INTO messages (id, chat_jid, sender, content, timestamp, is_from_me)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    msg_id,
                    payload.chat_jid,
                    msg.sender or "Customer",
                    msg.text,
                    msg.timestamp or datetime.now(timezone.utc).isoformat(),
                    1 if msg.sender == "me" else 0
                )
            )
            if cur.rowcount > 0:
                buffered += 1
                
        # Update last_message_time in chats
        if payload.messages:
            last_msg = payload.messages[-1]
            cur.execute(
                "UPDATE chats SET last_message_time = ? WHERE jid = ?",
                (last_msg.timestamp or datetime.now(timezone.utc).isoformat(), payload.chat_jid)
            )
            
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error("Failed to buffer messages: %s", e)
        raise HTTPException(status_code=500, detail=f"Failed to buffer messages: {e}")
        
    return {"buffered": buffered, "total_buffer": len(payload.messages)}



@router.get("/search-chats")
async def search_chats(q: Optional[str] = None, limit: int = 40):
    chats = _wa_list_chats(query=q, limit=limit)
    return {"chats": chats, "total": len(chats), "source": "real"}


@router.post("/add-chat")
async def add_chat(payload: AddChatPayload):
    jid = payload.chat_jid.strip()
    if any(c["chat_jid"] == jid for c in _monitored_chats):
        raise HTTPException(status_code=409, detail="Chat already monitored")
    entry = {
        "chat_jid": jid,
        "chat_name": payload.chat_name.strip(),
        "customer_name": payload.customer_name.strip(),
        "added_at": datetime.now(timezone.utc).isoformat(),
        "last_scanned": None,
        "order_count": 0,
    }
    _monitored_chats.append(entry)
    _save_json(_CHATS_FILE, _monitored_chats)
    return {"status": "added", "chat": entry}


@router.post("/bulk-add-chats")
async def bulk_add_chats(payload: BulkAddChatsPayload):
    added, skipped, new_chats = 0, 0, []
    for entry in payload.chats:
        jid = entry.chat_jid.strip()
        if any(c["chat_jid"] == jid for c in _monitored_chats):
            skipped += 1
            continue
        chat_entry = {
            "chat_jid": jid,
            "chat_name": entry.chat_name.strip(),
            "customer_name": entry.customer_name.strip(),
            "added_at": datetime.now(timezone.utc).isoformat(),
            "last_scanned": None,
            "order_count": 0,
        }
        _monitored_chats.append(chat_entry)
        new_chats.append(chat_entry)
        added += 1
    _save_json(_CHATS_FILE, _monitored_chats)
    return {"added": added, "skipped": skipped, "chats": new_chats}


@router.get("/chats")
async def list_chats():
    return {"chats": _monitored_chats, "total": len(_monitored_chats)}


@router.delete("/chats/{jid:path}")
async def remove_chat(jid: str):
    global _monitored_chats
    before = len(_monitored_chats)
    _monitored_chats = [c for c in _monitored_chats if c["chat_jid"] != jid]
    if len(_monitored_chats) == before:
        raise HTTPException(status_code=404, detail="Chat not found")
    _save_json(_CHATS_FILE, _monitored_chats)
    return {"status": "removed", "chat_jid": jid}


@router.post("/scan")
async def scan_chats(chat_jid: Optional[str] = None):
    return _run_scan_and_draft(chat_jid=chat_jid)


@router.get("/detected-orders")
async def get_detected_orders(status: Optional[str] = None, chat_jid: Optional[str] = None):
    orders = _detected_orders[:]
    if status:
        orders = [o for o in orders if o["status"] == status]
    if chat_jid:
        orders = [o for o in orders if o["chat_jid"] == chat_jid]
    return {
        "orders": sorted(orders, key=lambda o: o.get("detected_at") or o.get("created_at") or "", reverse=True),
        "total": len(orders),
        "pending": sum(1 for o in _detected_orders if o["status"] == "pending"),
        "confirmed": sum(1 for o in _detected_orders if o["status"] == "confirmed"),
        "rejected": sum(1 for o in _detected_orders if o["status"] == "rejected"),
    }


@router.post("/confirm-order")
async def confirm_order(payload: ConfirmOrderPayload):
    order = next((o for o in _detected_orders if o["id"] == payload.order_id), None)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    if order["status"] != "pending":
        raise HTTPException(status_code=409, detail=f"Order already {order['status']}")
    order["status"] = "confirmed"
    order["confirmed_at"] = datetime.now(timezone.utc).isoformat()
    _persist_all()
    ls_order = {
        "customer": order["customer_name"],
        "items": [{
            "name": order["product_hint"] or "WhatsApp Order",
            "product_id": order.get("product_id"),
            "sku": order.get("product_sku"),
            "qty": order["qty"],
            "unit_price": order.get("catalog_price", 0),
        }],
        "price": (order.get("catalog_price") or 0) * order["qty"],
        "status": "new",
        "channel": "whatsapp",
        "source_message": order["message_text"],
        "chat_jid": order["chat_jid"],
    }
    return {"status": "confirmed", "order": order, "localStorage_payload": ls_order}


@router.post("/reject-order")
async def reject_order(payload: RejectOrderPayload):
    order = next((o for o in _detected_orders if o["id"] == payload.order_id), None)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    if order["status"] != "pending":
        raise HTTPException(status_code=409, detail=f"Order already {order['status']}")
    order["status"] = "rejected"
    order["rejected_at"] = datetime.now(timezone.utc).isoformat()
    _persist_all()
    return {"status": "rejected", "order": order}


@router.get("/products")
async def get_products_endpoint():
    products = _get_products()
    return {"products": products, "total": len(products)}


@router.post("/send-direct")
async def send_direct(payload: DirectMessagePayload):
    """
    Send a message directly to any JID — used by CRM broadcast.
    If product_name + track_reply=True are set, the JID is registered as
    waiting_confirm so any YES reply will auto-create an order.
    """
    if not _is_bridge_running():
        raise HTTPException(status_code=503, detail="WhatsApp bridge is not running.")
    try:
        with httpx.Client(timeout=8.0) as client:
            resp = client.post(
                f"{BRIDGE_API}/api/send",
                json={"recipient": payload.jid, "message": payload.message},
            )
            if resp.status_code >= 400:
                raise HTTPException(status_code=502, detail=f"Bridge error {resp.status_code}: {resp.text}")
    except httpx.ConnectError:
        raise HTTPException(status_code=503, detail="Cannot connect to WhatsApp bridge.")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Send failed: {e}")

    # ── Register waiting_confirm state so YES reply triggers order creation ──
    if payload.track_reply and payload.product_name:
        jid = payload.jid

        # Ensure this contact is in monitored chats (needed by _create_confirmed_order)
        if not any(c["chat_jid"] == jid for c in _monitored_chats):
            _monitored_chats.append({
                "chat_jid": jid,
                "chat_name": payload.customer_name or jid,
                "customer_name": payload.customer_name or jid,
                "added_at": datetime.now(timezone.utc).isoformat(),
                "source": "crm_broadcast",
            })
            _save_json(_CHATS_FILE, _monitored_chats)

        # Append a new broadcast entry — never overwrite, supports multiple orders per contact
        broadcast_entry = {
            "id": str(uuid.uuid4()),
            "jid": jid,
            "customer_name": payload.customer_name or jid,
            "product_name": payload.product_name,
            "product_id": payload.product_id or "",
            "price": payload.price or 0.0,
            "qty": payload.qty or 1,
            "sent_at": datetime.now(timezone.utc).isoformat(),
            "source": "crm_broadcast",
            "confirmed": False,
            "last_confirmed_message_ts": None,  # tracks last YES timestamp seen
        }
        _pending_broadcasts.append(broadcast_entry)
        # Keep legacy state in sync (for backward compat with other code that reads it)
        _conversation_states[jid] = {
            "state": "waiting_confirm",
            "product_name": payload.product_name,
            "product_id": payload.product_id or "",
            "price": payload.price or 0.0,
            "qty": payload.qty or 1,
            "sent_at": broadcast_entry["sent_at"],
            "source": "crm_broadcast",
        }
        _persist_all()
        logger.info("CRM broadcast: tracking YES reply for jid=%s product=%s broadcast_id=%s", jid, payload.product_name, broadcast_entry["id"])

    return {"sent": True, "jid": payload.jid, "tracking": payload.track_reply and bool(payload.product_name)}


@router.post("/sync-products")
async def sync_products(payload: SyncProductsPayload):
    global _synced_products
    _synced_products = payload.products
    logger.info("Product catalog synced: %d product(s)", len(_synced_products))
    return {"synced": len(_synced_products), "products": _synced_products}


def _replies_response(replies: List[dict]) -> dict:
    return {
        "replies": sorted(replies, key=lambda r: r["created_at"], reverse=True),
        "total": len(replies),
        "draft_count": sum(1 for r in _drafted_replies if r["status"] == "draft"),
        "sent_count": sum(1 for r in _drafted_replies if r["status"] == "sent"),
    }


@router.get("/draft-replies")
async def get_draft_replies(status: Optional[str] = None):
    replies = _drafted_replies[:]
    if status:
        replies = [r for r in replies if r["status"] == status]
    return _replies_response(replies)


@router.post("/send-reply")
async def send_reply(payload: ReplyIdPayload):
    reply = next((r for r in _drafted_replies if r["id"] == payload.reply_id), None)
    if not reply:
        raise HTTPException(status_code=404, detail="Reply not found")
    if reply["status"] != "draft":
        raise HTTPException(status_code=409, detail=f"Reply already {reply['status']}")
    if not _is_bridge_running():
        raise HTTPException(status_code=503, detail="WhatsApp bridge is not running.")
    try:
        with httpx.Client(timeout=5.0) as client:
            resp = client.post(
                f"{BRIDGE_API}/api/send",
                json={"recipient": reply["chat_jid"], "message": reply["draft_message"]},
            )
            if resp.status_code >= 400:
                raise HTTPException(status_code=502, detail=f"Bridge error {resp.status_code}: {resp.text}")
    except httpx.ConnectError:
        raise HTTPException(status_code=503, detail="Cannot connect to WhatsApp bridge.")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Send failed: {e}")

    sent_at = datetime.now(timezone.utc).isoformat()
    reply["status"] = "sent"
    reply["sent_at"] = sent_at

    jid = reply["chat_jid"]
    if jid in _conversation_states:
        _conversation_states[jid]["sent_at"] = sent_at

    _pending_confirmations.append({
        "id": str(uuid.uuid4()),
        "reply_id": reply["id"],
        "chat_jid": jid,
        "customer_name": reply.get("customer_name", "Customer"),
        "product_hint": reply.get("product_name", ""),
        "product_id": reply.get("product_id"),
        "qty": reply.get("qty", 1),
        "price": reply.get("catalog_price"),
        "created_at": sent_at,
        "confirmed": False,
        "auto_detected": False,
    })
    _persist_all()
    return {"sent": True, "message": "Reply sent successfully", "reply": reply}


@router.post("/skip-reply")
async def skip_reply(payload: ReplyIdPayload):
    reply = next((r for r in _drafted_replies if r["id"] == payload.reply_id), None)
    if not reply:
        raise HTTPException(status_code=404, detail="Reply not found")
    reply["status"] = "skipped"
    reply["skipped_at"] = datetime.now(timezone.utc).isoformat()
    _persist_all()
    return {"skipped": True, "reply": reply}


@router.post("/edit-reply")
async def edit_reply(payload: EditReplyPayload):
    reply = next((r for r in _drafted_replies if r["id"] == payload.reply_id), None)
    if not reply:
        raise HTTPException(status_code=404, detail="Reply not found")
    if reply["status"] != "draft":
        raise HTTPException(status_code=409, detail=f"Cannot edit a {reply['status']} reply")
    reply["draft_message"] = payload.message
    reply["message_text"] = payload.message
    reply["edited_at"] = datetime.now(timezone.utc).isoformat()
    _persist_all()
    return {"status": "edited", "reply": reply}


@router.post("/check-confirmations")
async def check_confirmations():
    result = _run_check_confirmations()
    self_result = _scan_self_sent_confirmations()
    return {**result, "self_sent_created": self_result["created"], "self_sent_orders": self_result["orders"]}


@router.get("/next-scan-in")
async def next_scan_in():
    try:
        job = _wa_scheduler.get_job("wa_auto_scan")
        if job and job.next_run_time:
            now = datetime.now(job.next_run_time.tzinfo)
            seconds = max(0, int((job.next_run_time - now).total_seconds()))
            return {"seconds": seconds, "next_at": job.next_run_time.isoformat()}
    except Exception:
        pass
    return {"seconds": 120, "next_at": None}


@router.get("/pending-confirmations")
async def get_pending_confirmations():
    return {
        "confirmations": sorted(_pending_confirmations, key=lambda c: c["created_at"], reverse=True),
        "total": len(_pending_confirmations),
        "waiting": sum(1 for c in _pending_confirmations if not c["confirmed"]),
        "confirmed": sum(1 for c in _pending_confirmations if c["confirmed"]),
    }


@router.get("/crm-funnel")
async def get_crm_funnel():
    """
    Returns CRM broadcast funnel data:
    - Per-contact: messages sent, whether waiting_confirm, whether confirmed
    - Group tracking: all group JIDs that have been messaged via CRM
    - Overall funnel counts
    """
    now = datetime.now(timezone.utc)

    # Build per-contact broadcast history from conversation states + detected orders
    broadcasts = []
    for jid, state in _conversation_states.items():
        if state.get("source") != "crm_broadcast":
            continue
        chat = next((c for c in _monitored_chats if c["chat_jid"] == jid), {})
        confirmed_order = next((o for o in _detected_orders if o.get("chat_jid") == jid and o["status"] == "confirmed"), None)
        sent_at = state.get("sent_at", "")
        broadcasts.append({
            "jid": jid,
            "name": chat.get("customer_name") or chat.get("chat_name") or jid,
            "is_group": jid.endswith("@g.us"),
            "product_name": state.get("product_name", ""),
            "price": state.get("price", 0),
            "sent_at": sent_at,
            "current_state": state.get("state", "idle"),
            "confirmed": confirmed_order is not None,
            "confirmed_at": confirmed_order.get("confirmed_at", "") if confirmed_order else "",
            "order_id": confirmed_order.get("id", "") if confirmed_order else "",
        })

    # Also include confirmed orders that came through crm_broadcast but state already moved to idle
    for order in _detected_orders:
        if order.get("source") != "crm_broadcast":
            continue
        jid = order.get("chat_jid", "")
        if any(b["jid"] == jid for b in broadcasts):
            continue
        chat = next((c for c in _monitored_chats if c["chat_jid"] == jid), {})
        broadcasts.append({
            "jid": jid,
            "name": chat.get("customer_name") or order.get("customer_name") or jid,
            "is_group": jid.endswith("@g.us"),
            "product_name": order.get("product_hint", ""),
            "price": order.get("price", 0),
            "sent_at": order.get("confirmed_at", ""),
            "current_state": "idle",
            "confirmed": order["status"] == "confirmed",
            "confirmed_at": order.get("confirmed_at", ""),
            "order_id": order.get("id", ""),
        })

    total_sent = len(broadcasts)
    total_confirmed = sum(1 for b in broadcasts if b["confirmed"])
    total_waiting = sum(1 for b in broadcasts if b["current_state"] == "waiting_confirm")
    groups = [b for b in broadcasts if b["is_group"]]
    individuals = [b for b in broadcasts if not b["is_group"]]

    return {
        "funnel": {
            "sent": total_sent,
            "waiting": total_waiting,
            "confirmed": total_confirmed,
            "conversion_rate": round(total_confirmed / total_sent * 100, 1) if total_sent else 0,
        },
        "broadcasts": sorted(broadcasts, key=lambda b: b.get("sent_at", ""), reverse=True),
        "groups": sorted(groups, key=lambda b: b.get("sent_at", ""), reverse=True),
        "individuals": sorted(individuals, key=lambda b: b.get("sent_at", ""), reverse=True),
    }


class ManualConfirmPayload(BaseModel):
    jid: str
    qty: Optional[int] = 1


@router.post("/crm-manual-confirm")
async def crm_manual_confirm(payload: ManualConfirmPayload):
    """Manually mark a CRM broadcast JID as confirmed — used when customer confirmed outside WhatsApp."""
    jid = payload.jid
    state = _conversation_states.get(jid)
    if not state:
        raise HTTPException(status_code=404, detail="No broadcast state found for this JID")
    if state.get("state") == "idle" and any(o.get("chat_jid") == jid and o.get("status") == "confirmed" for o in _detected_orders):
        return {"already_confirmed": True}

    # Force state to waiting_confirm if somehow it's idle but no confirmed order exists
    if state.get("state") != "waiting_confirm":
        state["state"] = "waiting_confirm"

    result = _create_confirmed_order(jid)
    if not result:
        raise HTTPException(status_code=500, detail="Could not create confirmed order")
    _persist_all()
    logger.info("Manual confirm for jid=%s order=%s", jid, result.get("id"))
    return {"confirmed": True, "order": result}


@router.post("/confirm-from-wa")
async def confirm_from_wa(payload: ConfirmFromWAPayload):
    conf = next((c for c in _pending_confirmations if c["id"] == payload.confirmation_id), None)
    if not conf:
        raise HTTPException(status_code=404, detail="Confirmation not found")
    conf["confirmed"] = True
    conf["manually_confirmed_at"] = datetime.now(timezone.utc).isoformat()
    _persist_all()
    if conf.get("product_id"):
        _deduct_stock(conf["product_id"], conf.get("qty", 1))
    ls_order = {
        "customer": conf["customer_name"],
        "items": [{
            "name": conf.get("product_hint", "WhatsApp Order"),
            "product_id": conf.get("product_id"),
            "qty": conf.get("qty", 1),
            "unit_price": conf.get("price") or 0,
        }],
        "price": (conf.get("price") or 0) * conf.get("qty", 1),
        "status": "new",
        "channel": "whatsapp",
        "chat_jid": conf["chat_jid"],
    }
    return {"status": "confirmed", "confirmation": conf, "localStorage_payload": ls_order}


# ------------------------------------------------------------------ #
# Available chats (all contacts + groups from bridge DB)
# ------------------------------------------------------------------ #

@router.get("/available-chats")
async def available_chats(query: Optional[str] = None, limit: int = 100):
    """
    All WhatsApp contacts and groups visible to the bridge — not just monitored ones.
    Used by the share panel to let the user pick recipients.
    """
    return {"chats": _wa_list_chats(query=query, limit=limit)}


# ------------------------------------------------------------------ #
# Bulk broadcast — send same message to multiple JIDs
# ------------------------------------------------------------------ #

class BroadcastBulkPayload(BaseModel):
    jids: List[str]
    message: str
    product_name: Optional[str] = None
    product_id: Optional[str] = None
    price: Optional[float] = None
    qty: Optional[int] = 1
    track_reply: bool = True


@router.post("/broadcast-bulk")
async def broadcast_bulk(payload: BroadcastBulkPayload):
    """
    Send the same message to multiple JIDs at 1 msg/sec.
    Substitutes {name} from the contacts table when a match is found.
    Appends each to _pending_broadcasts when track_reply=True.
    """
    import time as _time

    if not _is_bridge_running():
        raise HTTPException(status_code=503, detail="WhatsApp bridge is not running.")

    db = get_db()
    # Build JID → name map from contacts table
    try:
        all_contacts = db.table("contacts").select("whatsapp_jid, name").not_.is_("whatsapp_jid", "null").execute().data
        jid_to_name = {c["whatsapp_jid"]: c["name"] for c in all_contacts if c.get("whatsapp_jid")}
    except Exception:
        jid_to_name = {}

    sent, failed = [], []
    for jid in payload.jids:
        contact_name = jid_to_name.get(jid) or jid.replace("@s.whatsapp.net", "").replace("@g.us", "Group")
        message = payload.message.replace("{name}", contact_name)

        try:
            with httpx.Client(timeout=8.0) as client:
                resp = client.post(f"{BRIDGE_API}/api/send", json={"recipient": jid, "message": message})
                if resp.status_code >= 400:
                    failed.append({"jid": jid, "error": f"Bridge HTTP {resp.status_code}"})
                    continue
        except Exception as e:
            failed.append({"jid": jid, "error": str(e)})
            continue

        if payload.track_reply and payload.product_name:
            if not any(c["chat_jid"] == jid for c in _monitored_chats):
                _monitored_chats.append({
                    "chat_jid": jid,
                    "chat_name": contact_name,
                    "customer_name": contact_name,
                    "added_at": datetime.now(timezone.utc).isoformat(),
                    "source": "broadcast_bulk",
                })
            broadcast_entry = {
                "id": str(uuid.uuid4()),
                "jid": jid,
                "customer_name": contact_name,
                "product_name": payload.product_name,
                "product_id": payload.product_id or "",
                "price": payload.price or 0.0,
                "qty": payload.qty or 1,
                "sent_at": datetime.now(timezone.utc).isoformat(),
                "source": "broadcast_bulk",
                "confirmed": False,
                "last_confirmed_message_ts": None,
            }
            _pending_broadcasts.append(broadcast_entry)
            _conversation_states[jid] = {
                "state": "waiting_confirm",
                "product_name": payload.product_name,
                "product_id": payload.product_id or "",
                "price": payload.price or 0.0,
                "qty": payload.qty or 1,
                "sent_at": broadcast_entry["sent_at"],
                "source": "broadcast_bulk",
            }

        sent.append(jid)
        _time.sleep(1)  # 1 msg/sec — stay well under WhatsApp rate limits

    _persist_all()
    return {"sent": len(sent), "failed": failed, "tracking": payload.track_reply}


# ------------------------------------------------------------------ #
# Share catalog item — high-level wrapper over broadcast-bulk
# ------------------------------------------------------------------ #

class SharePayload(BaseModel):
    product_id: str
    contact_ids: List[str] = []      # contacts table IDs
    list_ids: List[str] = []         # contact_lists table IDs
    group_jids: List[str] = []       # raw group JIDs
    template: str = "offer"
    custom_message: Optional[str] = None
    track_reply: bool = True


@router.post("/share")
async def share_catalog_item(payload: SharePayload):
    """
    Share a product to any combination of contacts, broadcast lists, and groups.
    Resolves JIDs, generates per-recipient messages, delegates to broadcast-bulk logic.
    """
    from ..catalog.link_generator import generate_product_message, product_to_dict

    if not _is_bridge_running():
        raise HTTPException(status_code=503, detail="WhatsApp bridge is not running.")

    db = get_db()

    # 1. Load product
    product_row = db.table("products").select("*, skus(selling_price, mrp)").eq("id", payload.product_id).execute()
    if not product_row.data:
        raise HTTPException(status_code=404, detail="Product not found")
    product = product_to_dict(product_row.data[0])

    # 2. Resolve JIDs from contact_ids
    jid_name_map: dict[str, str] = {}
    if payload.contact_ids:
        rows = db.table("contacts").select("whatsapp_jid, name").in_("id", payload.contact_ids).not_.is_("whatsapp_jid", "null").execute().data
        for r in rows:
            if r.get("whatsapp_jid"):
                jid_name_map[r["whatsapp_jid"]] = r["name"]

    # 3. Resolve JIDs from list_ids
    if payload.list_ids:
        for list_id in payload.list_ids:
            members = db.table("contact_list_members").select("contacts(whatsapp_jid, name)").eq("list_id", list_id).execute().data
            for m in members:
                c = m.get("contacts") or {}
                if c.get("whatsapp_jid"):
                    jid_name_map[c["whatsapp_jid"]] = c.get("name", "")

    # 4. Add raw group JIDs
    for jid in payload.group_jids:
        if jid not in jid_name_map:
            jid_name_map[jid] = jid.replace("@g.us", "Group")

    if not jid_name_map:
        raise HTTPException(status_code=400, detail="No valid WhatsApp recipients resolved. Verify contacts are checked for WhatsApp.")

    import time as _time
    sent, failed = [], []
    for jid, contact_name in jid_name_map.items():
        if payload.custom_message:
            message = payload.custom_message.replace("{name}", contact_name)
        else:
            message = generate_product_message(product, payload.template, contact_name)

        try:
            with httpx.Client(timeout=8.0) as client:
                resp = client.post(f"{BRIDGE_API}/api/send", json={"recipient": jid, "message": message})
                if resp.status_code >= 400:
                    failed.append({"jid": jid, "error": f"Bridge HTTP {resp.status_code}"})
                    continue
        except Exception as e:
            failed.append({"jid": jid, "error": str(e)})
            continue

        if payload.track_reply:
            if not any(c["chat_jid"] == jid for c in _monitored_chats):
                _monitored_chats.append({
                    "chat_jid": jid, "chat_name": contact_name,
                    "customer_name": contact_name,
                    "added_at": datetime.now(timezone.utc).isoformat(),
                    "source": "share",
                })
            entry = {
                "id": str(uuid.uuid4()),
                "jid": jid, "customer_name": contact_name,
                "product_name": product["name"],
                "product_id": payload.product_id,
                "price": product.get("selling_price") or 0.0,
                "qty": 1,
                "sent_at": datetime.now(timezone.utc).isoformat(),
                "source": "share",
                "confirmed": False,
                "last_confirmed_message_ts": None,
            }
            _pending_broadcasts.append(entry)
            _conversation_states[jid] = {
                "state": "waiting_confirm",
                "product_name": product["name"],
                "product_id": payload.product_id,
                "price": entry["price"], "qty": 1,
                "sent_at": entry["sent_at"], "source": "share",
            }

        sent.append({"jid": jid, "name": contact_name})
        _time.sleep(1)

    _persist_all()
    return {
        "product": product["name"],
        "sent": len(sent),
        "recipients": sent,
        "failed": failed,
        "tracking": payload.track_reply,
    }
