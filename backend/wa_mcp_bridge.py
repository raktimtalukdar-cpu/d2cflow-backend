"""
WhatsApp MCP bridge — fetch messages for a given chat JID.

Reads from ~/.d2cflow/wa_messages/{chat_jid}.json if it exists.
Falls back to sample data for local testing.
"""

import json
import os
from pathlib import Path

MESSAGES_DIR = Path.home() / ".d2cflow" / "wa_messages"

SAMPLE_MESSAGES = [
    {
        "id": "msg_001",
        "sender": "Customer",
        "text": "Hi, I want to buy 2 pieces of Cotton Kurta. How much does it cost?",
        "timestamp": "2024-01-15T10:30:00Z",
    },
    {
        "id": "msg_002",
        "sender": "Customer",
        "text": "Do you have the Silk Saree available? I'm interested in ordering one.",
        "timestamp": "2024-01-15T10:35:00Z",
    },
    {
        "id": "msg_003",
        "sender": "Customer",
        "text": "Can I get 3 Jute Bags? What's the price for bulk order?",
        "timestamp": "2024-01-15T11:00:00Z",
    },
    {
        "id": "msg_004",
        "sender": "Customer",
        "text": "Just checking in, how are you?",
        "timestamp": "2024-01-15T11:15:00Z",
    },
    {
        "id": "msg_005",
        "sender": "Customer",
        "text": "I'll take the Linen Shirt × 1. Please send me the payment link. Rs. 1299 right?",
        "timestamp": "2024-01-15T11:30:00Z",
    },
]


def fetch_messages(chat_jid: str, limit: int = 50) -> list[dict]:
    """
    Return messages for a chat JID.

    Priority:
    1. Read from ~/.d2cflow/wa_messages/{safe_jid}.json
    2. Fall back to sample data

    Message format: [{id, sender, text, timestamp}]
    """
    # Sanitize JID for filesystem use
    safe_jid = chat_jid.replace("/", "_").replace("\\", "_").replace(":", "_")
    file_path = MESSAGES_DIR / f"{safe_jid}.json"

    if file_path.exists():
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                messages = json.load(f)
            if isinstance(messages, list):
                return messages[:limit]
        except Exception as e:
            print(f"[wa_mcp_bridge] Could not read {file_path}: {e}")

    # Return sample data with jid attached
    return [dict(m, chat_jid=chat_jid) for m in SAMPLE_MESSAGES[:limit]]


def save_test_messages(chat_jid: str, messages: list[dict]) -> None:
    """Helper to save test messages for a chat JID."""
    MESSAGES_DIR.mkdir(parents=True, exist_ok=True)
    safe_jid = chat_jid.replace("/", "_").replace("\\", "_").replace(":", "_")
    file_path = MESSAGES_DIR / f"{safe_jid}.json"
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(messages, f, indent=2, ensure_ascii=False)
    print(f"[wa_mcp_bridge] Saved {len(messages)} messages to {file_path}")


if __name__ == "__main__":
    # Quick test
    import sys
    jid = sys.argv[1] if len(sys.argv) > 1 else "919876543210@s.whatsapp.net"
    msgs = fetch_messages(jid)
    print(f"Fetched {len(msgs)} messages for {jid}")
    for m in msgs:
        print(f"  [{m.get('timestamp', '')}] {m.get('sender', '')}: {m.get('text', '')[:80]}")
