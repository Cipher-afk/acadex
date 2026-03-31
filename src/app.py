from aiogram import Dispatcher, Bot, Router
from aiogram.exceptions import TelegramNetworkError
from aiogram.filters import Command
from aiogram.types import Message, FSInputFile
from config import settings
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from utils import hash_password, verify_password
from redis_config import save_userinfo, get_userinfo, get_payment, save_payment
from scraper_file import main as scraper_main
import asyncio
import httpx

bot = Bot(settings.BOT_TOKEN)
dp = Dispatcher()
router = Router()


async def check_payment(user_id,telegram_id,level,message:Message,bot:Bot):
    if not await get_payment(user_id=user_id):
        try:
            async with httpx.AsyncClient() as client:
                res = await client.post(
                    "http://127.0.0.1:9000/init-payment",
                    json={
                        "user_id": user_id,
                        "telegram_id": str(telegram_id),
                        "level": level,
                    },
                )
                payment_link = res.json()["payment_link"]
                if payment_link is not None:
                    message_ = f"Please procced with your payment here: {payment_link}"
                    await bot.send_message(chat_id=message.chat.id, text=message_)
                    return
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
    help_message = "/start - Start the bot\n/help - Get info about the bot\n/login - Login to your portal\n/download_receipts - Download Payment Receipts"
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
    await message.answer("Enter Current Level: ")
    await state.set_state(LoginState.level)


@router.message(LoginState.level)
async def get_level(message: Message, state: FSMContext):
    try:
        data = await state.get_data()
        username = data["username"]
        password = data["password"]
        level = message.text
        telegram_username = message.chat.username
        await save_userinfo(
            telegram_username=telegram_username,
            username=username,
            password=password,
            level=level,
        )
        await message.answer("Credentials Saved you can continue")
        await state.clear()
        await save_payment(user_id=username, truth_value="false")
    except TelegramNetworkError:
        await message.answer("Check Your Network and try again".title())


@router.message(Command("download_receipts"))
async def get_payment_receipts(message: Message, bot: Bot):
    telegram_username = message.chat.username
    data = await get_userinfo(telegram_username)
    telegram_id = message.chat.id
    level = data["level"]
    user_id = data["username"]
    await check_payment(user_id=user_id,telegram_id=telegram_id,level=level,message=message,bot=bot)
    username, password = data["username"], data["password"]
    print("Got username")
    await message.answer("Working....")
    try:
        await scraper_main(
            username=username,
            password=password,
            download_info="payment_receipts",
            message=message,
            bot=bot,
        )
    except TelegramNetworkError:
        await message.answer("Network error try again")

    # for receipt in receipts:
    #     await bot.send_document(
    #         chat_id=message.chat.id,
    #         document=FSInputFile(receipt),
    #         caption="Your Receipt",
    #     )


@router.message(Command("download_results"))
async def get_results(message: Message):
    pass


@router.message(Command("download_courses"))
async def get_courses(message: Message, bot: Bot):
    telegram_username = message.chat.username
    data = await get_userinfo(telegram_username)
    telegram_id = message.chat.id
    level = data["level"]
    user_id = data["username"]
    await check_payment(user_id=user_id,telegram_id=telegram_id,level=level,message=message,bot=bot)
    username, password = data["username"], data["password"]
    print("Got username")
    await scraper_main(
        username=username,
        password=password,
        download_info="courses",
        message=message,
        bot=bot,
    )


async def main():
    dp.include_router(router=router)
    await dp.start_polling(bot)


if __name__ == "__main__":
    print("starting....")
    asyncio.run(main())
