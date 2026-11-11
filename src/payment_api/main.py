from fastapi import FastAPI, Header, HTTPException, Depends
from .database_config import init_db, get_session
from .models import InitPayment
from fastapi.requests import Request
from .service import PaymentService
from sqlalchemy.ext.asyncio import AsyncSession
from aiogram import Bot
from config import settings
from contextlib import asynccontextmanager
import httpx

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
                'type':'user',
                "telegram_id": user.telegram_id,
                "level": user.level,
                "user_id": user.user_id,
            }
        payment_link_data = await service.generate_payment_link(amount=1000,metadata=metadata)
        return payment_link_data
    return {'payment_link':None}


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
