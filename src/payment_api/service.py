from sqlalchemy.ext.asyncio import AsyncSession
from .db_models import User
from config import settings
import hmac, hashlib, json
from redis_config import save_payment
from aiogram import Bot
from pprint import pprint

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

    async def verify_payment(self, body: bytes, session: AsyncSession):
        payload: dict = json.loads(body)
        pprint(payload)
        event = payload.get("event")
        data = payload.get("data")
        if event == "charge.success":
            metadata = data.get("metadata")
            telegram_id = metadata.get("telegram_id")
            level = metadata.get("level")
            if not telegram_id:
                await bot.send_message(chat_id=int(telegram_id), text="Payment Failed")
                return {"status": "ignored"}

        paid_user_data = {"telegram_id": telegram_id, "is_paid": True, "level": level}
        paid_user = User(**paid_user_data)
        session.add(paid_user)
        await session.commit()
        await save_payment(telegram_id=telegram_id)
        await bot.send_message(
            chat_id=int(telegram_id), text="Payment Verified Successfully"
        )
        return {"Payed": "Successfully"}
