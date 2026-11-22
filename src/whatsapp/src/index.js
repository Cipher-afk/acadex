import 'dotenv/config';
import crypto from 'node:crypto';
import fs from 'node:fs';
import express from 'express';
import pino from 'pino';
import qrcode from 'qrcode-terminal';
import {
  default as makeWASocket,
  DisconnectReason,
  fetchLatestBaileysVersion,
  useMultiFileAuthState,
} from '@whiskeysockets/baileys';

const PORT = Number(process.env.PORT || 3000);
const API_TOKEN = process.env.WHATSAPP_GATEWAY_TOKEN;
const BRIDGE_URL = process.env.ACADEX_BRIDGE_URL;
const BRIDGE_TOKEN = process.env.ACADEX_BRIDGE_TOKEN;
const AUTH_DIR = process.env.WHATSAPP_AUTH_DIR || './auth';
const JID_MAP_FILE = process.env.WHATSAPP_JIDMAP_FILE || './jid-map.json';

if (!API_TOKEN || !BRIDGE_URL || !BRIDGE_TOKEN) {
  throw new Error('Set WHATSAPP_GATEWAY_TOKEN, ACADEX_BRIDGE_URL and ACADEX_BRIDGE_TOKEN');
}

// ---- Never die silently -------------------------------------------------------------
process.on('unhandledRejection', (reason) => {
  console.error('Unhandled rejection:', reason?.stack || reason);
});
process.on('uncaughtException', (error) => {
  console.error('Uncaught exception:', error?.stack || error);
  // State is unknown after an uncaught exception: exit and let systemd/pm2 restart us.
  setTimeout(() => process.exit(1), 200);
});
for (const signal of ['SIGINT', 'SIGTERM']) {
  process.on(signal, () => {
    console.log(`${signal} received, shutting down.`);
    try { sock?.end(undefined); } catch {}
    setTimeout(() => process.exit(0), 300);
  });
}

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

const app = express();
app.use(express.json({ limit: '18mb' }));
let sock;
let isConnected = false;

// ---- Phone -> JID map ---------------------------------------------------------------
// WhatsApp may identify a sender by a privacy "LID" instead of a phone number. We always
// reply to the exact JID a user wrote from, and persist that so replies that start on the
// Python side later (e.g. the payment-success notice) still reach the right chat.
const jidMap = new Map();
try {
  const saved = JSON.parse(fs.readFileSync(JID_MAP_FILE, 'utf8'));
  for (const [phone, jid] of Object.entries(saved)) jidMap.set(phone, jid);
} catch { /* first run */ }

let jidSaveTimer;
function persistJidMap() {
  clearTimeout(jidSaveTimer);
  jidSaveTimer = setTimeout(() => {
    const tmp = `${JID_MAP_FILE}.tmp`;
    fs.writeFile(tmp, JSON.stringify(Object.fromEntries(jidMap)), (writeError) => {
      if (writeError) return console.error('Could not save JID map:', writeError.message);
      fs.rename(tmp, JID_MAP_FILE, (renameError) => {
        if (renameError) console.error('Could not save JID map:', renameError.message);
      });
    });
  }, 1000);
}

function resolveJid(to) {
  const raw = String(to);
  if (raw.includes('@')) return raw;
  const digits = raw.replace(/\D/g, '');
  return jidMap.get(digits) || `${digits}@s.whatsapp.net`;
}

// ---- Per-chat queues ----------------------------------------------------------------
// Outbound: one message at a time per chat with a short human-like pause (bursts of
// instant replies are a common trigger for WhatsApp restrictions).
const sendChains = new Map();
function enqueueSend(jid, task) {
  const previous = sendChains.get(jid) || Promise.resolve();
  const next = previous.catch(() => {}).then(async () => {
    const result = await task();
    await sleep(700 + Math.random() * 600);
    return result;
  });
  sendChains.set(jid, next);
  next.catch(() => {}).finally(() => {
    if (sendChains.get(jid) === next) sendChains.delete(jid);
  });
  return next;
}

// Inbound: process one message at a time per user so multi-step flows
// (username -> password -> ...) cannot race each other.
const forwardChains = new Map();
function enqueueForward(phone, task) {
  const previous = forwardChains.get(phone) || Promise.resolve();
  const next = previous.catch(() => {}).then(task);
  forwardChains.set(phone, next);
  next.catch(() => {}).finally(() => {
    if (forwardChains.get(phone) === next) forwardChains.delete(phone);
  });
  return next;
}

const seenMessageIds = new Set();
function alreadySeen(id) {
  if (!id) return false;
  if (seenMessageIds.has(id)) return true;
  seenMessageIds.add(id);
  if (seenMessageIds.size > 2000) seenMessageIds.delete(seenMessageIds.values().next().value);
  return false;
}

// ---- HTTP API -----------------------------------------------------------------------
function auth(req, res, next) {
  const given = Buffer.from(req.header('authorization') || '');
  const expected = Buffer.from(`Bearer ${API_TOKEN}`);
  if (given.length !== expected.length || !crypto.timingSafeEqual(given, expected)) {
    return res.status(401).json({ error: 'Unauthorized' });
  }
  next();
}

app.get('/health', (_req, res) => {
  res.json({ status: 'ok', whatsappConnected: isConnected });
});

function listToText(body) {
  const rows = (body.sections || []).flatMap((section) => section.rows || []);
  return [
    body.text || 'Choose an option',
    ...rows.map((row, index) => `${index + 1}. ${row.title}${row.description ? ` — ${row.description}` : ''}`),
  ].join('\n');
}

// The Python backend calls this endpoint to deliver text and files.
app.post('/send', auth, async (req, res) => {
  try {
    if (!sock || !isConnected) return res.status(503).json({ error: 'WhatsApp is not connected' });
    const { to, text, mediaBase64, mimetype, filename, caption } = req.body || {};
    if (!to) return res.status(400).json({ error: 'Missing recipient' });
    const jid = resolveJid(to);

    let buffer = null;
    if (mediaBase64) {
      buffer = Buffer.from(mediaBase64, 'base64');
      if (buffer.length > 12 * 1024 * 1024) return res.status(413).json({ error: 'File exceeds 12MB adapter limit' });
    }

    const result = await enqueueSend(jid, async () => {
      try {
        await sock.sendPresenceUpdate('composing', jid);
        await sleep(400 + Math.random() * 500);
      } catch { /* presence is cosmetic */ }

      if (req.body.type === 'list') {
        // Interactive lists are not reliably rendered; send the numbered text instead.
        return sock.sendMessage(jid, { text: listToText(req.body) });
      }
      if (buffer) {
        if ((mimetype || '').startsWith('image/')) {
          return sock.sendMessage(jid, { image: buffer, mimetype, caption: caption || text || '' });
        }
        return sock.sendMessage(jid, {
          document: buffer,
          mimetype: mimetype || 'application/octet-stream',
          fileName: filename || 'acadex-file',
          caption: caption || text || '',
        });
      }
      if (!text) throw new Error('Nothing to send');
      return sock.sendMessage(jid, { text: String(text) });
    });
    res.json({ ok: true, messageId: result?.key?.id || null });
  } catch (error) {
    console.error('Outbound WhatsApp send failed:', error?.message || error);
    res.status(500).json({ error: 'WhatsApp send failed' });
  }
});

// JSON errors instead of Express's default HTML pages (bad JSON, oversized bodies).
app.use((error, _req, res, _next) => {
  if (error?.type === 'entity.too.large') return res.status(413).json({ error: 'Payload too large' });
  console.error('Request error:', error?.message || error);
  res.status(400).json({ error: 'Bad request' });
});

// ---- Incoming messages --------------------------------------------------------------
async function forwardIncoming(phone, text, messageId) {
  const response = await fetch(`${BRIDGE_URL.replace(/\/$/, '')}/whatsapp/incoming`, {
    method: 'POST',
    headers: { 'content-type': 'application/json', authorization: `Bearer ${BRIDGE_TOKEN}` },
    body: JSON.stringify({ phone, text, message_id: messageId }),
    signal: AbortSignal.timeout(30000),
  });
  if (!response.ok) {
    const body = await response.text();
    throw new Error(`Acadex bridge returned ${response.status}: ${body.slice(0, 300)}`);
  }
}

function unwrapMessage(message) {
  let m = message;
  while (m?.ephemeralMessage?.message || m?.viewOnceMessage?.message || m?.viewOnceMessageV2?.message) {
    m = m.ephemeralMessage?.message || m.viewOnceMessage?.message || m.viewOnceMessageV2?.message;
  }
  return m || {};
}

function extractText(message) {
  const m = unwrapMessage(message);
  return m.conversation
    || m.extendedTextMessage?.text
    || m.buttonsResponseMessage?.selectedButtonId
    || m.listResponseMessage?.singleSelectReply?.selectedRowId
    || m.templateButtonReplyMessage?.selectedId
    || '';
}

// ---- Socket lifecycle ---------------------------------------------------------------
let reconnectAttempts = 0;
let reconnectTimer = null;
let starting = false;

function scheduleReconnect(immediate = false) {
  if (reconnectTimer) return;
  const delay = immediate
    ? 500
    : Math.min(60000, 2000 * 2 ** reconnectAttempts) + Math.random() * 1000;
  if (!immediate) reconnectAttempts += 1;
  console.error(`Reconnecting in ${Math.round(delay / 1000)}s (attempt ${reconnectAttempts}).`);
  reconnectTimer = setTimeout(() => {
    reconnectTimer = null;
    startSocket().catch((error) => {
      console.error('Reconnect failed:', error?.message || error);
      scheduleReconnect();
    });
  }, delay);
}

async function startSocket() {
  if (starting) return;
  starting = true;
  try {
    // Tear down the previous socket so listeners and sockets do not pile up.
    if (sock) {
      try {
        sock.ev.removeAllListeners('connection.update');
        sock.ev.removeAllListeners('messages.upsert');
        sock.ev.removeAllListeners('creds.update');
        sock.end(undefined);
      } catch { /* already closed */ }
    }

    const { state, saveCreds } = await useMultiFileAuthState(AUTH_DIR);
    let version;
    try {
      ({ version } = await fetchLatestBaileysVersion());
    } catch (error) {
      console.error('Could not fetch latest WhatsApp Web version; using library default:', error?.message || error);
    }
    sock = makeWASocket({
      ...(version ? { version } : {}),
      auth: state,
      logger: pino({ level: process.env.LOG_LEVEL || 'warn' }),
      browser: ['Acadex', 'Chrome', '1.0.0'],
      markOnlineOnConnect: false,
      syncFullHistory: false,
      generateHighQualityLinkPreview: false,
    });

    sock.ev.on('creds.update', saveCreds);
    sock.ev.on('connection.update', (update) => {
      const { connection, lastDisconnect, qr } = update;
      if (qr) {
        console.log('\nScan this QR from WhatsApp > Linked devices > Link a device:\n');
        qrcode.generate(qr, { small: true });
      }
      if (connection === 'open') {
        isConnected = true;
        reconnectAttempts = 0;
        console.log('Acadex WhatsApp connected.');
      }
      if (connection === 'close') {
        isConnected = false;
        const code = lastDisconnect?.error?.output?.statusCode;
        console.error('WhatsApp connection closed. status:', code, lastDisconnect?.error?.message || '');
        if (code === DisconnectReason.loggedOut) {
          console.error('WhatsApp logged out. Delete the auth folder and re-scan the QR only after checking the account.');
        } else if (code === DisconnectReason.connectionReplaced) {
          // Another client took over this linked-device slot. Reconnecting in a loop would
          // fight it and risks a restriction; stop and let a human look.
          console.error('Connection replaced: this WhatsApp account is linked somewhere else. Not reconnecting.');
        } else if (code === DisconnectReason.restartRequired) {
          scheduleReconnect(true); // expected right after QR pairing
        } else {
          scheduleReconnect();
        }
      }
    });

    sock.ev.on('messages.upsert', ({ messages, type }) => {
      if (type !== 'notify') return;
      for (const item of messages || []) {
        if (!item.message || item.key.fromMe) continue;
        const jid = item.key.remoteJid || '';
        if (!jid || jid === 'status@broadcast' || jid.endsWith('@g.us') || jid.endsWith('@newsletter') || jid.endsWith('@broadcast')) continue;
        if (alreadySeen(item.key.id)) continue;

        // Prefer the real phone-number JID when WhatsApp provides it (newer Baileys);
        // otherwise use whatever JID the message came from.
        const alt = item.key.remoteJidAlt || '';
        const source = alt.endsWith('@s.whatsapp.net') ? alt : jid;
        const phone = source.split('@')[0].split(':')[0].replace(/\D/g, '');
        const text = extractText(item.message).trim();
        if (!phone || !text) continue;

        if (jidMap.get(phone) !== jid) {
          jidMap.set(phone, jid);
          persistJidMap();
        }

        enqueueForward(phone, async () => {
          try {
            await forwardIncoming(phone, text, item.key.id);
          } catch (error) {
            console.error('Could not process incoming message:', error?.message || error);
            try {
              await enqueueSend(jid, () => sock.sendMessage(jid, { text: 'Acadex is temporarily having trouble processing that message. Please try again shortly.' }));
            } catch { /* nothing more we can do */ }
          }
        });
      }
    });
  } finally {
    starting = false;
  }
}

app.listen(PORT, '0.0.0.0', () => console.log(`Acadex WhatsApp gateway listening on ${PORT}`));
startSocket().catch((error) => {
  console.error('Could not start WhatsApp socket:', error);
  scheduleReconnect();
});
