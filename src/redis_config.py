from redis.asyncio import Redis
import asyncio
from config import settings
from datetime import timedelta
from utils import encrypt_portal_password, decrypt_portal_password

REDIS_PASSWORD = settings.REDIS_PASSWORD
REDIS_PORT = settings.REDIS_PORT
REDIS_HOST = settings.REDIS_HOST
TTL = int(timedelta(weeks=24).total_seconds())

red = Redis(
    host=REDIS_HOST, port=REDIS_PORT, password=REDIS_PASSWORD, decode_responses=True
)


async def store_url(url: str):
    await red.set("session_url", url, ex=300)


async def get_url():
    session_url = await red.get("session_url")
    return session_url


async def save_userinfo(
    telegram_username: str, username, password, level, university, referrer
):
    encrypted_password = await encrypt_portal_password(password=password)
    await red.hset(
        telegram_username,
        mapping={
            f"username": username,
            f"password": encrypted_password,
            "level": level,
            "university": university,
            "referrer": referrer,
        },
    )


async def get_userinfo(telegram_username: str):
    user_info = await red.hgetall(telegram_username)
    encrypted_password = user_info["password"]
    user_info["password"] = await decrypt_portal_password(
        encrypted_password=encrypted_password
    )
    return user_info


# async def register_user(telegram_id: str):
#     await red.set(f"paid:{telegram_id}", "false")


async def save_payment(user_id: str, truth_value: str, ttl_seconds: int | None = None):
    # Existing callers retain the original 24-week default. Payment activation
    # can supply the exact semester/session duration.
    await red.set(f"paid:{user_id}", truth_value, ex=ttl_seconds or TTL)


async def get_payment(user_id: str):
    paid = await red.get(f"paid:{user_id}")
    return True if paid == "truth" else False


if __name__ == "__main__":

    async def main():
        if await red.ping():
            print("yaay")
        else:
            print("naay")

    asyncio.run(main())
