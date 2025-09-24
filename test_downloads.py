from playwright.sync_api import sync_playwright
import time

def test_downloads_loading():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()

        # Enable console logging
        page.on("console", lambda msg: print(f"Console: {msg.type}: {msg.text}"))
        page.on("pageerror", lambda exc: print(f"Page error: {exc}"))

        # Navigate to translator page
        page.goto("http://localhost:8000/translator")

        # Wait for page to load
        time.sleep(3)

        # Check if downloads list is populated
        downloads_list = page.query_selector("#downloads-list")
        if downloads_list:
            content = downloads_list.inner_text()
            print(f"Downloads list content: {content}")

            # Check if API call indicator is still showing
            if "API 호출 중..." in content or "다운로드된 파일을 불러오는 중..." in content:
                print("Downloads are still loading - checking network activity")

                # Wait a bit more and check again
                time.sleep(5)
                content = downloads_list.inner_text()
                print(f"Downloads list after 5 more seconds: {content}")

        # Take a screenshot
        page.screenshot(path="/tmp/downloads_test.png")
        print("Screenshot saved to /tmp/downloads_test.png")

        browser.close()

if __name__ == "__main__":
    test_downloads_loading()