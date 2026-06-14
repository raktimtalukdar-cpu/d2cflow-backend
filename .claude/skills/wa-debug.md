---
name: wa-debug
description: Debug WhatsApp order sync and confirmation issues
---
# WhatsApp Debug Skill

## Flow Overview
Customer sends BUY/ORDER message → WhatsApp DB (messages.db) → `/api/whatsapp/scan` detects it → draft reply generated → reply sent via bridge → customer replies YES/CONFIRM → `/api/whatsapp/check-confirmations` confirms it → order saved to localStorage (d2cflow_orders)

## Step 1: Verify the bridge is running
```bash
curl http://localhost:8080/health
```
If down, restart the Go bridge: `cd ~/whatsapp-bridge && ./whatsapp-bridge`

## Step 2: Check monitored chats
```bash
curl http://localhost:8000/api/whatsapp/monitored-chats | jq '.'
```
If empty, go to CRM page → "Start Monitoring" for the relevant chat.

## Step 3: Trigger a scan manually
```bash
curl -X POST http://localhost:8000/api/whatsapp/scan | jq '.'
```
Look for `detected` count > 0. If 0, check that BUY/ORDER keywords are in `DETECTION_KEYWORDS` in `backend/routers/whatsapp.py`.

## Step 4: Check detected orders
```bash
curl http://localhost:8000/api/whatsapp/detected-orders | jq '.orders[]'
```
Orders in `pending_reply` state haven't had a reply sent yet. Orders in `awaiting_confirmation` are waiting for YES from the customer.

## Step 5: Check confirmations
```bash
curl -X POST http://localhost:8000/api/whatsapp/check-confirmations | jq '.'
```
This scans for YES/CONFIRM/BUY messages after the bot reply. Check `CONFIRMATION_KEYWORDS` in whatsapp.py if not matching.

## Step 6: Check localStorage sync
Open browser DevTools → Application → Local Storage → look for key `d2cflow_orders`.
Confirmed orders should appear here. If not, go to CRM page and click "Sync Confirmed → Orders" or wait 30s for auto-sync.

## Step 7: Check broadcasts
```bash
cat ~/.d2cflow/wa_broadcasts.json | jq '.'
```
Pending broadcasts show orders queued for WhatsApp broadcast messages.

## Common Issues
| Symptom | Root Cause | Fix |
|---------|-----------|-----|
| Scan returns 0 detected | Keywords not matched | Check DETECTION_KEYWORDS in whatsapp.py |
| Order stuck in awaiting_confirmation | Customer reply not matched | Check CONFIRMATION_KEYWORDS |
| Group messages missing | include_sent not set | Ensure @g.us JIDs use `include_sent=True` in DB query |
| Contact shows LID instead of name | Name not synced | Click "Sync from WhatsApp" in CRM page |
| Broadcast not queued | Order not confirmed | Confirm via `/api/whatsapp/check-confirmations` first |
| Bridge 404 | Wrong endpoint | Bridge API is at WHATSAPP_BRIDGE_API env var (default: http://localhost:8080) |

## Useful one-liners
```bash
# Full debug cycle
curl -X POST http://localhost:8000/api/whatsapp/scan && \
curl -X POST http://localhost:8000/api/whatsapp/check-confirmations && \
curl http://localhost:8000/api/whatsapp/detected-orders | jq '.orders[] | {id, status, phone, product}'

# Check health with metrics
curl http://localhost:8000/health/detailed | jq '.'
```
