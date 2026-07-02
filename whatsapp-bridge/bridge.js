/**
 * WhatsApp Bridge — Baileys-based
 * Exposes the same HTTP API the Python backend expects:
 *   POST /api/send        { recipient, message }
 *   GET  /                health check
 *   GET  /api/status      connection + QR state
 *
 * Incoming messages are forwarded to the Python backend via webhook.
 */

const { default: makeWASocket, DisconnectReason, useMultiFileAuthState, fetchLatestBaileysVersion } = require('@whiskeysockets/baileys');
const express = require('express');
const qrcode = require('qrcode-terminal');
const path = require('path');
const fs = require('fs');

const PORT = process.env.PORT || 8080;
const PYTHON_BACKEND = process.env.PYTHON_BACKEND || 'http://localhost:8000';
const AUTH_DIR = process.env.AUTH_DIR || path.join(__dirname, 'auth');
const LOG_LEVEL = process.env.LOG_LEVEL || 'silent';

// Ensure auth directory exists
fs.mkdirSync(AUTH_DIR, { recursive: true });

const app = express();
app.use(express.json());

// ── State ──────────────────────────────────────────────────────────────────
let sock = null;
let currentQR = null;
let connected = false;
let connecting = false;
let phoneNumber = '';

// ── Start WhatsApp connection ─────────────────────────────────────────────

async function connect() {
  if (connecting) return;
  connecting = true;

  const { state, saveCreds } = await useMultiFileAuthState(AUTH_DIR);
  const { version } = await fetchLatestBaileysVersion();

  console.log(`[Bridge] Using WA v${version.join('.')}`);

  sock = makeWASocket({
    version,
    auth: state,
    printQRInTerminal: false,
    logger: require('pino')({ level: LOG_LEVEL }),
    browser: ['d2cflow', 'Chrome', '120.0.0'],
    connectTimeoutMs: 30000,
    keepAliveIntervalMs: 15000,
  });

  sock.ev.on('creds.update', saveCreds);

  sock.ev.on('connection.update', async (update) => {
    const { connection, lastDisconnect, qr } = update;

    if (qr) {
      currentQR = qr;
      connected = false;
      qrcode.generate(qr, { small: true });
      console.log('[Bridge] QR code ready — scan in WhatsApp → Linked Devices');
    }

    if (connection === 'open') {
      currentQR = null;
      connected = true;
      connecting = false;
      phoneNumber = sock.user?.id?.split(':')[0] || '';
      console.log(`[Bridge] Connected as +${phoneNumber}`);

      // Notify Python backend
      notifyPython('/api/whatsapp/bridge-connected', { phone: phoneNumber });
    }

    if (connection === 'close') {
      connected = false;
      connecting = false;
      const shouldReconnect = lastDisconnect?.error?.output?.statusCode !== DisconnectReason.loggedOut;
      console.log('[Bridge] Connection closed, reconnect:', shouldReconnect);
      if (shouldReconnect) {
        setTimeout(() => connect(), 3000);
      } else {
        console.log('[Bridge] Logged out — delete auth dir to re-scan QR');
        currentQR = null;
      }
    }
  });

  // ── Incoming messages ──────────────────────────────────────────────────
  sock.ev.on('messages.upsert', async ({ messages, type }) => {
    if (type !== 'notify') return;

    for (const msg of messages) {
      if (msg.key.fromMe) continue;

      const from = msg.key.remoteJid || '';
      const body =
        msg.message?.conversation ||
        msg.message?.extendedTextMessage?.text ||
        msg.message?.imageMessage?.caption ||
        '';

      if (!body && !msg.message?.orderMessage) continue;

      console.log(`[Bridge] MSG from ${from}: ${body.slice(0, 80)}`);

      // Forward to Python backend
      await notifyPython('/api/whatsapp/incoming', {
        from,
        body,
        timestamp: msg.messageTimestamp,
        message_id: msg.key.id,
        order_data: msg.message?.orderMessage || null,
      });
    }
  });
}

// ── Forward events to Python ───────────────────────────────────────────────

async function notifyPython(endpoint, data) {
  try {
    await fetch(PYTHON_BACKEND + endpoint, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    });
  } catch (e) {
    console.error('[Bridge] notifyPython failed:', e.message);
  }
}

// ── HTTP API ────────────────────────────────────────────────────────────────

// Health / status check (used by Python bridge-status endpoint)
app.get('/', (req, res) => {
  res.json({ status: 'ok', connected, phone: phoneNumber });
});

app.get('/api/status', (req, res) => {
  res.json({
    connected,
    qr: currentQR || null,
    phone: phoneNumber,
    status: connected ? 'connected' : currentQR ? 'qr_pending' : 'offline',
  });
});

// Send a message — called by Python backend
app.post('/api/send', async (req, res) => {
  const { recipient, message } = req.body;
  if (!recipient || !message) return res.status(400).json({ error: 'recipient and message required' });
  if (!connected || !sock) return res.status(503).json({ error: 'Not connected to WhatsApp' });

  try {
    const jid = recipient.includes('@') ? recipient : `${recipient}@s.whatsapp.net`;
    await sock.sendMessage(jid, { text: message });
    res.json({ status: 'sent' });
  } catch (e) {
    console.error('[Bridge] Send failed:', e.message);
    res.status(500).json({ error: e.message });
  }
});

// Start / restart connection
app.post('/api/connect', async (req, res) => {
  if (!connected) {
    connect().catch(console.error);
    res.json({ status: 'connecting' });
  } else {
    res.json({ status: 'already_connected', phone: phoneNumber });
  }
});

// Logout and delete session
app.post('/api/logout', async (req, res) => {
  try {
    if (sock) await sock.logout().catch(() => {});
    fs.rmSync(AUTH_DIR, { recursive: true, force: true });
    fs.mkdirSync(AUTH_DIR, { recursive: true });
    connected = false;
    currentQR = null;
    phoneNumber = '';
    res.json({ status: 'logged_out' });
  } catch (e) {
    res.status(500).json({ error: e.message });
  }
});

// ── Start ───────────────────────────────────────────────────────────────────

app.listen(PORT, () => {
  console.log(`[Bridge] HTTP API running on port ${PORT}`);
  connect().catch(console.error);
});
