from playwright.async_api import async_playwright, BrowserContext, Locator, TimeoutError
import asyncio
from redis_config import get_url, store_url
from pathlib import Path
from PIL import Image
from aiogram.types import Message, FSInputFile
from aiogram import Bot
import os
from tasks import scraping_tasks

BASE_DIR = Path(__file__).resolve().parent


async def get_menu(session_url: str, context: BrowserContext, message: Message):
    try:
        page = await context.new_page()
        await page.goto(session_url, timeout=100000)
        await page.wait_for_selector(
            ".d-inline-flex.text-capitalize.user_text", timeout=80000
        )
        await message.answer("🏫 FUO Home Page Loaded")
        if await page.locator("#kt_aside_mobile_toggle").is_visible():
            await page.click("#kt_aside_mobile_toggle")
            print("Toggle clicked")
        else:
            await page.wait_for_selector("span.matric_no", timeout=50000)
            mat_num = await page.locator("span.matric_no").inner_text()
            await message.answer(f"👨‍🎓 Found Matric Number: {mat_num}")
        menu = page.locator("div.menu-item.menu-accordion")
        await message.answer("🤖 Side Menu Clicked")
        return menu, page
    except TimeoutError:
        await message.answer("❌ Network Timeout Retry")
        return


async def download_payment_receipts(
    session_url: str, context: BrowserContext, message: Message, bot: Bot
):
    menu, page = await get_menu(session_url, context, message=message)
    await menu.get_by_text("Payments", exact=True).click()
    await message.answer("🔍 Looking for your receipts....")
    await menu.get_by_text("Payment Receipts", exact=True).click()
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
    context: BrowserContext, session_url: str, message: Message, bot: Bot
):
    menu, page = await get_menu(
        session_url=session_url, context=context, message=message
    )
    await message.answer("📊 Fetching Results....")
    await menu.get_by_text("Courses", exact=True).click()
    print("Courses clicked")
    await menu.get_by_text("View Results", exact=True).click()
    print("View Results clicked")
    await page.wait_for_selector(".selection")
    await message.answer(f"🔍 Results Found")
    await page.click(".selection")
    options = page.locator("li[role='option']")
    # options_text = await options.all_inner_texts()
    # unique_options = list(dict.fromkeys(option.strip() for option in options_text if option != 'Select Session'))
    options_clicked = list(set([]))
    pdf_page = await context.new_page()
    await pdf_page.goto(session_url, wait_until="load")
    for i in reversed(range(1, await options.count())):
        print(options_clicked)
        session = await options.nth(i).inner_text()
        await message.answer(
            f" 🔎 Found your result for {session} session about to download"
        )
        if session not in options_clicked:
            await options.nth(i).click()
            await page.wait_for_selector(".highest_gpa")
            print("Found highest gpa")
            semesters = page.locator("li.nav-item")
            semester_count = await semesters.count()
            print(semester_count)
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
                    await page.wait_for_selector(".row.g-9")
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


async def download_courses(
    context: BrowserContext,
    session_url: str,
    message: Message,
    bot: Bot,
    level: int = None,
):
    menu, page = await get_menu(
        session_url=session_url, context=context, message=message
    )
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
            await page.wait_for_selector(".card-body.p-6", timeout=1000000)
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


# async def download_biodata(
#     context: BrowserContext,
#     session_url: str,
#     message: Message,
#     bot: Bot,
# ):
#     menu, page = await get_menu(
#         session_url=session_url, context=context, message=message
#     )
#     await message.answer("Fetching your biodata...")
#     await menu.get_by_text("Details", exact=True).click()
#     await menu.get_by_text("My details", exact=True).click()
#     await message.answer("Biodata page loading...")
#     pdf_page = await context.new_page()
#     # await pdf_page.goto(page.url)
#     await pdf_page.wait_for_load_state("networkidle")
#     await message.answer(
#         "Biodata page loaded\nDownloading your biodata...\nThis will take a couple of minutes based on your network speed\nSend 'Stop' at any moment to cancel the download"
#     )
#     try:
#         await page.wait_for_selector("#my_details")
#         print("selector found")
#         await asyncio.sleep(10)
#         element_html = await page.evaluate("""  ()=>{
#           const head = document.head.outerHtml;
#           const html = document.querySelector("#my_details")?.outerHTML ?? null;
#           return `<html><head>${head}</head><body>${html}</body></html>`}
#           """)
#         # print(element_html)

#         if not element_html:
#             await message.answer(
#                 "❌ Unable to find biodata on the page. Please try again later."
#             )
#         filename = Path(BASE_DIR, "biodata.pdf")
#         print(filename)
#         # await pdf_page.evaluate(
#         #     "(html) => {document.body.innerHTML = html}", element_html
#         # )
#         await pdf_page.set_content(element_html)

#         print("PDF page content set")
#         await asyncio.sleep(3)
#         print("slept")
#         await pdf_page.pdf(path=filename, format="A4", print_background=True)
#         print("pdf page gotten")
#         await bot.send_document(
#             chat_id=message.chat.id, document=FSInputFile(filename), caption="Biodata"
#         )
#         os.remove(filename)
#     except Exception as e:
#         await message.answer(f"Error{e}")
#         raise


async def download_admmission_forms(
    context: BrowserContext, session_url: str, message: Message, bot: Bot
):
    menu, page = await get_menu(
        context=context, session_url=session_url, message=message
    )
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
    except Exception as e:
        await message.answer(f"Error occured while getting documents try again")
        raise


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
        await message.answer("🔐 Logging you in...")
        await page.fill("#username", username)
        await page.get_by_text("Continue").click()
        print("continue clicked")
        await page.wait_for_url("https://ecampus.fuotuoke.edu.ng/ecampus/login.html#")
        await page.fill("#password", password)
        await page.click("#btn_login", timeout=100000)
        try:
            await page.wait_for_selector("span.swal2-x-mark", timeout=5000)
            await message.answer("❌ Name and password invalid Try again")
            return False
        except Exception as e:
            await message.answer("🏠 Credentials entered redirecting to home page..")
            await message.answer("Redirecting...")
            # print("redirecting you to home page")
            await page.wait_for_selector("span.student_name", timeout=80000)
            session_url = page.url
            await page.close()
            return session_url
    except TimeoutError:
        await message.answer("❌ Network Timeout Retry")
        return False


async def main(
    username: str, password: str, download_info: str, message: Message, bot: Bot
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
            session_url = await login(
                context=context, username=username, password=password, message=message
            )
            if session_url is not False:
                await store_url(session_url)
                await message.answer("✅ Logged In Successfully")
            else:
                return
            try:
                if download_info == "payment_receipts":
                    documents = await download_payment_receipts(
                        session_url=session_url,
                        context=context,
                        message=message,
                        bot=bot,
                    )
                elif download_info == "results":
                    documents = await download_results(
                        context=context,
                        session_url=session_url,
                        message=message,
                        bot=bot,
                    )
                elif download_info == "courses":
                    documents = await download_courses(
                        context=context,
                        session_url=session_url,
                        message=message,
                        bot=bot,
                    )

                # elif download_info == "biodata":
                #     await download_biodata(
                #         context=context,
                #         session_url=session_url,
                #         message=message,
                #         bot=bot,
                #     )
                #     print("Done")

                elif download_info == "admission_forms":
                    await download_admmission_forms(
                        context=context,
                        session_url=session_url,
                        message=message,
                        bot=bot,
                    )
            except asyncio.CancelledError:
                await browser.close()
                raise
            except TimeoutError:
                await message.answer("❌ Network Timeout Retry")
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
