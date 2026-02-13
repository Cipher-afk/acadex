from redis.asyncio import Redis
import asyncio
from config import settings

REDIS_PASSWORD = settings.REDIS_PASSWORD
REDIS_PORT = settings.REDIS_PORT
REDIS_HOST = settings.REDIS_HOST

red = Redis(
    host=REDIS_HOST, port=REDIS_PORT, password=REDIS_PASSWORD, decode_responses=True
)


async def store_url(url: str):
    await red.set("session_url", url, ex=300)


async def get_url():
    session_url = await red.get("session_url")
    return session_url


async def save_userinfo(telegram_username: str, username, password, level):
    await red.hset(
        telegram_username,
        mapping={f"username": username, f"password": password, "level": level},
    )


async def get_userinfo(telegram_username: str):
    user_info = await red.hgetall(telegram_username)
    return user_info


async def register_user(telegram_id: str):
    await red.set(f"paid:{telegram_id}", "false")


async def save_payment(telegram_id: str):
    await red.set(f"paid:{telegram_id}", "true")


async def get_payment(telegram_id: str):
    paid = await red.get(f"paid:{telegram_id}")
    return True if paid == "true" else False


if __name__ == "__main__":

    async def main():
        if await red.ping():
            print("yaay")
        else:
            print("naay")

    asyncio.run(main())
