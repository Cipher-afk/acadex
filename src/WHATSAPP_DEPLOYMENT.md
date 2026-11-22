# Acadex WhatsApp integration deployment

This is an additive integration. The existing Telegram polling bot remains a separate process and keeps its existing handlers. WhatsApp routes are mounted inside the existing FastAPI payment backend; there is no second Python bridge server.

## Architecture

- Existing Python/FastAPI backend: `https://acadexbot.duckdns.org/whatsapp/incoming`
- New Oracle instance: Node.js + Baileys WhatsApp gateway
- Existing Redis and PostgreSQL are reused.
- Existing `scraper_file.main()` is called for WhatsApp requests; scraper business logic is not duplicated.
- Telegram and WhatsApp have distinct channel identities in the existing `users.telegram_id` primary-key column. Telegram IDs remain unchanged; WhatsApp IDs are namespaced as `wa:<international-phone-number>`.
- The portal username remains the shared Redis subscription key (`paid:<portal-username>`), and successful payments synchronize subscription fields across channel records for that portal username.

## A. Update the existing Python/Telegram Oracle instance

1. Back up the project and database before deployment.
2. Replace the project source with this updated project while preserving your real `.env`, persistent database volume, Redis data, and Baileys auth folder (the latter is on the second server).
3. Add these values to the existing backend `.env`:

```env
ACADEX_BRIDGE_TOKEN=LONG_RANDOM_SECRET_A
WHATSAPP_GATEWAY_URL=https://YOUR-WHATSAPP-GATEWAY-DOMAIN
WHATSAPP_GATEWAY_TOKEN=LONG_RANDOM_SECRET_B
```

`ACADEX_BRIDGE_TOKEN` must match the Node instance's `ACADEX_BRIDGE_TOKEN`. `WHATSAPP_GATEWAY_TOKEN` must match the Node instance's `WHATSAPP_GATEWAY_TOKEN`.

4. The FastAPI app now includes `whatsapp_bridge.router` in `payment_api/main.py`. Rebuild and restart only the existing backend container:

```bash
docker compose build backend
docker compose up -d backend
```

Do not replace or stop the Telegram bot container. Its code and polling process remain separate. Check the backend logs after restart:

```bash
docker compose logs --tail=100 backend
```

5. **The backend image now installs Chromium** (WhatsApp scrapes run inside it), so the first `docker compose build backend` is larger and slower. On a 1 GB instance, the Telegram bot container and the backend container can each launch a browser, so keep swap enabled and watch memory.
6. Confirm your existing reverse proxy sends `https://acadexbot.duckdns.org` to the FastAPI backend on port 8000. The incoming WhatsApp endpoint is `/whatsapp/incoming`; the health endpoint is `/whatsapp/health`.

## B. New Oracle instance (Node/Baileys)

1. Install Node.js 20 or newer.
2. Copy `src/whatsapp/` to `/opt/acadex-whatsapp/whatsapp`.
3. Create `/opt/acadex-whatsapp/whatsapp/.env`:

```env
PORT=3000
WHATSAPP_GATEWAY_TOKEN=LONG_RANDOM_SECRET_B
ACADEX_BRIDGE_URL=https://acadexbot.duckdns.org
ACADEX_BRIDGE_TOKEN=LONG_RANDOM_SECRET_A
WHATSAPP_AUTH_DIR=/opt/acadex-whatsapp/whatsapp/auth
LOG_LEVEL=warn
```

`ACADEX_BRIDGE_URL` is the base domain, without `/whatsapp`; the Node gateway appends `/whatsapp/incoming` itself.

4. Install and start:

```bash
cd /opt/acadex-whatsapp/whatsapp
npm install
npm start
```

5. Put port 3000 behind HTTPS and set `WHATSAPP_GATEWAY_URL` on the Python backend to that HTTPS base URL. The Python app calls the gateway's `/send` endpoint.
6. Scan the QR printed in the terminal using WhatsApp → Linked devices → Link a device.
7. Keep the `auth/` directory (and `jid-map.json`, which maps phone numbers to the exact WhatsApp chat IDs) on persistent disk and private. Back both up. Anyone with those session files may gain access to the linked WhatsApp account.

Use the supplied systemd example as a template after adjusting paths and usernames. Run one Python backend worker for this in-process adapter because interactive scraper waiters and task tracking are process-local.

## C. First test sequence

1. Check `GET https://acadexbot.duckdns.org/test` and `GET https://acadexbot.duckdns.org/whatsapp/health`.
2. Check the Node gateway's `/health` endpoint and confirm `whatsappConnected: true` after QR pairing.
3. Send `hi` to the linked WhatsApp number and open the Acadex menu.
4. Connect a test portal account. Confirm a Redis credential hash is stored under `whatsapp:<phone>` and a PostgreSQL user row is created with `telegram_id` set to `wa:<phone>`.
5. Test **Download payment receipts** first because the existing project treats it as free.
6. Send `SUBSCRIBE`, choose Semester or Session, and verify the generated Paystack link and its metadata before making a low-value test payment.
7. Confirm the signed Paystack `charge.success` webhook updates the WhatsApp user row, any other channel rows for the same portal username, and the shared Redis `paid:<portal-username>` key. Confirm WhatsApp receives the success notification.
8. Confirm an existing Telegram test account can still register, generate a payment link, receive the Telegram webhook notification, and use the same paid status.
9. Test the fee-block workflow separately with a test account because it can involve real portal/Remita payment steps.

## Identity and payment behaviour

- Existing Telegram IDs remain their original numeric strings in `users.telegram_id`.
- WhatsApp uses `wa:<phone>` in the same existing column. No new database column is required.
- WhatsApp portal credentials are stored using the existing `save_userinfo()` helper under `whatsapp:<phone>`; Telegram credential keys are not overwritten.
- Both channels use the existing `paid:<portal-username>` Redis key. Paystack metadata carries `channel`, `telegram_id` (the channel identity), `whatsapp_id` for WhatsApp, `user_id`, `level`, and `type`.
- Old Telegram Paystack metadata without a `channel` remains treated as Telegram. The webhook routes the success notification according to the metadata/channel identity.
- Payment amount and NGN currency are checked against the existing ₦500 semester / ₦1,000 session prices before activating the subscription. Duplicate webhook references are ignored.

## Scope and known limitations

- The menu only exposes actions present in the supplied scraper: receipts, results, result summary, courses, biodata, admission forms, and fee-block workflow.
- The scraper's `ask_for_wait` function is imported into the `scraper_file` module namespace. The adapter replaces that module-level reference inside the FastAPI process, so the Telegram bot process retains its own original function.
- The original Redis `session_url` key is global. It is deliberately not changed in this integration. Concurrent portal scraping may therefore interfere; initially test with one active scrape at a time. A safe per-user session refactor should be a separate, explicitly tested change.
- Baileys is an unofficial WhatsApp Web integration. WhatsApp may disconnect or restrict the linked number. The official WhatsApp Business Platform is safer for production-critical messaging.
- Menus and prompts are sent as plain numbered text (interactive lists are not reliably rendered through Baileys). Users reply with the number or the option text. Text commands: `MENU`, `HELP`, `BACK`, `CANCEL`, `STOP`, and `SUBSCRIBE`.
- Scrapes (Telegram and WhatsApp) share one Chromium per Python process, each in its own isolated browser context and its own private job folder for screenshots/PDFs, so two users at once never get each other's files. At most `MAX_CONCURRENT_SCRAPES` (default 2) run at once; extra requests wait in a queue and the user is told. Tune with env vars: `MAX_CONCURRENT_SCRAPES` (use 1 on a 1 GB instance if you see OOM kills), `SCRAPE_JOB_TIMEOUT` (default 1800 s, frees a slot if a page or prompt hangs), `BROWSER_RECYCLE_AFTER` (default 50 jobs), `CHROMIUM_SINGLE_PROCESS=0` (drops `--single-process --no-zygote` if Chromium crashes). WhatsApp prompts (fee-block flow) wait at most `WHATSAPP_PROMPT_TIMEOUT` seconds (default 300), because a waiting prompt holds a concurrency slot.
- Files larger than 12MB are not sent by this adapter.
- This package has not been deployed against your live Oracle instances or live Paystack account. Complete the end-to-end test sequence before announcing the WhatsApp channel as production-ready.
