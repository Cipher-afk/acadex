from __future__ import annotations

import asyncio
import logging
from typing import Any

from redis_config import get_payment, get_userinfo, red, save_userinfo
from scraper_file import main as scraper_main
from tasks import scraping_tasks
from whatsapp.adapter import WhatsAppBot, WhatsAppMessage
from whatsapp.client import WhatsAppClient

logger = logging.getLogger(__name__)

SERVICE_COMMANDS = {
    "/receipts": ("payment_receipts", False, "Downloading your payment receipts..."),
    "/results": ("results", True, "Fetching your results..."),
    "/summary": ("result_summary", True, "Preparing your result summary..."),
    "/courses": ("courses", True, "Downloading your registered courses..."),
    "/biodata": ("biodata", True, "Getting your biodata..."),
    "/admission_forms": ("admission_forms", True, "Getting your admission forms..."),
}

START_TEXT = """👋 Hello, welcome to Acadex!

Use Acadex on WhatsApp to access your academic services.

Commands:
/start - Start Acadex
/help - Show commands
/login - Connect your FUO or RSU portal account
/services - Show available services

After logging in, use /receipts, /results, /summary, /courses, /biodata or /admission_forms."""

HELP_TEXT = """Acadex commands:
/start - Start the bot
/help - Show this help message
/login - Connect your university portal account
/services - List available services
/receipts - Download payment receipts (free)
/results - Download examination results
/summary - Get result summary
/courses - Download registered courses
/biodata - Download biodata
/admission_forms - Download admission forms
/stop - Request cancellation of a running scrape"""


async def _set_state(phone: str, state: str, **values: str) -> None:
    mapping = {"state": state, **values}
    await red.hset(f"whatsapp:state:{phone}", mapping=mapping)
    await red.expire(f"whatsapp:state:{phone}", 1800)


async def _get_state(phone: str) -> dict[str, str]:
    return await red.hgetall(f"whatsapp:state:{phone}")


async def _clear_state(phone: str) -> None:
    await red.delete(f"whatsapp:state:{phone}")


async def _start_login(message: WhatsAppMessage) -> None:
    await _set_state(message.chat.id, "university")
    await message.answer(
        "Let's connect your university portal account.\n\n"
        "Reply with one of these university codes:\nFUO - Federal University Otuoke\n"
        "RSU - Rivers State University"
    )


async def _handle_login_step(message: WhatsAppMessage, text: str, state: dict[str, str]) -> bool:
    phone = message.chat.id
    current = state.get("state")
    if not current:
        return False

    if current == "university":
        university = text.strip().upper()
        if university not in {"FUO", "RSU"}:
            await message.answer("Please reply with FUO or RSU.")
            return True
        await _set_state(phone, "username", university=university)
        await message.answer("Enter your university portal username or matric number:")
        return True

    if current == "username":
        await _set_state(phone, "password", university=state["university"], username=text.strip())
        await message.answer("Enter your university portal password. Your message is handled as a private credential; don't share it in groups.")
        return True

    if current == "password":
        await _set_state(phone, "level", university=state["university"], username=state["username"], password=text)
        await message.answer("Enter your current level (numbers only, e.g. 100):")
        return True

    if current == "level":
        level = text.strip()
        if not level.isdigit():
            await message.answer("Please enter your level as a number, e.g. 100.")
            return True
        await save_userinfo(
            telegram_username=phone,
            username=state["username"],
            password=state["password"],
            level=level,
            university=state["university"],
            referrer="none",
        )
        await _clear_state(phone)
        await message.answer("Your portal details have been saved. Use /services to see what you can access.")
        return True

    return False


async def _run_scraper(message: WhatsAppMessage, bot: WhatsAppBot, command: str) -> None:
    phone = message.chat.id
    data = await get_userinfo(phone)
    if not data or not data.get("username"):
        await message.answer("Please connect your university portal account first using /login.")
        return

    download_info, requires_paid_access, status = SERVICE_COMMANDS[command]
    if requires_paid_access and not await get_payment(user_id=data["username"]):
        await message.answer(
            "This service requires an active Acadex subscription. Please activate your subscription through your existing Acadex payment flow before using this service."
        )
        return

    current_task = scraping_tasks.get(phone)
    if current_task and not current_task.done():
        await message.answer("You already have an operation running. Send /stop before starting another one.")
        return

    await message.answer(status)
    task = asyncio.create_task(
        scraper_main(
            university=data["university"],
            username=data["username"],
            password=data["password"],
            download_info=download_info,
            message=message,
            bot=bot,
        )
    )
    scraping_tasks[phone] = task


async def handle_whatsapp_message(phone: str, text: str) -> None:
    client = WhatsAppClient()
    message = WhatsAppMessage(phone, client)
    bot = WhatsAppBot(client)
    command = text.strip().split()[0].lower() if text.strip() else ""

    # A pending login conversation takes precedence over command parsing,
    # except /cancel which safely abandons the credential-entry flow.
    if command == "/cancel":
        await _clear_state(phone)
        await message.answer("Login cancelled.")
        return

    state = await _get_state(phone)
    if state and await _handle_login_step(message, text.strip(), state):
        return

    if command in {"/start", "hi", "hello"}:
        await message.answer(START_TEXT)
    elif command == "/help":
        await message.answer(HELP_TEXT)
    elif command == "/services":
        await message.answer(
            "Available Acadex services:\n/receipts - Payment receipts (free)\n"
            "/results - Examination results\n/summary - Result summary\n"
            "/courses - Registered courses\n/biodata - Biodata\n"
            "/admission_forms - Admission forms"
        )
    elif command == "/login":
        await _start_login(message)
    elif command == "/stop":
        task = scraping_tasks.get(phone)
        if task and not task.done():
            task.cancel()
            await message.answer("Cancellation requested.")
        else:
            await message.answer("There is no running operation to stop.")
    elif command in SERVICE_COMMANDS:
        await _run_scraper(message, bot, command)
    else:
        await message.answer("I didn't recognise that command. Send /help to see what Acadex can do.")
