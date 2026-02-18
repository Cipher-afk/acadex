from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException
from sqlmodel import select
from .db_models import User
from .models import InitPayment
from config import settings
import hmac, hashlib, json
from redis_config import save_payment
from aiogram import Bot
from pprint import pprint
from datetime import datetime, timedelta
from redis_config import save_payment

PAYSTACK_SECRET = settings.PAYMENT_SECRET_KEY
bot = Bot(token=settings.BOT_TOKEN)


class PaymentService:
    async def verify_signature(self, body: bytes, signature: str | None) -> bool:
        if signature is None or PAYSTACK_SECRET is None:
            return False
        computed_hash = hmac.new(
            PAYSTACK_SECRET.encode(), body, hashlib.sha512
        ).hexdigest()
        return hmac.compare_digest(computed_hash, signature)

    async def create_user(self, user_info: InitPayment, session: AsyncSession):
        user_data = user_info.model_dump()
        new_user = User(**user_data)
        new_user.expiry = datetime.now() + timedelta(weeks=24)
        session.add(new_user)
        await session.commit()
        return new_user

    async def verify_payment(self, body: bytes, session: AsyncSession):
        payload: dict = json.loads(body)
        pprint(payload)
        event = payload.get("event")
        data = payload.get("data")
        if event == "charge.success":
            metadata = data.get("metadata")
            user_id = metadata.get("user_id")
            telegram_id = metadata.get("telegram_id")
            level = metadata.get("level")
            if not telegram_id:
                await bot.send_message(chat_id=int(telegram_id), text="Payment Failed")
                return {"status": "ignored"}
            await self.update_info(
                user_id=user_id, info={"is_paid": True}, session=session
            )
            await save_payment(user_id=user_id, truth_value="truth")
            await bot.send_message(
                chat_id=int(telegram_id), text="Payment Verified Successfully"
            )
            return {"Payed": "Successfully"}

    async def get_user(self, user_id: str, session: AsyncSession):
        statement = select(User).where(user_id == User.user_id)
        result = await session.execute(statement=statement)
        user = result.scalars().first()
        return user

    async def update_info(self, user_id: str, info: dict, session: AsyncSession):
        user = await self.get_user(user_id=user_id, session=session)
        if user is None:
            raise HTTPException(status_code=404, detail="User not found")
        for k, v in info.items():
            setattr(user, k, v)
        await session.commit()
        return {"Update": "Successful"}

    async def payment_expired(
        self, user_id: str, telegram_id: str, session: AsyncSession
    ):
        user = await self.get_user(user_id=user_id, session=session)
        if user is None:
            raise HTTPException(status_code=404, detail="User not found")
        today = datetime.now()
        if today > user.expiry or user.is_paid == False:
            user.is_paid = False
            await session.commit()
            await session.refresh(user)
            await save_payment(user_id=user.user_id, truth_value="false")
            await bot.send_message(
                chat_id=telegram_id,
                text="Payment Expired or Payment hasn't been made".title(),
            )
            return True
        return False
