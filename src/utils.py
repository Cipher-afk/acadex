from passlib.context import CryptContext
from datetime import datetime, timedelta
from aiogram.types import Message
from tasks import future_sessions
import asyncio

context = CryptContext(["argon2"])


def hash_password(password):
    hashed_password = context.hash(password)
    return hashed_password


def verify_password(password, hashed_password):
    return True if context.verify(password, hashed_password) else False

async def ask_for_wait(message:Message,text,callback_buttons,timeout=30000):
    user_id = message.from_user.id
    future = asyncio.get_running_loop().create_future()
    future_sessions[user_id] = future
    await message.answer(text,reply_markup=callback_buttons)
    try:
        return await asyncio.wait_for(future, timeout=timeout)
    except asyncio.TimeoutError:
        await message.answer("You took too long to respond. Please try again.")
        future_sessions.pop(user_id, None)
        return None
    finally:
        future_sessions.pop(user_id, None)
