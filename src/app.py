from aiogram import Dispatcher, Bot, Router, F
from aiogram.exceptions import TelegramNetworkError
from aiogram.filters import Command
from aiogram.types import Message, FSInputFile, CallbackQuery
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
from buttons import get_service_buttons, create_button,get_university_buttons,get_access_buttons,get_withdraw_refresh_buttons,confirm_retry_buttons
from payment_api.service import PaymentService
from payment_api.models import MarketerModel,InitPayment
from payment_api.db_models import Marketer
from payment_api.database_config import get_session_ctx

bot = Bot(settings.BOT_TOKEN)
dp = Dispatcher()
router = Router()
stop_router = Router()
payment_service = PaymentService()


DOMAIN_NAME = settings.DOMAIN_NAME
login_button = create_button(text="Login", callback_data="login")
services_buttons = get_service_buttons()
access_buttons = get_access_buttons()

async def get_marketer_data(marketer:Marketer):
    users_data = await payment_service.get_users_referred_by_marketer(marketer_username=marketer.username)
    all_users = users_data['all_users']
    paid_users = users_data['paid_users']
    amount_paid = marketer.amount_paid
    gain_made = ((1000 * paid_users) * 0.2) - amount_paid
    withdraw_refresh_buttons = get_withdraw_refresh_buttons(gain_made=gain_made)
    return all_users,paid_users,gain_made,amount_paid,withdraw_refresh_buttons

async def get_marketer_info(marketer:Marketer,state:FSMContext,message:Message):
    all_users,paid_users,gain_made,amount_paid,withdraw_refresh_buttons = await get_marketer_data(marketer=marketer)
    await state.clear()
    await message.answer(f"""
Your Records are as follows 

Normal Users 👨‍💻 = {all_users}

Paid Users 💲👨‍💻 = {paid_users}

Gain Made 💰 = {gain_made}

Amount Withdrawn = {amount_paid}
""",reply_markup=withdraw_refresh_buttons)

async def get_fresh_market_info(callback:CallbackQuery,marketer:Marketer):
    all_users,paid_users,gain_made,amount_paid,withdraw_refresh_buttons = await get_marketer_data(marketer=marketer)
    await callback.message.edit_text(f"""
Your Records are as follows 

Normal Users 👨‍💻 = {all_users}

Paid Users 💲👨‍💻 = {paid_users}

Gain Made 💰 = {gain_made}

Amount Withdrawn = {amount_paid}
""",reply_markup=withdraw_refresh_buttons)


async def payment_verified(
    user_id, telegram_id, level: str, message: Message, bot: Bot
):
    await message.answer("🤖 Bot loading.....")
    if user_id != "kudos.ajao":
        if not await get_payment(user_id=user_id):
            timeout = httpx.Timeout(connect=6.0, read=10.0, write=6.0, pool=5.0)
            try:
                print('Tried sending request cause payment wasn\'t gotten from redis',flush=True)
                async with httpx.AsyncClient(timeout=timeout) as client:
                    res = await client.post(
                        f"{DOMAIN_NAME}/init-payment",
                        json={
                            "user_id": user_id,
                            "telegram_id": str(telegram_id),
                            "level": str(level),
                        },
                    )
                    print(res.status_code,res.text,flush=True)
                    payment_link = res.json()["payment_link"]
                    if payment_link is not None:
                        message_ = f"Please procced with your payment of 1000 naira here for a session of complete freedom 😌: {payment_link}\n Note: All features will be unlocked immediately upon successful payment"
                        await bot.send_message(chat_id=message.chat.id, text=message_)
                        return False
                    print('Payment is None',flush=True)
                    return True
            except Exception as e:
                await message.answer("Network Error try again")
                print(e)
        print("Got from redis it was true",flush=True)
        return True



class LoginState(StatesGroup):
    university = State()
    username = State()
    password = State()
    referrer = State()
    level = State()

class AdminCodeState(StatesGroup):
    admin_code = State()

class MarketerSignup(StatesGroup):
    username = State()
    password = State()

class MarketerLogin(StatesGroup):
    username = State()
    password = State()

class WithdrawState(StatesGroup):
    account_number = State()
    bank = State()
    account_name = State()
    amount_to_withdraw = State()
    telegram_id = State()


@router.message(Command("start"))
async def start_command(message: Message):
    await message.answer(
        """
👋 *Hello Welcome to Acadex*

To get started, just follow these simple steps:

1️⃣️ *Login* - Connect your FUO Portal Account using the button below.

2️⃣ *Choose a service* - Use any of the available tools offered like:
🧾 Download Receipts, 📄 Download courses and much more

3️⃣ *Relax 🥂😎* - Chill and relax while the bot works in the background 😎🥂 

💰 *Note*: A one-time fee of 1000 naira is needed to unlock all services for your current academic session and during release of results
acadex might have a little delay in getting your results due to the portal's response time but rest assured you will get your results as soon as possible cause acadex is a bot that works 24/7 and never sleeps 😎🥂

🔧 *Commands you can use anytime:*

/login - Connect your FUO Portal Account
/services - Get the list of tools offered

Simple and Easy. Tap *Login* below to begin 👇
And also Downloading Receipts is free for all users, let's give you a test run of the bot by downloading your receipts for free 😎🥂
""",
        reply_markup=login_button,
        parse_mode="Markdown",
    )


@router.message(Command("help"))
async def get_help(message: Message):
    help_message = "/start - Start the bot\n/login - Connect Your FUO Portal Account\n/services - Get the list of tools offered"
    await message.answer(help_message)


@router.callback_query(F.data == "login")
async def login(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    university_buttons = get_university_buttons()
    await callback.message.answer('Pick your university',reply_markup=university_buttons)
    # await callback.message.answer("Enter portal username:")
    await state.set_state(LoginState.university)


@router.message(Command("login"))
async def login(message: Message, state: FSMContext):
    university_buttons = get_university_buttons()
    await message.answer("Enter portal username:")
    await message.answer('Pick your university',reply_markup=university_buttons)
        # await callback.message.answer("Enter portal username:")
    await state.set_state(LoginState.university)


@router.message(Command("services"))
async def get_services(message: Message):
    await message.answer(
        "Pick one of the services and enjoy your day while acadex does your work 🥂🛀",
        reply_markup=services_buttons,
    )

@router.message(Command('apply_for_marketer_position'))
async def apply_for_a_marketer(message:Message,state:FSMContext):
    await message.answer("Enter Code given to you by admin to login as an admin marketer\nor follow the options below for normal marketers",reply_markup=access_buttons)
    await state.set_state(AdminCodeState.admin_code)

@router.message(AdminCodeState.admin_code)
async def verify_admin_code(message:Message):
    admin_marketer_button = create_button(text='Login',callback_data='admin_marketer_login')
    user_entered_code = message.text
    admins_code = settings.ADMIN_CODE
    if user_entered_code == admins_code:
        await message.text('Hello There Admin Marketer click on the Login button below to identify your referrals',reply_markup=admin_marketer_button)
        return
    await message.answer('Sorry the code is wrong please contact the admin that gae it to you or create a new account as a marketer',reply_markup=access_buttons)

@router.callback_query(F.data == 'admin_marketer_login')
async def admin_marketer_login(callback:CallbackQuery,state:FSMContext):
    await callback.answer()
    telegram_id = str(callback.message.chat.id)
    payment_link_data = await payment_service.generate_marketer_payment_link(telegram_id=telegram_id)
    payment_link = payment_link_data['payment_link']
    if payment_link is not None:
        message_ = f"Please procced with your payment of 500 naira here to become a certified acadex marketer 😌: {payment_link}"
        await callback.message.edit_text(text=message_)
        return
    await callback.message.answer("Enter Username")
    await state.set_state(MarketerLogin.username)

@router.callback_query(F.data == 'marketer_login')
async def marketer_login(callback:CallbackQuery,state:FSMContext):
    await callback.answer()
    telegram_id = str(callback.message.chat.id)
    payment_link_data = await payment_service.generate_marketer_payment_link(telegram_id=telegram_id)
    payment_link = payment_link_data['payment_link']
    if payment_link is not None:
        message_ = f"Please procced with your payment of 500 naira here to become a certified acadex marketer 😌: {payment_link}"
        await callback.message.edit_text(text=message_)
        return
    await callback.message.answer("Enter Username")
    await state.set_state(MarketerLogin.username)

@router.message(MarketerLogin.username)
async def get_login_username(message:Message,state:FSMContext):
    username = message.text
    await state.update_data(username=username)
    await message.answer('Enter Password')
    await state.set_state(MarketerLogin.password)

@router.message(MarketerLogin.password)
async def get_login_password(message:Message,state:FSMContext):
    data = await state.get_data()
    username = data['username']
    password = message.text
    marketer = await payment_service.get_marketer_by_username(username=username)
    if marketer is None:
        await message.answer('Username Invalid Please enter a correct username')
        await state.clear()
        return
    verified = await payment_service.is_marketer_password(marketer=marketer,password=password)
    if verified:
        await get_marketer_info(marketer=marketer,state=state,message=message)
        return
    await message.answer('Password Incorrect Please Try Again')

@router.callback_query(F.data == 'signup')
async def marketer_signup(callback:CallbackQuery,state:FSMContext):
    await callback.answer()
    await callback.message.answer('Enter username(any username)')
    await state.set_state(MarketerSignup.username)

@router.message(MarketerSignup.username)
async def get_username(message:Message,state:FSMContext):
    username = message.text
    await state.update_data(username=username)
    await message.answer('Enter Password')
    await state.set_state(MarketerSignup.password)

@router.message(MarketerSignup.password)
async def get_password(message:Message,state:FSMContext):
    data = await state.get_data()
    telegram_id = str(message.chat.id)
    username = data['username']
    password = message.text
    marketer_model = MarketerModel(telegram_id=telegram_id,username=username,password=password)
    marketer = await payment_service.create_marketer(marketer_model=marketer_model)
    await get_marketer_info(marketer=marketer,state=state,message=message)

@router.callback_query(F.data.startswith('withdraw'))
async def withdraw_money(callback:CallbackQuery,state:FSMContext):
    await state.clear()
    await callback.answer()
    data = callback.data
    amount_to_withdraw = data.split(':')[1]
    await state.update_data(amount_to_withdraw=amount_to_withdraw)
    await callback.message.answer('Enter Your Account Number:')
    await state.set_state(WithdrawState.account_number)

@router.message(WithdrawState.account_number)
async def get_account_number(message:Message,state:FSMContext):
    account_number = message.text
    await state.update_data(account_number=account_number)
    await message.answer('Enter the Bank Associated with the account number')
    await state.set_state(WithdrawState.bank)

@router.message(WithdrawState.bank)
async def get_bank(message:Message,state:FSMContext):
    bank = message.text
    await state.update_data(bank=bank)
    await message.answer("Enter Account Name associated with bank(Ensure you put in the correct name)")
    await state.set_state(WithdrawState.account_name)

@router.message(WithdrawState.account_name)
async def get_account_name(message:Message,state:FSMContext):
    account_name = message.text
    amount_to_withdraw = await state.get_data()['amount_to_withdraw']
    confirm_retry_buttons_ = confirm_retry_buttons(gain_made=amount_to_withdraw)
    await state.update_data(account_name=account_name)
    await message.answer('Click on Confirm to confirm account details',reply_markup=confirm_retry_buttons_)

@router.callback_query(F.data == 'confirm')
async def confirm_payment(callback:CallbackQuery,bot:Bot,state:FSMContext):
    await callback.answer()
    data = await state.get_data()
    account_number = data['account_number']
    bank = data['bank']
    account_name = data['bank']
    amount_to_withdraw = data['amount_to_withdraw']
    telegram_id = str(callback.message.chat.id)
    if int(amount_to_withdraw) < 1000:
        await callback.message.answer('You must bring atleast 5 or more paid users to withdraw 😐')
        return
    marketer = await payment_service.get_marketer_by_telegram_id(telegram_id=telegram_id)
    username = marketer.username
    await callback.message.answer('Your Details have been sent to the admin you will remove your payment in less than 24hrs we at acadex thank you for your work'.title())
    admin_message = f"""
{username} requested a withdrawal

Account Number: {account_number}

Account Name: {account_name}

Bank Name: {bank}

Telegram_id: {telegram_id}

Amount: {amount_to_withdraw} naira
"""
    await bot.send_message(chat_id=settings.ADMINS_TELEGRAM_ID,text=admin_message)
    await payment_service.update_marketer_info(marketer=marketer,message=callback.message,info={'amount_paid':amount_to_withdraw})

@router.callback_query(F.data == 'refresh_users')
async def refresh_data(callback:CallbackQuery):
    await callback.answer()
    telegram_id = str(callback.message.chat.id)
    marketer = await payment_service.get_marketer_by_telegram_id(telegram_id=telegram_id)
    await get_fresh_market_info(callback=callback,marketer=marketer)

@router.callback_query(F.data.startswith('university'))
async def store_university(callback:CallbackQuery,state:FSMContext):
    await callback.answer()
    data = callback.data
    university_name = data.split(':')[1]
    await state.update_data(university=university_name)
    await callback.message.answer("Enter portal username:")
    await state.set_state(LoginState.username)

@router.message(LoginState.username)
async def get_username(message: Message, state: FSMContext):
    await state.update_data(username=message.text)
    await message.answer("Enter portal password:")
    await state.set_state(LoginState.password)

@router.message(LoginState.password)
async def get_password(message: Message, state: FSMContext):
    await state.update_data(password=message.text)
    telegram_id = str(message.chat.id)
    async with get_session_ctx() as session:
        user = await payment_service.get_user_by_telegram_id(telegram_id=telegram_id,session=session)
    if user is not None:
        if user.referrer is not None:
            await message.answer("Enter Current Level[Just the number (eg. 100)]: ")
            await state.set_state(LoginState.referrer)
            return
        await message.answer("Enter Your referrer name or none if you don't have one")
    await state.set_state(LoginState.referrer)

@router.message(LoginState.referrer)
async def get_referrer(message:Message,state:FSMContext):
    await state.update_data(referrer=message.text)
    await message.answer("Enter Current Level[Just the number (eg. 100)]: ")
    await state.set_state(LoginState.level)

@router.message(LoginState.level)
async def get_level(message: Message, state: FSMContext):
    try:
        data = await state.get_data()
        university = data['university']
        username = data["username"]
        password = data["password"]
        referrer = data['referrer'] if data['referrer'] not in ['none','None','NONE'] else None
        level = message.text
        telegram_username = str(message.chat.id)
        print(
            f'Got username: {telegram_username} and password: {"*"*len(password)} and level: {level}'
        )
        await save_userinfo(
            university=university,
            telegram_username=str(telegram_username),
            username=username,
            password=password,
            level=str(level),
            referrer=referrer if referrer is not None else 'none'
        )
        user_info = InitPayment(user_id=username,telegram_id=str(telegram_username),level=level,referrer=referrer)
        await payment_service.create_user(user_info=user_info)
        await message.answer(
            "Credentials Saved Pick a service to continue".title(),
            reply_markup=services_buttons,
        )
        await state.clear()
        await bot.send_message(
            chat_id=7928624104, text=f"New Login: {username} with level {level} and from {university} referred from {referrer}"
        )
        await save_payment(user_id=username, truth_value="false")
    except TelegramNetworkError:
        await message.answer("Check Your Network and try again".title())


@router.callback_query(F.data == "download_receipts")
async def get_payment_receipts(callback: CallbackQuery, bot: Bot):
    await callback.answer()
    message = callback.message
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
    username, password,university = data["username"], data["password"],data['university']
    await bot.send_message(
        chat_id=7928624104, text=f"{username} with level {level} and from {university} just attempted to download payment receipts"
    )
    print("Got username")
    await message.answer("Working....")
    try:
        task = asyncio.create_task(
            scraper_main(
                university=university,
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


@router.callback_query(F.data == "download_results")
async def get_results(callback: CallbackQuery, bot: Bot):
    await callback.answer()
    message = callback.message
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
    username, password,university = data["username"], data["password"],data['university']
    await bot.send_message(
        chat_id=7928624104, text=f"{username} with level {level} and from {university} just attempted to download results"
    )
    print("Got username")
    await message.answer("Working....")
    try:
        task = asyncio.create_task(
            scraper_main(
                university=university,
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


@router.callback_query(F.data == "result_summary")
async def get_result_summary(callback: CallbackQuery, bot: Bot):
    await callback.answer()
    message = callback.message
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
    username, password,university = data["username"], data["password"],data['university']
    await bot.send_message(
        chat_id=7928624104, text=f"{username} with level {level} and from {university} just attempted to download result summary"
    )
    print("Got username")
    await message.answer("Working....")
    try:
        task = asyncio.create_task(
            scraper_main(
                university=university,
                username=username,
                password=password,
                download_info="result_summary",
                message=message,
                bot=bot,
            )
        )
        scraping_tasks[telegram_id] = task
    except TelegramNetworkError:
        await message.answer("Network error try again")


@router.callback_query(F.data == "download_courses")
async def get_courses(callback: CallbackQuery, bot: Bot):
    await callback.answer()
    message = callback.message
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
    username, password,university = data["username"], data["password"],data['university']
    await bot.send_message(
        chat_id=7928624104, text=f"{username} with level {level} and from {university} just attempted to download course registration"
    )
    print("Got username")
    try:
        task = asyncio.create_task(
            scraper_main(
                university=university,
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


@router.callback_query(F.data == "download_biodata")
async def get_biodata(callback: CallbackQuery, bot: Bot):
    await callback.answer()
    message = callback.message
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
    username, password,university = data["username"], data["password"],data['university']
    await bot.send_message(
        chat_id=7928624104, text=f"{username} with level {level} and from {university} just attempted to download biodata"
    )
    print("Got username")
    try:
        task = asyncio.create_task(
            scraper_main(
                university=university,
                username=username,
                password=password,
                download_info="biodata",
                message=message,
                bot=bot,
            )
        )
        scraping_tasks[telegram_id] = task
    except TelegramNetworkError:
        await message.answer("Network error try again")


@router.callback_query(F.data == "admission_forms")
async def get_admission_forms(callback: CallbackQuery, bot: Bot):
    await callback.answer()
    message = callback.messagea
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
    username, password,university = data["username"], data["password"],data['university']
    await bot.send_message(
        chat_id=7928624104, text=f"{username} with level {level} and from {university} just attempted to download admission forms"
    )
    print("Got username")
    try:
        task = asyncio.create_task(
            scraper_main(
                university=university,
                username=username,
                password=password,
                download_info="admission_forms",
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


@stop_router.message(F.photo)
async def handle_photo(message: Message):
    await message.answer(
        "Photo received. Currently, I cannot process photos actually i don't need photos 🙂."
    )


async def main():
    dp.include_router(router=stop_router)
    dp.include_router(router=router)
    await dp.start_polling(bot)


if __name__ == "__main__":
    print("starting....")
    asyncio.run(main())
