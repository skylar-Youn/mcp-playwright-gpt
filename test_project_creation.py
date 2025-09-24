from playwright.sync_api import sync_playwright
import time

def test_project_creation():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()

        # Enable console logging
        page.on("console", lambda msg: print(f"Console: {msg.type}: {msg.text}"))
        page.on("pageerror", lambda exc: print(f"Page error: {exc}"))

        # Navigate to translator page
        page.goto("http://localhost:8000/translator")

        # Wait for downloads to load
        time.sleep(3)

        print("1. Checking if downloads loaded...")
        downloads_list = page.query_selector("#downloads-list")
        if downloads_list:
            content = downloads_list.inner_text()
            print(f"Downloads: {content[:200]}...")

        print("2. Selecting a source...")
        # Try to click on the first source
        first_source = page.query_selector("#downloads-list .source-item")
        if first_source:
            first_source.click()
            time.sleep(1)
            print("First source clicked")

        print("3. Checking AI commentary section...")
        # Check if AI commentary section shows selected source
        commentary_section = page.query_selector("#ai-commentary-section")
        if commentary_section:
            commentary_content = commentary_section.inner_text()
            print(f"AI Commentary section: {commentary_content[:200]}...")

        print("4. Testing project creation button...")
        # Try to click project creation button
        create_btn = page.query_selector("#create-project-btn")
        if create_btn and create_btn.is_enabled():
            print("Create button is enabled, clicking...")
            create_btn.click()
            time.sleep(3)

            # Check if we navigated to project view or got an error
            current_url = page.url
            print(f"Current URL after create: {current_url}")

            # Check for any success/error messages
            body_text = page.query_selector("body").inner_text()
            if "error" in body_text.lower():
                print(f"Error in response: {body_text[:500]}")
            else:
                print("Project creation seems successful")

        else:
            print("Create button is not enabled or not found")
            if create_btn:
                print(f"Button disabled: {create_btn.is_disabled()}")

        # Take final screenshot
        page.screenshot(path="/tmp/project_creation_test.png")
        print("Screenshot saved to /tmp/project_creation_test.png")

        browser.close()

if __name__ == "__main__":
    test_project_creation()