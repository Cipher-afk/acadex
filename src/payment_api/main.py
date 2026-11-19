from fastapi import FastAPI, Header, HTTPException, Depends
from fastapi.responses import PlainTextResponse
from .database_config import init_db, get_session
from .models import InitPayment
from fastapi.requests import Request
from .service import PaymentService
from sqlalchemy.ext.asyncio import AsyncSession
from aiogram import Bot
from config import settings
from contextlib import asynccontextmanager
import httpx
import asyncio
import hashlib
import hmac
import logging

from whatsapp.handlers import handle_whatsapp_message
from redis_config import red

service = PaymentService()


@asynccontextmanager
async def lifespan(app: FastAPI):
    print("Server starting..")
    await init_db()
    yield
    print("Server ending..")


app = FastAPI(lifespan=lifespan)


@app.get("/test")
async def check_health():
    return {"status": "ok"}


@app.post("/init-payment")
async def initialize_payment(
    payload: InitPayment, session: AsyncSession = Depends(get_session)
):
    user = await service.get_user_by_telegram_id(
        telegram_id=payload.telegram_id, session=session
    )
    user_id = await service.get_user(user_id=payload.user_id, session=session)
    if user is None and user_id is None:
        user = await service.create_user(user_info=payload)
    else:
        await service.update_info(
            telegram_id=user.telegram_id,
            info={"user_id": payload.user_id, "level": payload.level},
            session=session,
        )
    if (
        await service.payment_expired(
            user_id=user.user_id, telegram_id=user.telegram_id, session=session
        )
        == True
    ):
        metadata = {
            "type": payload.type,
            "telegram_id": user.telegram_id,
            "level": user.level,
            "user_id": user.user_id,
        }
        payment_link_data = await service.generate_payment_link(
            amount=1000, metadata=metadata
        )
        return payment_link_data
    return {"payment_link": None}


@app.post("/webhooks/paystack")
async def paystack_hook(
    request: Request,
    x_paystack_signature: str = Header(None),
    session: AsyncSession = Depends(get_session),
):
    print("Called")
    body = await request.body()
    print("gotten")
    if not service.verify_signature(body, x_paystack_signature):
        raise HTTPException(status_code=400, detail="Invalid signature")
    status = await service.verify_payment(body, session)
    return status


logger = logging.getLogger(__name__)


@app.get("/webhooks/whatsapp")
async def verify_whatsapp_webhook(request: Request):
    """Meta webhook verification endpoint."""
    mode = request.query_params.get("hub.mode")
    token = request.query_params.get("hub.verify_token")
    challenge = request.query_params.get("hub.challenge")

    if (
        mode == "subscribe"
        and settings.WHATSAPP_VERIFY_TOKEN
        and token == settings.WHATSAPP_VERIFY_TOKEN
        and challenge is not None
    ):
        return PlainTextResponse(challenge)

    raise HTTPException(status_code=403, detail="Webhook verification failed")


@app.post("/webhooks/whatsapp")
async def receive_whatsapp_webhook(request: Request):
    """Receive WhatsApp messages and dispatch them to the Acadex channel adapter."""
    body = await request.body()

    # If an app secret is configured, verify Meta's X-Hub-Signature-256 header.
    if not settings.WHATSAPP_APP_SECRET:
        raise HTTPException(
            status_code=503, detail="Configure WHATSAPP_APP_SECRET before enabling the webhook"
        )
    signature = request.headers.get("X-Hub-Signature-256", "")
    expected = "sha256=" + hmac.new(
        settings.WHATSAPP_APP_SECRET.encode("utf-8"), body, hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(signature, expected):
        raise HTTPException(status_code=401, detail="Invalid webhook signature")

    try:
        payload = await request.json()
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Invalid JSON payload") from exc

    # Acknowledge status notifications and non-message events without processing.
    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})
            for incoming in value.get("messages", []) or []:
                message_id = incoming.get("id")
                phone = incoming.get("from")
                message_type = incoming.get("type")
                text = (incoming.get("text") or {}).get("body") if message_type == "text" else None

                if not phone or not text:
                    continue

                # Meta can retry webhook deliveries. Ignore a message ID already seen.
                if message_id:
                    is_new = await red.set(
                        f"whatsapp:webhook:{message_id}", "1", ex=86400, nx=True
                    )
                    if not is_new:
                        continue

                try:
                    await handle_whatsapp_message(phone=phone, text=text)
                except Exception:
                    logger.exception("Failed to process incoming WhatsApp message")

    return {"status": "ok"}
