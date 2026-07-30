from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardButton


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
