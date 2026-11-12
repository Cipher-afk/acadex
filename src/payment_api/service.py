from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException
from sqlmodel import select
from .db_models import User, Marketer
from .models import InitPayment, MarketerModel
from config import settings
import hmac, hashlib, json
from redis_config import save_payment
from aiogram import Bot
from pprint import pprint
from datetime import datetime, date, timedelta
from redis_config import save_payment
from utils import hash_password, verify_password
from payment_api.database_config import get_session_ctx
from aiogram.types import Message
import httpx

PAYSTACK_SECRET = settings.PAYMENT_SECRET_KEY
bot = Bot(token=settings.BOT_TOKEN)


class PaymentService:
    async def generate_payment_link(self, amount: int, metadata: dict):
        headers = {
            "Authorization": f"Bearer {settings.PAYMENT_SECRET_KEY}",
            "Content-type": "application/json",
        }

        data = {
            "email": f"ajaokudos34@gmail.com",
            "amount": amount * 100,
            "channels": ["bank_transfer"],
            "metadata": metadata,
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

    async def generate_marketer_payment_link(self, telegram_id: str):
        metadata = {"type": "marketer", "telegram_id": telegram_id}
        # marketer = await self.get_marketer_by_telegram_id(telegram_id=telegram_id)
        # if marketer.subscribed:
        #     return {'payment_link':None}
        payment_link_data = await self.generate_payment_link(
            amount=500, metadata=metadata
        )
        return payment_link_data

    async def verify_signature(self, body: bytes, signature: str | None) -> bool:
        if signature is None or PAYSTACK_SECRET is None:
            return False
        computed_hash = hmac.new(
            PAYSTACK_SECRET.encode(), body, hashlib.sha512
        ).hexdigest()
        return hmac.compare_digest(computed_hash, signature)

    async def create_user(self, user_info: InitPayment):
        async with get_session_ctx() as session:
            user_data = user_info.model_dump()
            new_user = User(**user_data)
            new_user.expiry = datetime.now() + timedelta(weeks=24)
            session.add(new_user)
            await session.commit()
            return new_user

    async def create_marketer(self, marketer_model: MarketerModel):
        async with get_session_ctx() as session:
            marketer_data = marketer_model.model_dump()
            hashed_password = hash_password(marketer_model.password)
            new_marketer = Marketer(**marketer_data)
            new_marketer.password = hashed_password
            session.add(new_marketer)
            await session.commit()
            return new_marketer

    async def get_all_marketers_by_university(self, university: str):
        async with get_session_ctx() as session:
            statement = select(Marketer).where(Marketer.university == university)
            results = await session.execute(statement)
            marketers = results.scalars().all()
            return marketers

    async def get_marketer_by_username(self, username: str):
        async with get_session_ctx() as session:
            statement = select(Marketer).where(username == Marketer.username)
            result = await session.execute(statement=statement)
            marketer = result.scalars().first()
            return marketer

    async def get_marketer_by_telegram_id(self, telegram_id: str):
        async with get_session_ctx() as session:
            statement = select(Marketer).where(telegram_id == Marketer.telegram_id)
            result = await session.execute(statement=statement)
            marketer = result.scalars().first()
            return marketer

    async def is_marketer_password(self, marketer: Marketer, password: str):
        hashed_password = marketer.password
        verified = verify_password(password=password, hashed_password=hashed_password)
        return True if verified else False

    async def update_marketer_info(self, marketer: Marketer, info: dict):
        async with get_session_ctx() as session:
            try:
                for key, value in info.items():
                    setattr(marketer, key, value)
                await session.commit()
                await session.refresh(marketer)
                return True
            except Exception as e:
                print(e, flush=True)
                return False

    async def get_users_referred_by_marketer(self, marketer_username: str):
        async with get_session_ctx() as session:
            statement = select(User).where(User.referrer == marketer_username)
            results = await session.execute(statement=statement)
            users = results.scalars().all()
            paid_users = (
                filter(lambda user: user.is_paid == True, users)
                if users is not None
                else None
            )
            return {
                "all_users": len(users) if users is not None else 0,
                "paid_users": (
                    len(paid_users) if paid_users is not None and paid_users else 0
                ),
            }

    async def verify_payment(self, body: bytes, session: AsyncSession):
        payload: dict = json.loads(body)
        pprint(payload)
        event = payload.get("event")
        data = payload.get("data")
        if event == "charge.success":
            metadata = data.get("metadata")
            if metadata.get("type") == "user":
                user_id = metadata.get("user_id")
                telegram_id = metadata.get("telegram_id")
                level = metadata.get("level")
                if not telegram_id:
                    await bot.send_message(
                        chat_id=int(telegram_id), text="Payment Failed"
                    )
                    return {"status": "ignored"}
                await self.update_info(
                    telegram_id=telegram_id, info={"is_paid": True}, session=session
                )
                await save_payment(user_id=user_id, truth_value="truth")
            else:
                telegram_id = metadata.get("telegram_id")
                marketer = await self.get_marketer_by_telegram_id(
                    telegram_id=telegram_id
                )
                updated = await self.update_marketer_info(
                    marketer=marketer, info={"subscribed": True}
                )
                if not updated:
                    await bot.send_message(
                        chat_id=int(telegram_id), text="Payment Failed Try Again"
                    )
            await bot.send_message(
                chat_id=int(telegram_id), text="Payment Verified Successfully"
            )
            return {"Payed": "Successfully"}
        else:
            await bot.send_message(
                chat_id=int(telegram_id), text="Payment Failed Try Again"
            )

    async def get_user(self, user_id: str, session: AsyncSession):
        statement = select(User).where(user_id == User.user_id)
        result = await session.execute(statement=statement)
        user = result.scalars().first()
        return user

    async def update_info(self, telegram_id: str, info: dict, session: AsyncSession):
        user = await self.get_user_by_telegram_id(
            telegram_id=telegram_id, session=session
        )
        if user is None:
            raise HTTPException(status_code=404, detail="User not found")
        for k, v in info.items():
            setattr(user, k, v)
        await session.commit()
        return {"Update": "Successful"}

    async def get_user_by_telegram_id(self, telegram_id: str, session: AsyncSession):
        result = await session.execute(
            select(User).where(telegram_id == User.telegram_id)
        )
        return result.scalars().first()

    async def payment_expired(
        self, user_id: str, telegram_id: str, session: AsyncSession
    ):
        user = await self.get_user(user_id=user_id, session=session)
        if user is None:
            raise HTTPException(status_code=404, detail="User not found")
        today = datetime.now()
        if today.date() > user.expiry or user.is_paid == False:
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
