
import os
import pytest
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

load_dotenv()

APP_URL = "http://localhost:5173/"
EMAIL = os.getenv("APP_EMAIL")
PASSWORD = os.getenv("APP_PASSWORD")


@pytest.fixture
def browser_page():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        yield page
        browser.close()


def test_login_and_logout_without_chatbot_calls(browser_page):
    if not EMAIL or not PASSWORD:
        pytest.skip("APP_EMAIL or APP_PASSWORD is missing from .env")

    page = browser_page
    page.goto(APP_URL)

    # Log in using the existing application UI.
    page.get_by_label("Email").fill(EMAIL)
    page.get_by_label("Password").fill(PASSWORD)
    page.get_by_role("button", name="Login").click()

    page.wait_for_url("**/upload", timeout=15000)

    # Verify that the session token exists after login.
    token = page.evaluate("localStorage.getItem('access_token')")
    assert token, "Login succeeded, but access_token was not found."

    # Log out and verify client-side values are cleared.
    page.get_by_role("button", name="Logout").click()
    page.wait_for_url(APP_URL, timeout=10000)

    assert page.evaluate("localStorage.getItem('access_token')") is None
    assert page.evaluate("localStorage.getItem('document_id')") is None

    # Check whether the UI redirects an unauthenticated user.
    page.goto(APP_URL + "chat")
    page.wait_for_timeout(1000)

    assert page.url.rstrip("/") != (APP_URL + "chat").rstrip("/"), (
        "Unauthenticated user remained on /chat. "
        "Check the frontend route guard."
    )
