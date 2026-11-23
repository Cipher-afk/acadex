"""Additive WhatsApp-to-Acadex bridge.

Run on the EXISTING Python/Telegram Oracle instance. It does not edit app.py,
redis_config.py, scraper_file.py, credentials, or Telegram handlers.
"""
from __future__ import annotations

import asyncio
import base64
import hmac
import json
import logging
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from config import settings
from redis_config import red, save_userinfo, get_userinfo, get_payment, save_payment
from payment_api.database_config import get_session_ctx
from payment_api.models import InitPayment, MarketerModel
from payment_api.service import PaymentService
from sqlmodel import select
from payment_api.db_models import Marketer, User
import scraper_file
from scraper_file import main as scraper_main

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("acadex.whatsapp.bridge")

BRIDGE_TOKEN = os.getenv("ACADEX_BRIDGE_TOKEN", "")
GATEWAY_URL = os.getenv("WHATSAPP_GATEWAY_URL", "").rstrip("/")
GATEWAY_TOKEN = os.getenv("WHATSAPP_GATEWAY_TOKEN", "")
STATE_TTL = 60 * 60 * 2
# Prompt timeout in SECONDS (the original utils.ask_for_wait treats `timeout` as seconds).
# Capped because a waiting prompt holds one of the scraper's concurrency slots.
PROMPT_TIMEOUT_CAP = int(os.getenv("WHATSAPP_PROMPT_TIMEOUT", "300"))

if not BRIDGE_TOKEN or not GATEWAY_URL or not GATEWAY_TOKEN:
    log.warning("WhatsApp bridge env is incomplete; set ACADEX_BRIDGE_TOKEN, WHATSAPP_GATEWAY_URL and WHATSAPP_GATEWAY_TOKEN")

router = APIRouter(tags=["WhatsApp"])
payment_service = PaymentService()
WA_USER_PREFIX = "wa:"

class Incoming(BaseModel):
    phone: str
    text: str
    message_id: str | None = None

class WhatsAppChat:
    def __init__(self, chat_id: str):
        self.id = chat_id

class WhatsAppMessage:
    def __init__(self, phone: str):
        self.chat = WhatsAppChat(phone)
        self.from_user = type("User", (), {"id": phone, "username": phone})()

    async def answer(self, text: str, reply_markup: Any = None, **kwargs):
        # Scraper progress text is sent as-is. Inline keyboard markup is translated
        # by the WhatsApp ask_for_wait adapter below, not silently discarded.
        await safe_send_text(self.chat.id, str(text))

class WhatsAppBot:
    async def send_message(self, chat_id: str, text: str, **kwargs):
        await safe_send_text(str(chat_id), str(text))

    async def send_document(self, chat_id: str, document: Any, caption: str | None = None, **kwargs):
        await safe_send_file(str(chat_id), document, caption=caption)

    async def send_photo(self, chat_id: str, photo: Any, caption: str | None = None, **kwargs):
        await safe_send_file(str(chat_id), photo, caption=caption)

bot_adapter = WhatsAppBot()
active_tasks: dict[str, asyncio.Task] = {}
waiters: dict[str, dict[str, Any]] = {}
background_tasks: set[asyncio.Task] = set()

async def send_text(phone: str, text: str):
    await gateway_request({"to": phone, "text": text})

async def safe_send_text(phone: str, text: str):
    # Used by the scraper adapters: a transient gateway hiccup must not abort a scrape.
    try:
        await send_text(phone, text)
    except Exception:
        log.exception("WhatsApp text send failed for %s", phone)

async def safe_send_file(phone: str, file_obj: Any, caption: str | None = None):
    try:
        await send_file(phone, file_obj, caption=caption)
    except Exception:
        log.exception("WhatsApp file send failed for %s", phone)

async def send_list(
    phone: str,
    text: str,
    rows: list[dict[str, str]],
    title: str = "Acadex",
    button_text: str = "Choose an option",
    by_rowid: bool = False,
):
    """Send choices as a plain numbered text message.

    WhatsApp does not reliably render interactive list messages sent through Baileys
    (and the send does not throw when it is not rendered), so a text menu is the
    dependable option. Replies are matched by number or by the option text.
    by_rowid=True uses each row's own id as its label (main menu); otherwise rows are
    numbered 1..n in order, which is what the prompt/waiter handlers expect.
    """
    lines = [f"*{title}*", text, ""]
    for index, row in enumerate(rows, start=1):
        row_id = str(row.get("rowId", ""))
        if by_rowid:
            label = f"{row_id}." if row_id.isdigit() else f"{row_id} →"
        else:
            label = f"{index}."
        description = row.get("description")
        line = f"{label} {row['title']}"
        if description and description != row["title"]:
            line += f" — {description}"
        lines.append(line)
    lines += ["", "Reply with the number of your choice." if not by_rowid else "Reply with a number, or type the keyword shown."]
    await send_text(phone, "\n".join(lines))

async def send_file(phone: str, file_obj: Any, caption: str | None = None):
    path = getattr(file_obj, "path", file_obj)
    path = Path(path)
    if not path.exists() or not path.is_file():
        await send_text(phone, caption or "Acadex could not locate the generated file.")
        return
    data = await asyncio.to_thread(path.read_bytes)
    if len(data) > 12 * 1024 * 1024:
        await send_text(phone, "The generated file is larger than the WhatsApp adapter's 12MB transfer limit. Please try a smaller request or use Telegram for this file.")
        return
    import mimetypes
    mimetype = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    await gateway_request({
        "to": phone,
        "mediaBase64": await asyncio.to_thread(lambda: base64.b64encode(data).decode("ascii")),
        "mimetype": mimetype,
        "filename": path.name,
        "caption": caption or "",
    })

async def gateway_request(payload: dict[str, Any], retries: int = 2):
    """POST to the Node gateway. Only retries cases where nothing was sent
    (connection refused / gateway reports WhatsApp not connected), never after a
    timeout, so a message is not delivered twice."""
    for attempt in range(retries + 1):
        try:
            async with httpx.AsyncClient(timeout=90) as client:
                response = await client.post(
                    f"{GATEWAY_URL}/send",
                    json=payload,
                    headers={"Authorization": f"Bearer {GATEWAY_TOKEN}"},
                )
        except (httpx.ConnectError, httpx.ConnectTimeout):
            if attempt < retries:
                await asyncio.sleep(2 * (attempt + 1))
                continue
            raise
        if response.status_code == 503 and attempt < retries:
            await asyncio.sleep(2 * (attempt + 1))
            continue
        response.raise_for_status()
        return response.json()

async def state_get(phone: str) -> dict[str, Any]:
    raw = await red.get(f"wa:flow:{phone}")
    return json.loads(raw) if raw else {}

async def state_set(phone: str, state: dict[str, Any]):
    await red.set(f"wa:flow:{phone}", json.dumps(state), ex=STATE_TTL)

async def state_clear(phone: str):
    await red.delete(f"wa:flow:{phone}")

async def show_menu(phone: str, intro: str | None = None):
    if intro:
        await send_text(phone, intro)
    rows = [
        {"title": "Connect portal account", "rowId": "1", "description": "Link your FUO or RSU portal"},
        {"title": "Download payment receipts", "rowId": "2", "description": "Free for all users"},
        {"title": "Download results", "rowId": "3", "description": "Requires an active subscription"},
        {"title": "Get result summary", "rowId": "4", "description": "Requires an active subscription"},
        {"title": "Registered courses", "rowId": "5", "description": "Requires an active subscription"},
        {"title": "Download biodata", "rowId": "6", "description": "Requires an active subscription"},
        {"title": "Admission documents", "rowId": "7", "description": "Requires an active subscription"},
        {"title": "Pay fee block", "rowId": "8", "description": "Portal fee-block workflow"},
        {"title": "Activate subscription", "rowId": "SUBSCRIBE", "description": "Unlock paid Acadex services"},
        {"title": "Marketer account", "rowId": "9", "description": "Sign up or log in to your marketer account"},
    ]
    await send_list(phone, "Select a service below. You can also type MENU, HELP, BACK, CANCEL or STOP at any time.", rows, title="Acadex Main Menu", by_rowid=True)

SERVICE_MAP = {
    "2": ("payment_receipts", "payment_receipts", True),
    "receipts": ("payment_receipts", "payment_receipts", True),
    "download receipts": ("payment_receipts", "payment_receipts", True),
    "3": ("results", "results", False),
    "results": ("results", "results", False),
    "download results": ("results", "results", False),
    "4": ("result summary", "result_summary", False),
    "result summary": ("result summary", "result_summary", False),
    "5": ("registered courses", "courses", False),
    "courses": ("registered courses", "courses", False),
    "registered courses": ("registered courses", "courses", False),
    "6": ("biodata", "biodata", False),
    "biodata": ("biodata", "biodata", False),
    "7": ("admission forms", "admission_forms", False),
    "admission forms": ("admission forms", "admission_forms", False),
    "8": ("pay fee block", "pay_fee_block", False),
    "pay fee block": ("pay fee block", "pay_fee_block", False),
}

async def ensure_whatsapp_database_user(phone: str, profile: dict[str, Any]):
    """Create/update the channel-specific DB identity from an existing Redis profile.

    This also upgrades WhatsApp profiles saved by earlier bridge versions that
    stored credentials in Redis but did not create a PostgreSQL user row.
    """
    username = profile.get("username")
    if not username:
        return None
    wa_user_id = f"{WA_USER_PREFIX}{phone}"
    raw_referrer = profile.get("referrer")
    referrer = raw_referrer if raw_referrer and str(raw_referrer).casefold() != "none" else None

    async with get_session_ctx() as session:
        if referrer:
            marketer_result = await session.execute(
                select(Marketer).where(Marketer.username == referrer)
            )
            if marketer_result.scalars().first() is None:
                referrer = None

        user = await payment_service.get_user_by_telegram_id(wa_user_id, session)
        if user is None:
            user = User(
                telegram_id=wa_user_id,
                user_id=username,
                level=int(profile.get("level") or 0),
                referrer=referrer,
                is_paid=False,
                expiry=datetime.now() + timedelta(weeks=24),
            )
            session.add(user)
            await session.commit()
            await session.refresh(user)
        else:
            await payment_service.update_info(
                wa_user_id,
                {"user_id": username, "level": int(profile.get("level") or 0), "referrer": referrer},
                session,
            )

        # If another channel already paid for this portal username, synchronize
        # the new WhatsApp identity with that same subscription.
        related_result = await session.execute(select(User).where(User.user_id == username))
        related_users = related_result.scalars().all()
        today = datetime.now().date()
        active = [u for u in related_users if u.is_paid and u.expiry is not None and today <= u.expiry]
        if active:
            latest_expiry = max(u.expiry for u in active)
            for related_user in related_users:
                related_user.is_paid = True
                related_user.expiry = latest_expiry
            await session.commit()
            remaining = max((latest_expiry - today).days, 1)
            await save_payment(username, "truth", ttl_seconds=remaining * 24 * 60 * 60)
    return wa_user_id


async def refresh_whatsapp_subscription(phone: str, username: str) -> bool:
    # Match Telegram's permanent exemption for this portal username.
    if str(username).strip().casefold() == "kudos.ajao":
        return True
    profile = await get_userinfo(f"{WA_USER_PREFIX}{phone}")
    if profile:
        await ensure_whatsapp_database_user(phone, profile)
    wa_user_id = f"{WA_USER_PREFIX}{phone}"
    async with get_session_ctx() as session:
        user = await payment_service.get_user_by_telegram_id(wa_user_id, session)
        if user is not None and user.user_id == username:
            await payment_service.payment_expired(
                user_id=username, telegram_id=wa_user_id, session=session
            )
    return await get_payment(user_id=username)


async def launch_scraper(phone: str, action: str):
    key = f"{WA_USER_PREFIX}{phone}"
    data = await get_userinfo(key)
    if not data:
        await send_text(phone, "Please connect your portal account first. Choose MENU → Connect portal account.")
        return
    username = data.get("username")
    if not username:
        await send_text(phone, "Your saved portal profile is incomplete. Please connect your account again.")
        return
    if action != "payment_receipts" and not await refresh_whatsapp_subscription(phone, username):
        await send_text(phone, "This service requires an active Acadex subscription. Send SUBSCRIBE to activate your subscription here on WhatsApp.")
        return
    existing = active_tasks.get(phone)
    if existing is not None and not existing.done():
        await send_text(phone, "You already have an Acadex task running. Send STOP to cancel it.")
        return
    message = WhatsAppMessage(phone)

    async def run_scrape():
        # Concurrency limits, queueing and per-job file isolation live in scraper_file.main.
        await safe_send_text(phone, "⏳ Acadex is starting your request. This may take a few minutes.")
        await scraper_main(
            university=data.get("university", ""),
            username=data.get("username", ""),
            password=data.get("password", ""),
            download_info=action,
            message=message,
            bot=bot_adapter,
        )

    # No await between the check above and this registration, so two quick messages
    # cannot both start a scrape for the same user.
    task = asyncio.create_task(run_scrape())
    active_tasks[phone] = task

    async def cleanup():
        try:
            await task
        except asyncio.CancelledError:
            await safe_send_text(phone, "Your Acadex operation was stopped.")
        except Exception:
            log.exception("WhatsApp scraper task failed for %s", phone)
            await safe_send_text(phone, "Acadex encountered an error while processing your request. Please try again later.")
        finally:
            if active_tasks.get(phone) is task:
                active_tasks.pop(phone, None)

    cleanup_task = asyncio.create_task(cleanup())
    background_tasks.add(cleanup_task)
    cleanup_task.add_done_callback(background_tasks.discard)

# Adapt the existing scraper's ask_for_wait interaction to WhatsApp replies.
# This keeps scraper_file.py unchanged and returns the same callback_data values
# that its existing fee-block workflow expects.
async def whatsapp_ask_for_wait(message: WhatsAppMessage, text: str, callback_buttons: Any, timeout: int = 30000):
    phone = message.chat.id
    buttons = []
    keyboard = getattr(callback_buttons, "inline_keyboard", []) or []
    for row in keyboard:
        for button in row:
            buttons.append({"text": button.text, "id": button.callback_data or button.text})
    future = asyncio.get_running_loop().create_future()
    waiters[phone] = {"future": future, "buttons": buttons, "rrr_input": False}
    if buttons:
        await send_list(phone, text, [
            {"title": button["text"], "rowId": button["id"]}
            for button in buttons
        ], title="Acadex - confirm your choice")
    else:
        await send_text(phone, text)
    try:
        # `timeout` is in seconds (as in utils.ask_for_wait); the scraper passes 30000.
        wait_seconds = min(max(float(timeout), 1.0), float(PROMPT_TIMEOUT_CAP))
        return await asyncio.wait_for(future, timeout=wait_seconds)
    except asyncio.TimeoutError:
        await safe_send_text(phone, "You took too long to respond. The operation timed out.")
        return None
    finally:
        waiters.pop(phone, None)

# Patch only this bridge process's imported scraper module. The Telegram bot runs
# in its own process and retains its original utils.ask_for_wait implementation.
scraper_file.ask_for_wait = whatsapp_ask_for_wait

async def handle_waiter(phone: str, text: str) -> bool:
    waiter = waiters.get(phone)
    if not waiter:
        return False
    future = waiter["future"]
    if future.done():
        waiters.pop(phone, None)
        return False
    if waiter.get("rrr_input"):
        future.set_result(text.strip())
        return True
    buttons = waiter.get("buttons", [])
    selected = None
    if text.isdigit() and 1 <= int(text) <= len(buttons):
        selected = buttons[int(text) - 1]
    else:
        normalized = text.casefold()
        selected = next((b for b in buttons if normalized in {b["text"].casefold(), b["id"].casefold()}), None)
    if not selected:
        await send_text(phone, "Please choose one of the listed options.")
        return True
    callback = selected["id"]
    if callback.startswith("rrr-confirmed:"):
        if callback.endswith("true"):
            waiter["rrr_input"] = True
            await send_text(phone, "Please enter your RRR code.")
        else:
            future.set_result("No")
    elif callback.startswith("confirm:"):
        future.set_result("Confirm" if callback.endswith("true") else "No")
    elif callback.startswith("money_sent:"):
        future.set_result("True" if callback.endswith("true") else "False")
    elif callback.startswith("fee:"):
        # Telegram's fee callback handler strips the "fee:" prefix and
        # returns exactly "<fee name>:<price>" to scraper_file.pay_fee_block.
        # Match that contract here; returning the full callback makes the
        # scraper look up a fee literally named "fee".
        _, _, fee_selection = callback.partition(":")
        if not fee_selection or ":" not in fee_selection:
            await send_text(phone, "That fee selection is invalid. Please choose a fee again.")
            return True
        future.set_result(fee_selection)
    else:
        future.set_result(callback)
    return True

async def update_marketer_withdrawn_amount(marketer_username: str, amount: float) -> bool:
    """Persist the withdrawal total using the existing marketer table/columns."""
    async with get_session_ctx() as session:
        result = await session.execute(
            select(Marketer).where(Marketer.username == marketer_username)
        )
        current_marketer = result.scalars().first()
        if current_marketer is None:
            return False
        current_marketer.amount_paid = amount
        await session.commit()
        return True


async def show_marketer_dashboard(phone: str, marketer: Marketer):
    if marketer.barred:
        await state_clear(phone)
        await send_text(phone, "This marketer account is restricted. Please contact Acadex support.")
        return
    referred = await payment_service.get_users_referred_by_marketer(marketer_username=marketer.username)
    all_users = referred.get("all_users", 0)
    paid_users = referred.get("paid_users", 0)
    gain_made = (1000 * paid_users * 0.2) - (marketer.amount_paid or 0)
    await state_set(phone, {"authenticated_marketer": marketer.username})
    await send_text(
        phone,
        "*Acadex Marketer Dashboard*\n\n"
        f"Username: {marketer.username}\n"
        f"University: {marketer.university}\n\n"
        f"Normal users referred: {all_users}\n"
        f"Paid users referred: {paid_users}\n"
        f"Gain made: ₦{gain_made:,.2f}\n"
        f"Amount withdrawn: ₦{(marketer.amount_paid or 0):,}\n\n"
        "Send WITHDRAW to request a payout.\n"
        "Send REFRESH to update your figures or MENU to return."
    )


async def process_incoming(phone: str, text: str):
    clean = text.strip()
    lower = clean.casefold()
    if lower == "stop":
        task = active_tasks.get(phone)
        if task and not task.done():
            task.cancel()
            await send_text(phone, "Stopping your current operation…")
        else:
            await send_text(phone, "There is no active operation to stop.")
        await state_clear(phone)
        return
    if await handle_waiter(phone, clean):
        return
    if lower in {"menu", "start", "hi", "hello", "hey"}:
        await state_clear(phone)
        await show_menu(phone, "👋 Welcome to Acadex!")
        return
    if lower in {"subscribe", "subscription", "activate subscription", "pay"}:
        profile = await get_userinfo(f"{WA_USER_PREFIX}{phone}")
        if not profile or not profile.get("username"):
            await send_text(phone, "Connect your portal account first using MENU → Connect portal account.")
            return
        if await refresh_whatsapp_subscription(phone, profile["username"]):
            await send_text(phone, "Your Acadex subscription is already active. You can use the paid services now.")
            return
        await state_set(phone, {"step": "subscription_plan"})
        await send_list(phone, "Choose your Acadex subscription plan.", [
            {"title": "Per Semester — ₦500", "rowId": "semester", "description": "Unlock paid services for a semester"},
            {"title": "Per Session — ₦1,000", "rowId": "session", "description": "Unlock paid services for a session"},
        ], title="Choose subscription")
        return
    if lower == "help":
        await show_menu(phone, "Acadex supports the services listed below. Follow the prompts; you do not need to memorise commands.")
        return
    if lower in {"back", "cancel"}:
        await state_clear(phone)
        await show_menu(phone, "Okay, returning to the main menu.")
        return
    state = await state_get(phone)
    step = state.get("step")
    if step == "subscription_plan":
        first_word = (lower.replace("per ", "").split() or [""])[0]
        plan = {"1": "semester", "2": "session"}.get(first_word, first_word)
        if plan not in {"semester", "session"}:
            await send_text(phone, "Please choose Semester or Session from the options.")
            return
        profile = await get_userinfo(f"{WA_USER_PREFIX}{phone}")
        if not profile or not profile.get("username"):
            await state_clear(phone)
            await send_text(phone, "Your portal profile is missing. Please connect it again from MENU.")
            return
        wa_user_id = f"{WA_USER_PREFIX}{phone}"
        metadata = {
            "telegram_id": wa_user_id,
            "whatsapp_id": phone,
            "channel": "whatsapp",
            "user_id": profile["username"],
            "level": int(profile.get("level") or 0),
            "type": plan,
        }
        payment_link = await payment_service.generate_subscription_link(metadata)
        await state_clear(phone)
        await send_text(phone, f"Your {plan} subscription costs ₦{payment_link['amount']:,}. Complete payment securely using this Paystack link:\n{payment_link['payment_link']}\n\nYour subscription will activate after Paystack confirms payment.")
        return
    if step == "marketer_choice":
        choice = lower.strip()
        if choice in {"1", "signup", "sign up", "register"}:
            await state_set(phone, {"step": "marketer_signup_username"})
            await send_text(phone, "Choose a username for your marketer account.")
            return
        if choice in {"2", "login", "log in", "sign in"}:
            await state_set(phone, {"step": "marketer_login_username"})
            await send_text(phone, "Enter your existing marketer username.")
            return
        await send_text(phone, "Reply 1 to sign up or 2 to log in.")
        return

    if step == "marketer_signup_username":
        if len(clean) < 3 or len(clean) > 40:
            await send_text(phone, "Choose a username between 3 and 40 characters.")
            return
        if await payment_service.get_marketer_by_username(clean):
            await send_text(phone, "That marketer username is already taken. Please choose another.")
            return
        state.update({"marketer_username": clean, "step": "marketer_signup_university"})
        await state_set(phone, state)
        await send_list(phone, "Choose your university.", [
            {"title": "Federal University Otuoke", "rowId": "FUO"},
            {"title": "Rivers State University", "rowId": "RSU"},
        ], title="Marketer university")
        return

    if step == "marketer_signup_university":
        choice = lower.replace(" ", "")
        university = "FUO" if choice in {"1", "fuo", "fuotuoke", "federaluniversityotuoke"} else "RSU" if choice in {"2", "rsu", "riversstateuniversity"} else None
        if not university:
            await send_text(phone, "Choose FUO (1) or RSU (2).")
            return
        marketers = await payment_service.get_all_marketers_by_university(university=university)
        if len(marketers) >= 30:
            await send_text(phone, "Sorry, the marketer capacity for this university is full.")
            return
        state.update({"marketer_university": university, "step": "marketer_signup_password"})
        await state_set(phone, state)
        await send_text(phone, "Create your marketer account password.")
        return

    if step == "marketer_signup_password":
        if len(clean) < 6:
            await send_text(phone, "Use a password with at least 6 characters.")
            return
        username = state.get("marketer_username")
        university = state.get("marketer_university")
        if not username or not university:
            await state_clear(phone)
            await send_text(phone, "Your signup session expired. Please start again from MENU.")
            return
        existing_phone_account = await payment_service.get_marketer_by_telegram_id(telegram_id=f"{WA_USER_PREFIX}{phone}")
        if existing_phone_account:
            await state_clear(phone)
            await send_text(phone, "A marketer account is already linked to this WhatsApp number. Choose Log in instead.")
            return
        try:
            marketer = await payment_service.create_marketer(MarketerModel(
                telegram_id=f"{WA_USER_PREFIX}{phone}", username=username,
                university=university, password=clean,
            ))
        except Exception:
            log.exception("WhatsApp marketer signup failed for %s", phone)
            await send_text(phone, "I couldn't create that account. The username may already be taken; please try another.")
            return
        await show_marketer_dashboard(phone, marketer)
        return

    if step == "marketer_login_username":
        state.update({"marketer_login_username": clean, "step": "marketer_login_password"})
        await state_set(phone, state)
        await send_text(phone, "Enter your marketer account password.")
        return

    if step == "marketer_login_password":
        username = state.get("marketer_login_username")
        marketer = await payment_service.get_marketer_by_username(username=username) if username else None
        if marketer is None or not await payment_service.is_marketer_password(marketer=marketer, password=clean):
            await state_clear(phone)
            await send_text(phone, "Username or password is incorrect. Send MENU → Marketer account to try again.")
            return
        await show_marketer_dashboard(phone, marketer)
        return

    if step == "university":
        choice = lower.replace(" ", "")
        if choice in {"1", "fuo", "fuotuoke", "federaluniversityotuoke"}:
            state["university"] = "FUO"
        elif choice in {"2", "rsu", "riversstateuniversity"}:
            state["university"] = "RSU"
        else:
            await send_text(phone, "Choose 1 for Federal University Otuoke (FUO) or 2 for Rivers State University (RSU).")
            return
        state["step"] = "username"
        await state_set(phone, state)
        await send_text(phone, "Enter your university portal username.")
        return
    if step == "username":
        state["username"] = clean
        state["step"] = "password"
        await state_set(phone, state)
        await send_text(phone, "Enter your university portal password.")
        return
    if step == "password":
        state["password"] = clean
        wa_user_id = f"{WA_USER_PREFIX}{phone}"
        async with get_session_ctx() as session:
            user = await payment_service.get_user_by_telegram_id(telegram_id=wa_user_id,session=session)
        if user is not None:
            # Existing WhatsApp identity: refresh credentials only. Keep the
            # stored level/referrer and the university explicitly selected now.
            await save_userinfo(
                telegram_username=wa_user_id,
                username=state["username"],
                password=state["password"],
                level=str(user.level),
                university=state["university"],
                referrer=user.referrer or "none",
            )
            async with get_session_ctx() as update_session:
                current_user = await payment_service.get_user_by_telegram_id(
                    telegram_id=wa_user_id, session=update_session
                )
                if current_user is not None:
                    current_user.user_id = state["username"]
                    await update_session.commit()
            await state_clear(phone)
            await send_text(phone, "✅ Your portal login details have been updated. Your existing level, referrer and subscription status were preserved.")
            await show_menu(phone)
            return
        state["step"] = "referrer"
        await state_set(phone, state)
        await send_text(phone, "Enter your Acadex referrer name, or type none if you do not have one.")
        return
    if step == "referrer":
        state["referrer"] = clean if lower != "none" else "none"
        state["step"] = "level"
        await state_set(phone, state)
        await send_text(phone, "Enter your current level using numbers only (for example, 100).")
        return
    if step == "level":
        if not clean.isdigit():
            await send_text(phone, "Please enter your current level as a number, for example 100.")
            return
        if any(key not in state for key in ("university", "username", "password", "referrer")):
            # Flow state expired or was cleared part-way through; restart cleanly.
            await state_clear(phone)
            await send_text(phone, "Your setup session expired. Let's start again.")
            await show_menu(phone)
            return
        # Use the existing Redis helper and same field names. The Telegram keys
        # and saved credential records are not modified.
        wa_user_id = f"{WA_USER_PREFIX}{phone}"
        referrer_value = state["referrer"] if state["referrer"] != "none" else None
        # A non-existent marketer username must not violate the users.referrer FK.
        if referrer_value:
            async with get_session_ctx() as ref_session:
                marketer_result = await ref_session.execute(
                    select(Marketer).where(Marketer.username == referrer_value)
                )
                if marketer_result.scalars().first() is None:
                    referrer_value = None
        await save_userinfo(
            telegram_username=wa_user_id,
            username=state["username"],
            password=state["password"],
            level=clean,
            university=state["university"],
            referrer=referrer_value or "none",
        )
        # Ensure the existing users table contains this WhatsApp identity.
        await ensure_whatsapp_database_user(phone, {
            "username": state["username"],
            "level": clean,
            "referrer": referrer_value,
        })
        await state_clear(phone)
        await send_text(phone, "✅ Your portal details have been saved in Acadex. Your WhatsApp profile is registered and ready. Send SUBSCRIBE to activate paid services, or choose a service from MENU.")
        await show_menu(phone)
        return

    if lower in {"9", "marketer", "marketer account", "marketer login", "marketer signup"}:
        await state_set(phone, {"step": "marketer_choice"})
        await send_list(phone, "Choose what you want to do.", [
            {"title": "Sign up", "rowId": "1"},
            {"title": "Log in", "rowId": "2"},
        ], title="Marketer account")
        return

    if lower == "refresh":
        marketer_state = await state_get(phone)
        marketer_username = marketer_state.get("authenticated_marketer")
        if marketer_username:
            marketer = await payment_service.get_marketer_by_username(username=marketer_username)
            if marketer:
                await show_marketer_dashboard(phone, marketer)
                return

    marketer_state = await state_get(phone)
    marketer_username = marketer_state.get("authenticated_marketer")
    if lower in {"withdraw", "withdraw money", "request withdrawal"} and marketer_username:
        marketer = await payment_service.get_marketer_by_username(username=marketer_username)
        if not marketer:
            await state_clear(phone)
            await send_text(phone, "I couldn't find your marketer account. Please log in again.")
            return
        referred = await payment_service.get_users_referred_by_marketer(marketer_username=marketer.username)
        paid_users = referred.get("paid_users", 0)
        available = (1000 * paid_users * 0.2) - (marketer.amount_paid or 0)
        if available < 1000:
            await send_text(phone, "You need at least ₦1,000 in available earnings (normally 5 or more paid referrals) before requesting a withdrawal.")
            return
        await state_set(phone, {
            "authenticated_marketer": marketer.username,
            "withdraw_amount": round(available, 2),
            "withdraw_step": "account_number",
        })
        await send_text(phone, f"You can request ₦{available:,.2f}. Enter your bank account number. Send CANCEL to stop.")
        return

    if marketer_state.get("withdraw_step"):
        withdraw_step = marketer_state["withdraw_step"]
        if lower in {"cancel", "stop", "back"}:
            await state_set(phone, {"authenticated_marketer": marketer_state.get("authenticated_marketer")})
            await send_text(phone, "Withdrawal request cancelled. Send WITHDRAW whenever you're ready.")
            return
        if withdraw_step == "account_number":
            account_number = "".join(ch for ch in clean if ch.isdigit())
            if len(account_number) < 10 or len(account_number) > 12:
                await send_text(phone, "Enter a valid bank account number (10 digits).")
                return
            marketer_state.update({"account_number": account_number, "withdraw_step": "bank"})
            await state_set(phone, marketer_state)
            await send_text(phone, "Enter the name of your bank.")
            return
        if withdraw_step == "bank":
            if len(clean) < 2 or len(clean) > 80:
                await send_text(phone, "Please enter a valid bank name.")
                return
            marketer_state.update({"bank": clean, "withdraw_step": "account_name"})
            await state_set(phone, marketer_state)
            await send_text(phone, "Enter the account holder's full name.")
            return
        if withdraw_step == "account_name":
            if len(clean) < 3 or len(clean) > 100:
                await send_text(phone, "Please enter the full account name.")
                return
            marketer_state.update({"account_name": clean, "withdraw_step": "confirm"})
            await state_set(phone, marketer_state)
            await send_text(
                phone,
                "Please confirm your withdrawal details:\n\n"
                f"Amount: ₦{marketer_state['withdraw_amount']:,.2f}\n"
                f"Account number: {marketer_state['account_number']}\n"
                f"Bank: {marketer_state['bank']}\n"
                f"Account name: {marketer_state['account_name']}\n\n"
                "Reply CONFIRM to submit or CANCEL to stop."
            )
            return
        if withdraw_step == "confirm":
            if lower not in {"confirm", "yes", "1"}:
                await send_text(phone, "Reply CONFIRM to submit the request or CANCEL to stop.")
                return
            marketer = await payment_service.get_marketer_by_username(
                username=marketer_state.get("authenticated_marketer")
            )
            if not marketer or marketer.barred:
                await state_clear(phone)
                await send_text(phone, "Your marketer account could not be verified. Please contact Acadex support.")
                return
            amount = float(marketer_state["withdraw_amount"])
            # Recalculate immediately before submission so stale dashboard figures
            # cannot be used to request more than the current available earnings.
            referred = await payment_service.get_users_referred_by_marketer(marketer_username=marketer.username)
            current_available = (1000 * referred.get("paid_users", 0) * 0.2) - (marketer.amount_paid or 0)
            if current_available < 1000 or amount > current_available:
                await show_marketer_dashboard(phone, marketer)
                await send_text(phone, "Your available balance changed. Please review the updated dashboard before requesting another withdrawal.")
                return
            admin_phone = "2347025614656"
            admin_message = (
                "💸 AC ADEX MARKETER WITHDRAWAL REQUEST\n\n"
                f"Marketer username: {marketer.username}\n"
                f"University: {marketer.university}\n"
                f"Telegram ID / marketer database ID: {marketer.telegram_id}\n"
                f"WhatsApp number: {phone}\n"
                f"Amount requested: ₦{amount:,.2f}\n\n"
                f"Account number: {marketer_state['account_number']}\n"
                f"Bank: {marketer_state['bank']}\n"
                f"Account name: {marketer_state['account_name']}"
            )
            try:
                await send_text(admin_phone, admin_message)
            except Exception:
                log.exception("Could not send WhatsApp withdrawal notification for marketer %s", marketer.username)
                await send_text(phone, "I couldn't deliver your withdrawal request to Acadex right now. Your balance has not been updated. Please try again later.")
                return
            updated = await update_marketer_withdrawn_amount(
                marketer_username=marketer.username,
                amount=amount,
            )
            if not updated:
                log.error("Admin received withdrawal request but marketer amount_paid update failed: %s", marketer.username)
                await send_text(phone, "Your request was sent to Acadex, but your dashboard balance could not be updated automatically. Please contact support and quote your username: " + marketer.username)
                await state_set(phone, {"authenticated_marketer": marketer.username})
                return
            await state_set(phone, {"authenticated_marketer": marketer.username})
            await send_text(phone, "✅ Your withdrawal request has been sent to Acadex. Your bank details and account ID have been delivered to the admin WhatsApp number. Please allow up to 24 hours for processing.")
            await show_marketer_dashboard(phone, await payment_service.get_marketer_by_username(username=marketer.username))
            return

    if lower in {"1", "login", "connect account", "connect portal account"}:
        await state_set(phone, {"step": "university"})
        await send_list(phone, "Which university do you attend?", [
            {"title": "Federal University Otuoke", "rowId": "FUO", "description": "FUO"},
            {"title": "Rivers State University", "rowId": "RSU", "description": "RSU"},
        ], title="Choose your university")
        return

    service = SERVICE_MAP.get(lower)
    if service:
        _label, action, _free = service
        await launch_scraper(phone, action)
        return

    await show_menu(phone, "I couldn't match that to an Acadex option.")

@router.get("/whatsapp/health")
async def health():
    return {"status": "ok", "service": "acadex-whatsapp-bridge"}

@router.post("/whatsapp/incoming")
async def incoming(payload: Incoming, authorization: str | None = Header(default=None)):
    if not BRIDGE_TOKEN or not hmac.compare_digest(
        (authorization or "").encode(), f"Bearer {BRIDGE_TOKEN}".encode()
    ):
        raise HTTPException(status_code=401, detail="Unauthorized")
    phone = "".join(ch for ch in payload.phone if ch.isdigit())
    if not phone:
        raise HTTPException(status_code=400, detail="Invalid sender")
    seen_key = f"wa:seen:{phone}:{payload.message_id}" if payload.message_id else None
    if seen_key:
        # WhatsApp can redeliver after a reconnect; never run the same message twice.
        if not await red.set(seen_key, "1", nx=True, ex=60 * 60 * 24):
            return {"ok": True, "duplicate": True}
    try:
        await process_incoming(phone, payload.text)
    except Exception:
        if seen_key:
            await red.delete(seen_key)
        log.exception("Could not process WhatsApp message from %s", phone)
        try:
            await send_text(phone, "Acadex encountered an unexpected error. Please send MENU and try again.")
        except Exception:
            pass
        raise HTTPException(status_code=500, detail="Message processing failed")
    return {"ok": True}
