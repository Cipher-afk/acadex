from playwright.async_api import (
    async_playwright,
    BrowserContext,
    Locator,
    TimeoutError,
    Page,
    Error as PlaywrightError,
)
import asyncio
import builtins
import contextvars
import shutil
import time
import uuid
from contextlib import asynccontextmanager
from redis_config import get_url, store_url
from pathlib import Path
from PIL import Image
from aiogram.types import Message, FSInputFile, CallbackQuery
from aiogram import Bot
import os
from tasks import scraping_tasks
from buttons import build_payment_buttons, ButtonInfoDict
from typing import List
from utils import ask_for_wait
from datetime import datetime, timedelta

_APP_DIR = Path(__file__).resolve().parent

# Every scrape gets its own private folder for screenshots/PDFs/downloads so two users
# running at the same time can never overwrite, delete or receive each other's files.
# BASE_DIR stays a drop-in replacement: `Path(BASE_DIR, "biodata.pdf")` is unchanged at
# every call site, it just resolves to the running job's folder.
_job_dir_var: contextvars.ContextVar = contextvars.ContextVar(
    "acadex_job_dir", default=None
)


class _JobDir(os.PathLike):
    def __fspath__(self) -> str:
        return str(_job_dir_var.get() or _APP_DIR)

    def __str__(self) -> str:
        return self.__fspath__()

    def __truediv__(self, other):
        return Path(self.__fspath__()) / other


BASE_DIR = _JobDir()

UNIVERSITIES_PERMITTED = {
    "FUO": "https://ecampus.fuotuoke.edu.ng/ecampus/login.html",
    "RSU": "https://ecampus.rsu.edu.ng/ecampus/login.html",
}


async def is_fee_blocked(page: Page, bot: Bot, message: Message):
    if await page.locator(".row.g-5.myfeelist").is_visible():
        await page.screenshot(path=Path(BASE_DIR, "payment-screenshot.png"))
        await bot.send_photo(
            chat_id=message.chat.id,
            photo=FSInputFile(Path(BASE_DIR, "payment-screenshot.png")),
            caption="Your portal is blocked due to unpaid fees 😣😥",
        )
        return True
    return False


async def get_menu(
    session_url: str, page: Page, bot: Bot, context: BrowserContext, message: Message
):
    while True:
        try:
            # page = await context.new_page()
            # await message.answer('Getting Menu...')
            # await page.goto(session_url, timeout=8000000,wait_until='domcontentloaded')
            await message.answer("Menu page loaded")
            # try:
            #     await page.wait_for_selector(".row.g-5.myfeelist",state='visible',timeout=120000)
            # except TimeoutError:
            #     await page.wait_for_selector("span.matric_no", timeout=120000,state='visible')
            #     mat_num = await page.locator("span.matric_no").inner_text()
            #     await message.answer(f"👨‍🎓 Found Matric Number: {mat_num}")
            # await message.answer('Looking for your profile details...')
            # await page.wait_for_selector(
            #     ".user_text", timeout=7000,state='visible'
            # )
            if await page.locator("#kt_aside_mobile_toggle").is_visible():
                await page.click("#kt_aside_mobile_toggle")
                print("Toggle clicked")
            await message.answer("Getting Menu....")
            menu = page.locator("div.menu-item.menu-accordion")
            # await message.answer("🤖 Side Menu Clicked")
            return menu, page
        except TimeoutError as e:
            await page.screenshot(path=Path(BASE_DIR, "error1-screenshot.png"))
            await bot.send_photo(
                chat_id=message.chat.id,
                photo=FSInputFile(Path(BASE_DIR, "error1-screenshot.png")),
                caption=e,
            )
            await message.answer("❌ Network Timeout Retrying...")
            await page.close()
            continue


async def download_payment_receipts(
    session_url: str, context: BrowserContext, message: Message, bot: Bot, page: Page
):
    menu, page = await get_menu(
        session_url=session_url, page=page, bot=bot, context=context, message=message
    )
    # fee_blocked = await is_fee_blocked(page=page, bot=bot, message=message)
    # if fee_blocked:
    #     return
    await menu.get_by_text("Payments", exact=True).click(timeout=800000)
    await message.answer("🔍 Looking for your receipts....")
    await menu.get_by_text("Payment Receipts", exact=True).click(timeout=800000)
    # await message.answer("Payment Receipts Clicked")
    await page.wait_for_selector("div.d-flex.py-3.rounded-1.row.mx-0")
    receipts = page.locator("div.d-flex.py-3.rounded-1.row.mx-0")
    # documents = []
    await message.answer(
        "Downloading......\nThis will take a couple of minutes based on your network speed\nSend 'Stop' at any moment to cancel the download"
    )
    for i in range(await receipts.count() - 1):
        try:
            document_name = (
                await page.locator("a.text-secondary.fw-bolder.me-2")
                .nth(i)
                .inner_text()
            )
        except Exception as e:
            await message.answer(
                "Download Completed\nIf your documents are not complete try downloading again"
            )
        try:
            await receipts.nth(i).click()
            await page.wait_for_selector(".watermark", timeout=100000)
        except Exception as e:
            pass
        async with page.expect_download() as download_info:
            await page.click("#download_btn")
        # await asyncio.sleep(2)
        download = await download_info.value
        await download.path()
        # print(download.suggested_filename)
        # print("Downloaded")
        filename = Path(BASE_DIR, f"{document_name}{download.suggested_filename}")
        pdf_filename = str(filename).replace(".png", ".pdf")
        await download.save_as(filename)
        img = Image.open(filename)
        img.convert("RGB").save(pdf_filename, format="PDF")
        print("Saved as pdf")
        await bot.send_document(
            chat_id=message.chat.id,
            document=FSInputFile(pdf_filename),
            caption=f"{document_name} downloaded",
        )
        os.remove(filename)
        # documents.append(pdf_filename)
        # print("Added")
        await page.click('div[aria-label="Close"]')
    await page.close()
    # print(documents)
    # return documents


async def download_results(
    context: BrowserContext, page: Page, session_url: str, message: Message, bot: Bot
):
    menu, page = await get_menu(
        session_url=session_url, page=page, bot=bot, context=context, message=message
    )
    # fee_blocked = await is_fee_blocked(page=page, bot=bot, message=message)
    # if fee_blocked:
    #     return
    await message.answer("📊 Fetching Results....")
    while True:
        try:
            await menu.get_by_text("Courses", exact=True).click(timeout=60000)
            print("Courses clicked")
            await menu.get_by_text("View Results", exact=True).click(timeout=60000)
            await message.answer("View Results clicked")
            await page.wait_for_selector(".selection", timeout=60000)
            await message.answer(f"🔍 Results Found")
            await page.screenshot(path=Path(BASE_DIR, "result-screenshot.png"))
            # await bot.send_photo(
            #     chat_id=message.chat.id,
            #     photo=FSInputFile(Path(BASE_DIR, "result-screenshot.png"))
            # )
            await page.click(".selection")
            await page.screenshot(path=Path(BASE_DIR, "result-screenshot.png"))
            await bot.send_photo(
                chat_id=message.chat.id,
                photo=FSInputFile(Path(BASE_DIR, "result-screenshot.png")),
                caption="Result page",
            )
            await page.wait_for_selector("li[role='option']", timeout=60000)
            options = page.locator("li[role='option']")
            if await options.count() <= 1:
                await message.answer(
                    "Page not loaded properly due to website issues 💀 Retrying now..."
                )
                continue
            else:
                break
        except TimeoutError:
            await message.answer("❌ Network Timeout Retrying...")
            continue

    # options_text = await options.all_inner_texts()
    # unique_options = list(dict.fromkeys(option.strip() for option in options_text if option != 'Select Session'))
    options_clicked = list(set([]))
    pdf_page = await context.new_page()
    await pdf_page.goto(session_url, wait_until="domcontentloaded")
    for i in range(1, await options.count()):
        print(options_clicked)
        session = await options.nth(i).inner_text(timeout=60000)
        await message.answer(
            f" 🔎 Found your result for {session} session about to download"
        )
        if session not in options_clicked:
            await options.nth(i).click()
            while True:
                try:
                    await page.wait_for_selector(".highest_gpa", timeout=60000)
                    highest_gpa = await page.locator(".highest_gpa").text_content(
                        timeout=800000
                    )
                    if len(highest_gpa) > 1:
                        pass
                    else:
                        await message.answer(
                            "Page not loaded properly due to website issues 💀 Retrying now..."
                        )
                        await options.nth(i).click()
                        continue
                    print("Found highest gpa")
                    await message.answer(f"Your Highest GPA is {highest_gpa}")
                    semesters = page.locator("li.nav-item")
                    semester_count = await semesters.count()
                    print(semester_count)
                    break
                except TimeoutError:
                    await message.answer(
                        "Page not loaded properly due to website issues 💀 Retrying now..."
                    )
                    continue
            for j in range(1, semester_count):
                if j <= 2:
                    current_semester = await semesters.nth(j).inner_text()
                    if j == 2:
                        await page.locator(
                            ".nav-link.link2"
                        ).click()  # Means click on the second semester
                        current_semester = "2nd Semester"
                    await page.click("#btnprint")  # Click the download semester button
                    print("Clicked button")

                    await message.answer(
                        f"Downloading your {current_semester} result...\nThis will take a couple of minutes based on your network speed\nSend 'Stop' at any moment to cancel the download"
                    )
                    await page.wait_for_selector(".row.g-9", timeout=800000)
                    # session = await page.locator("p[field='session']").nth(1).inner_text()
                    session = session.replace("/", r"-")

                    print(session)
                    # session_result = await page.locator(".col-12.card.card-custom.p-8.mx-auto")
                    result_name = f"{session} {current_semester.replace(r"\n","").strip()} results.pdf"
                    filename = Path(BASE_DIR, result_name)
                    element_html = await page.evaluate(
                        "() => document.querySelector('#result_body').outerHTML;"  # Get the html of the pdf
                    )
                    # else:
                    #     element_html = await page.evaluate(
                    #         "() => document.querySelector('#view_second_sem').outerHTML;"
                    #     )
                    # pdf_page = await context.new_page()
                    await pdf_page.evaluate(
                        "(html) => {document.body.innerHTML = html}",
                        element_html,  # Include that in your main page
                    )
                    #             await pdf_page.set_content(
                    #                 f"""
                    #                 <html>
                    #                     <body>
                    #                     {html}
                    #                     </body>
                    #                 </html>
                    # """
                    #             )
                    await pdf_page.pdf(
                        path=filename,
                        format="A4",
                        print_background=True,
                    )
                    print("Got document")
                    await bot.send_document(
                        chat_id=message.chat.id,
                        document=FSInputFile(filename),
                        caption=result_name,
                    )
                    await message.answer(
                        f"✅ {session} {current_semester} results downloaded successsfully"
                    )
                    print("sent document")
                    os.remove(filename)
                    options_clicked.append(session)
                    await page.click("div[data-bs-dismiss='modal']", force=True)
                    await page.click(".selection")
                else:
                    break
        else:
            print(session)
            pass


async def get_result_summary(
    context: BrowserContext, session_url: str, message: Message, bot: Bot, page: Page
):
    menu, page = await get_menu(
        session_url=session_url, page=page, bot=bot, context=context, message=message
    )
    fee_blocked = await is_fee_blocked(page=page, bot=bot, message=message)
    if fee_blocked:
        return
    await message.answer("📊 Fetching Results....")
    try:
        await menu.get_by_text("Courses", exact=True).click(timeout=800000)
        print("Courses clicked")
        await menu.get_by_text("Result Summary", exact=True).click(timeout=800000)
        await page.wait_for_selector("#resultdiv", timeout=120000, state="visible")
        await message.answer("Results Page Loading.... 🔃")
        pdf_page = await context.new_page()
        await pdf_page.goto(session_url, wait_until="domcontentloaded")
        await message.answer(
            f"Downloading your Result summary...\nThis will take a couple of minutes based on your network speed\nSend 'Stop' at any moment to cancel the download"
        )
        element_html = await page.evaluate(
            "()=> document.querySelector('#resultdiv').outerHTML;"
        )
        filename = Path(BASE_DIR, "Result Summary.pdf")
        await pdf_page.evaluate(
            "(html)=>{document.body.innerHTML = html};", element_html
        )
        await pdf_page.pdf(path=filename, format="A4", print_background=True)
        await bot.send_document(
            chat_id=message.chat.id,
            document=FSInputFile(path=filename),
            caption="Your Result summary has been successfully downloaded Thank you for choosing acadex 😎🥰".title(),
        )
        os.remove(path=filename)
    except TimeoutError:
        await message.answer("Network Timeout Error Retry ❌")


async def download_courses(
    context: BrowserContext,
    session_url: str,
    message: Message,
    bot: Bot,
    page: Page,
    level: int = None,
):
    menu, page = await get_menu(
        session_url=session_url, page=page, bot=bot, context=context, message=message
    )
    fee_blocked = await is_fee_blocked(page=page, bot=bot, message=message)
    if fee_blocked:
        return
    await menu.get_by_text("Courses", exact=True).click()
    print("Courses clicked")
    await asyncio.sleep(3)
    await menu.get_by_text("View Registered Courses", exact=True).click()
    await message.answer("📚 Fetching your courses.....")
    print("clicked registered courses")
    if await page.locator("#nocoursefirst").is_visible():
        await message.answer("Register your courses")
    else:
        try:
            documents = []
            await page.wait_for_selector(".card-body.p-6", timeout=800000)
            await message.answer("🔍 Found Courses")
        except Exception as e:
            await message.answer("❌ Portal issues please try again")
            print(e)
        pdf_page = await context.new_page()
        try:
            await pdf_page.goto(page.url)
            await pdf_page.wait_for_load_state("networkidle", timeout=100000)
        except TimeoutError as e:
            await message.answer("Network Timeout Retry")
            print(e)
            return
        await page.locator("span.selection").nth(0).click()
        await message.answer("Sessions Clicked")
        await message.answer("Levels Loading....")
        options = page.locator(".select2-results li")
        print(options)
        count = await options.count()
        print(count)
        for i in range(1, count):
            level = await options.nth(i).inner_text()
            print(level)
            await options.nth(i).click()  # Click levels
            await message.answer(f"{level} session clicked")
            await message.answer("Courses page loading......")
            await page.click("#toggle_search")  # select printable version
            print("Clicked toggle search")
            semesters = await page.locator(
                "li.nav-item"
            ).all_inner_texts()  # get semesters
            unique_semesters = list(
                dict.fromkeys(t.strip() for t in semesters if t.strip() != "Alerts")
            )
            print(unique_semesters)
            semester_count = len(unique_semesters) - 1  # remove third semester
            print(semester_count)

            for j in range(semester_count):
                if j == 1:  # if second semester click on it
                    await page.get_by_role("link", name="2nd Semester").click()
                    print("clicked")
                    await asyncio.sleep(3)
                    await page.click("#toggle_search")
                    print("Toggle clicked")

                pdf_element = page.locator(".row.d-print-block")
                print("Found pdf element")
                original_body = await page.evaluate("document.body.innerHTML")
                semester = unique_semesters[j]
                semester = semester.strip()
                await message.answer(
                    f"{level} {semester} courses downloading......\nThis will take a couple of minutes based on your network speed\nSend 'Stop' at any moment to cancel the download"
                )
                course_name = f"{level}_{semester}_courses"
                filename = Path(BASE_DIR, f"{level}_{semester}_courses.pdf")
                if j != 1:
                    element_html = await page.evaluate(
                        "() => document.querySelector('.row.d-print-block').outerHTML;"
                    )
                else:
                    element_html = await page.evaluate(
                        "() => document.querySelector('#view_second_sem').outerHTML;"
                    )
                # pdf_page = await context.new_page()
                await pdf_page.evaluate(
                    "(html) => {document.body.innerHTML = html}", element_html
                )
                #             await pdf_page.set_content(
                #                 f"""
                #                 <html>
                #                     <body>
                #                     {html}
                #                     </body>
                #                 </html>
                # """
                #             )
                await pdf_page.pdf(
                    path=filename,
                    format="A4",
                    print_background=True,
                )
                print("Got document")
                await bot.send_document(
                    chat_id=message.chat.id,
                    document=FSInputFile(filename),
                    caption=course_name,
                )
                print("sent document")
                os.remove(filename)
                await page.locator("span.selection").nth(0).click()
                await options.nth(i).click()
                print("original body back")
                await pdf_page.evaluate("() => {document.body.innerHTML = ''}")
            await page.locator("span.selection").nth(0).click()
        await pdf_page.close()


async def download_biodata(
    context: BrowserContext,
    page: Page,
    session_url: str,
    message: Message,
    bot: Bot,
):
    menu, page = await get_menu(
        session_url=session_url, bot=bot, context=context, page=page, message=message
    )
    fee_blocked = await is_fee_blocked(page=page, bot=bot, message=message)
    if fee_blocked:
        return
    await message.answer("Fetching your biodata...")
    await menu.get_by_text("Details", exact=True).click()
    await menu.get_by_text("My details", exact=True).click()
    await message.answer("Biodata page loading...")
    pdf_page = await context.new_page()
    # await pdf_page.goto(page.url)
    await pdf_page.wait_for_load_state("domcontentloaded")
    await message.answer(
        "Biodata page loaded\nDownloading your biodata...\nThis will take a couple of minutes based on your network speed\nSend 'Stop' at any moment to cancel the download"
    )
    try:
        await page.wait_for_selector("#my_details", state="visible")
        print("selector found")
        await asyncio.sleep(10)
        element_html = await page.evaluate(
            """()=> document.querySelector("#my_details").outerHTML
          """
        )
        # print(element_html)

        if not element_html:
            await message.answer(
                "❌ Unable to find biodata on the page. Please try again later."
            )
            return
        filename = Path(BASE_DIR, "biodata.pdf")
        print(filename)
        # await pdf_page.evaluate(
        #     "(html) => {document.body.innerHTML = html}", element_html
        # )
        await pdf_page.set_content(element_html)

        print("PDF page content set")
        await asyncio.sleep(3)
        print("slept")
        await pdf_page.pdf(path=filename, format="A4", print_background=True)
        print("pdf page gotten")
        await bot.send_document(
            chat_id=message.chat.id, document=FSInputFile(filename), caption="Biodata"
        )
        os.remove(filename)
    except Exception as e:
        await message.answer(f"Error{e}")
        raise


async def download_admmission_forms(
    context: BrowserContext, session_url: str, message: Message, bot: Bot, page: Page
):
    menu, page = await get_menu(
        context=context, bot=bot, session_url=session_url, message=message, page=page
    )
    fee_blocked = await is_fee_blocked(page=page, bot=bot, message=message)
    if fee_blocked:
        return
    await menu.get_by_text("Details", exact=True).click()
    await menu.get_by_text("Registration Documents", exact=True).click()
    await message.answer("Registration Documents Pages Loading.....")
    await page.wait_for_selector(".text-secondary.fw-bolder.fs-5")
    document_names = page.locator(".text-secondary.fw-bolder.fs-5")
    # document_downloads = page.locator(
    #     "bi.bi-download.text-secondary.fw-bold.acceptance_form_download"
    # )

    await message.answer(
        "Registration Documents Page Loaded\nDownloading your documents...\nThis will take a couple of minutes based on your network speed\nSend 'Stop' at any moment to cancel the download"
    )
    try:
        for i in range(len(await document_names.all_inner_texts())):
            document_name = await document_names.nth(i).inner_text()
            print(document_name)
            download_btn = page.locator(
                f"i[data-tile='{document_name.strip().lower().replace(' ', '_')}']"
            )
            async with page.expect_download() as download_info:
                await download_btn.click()
            download = await download_info.value
            await download.path()
            file_name = Path(BASE_DIR, f"{download.suggested_filename}")
            await download.save_as(file_name)
            await bot.send_document(
                chat_id=message.chat.id,
                document=FSInputFile(file_name),
                caption=f"{document_name} downloaded successfully",
            )
            os.remove(file_name)
    except Exception as e:
        await message.answer(f"Error occured while getting documents try again")
        raise


# async def pay_fee_blocks(context: BrowserContext, session_url: str, message: Message, bot: Bot, page: Page):
#     pass


async def pay_with_remita(remita_page: Page, rrr_code: str, bot: Bot, message: Message):
    telegram_id = message.chat.id
    await message.answer("Accepting cookies to use the remita website")
    cookies_accept_button = remita_page.locator("button.site-agreement-button").first
    await cookies_accept_button.click()

    await message.answer("filling in remita code")
    # await remita_page.wait_for_selector('input#mat-input-0',60000)
    # await remita_page.fill("input#mat-input-0", rrr_code)
    await remita_page.get_by_placeholder("Enter RRR").fill(rrr_code)
    await message.answer("Filled in matric number")
    await remita_page.screenshot(path=Path(BASE_DIR, "remita-screenshot.png"))
    await bot.send_photo(
        chat_id=telegram_id, photo=FSInputFile(Path(BASE_DIR, "remita-screenshot.png"))
    )
    await asyncio.sleep(2)
    await remita_page.get_by_role("button", name="Proceed").click()
    await remita_page.wait_for_selector("div.payment-summary")
    payment_summary_modal = remita_page.locator("div.payment-summary")
    total_amount = await payment_summary_modal.locator("p.total").text_content()
    await remita_page.screenshot(path=Path(BASE_DIR, "remita-screenshot.png"))
    await bot.send_photo(
        chat_id=telegram_id,
        photo=FSInputFile(Path(BASE_DIR, "remita-screenshot.png")),
    )
    confirmation_button_info: List[ButtonInfoDict] = [
        {"button_name": "Confirm", "button_callback": "confirm:true"},
        {"button_name": "Cancel", "button_callback": "confirm:false"},
    ]
    confirmation_buttons = await build_payment_buttons(
        button_infos=confirmation_button_info
    )
    payment_choice = await ask_for_wait(
        message=message,
        text=f"You are about to pay {total_amount} for your fee block\nPlease confirm that these details are correct",
        callback_buttons=confirmation_buttons,
        timeout=30000,
    )
    if payment_choice == "No":
        await message.answer(
            "Please verify your details and try again later Thank You for using Acadex"
        )
        return
    payment_button = payment_summary_modal.locator(
        "button.button-primary-large-rounded"
    )
    await payment_button.click()
    await message.answer("Payment Button Clicked")
    await message.answer("Getting Account Details....")
    remita_frame = remita_page.frame_locator("iframe.iframe-pop").first
    await remita_frame.locator('a[href="/bank-transfer"]').wait_for(timeout=60000)
    await remita_frame.locator('a[href="/bank-transfer"]').click()
    await remita_frame.locator("div.fade-in-up").wait_for(timeout=60000)
    time_when_sent = datetime.now()
    expiry_time = time_when_sent + timedelta(minutes=30)
    account_details_modal = remita_frame.locator("div.fade-in-up")
    account_details = await account_details_modal.locator("h3.font-medium").all()
    details_text = []
    for detail in account_details:
        detail_text = await detail.text_content()
        details_text.append(detail_text)
    print(details_text, flush=True)
    await message.answer("Account Details Gotten")
    await remita_page.screenshot(path=Path(BASE_DIR, "remita-screenshot.png"))
    await bot.send_photo(
        chat_id=telegram_id, photo=FSInputFile(Path(BASE_DIR, "remita-screenshot.png"))
    )
    await message.answer(f"""
Bank Name: {details_text[0]}

Account Name: {details_text[1]}

Account Number: {details_text[2]}

Total Amount: {details_text[3]}
    """)
    sent_the_money_button = account_details_modal.locator("button.btn-primary")
    sent_the_money_button_info: List[ButtonInfoDict] = [
        {"button_name": "I have sent the money", "button_callback": "money_sent:true"}
    ]
    sent_the_money_buttons = await build_payment_buttons(
        button_infos=sent_the_money_button_info
    )
    sent_the_money_choice = await ask_for_wait(
        message=message,
        text="Have you sent the money to the account details provided above expires in 30mins or send Stop to end the process?",
        callback_buttons=sent_the_money_buttons,
        timeout=30000,
    )
    if sent_the_money_choice == "True":
        if datetime.now() >= expiry_time:
            await message.answer(
                "Time Limit Reached for sending the money please try again"
            )
            return
    sent_the_money_button.click()
    await message.answer(
        "Remita is Processing your payment please wait for a few minutes.."
    )
    await asyncio.sleep(120)
    await remita_page.screenshot(path=Path(BASE_DIR, "remita-screenshot.png"))
    await bot.send_photo(
        chat_id=telegram_id,
        photo=FSInputFile(Path(BASE_DIR, "remita-screenshot.png")),
        caption=f"Your Payment Status is as follows if it's still showing pending wait a while or check your portal that is if you actually sent the money 🙂",
    )


async def pay_fee_block(
    context: BrowserContext, session_url: str, message: Message, bot: Bot, page: Page
):
    menu, page = await get_menu(
        context=context, bot=bot, session_url=session_url, message=message, page=page
    )
    fee_blocked = await is_fee_blocked(page=page, bot=bot, message=message)
    if not fee_blocked:
        await message.answer("There are no fee blocks to pay")
        return
    fee_block_div = page.locator(".row.g-5.myfeelist").first
    all_fees = await fee_block_div.locator(".card-body").all()
    number_of_fees = len(all_fees)
    await message.answer(f"Found {number_of_fees} fee blocks")
    button_info: List[ButtonInfoDict] = []
    fee_name_block = {}
    for fee in all_fees:
        fee_name = await fee.locator("h6.text-secondary").first.text_content(
            timeout=60000
        )
        print(fee_name, flush=True)
        fee_price = await fee.locator("span.fw-bolder").first.text_content(
            timeout=60000
        )
        button_info.append(
            {"button_name": fee_name, "button_callback": f"fee:{fee_name}:{fee_price}"}
        )
        fee_name_block[fee_name] = fee
    payment_buttons = await build_payment_buttons(button_infos=button_info)
    fee_choice = await ask_for_wait(
        message=message,
        text=f"You have a total of {number_of_fees} fee blocks pick the one you want to pay",
        callback_buttons=payment_buttons,
        timeout=30000,
    )
    try:
        if not fee_choice:
            await message.answer(
                "No fee was selected. Please start the fee payment again."
            )
            return
        print(fee_choice, flush=True)
        fee_data = fee_choice.split(":", 1)
        print(fee_data, flush=True)
        if len(fee_data) != 2:
            raise ValueError(
                f"Invalid fee selection returned by ask_for_wait: {fee_choice!r}"
            )
        selected_fee_name, selected_fee_price = fee_data
        chosen_fee_block: Locator = fee_name_block[selected_fee_name]
        print(chosen_fee_block, flush=True)
        payment_button = chosen_fee_block.get_by_text("Pay", exact=True)
        print(payment_button, flush=True)
        await payment_button.click()
        await page.wait_for_selector(".swal2-popup", timeout=60000)
        popup_div = page.locator(".swal2-popup")
        print(popup_div, flush=True)
    except Exception as e:
        print(f"Could not prepare fee payment confirmation: {e}", flush=True)
        await message.answer(
            "I couldn't open the selected fee's payment confirmation. "
            "Please try the fee payment again."
        )
        return
    await page.screenshot(path=Path(BASE_DIR, "payment-screenshot.png"))
    await bot.send_photo(
        chat_id=message.chat.id,
        photo=FSInputFile(Path(BASE_DIR, "payment-screenshot.png")),
    )
    confirmation_button_info: List[ButtonInfoDict] = [
        {"button_name": "Confirm", "button_callback": "confirm:true"},
        {"button_name": "Cancel", "button_callback": "confirm:false"},
    ]
    confirmation_buttons = await build_payment_buttons(
        button_infos=confirmation_button_info
    )
    confirmation_choice = await ask_for_wait(
        message=message,
        text="Please confirm that these details are correct",
        callback_buttons=confirmation_buttons,
        timeout=30000,
    )
    if confirmation_choice == "No":
        await popup_div.locator("button.swal2-deny").click()
        await message.answer("Payment Cancelled")
        return
    await popup_div.locator("button.swal2-confirm").click()
    await message.answer("Proceeding to the next step..")
    frame = page.frame_locator("iframe.paypanelframe").first
    print(frame, flush=True)
    await frame.locator("span#payerEmail").wait_for(timeout=60000)
    print("Found Email", flush=True)
    await frame.get_by_text("Continue", exact=True).click()
    print("Clicked on continue", flush=True)
    await frame.locator("span#amount").wait_for(timeout=60000)
    total_amount = await frame.locator("span#amount").text_content(timeout=60000)
    await page.screenshot(path=Path(BASE_DIR, "payment-screenshot.png"))
    await bot.send_photo(
        chat_id=message.chat.id,
        photo=FSInputFile(Path(BASE_DIR, "payment-screenshot.png")),
        caption=f"You are about to pay {total_amount} for {selected_fee_name} fee block\nPlease confirm that these details are correct",
    )
    info_confirmation_button_info: List[ButtonInfoDict] = [
        {"button_name": "Confirm", "button_callback": "confirm:true"},
        {"button_name": "Cancel", "button_callback": "confirm:false"},
    ]
    info_confirmation_buttons = await build_payment_buttons(
        button_infos=info_confirmation_button_info
    )
    info_confirmation_choice = await ask_for_wait(
        message=message,
        text=f"You are about to pay {total_amount} for {selected_fee_name} fee block\nPlease confirm that these details are correct",
        callback_buttons=info_confirmation_buttons,
        timeout=30000,
    )
    if info_confirmation_choice == "No":
        await message.answer(
            "Payment Failed You can try again after resolving your details"
        )
        return
    await frame.get_by_title("Click to Pay with Remita").click()
    await frame.locator("button.paymentbtn").wait_for(timeout=60000)
    email = await frame.locator("span#email").text_content()
    await frame.locator("button.paymentbtn").click()
    confirm_rrr_button_info: List[ButtonInfoDict] = [
        {
            "button_name": "I Have My RRR Remita Code",
            "button_callback": "rrr-confirmed:true",
        },
        {"button_name": "Cancel", "button_callback": "rrr-confirmed:false"},
    ]
    confirm_rrr_buttons = await build_payment_buttons(
        button_infos=confirm_rrr_button_info
    )
    confirm_rrr_choice = await ask_for_wait(
        message=message,
        text=f"Your RRR code should be sent to {email} in less than 3mins",
        callback_buttons=confirm_rrr_buttons,
        timeout=30000,
    )
    if confirm_rrr_choice is None:
        await message.answer("Please enter a valid code when tryng again")
        return
    rrr_code = confirm_rrr_choice
    remita_page = await context.new_page()
    await remita_page.goto(
        "https://www.remita.net/pay/pay-rrr", wait_until="domcontentloaded"
    )
    await message.answer("Remita Page Loaded")
    await pay_with_remita(
        remita_page=remita_page, rrr_code=rrr_code, bot=bot, message=message
    )


async def login(
    context: BrowserContext,
    university: str,
    username: str,
    password: str,
    message: Message,
    bot: Bot,
):
    # await message.answer("Login Started")
    MAX_RETRIES = 5
    session_expired = False
    while True:
        try:
            page = await context.new_page()
            if university in UNIVERSITIES_PERMITTED:
                await page.goto(
                    UNIVERSITIES_PERMITTED[university],
                    timeout=800000,
                    wait_until="domcontentloaded",
                )
            else:
                await message.answer(
                    f"The university {university} is unfortunately not on acadex yet 😞💔"
                )
                return
            print("Page opened")
            await message.answer("🔐 Logging you in...")
            await page.fill("#username", username)
            await page.get_by_text("Continue").click()
            print("continue clicked")
            await page.wait_for_selector("#password", timeout=60000)
            await page.fill("#password", password)
            await page.click("#btn_login", timeout=60000)
            try:
                await message.answer("Checking credentials...")
                await page.wait_for_selector("span.swal2-x-mark", timeout=5000)
                await message.answer("❌ Name and password invalid Try again")
                return False
            except Exception as e:
                await message.answer(
                    "🏠 Credentials entered redirecting to home page.."
                )
            for attempt in range(1, MAX_RETRIES + 1):
                try:
                    # print("redirecting you to home page")
                    if await page.wait_for_selector(
                        ".user_text", timeout=180000, state="visible"
                    ):
                        try:
                            if await page.wait_for_selector(
                                "span.student_name", state="visible", timeout=10000
                            ):
                                print("Student name found", flush=True)
                                await message.answer(
                                    f"🏫 {university} Home Page Loaded"
                                )
                                await message.answer(
                                    "Getting your profile details...🔃"
                                )
                        except TimeoutError:
                            try:
                                if (
                                    await page.wait_for_selector(
                                        ".row.g-5.myfeelist",
                                        state="visible",
                                        timeout=10000,
                                    )
                                    != None
                                ):
                                    await message.answer(
                                        f"🏫 {university} Home Page Loaded"
                                    )
                                    await message.answer(
                                        "Getting your profile details...🔃"
                                    )
                            except TimeoutError:
                                if page.get_by_text(
                                    "You are not signed in or your session has expired."
                                ):
                                    session_expired = True
                                    await message.answer(
                                        "Your session has expired attempting to relogin 🤕\nI will get your dashboard even if it kills me you just relax 👩‍💻🤖"
                                    )
                                    await page.screenshot(
                                        path=Path(BASE_DIR, "error-screenshot.png")
                                    )
                                    await bot.send_photo(
                                        chat_id=message.chat.id,
                                        photo=FSInputFile(
                                            Path(BASE_DIR, "error-screenshot.png")
                                        ),
                                    )
                                    break
                                await page.screenshot(
                                    path=Path(BASE_DIR, "error-screenshot.png")
                                )
                                await bot.send_photo(
                                    chat_id=message.chat.id,
                                    photo=FSInputFile(
                                        Path(BASE_DIR, "error-screenshot.png")
                                    ),
                                )
                                await message.answer("Page not loaded properly")
                                raise TimeoutError("Page not loaded properly")
                    # await page.wait_for_selector(
                    #     ".d-inline-flex.text-capitalize.user_text", timeout=180000
                    # )
                    # await page.wait_for_selector(
                    #     "span.student_name", timeout=800000, state="visible"
                    # )
                    if session_expired:
                        continue
                    await page.screenshot(path=Path(BASE_DIR, "screenshot.png"))
                    await bot.send_photo(
                        chat_id=message.chat.id,
                        photo=FSInputFile(Path(BASE_DIR, "screenshot.png")),
                    )
                    session_url = page.url
                    return session_url, page
                except TimeoutError:
                    if attempt == MAX_RETRIES:
                        await message.answer(
                            f"Couldn't load the portal try again later 🤕"
                        )
                        return False
                    await message.answer(
                        f"❌ Page not loaded properly attempting retry {attempt} of {MAX_RETRIES}...."
                    )
                    try:
                        await page.reload(wait_until="domcontentloaded", timeout=180000)
                    except Exception as e:
                        pass
                    await asyncio.sleep(2)
                    continue
        except TimeoutError as e:
            print(e, flush=True)
            await message.answer("❌ Network Timeout Retrying....")
            await page.close()
            continue


# --------------------------------------------------------------------------------------
# Concurrency: one shared Chromium, one isolated BrowserContext per scrape, and a cap on
# how many scrapes run at once (extra requests wait in a queue and are told so).
# --------------------------------------------------------------------------------------
MAX_CONCURRENT_SCRAPES = max(1, int(os.getenv("MAX_CONCURRENT_SCRAPES", "2")))
# Safety net so a stuck page or an ignored prompt can't hold a slot forever.
SCRAPE_JOB_TIMEOUT = int(os.getenv("SCRAPE_JOB_TIMEOUT", "1800"))
# Chromium grows over time; restart it (only while idle) after this many jobs.
BROWSER_RECYCLE_AFTER = int(os.getenv("BROWSER_RECYCLE_AFTER", "50"))

_LAUNCH_ARGS = ["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"]
# --single-process makes one crashed page take down the whole shared browser (and every
# other job using it), so it is OFF unless you explicitly set CHROMIUM_SINGLE_PROCESS=1.
if os.getenv("CHROMIUM_SINGLE_PROCESS", "0") == "1":
    _LAUNCH_ARGS += ["--single-process", "--no-zygote"]

_scrape_slots = asyncio.Semaphore(MAX_CONCURRENT_SCRAPES)
_browser_lock = asyncio.Lock()
_pw = None
_browser = None
_active_jobs = 0
_jobs_on_browser = 0


def _sweep_stale_job_dirs():
    """Remove job folders left behind by a crash (older than 6 hours)."""
    try:
        cutoff = time.time() - 6 * 3600
        for old in Path(_APP_DIR, ".jobs").glob("*"):
            if old.stat().st_mtime < cutoff:
                shutil.rmtree(old, ignore_errors=True)
    except Exception:
        pass


_sweep_stale_job_dirs()


async def _get_browser():
    """Return the shared Chromium, (re)launching it if it is missing or has crashed."""
    global _pw, _browser, _jobs_on_browser
    async with _browser_lock:
        if _browser is None or not _browser.is_connected():
            if _browser is not None:
                print("Shared browser disconnected, relaunching")
            _browser = None
            for attempt in (1, 2):
                if _pw is None:
                    _pw = await async_playwright().start()
                try:
                    _browser = await _pw.chromium.launch(
                        headless=True, args=_LAUNCH_ARGS
                    )
                    break
                except Exception:
                    try:
                        await _pw.stop()
                    except Exception:
                        pass
                    _pw = None
                    if attempt == 2:
                        raise
            _jobs_on_browser = 0
        _jobs_on_browser += 1
        return _browser


async def _recycle_browser_if_due():
    global _browser
    async with _browser_lock:
        if (
            _browser is not None
            and _active_jobs == 0
            and _jobs_on_browser >= BROWSER_RECYCLE_AFTER
        ):
            try:
                await _browser.close()
            except Exception:
                pass
            _browser = None


async def warm_browser():
    """Launch the shared Chromium at startup so the first user doesn't pay for (or hit a
    failure during) a cold launch. Never raises: if it fails, the first job retries."""
    try:
        await _get_browser()
        print("Chromium warmed up")
    except Exception as e:
        print(f"Chromium warm-up failed (will retry on first job): {e!r}")


async def shutdown_browser():
    global _pw, _browser
    async with _browser_lock:
        try:
            if _browser is not None:
                await _browser.close()
        except Exception:
            pass
        try:
            if _pw is not None:
                await _pw.stop()
        except Exception:
            pass
        _browser = None
        _pw = None


async def _open_page(job):
    """Open this job's isolated context + first page. If the shared browser turns out to
    be dead (crashed between jobs or between the liveness check and now), force a fresh
    launch and try once more instead of failing the user's request."""
    global _browser
    last_error = None
    for attempt in (1, 2, 3):
        context = None
        try:
            browser = await _get_browser()
            context = await browser.new_context()
            job.context = context  # closed for us on every exit path
            page = await context.new_page()
            return context, page
        except PlaywrightError as e:
            last_error = e
            print(f"Opening page failed (attempt {attempt}): {e!r}")
            if context is not None:
                try:
                    await context.close()
                except Exception:
                    pass
            job.context = None
            # Only discard the shared browser if it is really dead; otherwise a transient
            # error here would kill another user's in-flight scrape.
            dead = "closed" in str(e).lower()
            async with _browser_lock:
                if _browser is not None and (dead or not _browser.is_connected()):
                    try:
                        await _browser.close()
                    except Exception:
                        pass
                    _browser = None
            await asyncio.sleep(1.5 * attempt)
    raise last_error


@asynccontextmanager
async def _scrape_slot(message):
    """Wait for a free scrape slot (telling the user they're queued), then hold it."""
    global _active_jobs
    if _scrape_slots.locked():
        try:
            await message.answer(
                "⏳ The server is busy with other requests. You're in the queue and will start automatically."
            )
        except Exception:
            pass
    await _scrape_slots.acquire()
    _active_jobs += 1
    try:
        yield
    finally:
        _active_jobs -= 1
        _scrape_slots.release()
        try:
            await _recycle_browser_if_due()
        except Exception:
            pass


class _Job:
    context = None


@asynccontextmanager
async def _job_workspace(message):
    """Private folder + guaranteed context cleanup + overall time limit for one scrape."""
    job = _Job()
    job_dir = Path(_APP_DIR, ".jobs", uuid.uuid4().hex)
    job_dir.mkdir(parents=True, exist_ok=True)
    token = _job_dir_var.set(job_dir)
    limit = asyncio.timeout(SCRAPE_JOB_TIMEOUT)
    try:
        async with limit:
            yield job
    except builtins.TimeoutError:
        # `TimeoutError` in this module is Playwright's, so the builtin is named explicitly.
        if not limit.expired():
            raise
        try:
            await message.answer(
                "⏱ This took too long and was stopped. Please try again."
            )
        except Exception:
            pass
    finally:
        if job.context is not None:
            try:
                await job.context.close()  # only this job's context; the shared browser stays up
            except Exception:
                pass
        _job_dir_var.reset(token)
        shutil.rmtree(job_dir, ignore_errors=True)


async def main(
    username: str,
    password: str,
    university: str,
    download_info: str,
    message: Message,
    bot: Bot,
):
    async with _scrape_slot(message), _job_workspace(message) as job:
        if university == "FUO":
            await message.answer(
                "Acadex has been paused in this university due to review from the univeristy bodies\nWe're very sorry for the incovenience 😞💔"
            )
            return
        await message.answer("Scrape started")
        await message.answer("Loading...")
        context, page = await _open_page(job)
        if await get_url() == "":
            print("None")
            session_url = await get_url()
        else:
            session_url, page = await login(
                university=university,
                context=context,
                username=username,
                password=password,
                message=message,
                bot=bot,
            )
            if session_url is not False:
                await store_url(session_url)
                await message.answer("✅ Logged In Successfully")
                await message.answer("Getting Profile details... 👨‍💻")
            else:
                return
            try:
                if download_info == "payment_receipts":
                    documents = await download_payment_receipts(
                        session_url=session_url,
                        page=page,
                        context=context,
                        message=message,
                        bot=bot,
                    )
                elif download_info == "results":
                    documents = await download_results(
                        context=context,
                        page=page,
                        session_url=session_url,
                        message=message,
                        bot=bot,
                    )
                elif download_info == "result_summary":
                    documents = await get_result_summary(
                        context=context,
                        page=page,
                        session_url=session_url,
                        message=message,
                        bot=bot,
                    )
                elif download_info == "courses":
                    documents = await download_courses(
                        context=context,
                        page=page,
                        session_url=session_url,
                        message=message,
                        bot=bot,
                    )

                elif download_info == "biodata":
                    await download_biodata(
                        context=context,
                        page=page,
                        session_url=session_url,
                        message=message,
                        bot=bot,
                    )
                    print("Done")

                elif download_info == "admission_forms":
                    await download_admmission_forms(
                        context=context,
                        page=page,
                        session_url=session_url,
                        message=message,
                        bot=bot,
                    )
                elif download_info == "pay_fee_block":
                    await pay_fee_block(
                        context=context,
                        page=page,
                        session_url=session_url,
                        message=message,
                        bot=bot,
                    )
            except asyncio.CancelledError:
                await context.close()
                raise
            except TimeoutError as e:
                await message.answer("❌ Network Timeout Retry")
                raise (e)
                return
            finally:
                scraping_tasks.pop(message.chat.id, None)
        print("Browser closing")
        await context.close()


# payments = page.locator("#kt_aside_menu_wrapper menu-title").filter(
#     has_text="Payments"
# )
# payments.click()
# print("Payments clicked")
# page.wait_for_selector(".menu-item")
# if page.get_by_text("Payment Receipts").is_visible():
#     page.get_by_text("Payment Receipts").click()
#     print("Payment receipts clicked")
# print("Payment clicked")


if __name__ == "__main__":
    asyncio.run(main("kudos.ajao", "07030625463", "courses"))
