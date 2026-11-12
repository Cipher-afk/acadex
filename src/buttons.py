from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardButton
from typing import List


def get_service_buttons():
    builder = InlineKeyboardBuilder()
    builder.button(text="Download Receipts 🧾", callback_data="download_receipts")
    builder.button(text="Download Results 📄", callback_data="download_results")
    builder.button(text="Get Result Summary 🧾", callback_data="result_summary")
    builder.button(text="Download Courses 📄", callback_data="download_courses")
    builder.button(text="Download_Biodata 🧾", callback_data="download_biodata")
    builder.button(text="Download Admission Forms 📄", callback_data="admission_forms")
    builder.adjust(2)
    return builder.as_markup()


def create_button(text: str, callback_data: str):
    builder = InlineKeyboardBuilder()
    builder.button(text=text, callback_data=callback_data)
    return builder.as_markup()


def get_university_buttons(marketer: bool = False):
    builder = InlineKeyboardBuilder()
    builder.button(
        text="Federal University Of Otueke",
        callback_data="university:FUO" if not marketer else "marketer_university:FUO",
    )
    builder.button(
        text="Rivers State University Of Science and Technology",
        callback_data="university:RSU" if not marketer else "marketer_university:RSU",
    )
    builder.adjust(2)
    return builder.as_markup()


def get_access_buttons():
    builder = InlineKeyboardBuilder()
    builder.button(text="Signup", callback_data="signup:marketer")
    builder.button(text="Login", callback_data="marketer_login")
    builder.adjust(2)
    return builder.as_markup()


def get_withdraw_refresh_buttons(gain_made: int):
    builder = InlineKeyboardBuilder()
    builder.button(text="Withdraw", callback_data=f"withdraw:{gain_made}")
    builder.button(text="Refresh", callback_data="refresh_users")
    builder.adjust(2)
    return builder.as_markup()


def confirm_retry_buttons(gain_made: int):
    builder = InlineKeyboardBuilder()
    builder.button(text="Confirm Pay", callback_data=f"confirm")
    builder.button(text="Edit Details", callback_data=f"withdraw:{gain_made}")
    builder.adjust(2)
    return builder.as_markup()
