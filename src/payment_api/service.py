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
from utils import hash_password, verify_password, ask_for_wait
from payment_api.database_config import get_session_ctx
from aiogram.types import Message
from typing import List
import httpx
from buttons import ButtonInfoDict, build_payment_buttons
from typing import TypedDict

PAYSTACK_SECRET = settings.PAYMENT_SECRET_KEY
bot = Bot(token=settings.BOT_TOKEN)


class MetaDataDict(TypedDict):
    type: str
    telegram_id: str
    user_id: str
    level: int
    referrer: str


class PaymentService:
    async def initialize_payment(self, payload: InitPayment, message: Message):
        async with get_session_ctx() as session:
            user = await self.get_user_by_telegram_id(
                telegram_id=payload.telegram_id, session=session
            )
            # A portal username may be used on more than one channel. The
            # telegram_id is the channel identity, so never update another
            # channel's row merely because its portal username matches.
            if user is None:
                user = await self.create_user(user_info=payload)
            else:
                await self.update_info(
                    telegram_id=user.telegram_id,
                    info={"user_id": payload.user_id, "level": payload.level},
                    session=session,
                )
            if (
                await self.payment_expired(
                    user_id=user.user_id, telegram_id=user.telegram_id, session=session
                )
                == True
            ):
                type_choice_button_info: List[ButtonInfoDict] = [
                    {
                        "button_name": "Pay per semester",
                        "button_callback": "pay:semester",
                    },
                    {
                        "button_name": "Pay per session",
                        "button_callback": "pay:session",
                    },
                ]
                type_choice_buttons = await build_payment_buttons(
                    button_infos=type_choice_button_info
                )
                type_choice = await ask_for_wait(
                    message=message,
                    text="Pick a plan you want to pay for to unlock all services for a time period 🥳🥂\n\nPer Semester for 500 naira\n\nPer Session for 1000 naira",
                    callback_buttons=type_choice_buttons,
                )
                metadata = {
                    "telegram_id": user.telegram_id,
                    "level": user.level,
                    "user_id": user.user_id,
                    "type": type_choice,
                }
                payment_link_data = await self.generate_subscription_link(
                    metadata=metadata
                )
                return payment_link_data
            return {"payment_link": None}

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

        async with httpx.AsyncClient() as client:
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
            return {"payment_link": payment_link, "amount": amount}

    async def generate_subscription_link(self, metadata: MetaDataDict):
        # marketer = await self.get_marketer_by_telegram_id(telegram_id=telegram_id)
        # if marketer.subscribed:
        #     return {'payment_link':None}
        if metadata["type"] == "semester":
            payment_link_data = await self.generate_payment_link(
                amount=500, metadata=metadata
            )
        else:
            payment_link_data = await self.generate_payment_link(
                amount=1000, metadata=metadata
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
            print(users, flush=True)
            paid_users = (
                filter(lambda user: user.is_paid == True, users) if users else None
            )
            return {
                "all_users": len(users) if users else 0,
                "paid_users": (
                    len(list(paid_users))
                    if paid_users is not None and paid_users
                    else 0
                ),
            }

    async def verify_payment(self, body: bytes, session: AsyncSession):
        """Apply a verified Paystack success event to the correct channel user.

        Legacy events without a channel remain Telegram events, preserving the
        existing bot's payment metadata contract.
        """
        payload: dict = json.loads(body)
        event = payload.get("event")
        data = payload.get("data") or {}
        if event != "charge.success":
            return {"status": "ignored", "reason": "unsupported_event"}

        metadata = data.get("metadata") or {}
        telegram_id = metadata.get("telegram_id")
        user_id = metadata.get("user_id")
        plan_type = metadata.get("type")
        if not telegram_id or not user_id or plan_type not in {"semester", "session"}:
            return {"status": "ignored", "reason": "incomplete_metadata"}

        channel = metadata.get("channel") or (
            "whatsapp" if str(telegram_id).startswith("wa:") else "telegram"
        )
        expected_amount = 50000 if plan_type == "semester" else 100000
        amount = data.get("amount")
        if amount is not None and int(amount) != expected_amount:
            return {"status": "ignored", "reason": "amount_mismatch"}
        if data.get("currency") and data.get("currency") != "NGN":
            return {"status": "ignored", "reason": "currency_mismatch"}
        if data.get("status") and data.get("status") != "success":
            return {"status": "ignored", "reason": "transaction_not_successful"}

        # Paystack can retry webhook delivery. Avoid extending the same payment
        # repeatedly when the same reference is delivered more than once.
        reference = data.get("reference")
        if reference:
            from redis_config import red
            if await red.get(f"paystack:processed:{reference}"):
                return {"status": "already_processed"}

        current_time = datetime.now()
        expiry_date = current_time + (
            timedelta(weeks=16) if plan_type == "semester" else timedelta(weeks=24)
        )
        user = await self.get_user_by_telegram_id(str(telegram_id), session)
        if user is None or user.user_id != user_id:
            return {"status": "ignored", "reason": "user_not_found_or_mismatch"}

        # A portal account can have one Telegram row and one or more WhatsApp
        # rows. Keep the subscription fields synchronized across all channel IDs.
        related_result = await session.execute(select(User).where(User.user_id == user_id))
        related_users = related_result.scalars().all()
        for related_user in related_users:
            related_user.is_paid = True
            related_user.expiry = expiry_date
            related_user.level = int(metadata.get("level") or related_user.level)
        await session.commit()
        paid_ttl = int((timedelta(weeks=16 if plan_type == "semester" else 24)).total_seconds())
        await save_payment(user_id=user_id, truth_value="truth", ttl_seconds=paid_ttl)
        if reference:
            from redis_config import red
            await red.set(f"paystack:processed:{reference}", "1", ex=60 * 60 * 24 * 365)

        if channel == "whatsapp":
            phone = metadata.get("whatsapp_id") or str(telegram_id).removeprefix("wa:")
            gateway_url = __import__("os").getenv("WHATSAPP_GATEWAY_URL", "").rstrip("/")
            gateway_token = __import__("os").getenv("WHATSAPP_GATEWAY_TOKEN", "")
            if phone and gateway_url and gateway_token:
                try:
                    async with httpx.AsyncClient(timeout=20) as client:
                        await client.post(
                            f"{gateway_url}/send",
                            json={"to": phone, "text": "✅ Payment verified successfully! Your Acadex subscription is now active. Send MENU to continue."},
                            headers={"Authorization": f"Bearer {gateway_token}"},
                        )
                except Exception as exc:
                    print(f"WhatsApp payment notification failed: {exc}", flush=True)
        else:
            try:
                await bot.send_message(
                    chat_id=str(telegram_id),
                    text="✅ Payment Verified Successfully. Your Acadex subscription is now active.",
                )
            except Exception as exc:
                print(f"Telegram payment notification failed: {exc}", flush=True)
        return {"status": "success", "channel": channel}

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
        """Check the shared portal account subscription across channel records."""
        current_user = await self.get_user_by_telegram_id(telegram_id=telegram_id, session=session)
        if current_user is None or current_user.user_id != user_id:
            raise HTTPException(status_code=404, detail="User not found")

        result = await session.execute(select(User).where(User.user_id == user_id))
        related_users = result.scalars().all()
        today = datetime.now().date()
        active_users = [
            item for item in related_users
            if item.is_paid and item.expiry is not None and today <= item.expiry
        ]
        if active_users:
            latest_expiry = max(item.expiry for item in active_users)
            for item in related_users:
                item.is_paid = True
                item.expiry = latest_expiry
            await session.commit()
            remaining = max((latest_expiry - today).days, 1)
            await save_payment(
                user_id=user_id,
                truth_value="truth",
                ttl_seconds=remaining * 24 * 60 * 60,
            )
            return False

        for item in related_users:
            item.is_paid = False
        await session.commit()
        await save_payment(user_id=user_id, truth_value="false")
        # This method is used by the Telegram payment flow. Never try to send a
        # WhatsApp namespaced ID to Telegram's Bot API.
        if not str(telegram_id).startswith("wa:"):
            try:
                await bot.send_message(
                    chat_id=str(telegram_id),
                    text="Payment Expired or Payment hasn't been made".title(),
                )
            except Exception as exc:
                print(f"Telegram expiry notification failed: {exc}", flush=True)
        return True
