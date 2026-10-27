
import os
from pathlib import Path

from dotenv import load_dotenv
from playwright.sync_api import sync_playwright, expect

load_dotenv()

APP_URL = "http://localhost:5173/"
EMAIL = os.getenv("APP_EMAIL")
PASSWORD = os.getenv("APP_PASSWORD")
PDF_PATH = os.getenv("PDF_PATH")

EVIDENCE_DIR = Path("screenshots")
EVIDENCE_DIR.mkdir(exist_ok=True)


def test_chatbot_login_upload_question_logout():
    assert EMAIL, "APP_EMAIL is missing from .env"
    assert PASSWORD, "APP_PASSWORD is missing from .env"
    assert PDF_PATH, "PDF_PATH is missing from .env"

    pdf_file = Path(PDF_PATH)
    assert pdf_file.is_file(), f"PDF not found: {PDF_PATH}"

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=False)
        page = browser.new_page()

        try:
            # 1. Open the application
            page.goto(APP_URL)

            email_box = page.get_by_role("textbox", name="Email")
            password_box = page.get_by_role("textbox", name="Password")

            expect(email_box).to_be_visible()
            expect(password_box).to_be_visible()

            page.screenshot(
                path=str(EVIDENCE_DIR / "01_login_page.png"),
                full_page=True,
            )

            # 2. Login
            email_box.fill(EMAIL)
            password_box.fill(PASSWORD)
            page.get_by_role("button", name="Login").click()

            page.wait_for_url("**/upload", timeout=15000)

            # 3. Upload PDF and verify the backend response
            with page.expect_response(
                lambda response: (
                    response.request.method == "POST"
                    and "/documents" in response.url
                ),
                timeout=60000,
            ) as response_info:
                page.locator('input[type="file"]').set_input_files(
                    str(pdf_file)
                )

            upload_response = response_info.value

            assert upload_response.status in (200, 201), (
                f"Upload failed with HTTP {upload_response.status}"
            )

            # Upload.jsx navigates to /chat on success
            page.wait_for_url("**/chat", timeout=15000)

            question_box = page.get_by_role(
                "textbox", name="Ask a question..."
            )
            expect(question_box).to_be_visible()

            page.screenshot(
                path=str(EVIDENCE_DIR / "03_after_upload.png"),
                full_page=True,
            )

            # 4. Ask a question
            question_box.fill("What is an INNER JOIN?")
            page.get_by_role("button", name="Ask").click()

            # Find the paragraph containing the generated answer.
            answer = page.locator("p").filter(
                has_text="INNER JOIN"
            ).last

            expect(answer).to_be_visible(timeout=60000)

            answer_text = answer.inner_text().strip()
            normalized = " ".join(answer_text.lower().split())

            assert "inner join" in normalized, (
                f"Answer does not mention INNER JOIN: {answer_text}"
            )
            assert "matching" in normalized, (
                f"Answer does not mention matching values: {answer_text}"
            )
            assert "both tables" in normalized, (
                f"Answer does not mention both tables: {answer_text}"
            )

            print("Verified chatbot answer:", answer_text)

            page.screenshot(
                path=str(EVIDENCE_DIR / "04_chat_answer.png"),
                full_page=True,
            )

            # 5. Logout
            page.get_by_role("button", name="Logout").click()

            expect(
                page.get_by_role("textbox", name="Email")
            ).to_be_visible(timeout=15000)

            page.screenshot(
                path=str(EVIDENCE_DIR / "05_logout.png"),
                full_page=True,
            )

        except Exception:
            # Save a screenshot if any step fails
            try:
                page.screenshot(
                    path=str(EVIDENCE_DIR / "failure.png"),
                    full_page=True,
                )
            except Exception:
                pass

            raise

        finally:
            browser.close()
