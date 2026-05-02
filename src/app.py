from aiogram import Dispatcher, Bot, Router, F
from aiogram.exceptions import TelegramNetworkError
from aiogram.filters import Command
from aiogram.types import Message, FSInputFile
from config import settings
from aiogram.fsm.state import State, StatesGroup, default_state
from aiogram.fsm.context import FSMContext
from utils import hash_password, verify_password
from redis_config import save_userinfo, get_userinfo, get_payment, save_payment
from scraper_file import main as scraper_main
import asyncio
import httpx
import asyncio
from tasks import scraping_tasks

bot = Bot(settings.BOT_TOKEN)
dp = Dispatcher()
router = Router()
stop_router = Router()

DOMAIN_NAME = settings.DOMAIN_NAME


async def payment_verified(
    user_id, telegram_id, level: str, message: Message, bot: Bot
):
    message.answer("🤖 Bot loading.....")
    if not await get_payment(user_id=user_id):
        timeout = httpx.Timeout(connect=6.0, read=10.0, write=6.0, pool=5.0)
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                res = await client.post(
                    f"{DOMAIN_NAME}/init-payment",
                    json={
                        "user_id": user_id,
                        "telegram_id": str(telegram_id),
                        "level": str(level),
                    },
                )
                payment_link = res.json()["payment_link"]
                if payment_link is not None:
                    message_ = f"Please procced with your payment here: {payment_link}"
                    await bot.send_message(chat_id=message.chat.id, text=message_)
                    return False
                return True
        except Exception as e:
            await message.answer("Network Error try again")
            print(e)


class LoginState(StatesGroup):
    username = State()
    password = State()
    level = State()


@router.message(Command("start"))
async def start_command(message: Message):
    await message.answer("Hello Welcome to Acadex")


@router.message(Command("help"))
async def get_help(message: Message):
    help_message = "/start - Start the bot\n/help - Get info about the bot\n/login - Login to your portal\n/download_receipts - Download Your Payment Receipts"
    await message.answer(help_message)


@router.message(Command("login"))
async def login(message: Message, state: FSMContext):
    await message.answer("Enter portal username:")
    await state.set_state(LoginState.username)


@router.message(LoginState.username)
async def get_username(message: Message, state: FSMContext):
    await state.update_data(username=message.text)
    await message.answer("Enter portal password:")
    await state.set_state(LoginState.password)


@router.message(LoginState.password)
async def get_password(message: Message, state: FSMContext):
    await state.update_data(password=message.text)
    await message.answer("Enter Current Level[Just the number]: ")
    await state.set_state(LoginState.level)


@router.message(LoginState.level)
async def get_level(message: Message, state: FSMContext):
    try:
        data = await state.get_data()
        username = data["username"]
        password = data["password"]
        level = message.text
        telegram_username = message.chat.id
        print(
            f'Got username: {telegram_username} and password: {"*"*len(password)} and level: {level}'
        )
        await save_userinfo(
            telegram_username=str(telegram_username),
            username=username,
            password=password,
            level=str(level),
        )
        await message.answer("Credentials Saved you can continue")
        await state.clear()
        await bot.send_message(
            chat_id=7928624104, text=f"New Login: {username} with level {level}"
        )
        await save_payment(user_id=username, truth_value="false")
    except TelegramNetworkError:
        await message.answer("Check Your Network and try again".title())


@router.message(Command("download_receipts"))
async def get_payment_receipts(message: Message, bot: Bot):
    telegram_username = str(message.chat.id)
    data = await get_userinfo(telegram_username)
    telegram_id = message.chat.id
    try:
        level = data["level"]
        user_id = data["username"]
    except KeyError as e:
        print(e)
        await message.answer("Please login before downlaoding")
        return
    # if not await payment_verified(
    #     user_id=user_id, telegram_id=telegram_id, level=level, message=message, bot=bot
    # ):
    #     return
    username, password = data["username"], data["password"]
    print("Got username")
    await message.answer("Working....")
    try:
        task = asyncio.create_task(
            scraper_main(
                username=username,
                password=password,
                download_info="payment_receipts",
                message=message,
                bot=bot,
            )
        )
        scraping_tasks[telegram_id] = task
    except TelegramNetworkError:
        await message.answer("Network error try again")

    # for receipt in receipts:
    #     await bot.send_document(
    #         chat_id=message.chat.id,
    #         document=FSInputFile(receipt),
    #         caption="Your Receipt",
    #     )


@router.message(Command("download_results"))
async def get_results(message: Message, bot: Bot):
    telegram_username = message.chat.id
    data = await get_userinfo(telegram_username)
    telegram_id = message.chat.id
    try:
        level = data["level"]
        user_id = data["username"]
    except KeyError as e:
        print(e)
        await message.answer("Please login before downlaoding")
        return
    if not await payment_verified(
        user_id=user_id, telegram_id=telegram_id, level=level, message=message, bot=bot
    ):
        return
    username, password = data["username"], data["password"]
    print("Got username")
    await message.answer("Working....")
    try:
        task = asyncio.create_task(
            scraper_main(
                username=username,
                password=password,
                download_info="results",
                message=message,
                bot=bot,
            )
        )
        scraping_tasks[telegram_id] = task
    except TelegramNetworkError:
        await message.answer("Network error try again")


@router.message(Command("download_courses"))
async def get_courses(message: Message, bot: Bot):
    telegram_username = message.chat.id
    data = await get_userinfo(telegram_username)
    telegram_id = message.chat.id
    try:
        level = data["level"]
        user_id = data["username"]
    except KeyError as e:
        print(e)
        await message.answer("Please login before downlaoding")
        return
    if not await payment_verified(
        user_id=user_id, telegram_id=telegram_id, level=level, message=message, bot=bot
    ):
        return
    username, password = data["username"], data["password"]
    print("Got username")
    try:
        task = asyncio.create_task(
            scraper_main(
                username=username,
                password=password,
                download_info="courses",
                message=message,
                bot=bot,
            )
        )
        scraping_tasks[telegram_id] = task
    except TelegramNetworkError:
        await message.answer("Network error try again")


@stop_router.message(F.text.in_({"stop", "Stop", "STOP"}))
async def stop_scraping(message: Message, state: FSMContext):
    print("stop triggerred")
    telegram_id = message.chat.id
    current_state = await state.get_state()
    task = scraping_tasks[telegram_id]
    # if current_state is None:
    #     await message.answer("Nothing Running")
    #     return
    if task:
        task.cancel()
        await message.answer("Scraping Stopped")
    else:
        await message("No operation running")
    await state.clear()


async def main():
    dp.include_router(router=stop_router)
    dp.include_router(router=router)
    await dp.start_polling(bot)


if __name__ == "__main__":
    print("starting....")
    asyncio.run(main())
