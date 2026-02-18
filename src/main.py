from fastapi import FastAPI, Header, HTTPException, Depends
from payment_api.database_config import init_db, get_session
from payment_api.models import InitPayment
from fastapi.requests import Request
from payment_api.service import PaymentService
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
    user = await service.get_user(user_id=payload.user_id, session=session)
    if user is None:
        user = await service.create_user(user_info=payload, session=session)
    if (
        await service.payment_expired(
            user_id=user.user_id, telegram_id=user.telegram_id, session=session
        )
        == True
    ):
        headers = {
            "Authorization": f"Bearer {settings.PAYMENT_SECRET_KEY}",
            "Content-type": "application/json",
        }

        data = {
            "email": f"ajaokudos34@gmail.com",
            "amount": 1000 * 100,
            "metadata": {
                "telegram_id": user.telegram_id,
                "level": user.level,
                "user_id": user.user_id,
            },
        }

        async with httpx.AsyncClient(verify=False) as client:
            res = await client.post(
                "https://api.paystack.co/transaction/initialize",
                headers=headers,
                json=data,
                timeout=100,
            )
            result = res.json()
            if not result["status"]:
                raise HTTPException(status_code=400, detail=result["message"])
            payment_link = result["data"]["authorization_url"]
            return {"payment_link": payment_link}
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
