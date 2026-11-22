# Acadex WhatsApp Baileys gateway

This Node.js service runs on the second Oracle Cloud instance. It handles the persistent Baileys WhatsApp Web connection and forwards incoming messages to the existing FastAPI backend. It does not contain scraper or subscription business logic.

## Configure

Create `.env` from `.env.example`:

```env
PORT=3000
WHATSAPP_GATEWAY_TOKEN=LONG_RANDOM_SECRET_B
ACADEX_BRIDGE_URL=https://acadexbot.duckdns.org
ACADEX_BRIDGE_TOKEN=LONG_RANDOM_SECRET_A
WHATSAPP_AUTH_DIR=/opt/acadex-whatsapp/whatsapp/auth
LOG_LEVEL=warn
```

`ACADEX_BRIDGE_URL` must be the FastAPI base domain without `/whatsapp`. The gateway forwards incoming messages to `/whatsapp/incoming` automatically.

## Install and run

```bash
npm install
npm start
```

Scan the QR code printed in the terminal with WhatsApp → Linked devices → Link a device. Keep the `auth` directory persistent and private.

The gateway exposes:

- `GET /health` — connection status
- `POST /send` — authenticated outbound messages and files

The Python backend calls `/send` using `WHATSAPP_GATEWAY_URL` and `WHATSAPP_GATEWAY_TOKEN`. The Node gateway calls the FastAPI app using `ACADEX_BRIDGE_URL` and `ACADEX_BRIDGE_TOKEN`.

See `../WHATSAPP_DEPLOYMENT.md` for the full two-server deployment sequence. The Python bridge is an APIRouter included in `payment_api/main.py`; do not run a separate Uvicorn process for `whatsapp_bridge.py`.

Baileys is an unofficial WhatsApp Web integration and may be disconnected or restricted by WhatsApp. Keep this service on a persistent server and monitor `/health`.
