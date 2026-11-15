from playwright.async_api import (
    async_playwright,
    BrowserContext,
    Locator,
    TimeoutError,
    Page,
)
import asyncio
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

BASE_DIR = Path(__file__).resolve().parent

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
            await message.answer("🤖 Side Menu Clicked")
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
    await message.answer("🧾 Receipts Found")
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
    cookies_accept_button = remita_page.locator("button.site-agreement-button").first
    await cookies_accept_button.click()
    await remita_page.fill("#mat-input-0", rrr_code)
    await remita_page.wait_for_selector("div.payment-summary")
    payment_summary_modal = remita_page.locator("div.payment-summary")
    total_amount = payment_summary_modal.locator("p.total").text_content()
    await remita_page.screenshot(path=Path("remita-screenshot.png"))
    await bot.send_photo(
        chat_id=telegram_id,
        photo=FSInputFile(Path("remita-screenshot.png")),
    )
    confirmation_button_info: List[ButtonInfoDict] = [
        {"button_name": "Confirm", "button_callback": "confirm:true"},
        {"button_name": "Cancel", "button_callback": "confirm:false"},
    ]
    confirmation_buttons = await build_payment_buttons(
        button_info=confirmation_button_info
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
    await remita_page.get_by_text("Bank Transfer", exact=True).click()
    await remita_page.wait_for_selector("div.fade-in-up")
    time_when_sent = datetime.now()
    expiry_time = time_when_sent + timedelta(minutes=30)
    account_details_modal = remita_page.locator("div.fade-in-up")
    await remita_page.screenshot(path=Path("remita-screenshot.png"))
    await bot.send_photo(
        chat_id=telegram_id, photo=FSInputFile(Path("remita-screenshot.png"))
    )
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
    await remita_page.screenshot(path=Path("remita-screenshot.png"))
    await bot.send_photo(
        chat_id=telegram_id,
        photo=FSInputFile(Path("remita-screenshot.png")),
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
    payment_buttons = await build_payment_buttons(button_info)
    fee_choice = await ask_for_wait(
        message=message,
        text=f"You have a total of {number_of_fees} fee blocks pick the one you want to pay",
        callback_buttons=payment_buttons,
        timeout=30000,
    )
    try:
        print(fee_choice, flush=True)
        fee_data = fee_choice.split(":")
        print(fee_data, flush=True)
        selected_fee_name = fee_data[1]
        selected_fee_price = fee_data[2]
        chosen_fee_block: Locator = fee_name_block[selected_fee_name]
        print(chosen_fee_block, flush=True)
        chosen_fee_block_index = list(fee_name_block.keys()).index(selected_fee_name)
        payment_button = chosen_fee_block.get_by_text("Pay", exact=True)
        print(payment_button, flush=True)
        await payment_button.click()
        await page.wait_for_selector(".swal2-popup", timeout=60000)
        popup_div = page.locator(".swal2-popup")
        print(popup_div, flush=True)
    except Exception as e:
        print(e, flush=True)
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
        button_info=confirmation_button_info
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
    await page.wait_for_selector("div.contact-box", timeout=60000)
    await page.get_by_text("Continue", exact=True).click()
    await page.wait_for_selector("span#amount", timeout=60000)
    total_amount = await page.locator("span#amount").text_content(timeout=60000)
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
        button_info=info_confirmation_button_info
    )
    info_confirmation_choice = await ask_for_wait(
        message=message,
        text="You are about to pay {total_amount} for {selected_fee_name} fee block\nPlease confirm that these details are correct",
        callback_buttons=info_confirmation_buttons,
        timeout=30000,
    )
    if info_confirmation_choice == "No":
        await message.answer(
            "Payment Failed You can try again after resolving your details"
        )
        return
    await page.locator("img.monify").click()
    await page.wait_for_selector("button.paymentbtn")
    email = await page.locator("span#email").text_content()
    await page.locator("button.paymentbtn").click()
    confirm_rrr_button_info: List[ButtonInfoDict] = [
        {
            "button_name": "I Have My RRR Remita Code",
            "button_callback": "rrr-confirmed:true",
        },
        {"button_name": "Cancel", "button_callback": "rrr-confirmed:false"},
    ]
    confirm_rrr_buttons = await build_payment_buttons(
        button_info=confirm_rrr_button_info
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
    await remita_page.goto("https://www.remita.net/pay-rrr")
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
                await page.goto(UNIVERSITIES_PERMITTED[university], timeout=800000)
            else:
                await message.answer(
                    f"The university {university} is unfortunately not on acadex yet 😞💔"
                )
                return
            print("Page opened")
            await message.answer("🔐 Logging you in...")
            await page.fill("#username", username)
            await message.answer("Username entered")
            await page.get_by_text("Continue").click()
            print("continue clicked")
            await message.answer("Password page loading...")
            await page.wait_for_selector("#password", timeout=60000)
            await page.fill("#password", password)
            await message.answer("Password entered")
            await page.click("#btn_login", timeout=60000)
            await message.answer("Logging in...")
            try:
                await message.answer("Checking credentials...")
                await page.wait_for_selector("span.swal2-x-mark", timeout=30000)
                await message.answer("❌ Name and password invalid Try again")
                return False
            except Exception as e:
                await message.answer(
                    "🏠 Credentials entered redirecting to home page.."
                )
            for attempt in range(1, MAX_RETRIES + 1):
                try:
                    await message.answer("Redirecting...")

                    # print("redirecting you to home page")
                    if await page.wait_for_selector(
                        ".user_text", timeout=180000, state="visible"
                    ):
                        try:
                            if await page.wait_for_selector(
                                "span.student_name", state="visible", timeout=80000
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
                                        timeout=80000,
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
        except TimeoutError:
            await message.answer("❌ Network Timeout Retrying....")
            await page.close()
            continue


async def main(
    username: str,
    password: str,
    university: str,
    download_info: str,
    message: Message,
    bot: Bot,
):
    async with async_playwright() as p:
        await message.answer("Scrape started")
        await message.answer("Loading...")
        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
                "--single-process",
                "--no-zygote",
            ],
        )
        context = await browser.new_context()
        page = await context.new_page()
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
                await browser.close()
                raise
            except TimeoutError as e:
                await message.answer("❌ Network Timeout Retry")
                raise (e)
                return
            finally:
                scraping_tasks.pop(message.chat.id, None)
        await asyncio.sleep(10)
        print("Browser closing")
        await browser.close()


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
