from playwright.async_api import async_playwright, BrowserContext, Locator, TimeoutError
import asyncio
from redis_config import get_url, store_url
from pathlib import Path
from PIL import Image
from aiogram.types import Message, FSInputFile
from aiogram import Bot

BASE_DIR = Path(__file__).resolve().parent


async def get_menu(session_url: str, context: BrowserContext, message: Message):
    page = await context.new_page()
    await page.goto(session_url, timeout=100000)
    await page.wait_for_selector(
        ".d-inline-flex.text-capitalize.user_text", timeout=80000
    )
    await message.answer("FUO Home Page Loaded")
    if await page.locator("#kt_aside_mobile_toggle").is_visible():
        await page.click("#kt_aside_mobile_toggle")
        print("Toggle clicked")
    else:
        await page.wait_for_selector("span.matric_no", timeout=50000)
        mat_num = await page.locator("span.matric_no").inner_text()
        await message.answer(f"Found Matric Number: {mat_num}")
    menu = page.locator("div.menu-item.menu-accordion")
    await message.answer("Found Side Menu")
    return menu, page


async def download_payment_receipts(
    session_url: str, context: BrowserContext, message: Message, bot: Bot
):
    menu, page = await get_menu(session_url, context, message=message)
    await menu.get_by_text("Payments", exact=True).click()
    await message.answer("Payments Button Clicked")
    await menu.get_by_text("Payment Receipts", exact=True).click()
    await message.answer("Payment Receipts Clicked")
    await page.wait_for_selector("div.d-flex.py-3.rounded-1.row.mx-0")
    receipts = page.locator("div.d-flex.py-3.rounded-1.row.mx-0")
    await message.answer("Yaay I Found Your Receipts")
    # documents = []
    await message.answer(
        "Downloading......\nThis will take a couple of minutes based on your network speed"
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
        print(download.suggested_filename)
        # print("Downloaded")
        filename = Path(BASE_DIR, f"{document_name}{download.suggested_filename}")
        pdf_filename = str(filename).replace(".png", ".pdf")
        await download.save_as(filename)
        img = Image.open(filename)
        img.convert("RGB").save(pdf_filename)
        print("Saved as pdf")
        await bot.send_document(
            chat_id=message.chat.id,
            document=FSInputFile(pdf_filename),
            caption=f"{document_name} downloaded",
        )
        # documents.append(pdf_filename)
        # print("Added")
        await page.click('div[aria-label="Close"]')
    await page.close()
    # print(documents)
    # return documents


async def download_results(context: BrowserContext, session_url: str, message: Message):
    menu, page = await get_menu(session_url=session_url, context=context)
    await menu.get_by_text("Courses", exact=True).click()
    print("Courses clicked")
    await menu.get_by_text("View Results", exact=True).click()
    print("View Results clicked")
    await page.wait_for_selector(".selection")
    await page.click(".selection")
    options = page.locator("li[role='option']")
    for i in reversed(range(await options.count())):
        await options.nth(i).click()
        await page.wait_for_selector(".highest_gpa")
        print("Found highest gpa")
        await page.click("#btnprint_all")
        print("Clicked button")
        await page.wait_for_selector(".row.g-9")
        session = await page.locator("p[field='session']").nth(1).inner_text()
        print(session)
        session_result = await page.locator(".col-12.card.card-custom.p-8.mx-auto")
        page.add_style_tag(
            content="""
        body * {
                display:none !important
                    }
        .col-12.card.card-custom.p-8.mx-auto {
                display:block !important
                    }
"""
        )
        # await session_result.pd
        # await page.evaluate("window.print = () => {}")
        await page.pdf(
            path=f"{session} results.pdf", format="A4", print_background=True
        )
        await page.click("div[data-bs-dismiss='modal']")
        await page.click(".selection")


async def download_courses(
    context: BrowserContext, session_url: str, message: Message, bot: Bot
):
    menu, page = await get_menu(
        session_url=session_url, context=context, message=message
    )
    await menu.get_by_text("Courses", exact=True).click()
    print("Courses clicked")
    await asyncio.sleep(3)
    await menu.get_by_text("View Registered Courses", exact=True).click()
    print("clicked registered courses")
    if await page.get_by_text("Sorry, no course found", exact=True).is_visible():
        await message.answer("Register your courses")
    else:
        try:
            documents = []
            await page.wait_for_selector(".card-body.p-6", timeout=1000000)
            print("Load complete")
        except Exception as e:
            await message.answer("Portal issues please try again")
            print(e)
        await page.locator("span.selection").nth(0).click()
        print("Clicked selections")
        options = page.locator(".select2-results li")
        print(options)
        count = await options.count()
        print(count)
        for i in range(1, count):
            level = await options.nth(i).inner_text()
            print(level)
            await options.nth(i).click()  # Click levels
            print("Clicked level")
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
                    await page.get_by_text(unique_semesters[i]).nth(2).click()
                pdf_element = page.locator(".row.d-print-block")
                print("Found pdf element")
                original_body = await page.evaluate("document.body.innerHTML")
                semester = unique_semesters[j]
                semester = semester.strip()
                course_name = f"{level}_{semester}_courses"
                filename = Path(BASE_DIR, f"{level}_{semester}_courses.pdf")
                element_html = await page.evaluate(
                    "() => document.querySelector('.row.d-print-block').outerHTML;"
                )
                pdf_page = await context.new_page()
                await pdf_page.goto(page.url)
                await pdf_page.wait_for_load_state("networkidle")
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
                await pdf_page.close()
                await page.locator("span.selection").nth(0).click()
                await options.nth(i).click()
                print("original body back")
                documents.append(filename)
            await page.locator("span.selection").nth(0).click()


async def login(
    context: BrowserContext, username: str, password: str, message: Message
):
    # await message.answer("Login Started")
    try:
        page = await context.new_page()
        await page.goto(
            "https://ecampus.fuotuoke.edu.ng/ecampus/login.html", timeout=100000
        )
        print("Page opened")
        await message.answer("Login Started")
        await page.fill("#username", username)
        await page.get_by_text("Continue").click()
        print("continue clicked")
        await page.wait_for_url("https://ecampus.fuotuoke.edu.ng/ecampus/login.html#")
        await page.fill("#password", password)
        await page.click("#btn_login", timeout=100000)
        await message.answer("Credentials entered redirecting to home page..")
        await message.answer("Redirecting...")
        if await page.locator("#swal2-html-container").is_visible():
            await message.answer("Error name and password invalid Try again")
            return False
        else:
            # print("redirecting you to home page")
            await page.wait_for_selector("span.student_name", timeout=80000)
            session_url = page.url
            return session_url
    except TimeoutError:
        await message.answer("Network Timeout Retry")


async def main(
    username: str, password: str, download_info: str, message: Message, bot: Bot
):
    async with async_playwright() as p:
        await message.answer("Scrape started")
        await message.answer("Loading...")
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()
        if await get_url() == "":
            print("None")
            session_url = await get_url()
        else:
            session_url = await login(
                context=context, username=username, password=password, message=message
            )
            if session_url is not False:
                await store_url(session_url)
                await message.answer("Logged In")
            if download_info == "payment_receipts":
                documents = await download_payment_receipts(
                    session_url=session_url, context=context, message=message, bot=bot
                )
            elif download_info == "results":
                documents = download_results(
                    context=context, session_url=session_url, message=message
                )
            elif download_info == "courses":
                documents = await download_courses(
                    context=context, session_url=session_url, message=message, bot=bot
                )
        await asyncio.sleep(10)
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
