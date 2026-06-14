---
name: order-debug  
description: Debug why an order isn't appearing in the Orders page
---
# Order Debug Skill

## Flow Overview
Customer message → WhatsApp DB → scan → detection → draft reply → send reply → customer YES → confirmation → localStorage

## Step 1: Check backend has the order
```bash
curl http://localhost:8000/api/whatsapp/detected-orders | jq '.orders[] | select(.status=="confirmed")'
```

## Step 2: Check if it's in localStorage  
Open browser DevTools → Application → Local Storage → d2cflow_orders

## Step 3: Force sync
Go to CRM page — auto-sync runs every 30 seconds, or click "Sync Confirmed → Orders"

## Step 4: Check scan window
```bash
curl -X POST http://localhost:8000/api/whatsapp/scan
curl -X POST http://localhost:8000/api/whatsapp/check-confirmations
```

## Common Issues
- BUY/YES not in CONFIRMATION_KEYWORDS → check backend/routers/whatsapp.py
- Group messages not fetched → ensure @g.us JIDs use include_sent=True query
- Broadcast not in _pending_broadcasts → check wa_broadcasts.json in ~/.d2cflow/
- Contact shows LID instead of name → click "Sync from WhatsApp" in CRM page
