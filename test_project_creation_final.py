from playwright.sync_api import sync_playwright
import time

def test_complete_project_creation():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()

        # Enable console logging
        page.on("console", lambda msg: print(f"Console: {msg.type}: {msg.text}"))
        page.on("pageerror", lambda exc: print(f"Page error: {exc}"))

        try:
            # Navigate to translator page
            page.goto("http://localhost:8000/translator")

            # Wait for downloads to load
            time.sleep(3)

            print("1. Selecting source...")
            # Select first radio button
            first_radio = page.query_selector('input[name="source"]')
            if first_radio:
                first_radio.click()
                time.sleep(2)
                print("✅ Source selected")

                # Verify AI commentary section updated
                video_name = page.query_selector("#selected-video-name").inner_text()
                print(f"Selected video: {video_name}")

                print("2. Testing project creation...")
                # Click create project button
                create_btn = page.query_selector("#create-project-btn")
                if create_btn and not create_btn.is_disabled():
                    create_btn.click()
                    print("Create button clicked, waiting for response...")

                    # Wait for navigation or response
                    time.sleep(5)

                    current_url = page.url
                    print(f"Current URL: {current_url}")

                    if "project_id=" in current_url:
                        print("✅ Project created successfully! Redirected to project page")

                        # Take screenshot of project page
                        page.screenshot(path="/tmp/project_created_success.png")

                        # Check for project content
                        page_text = page.query_selector("body").inner_text()
                        if "세그먼트" in page_text or "번역" in page_text:
                            print("✅ Project page loaded with content")
                        else:
                            print("⚠️ Project page may not have loaded correctly")

                    else:
                        print("❌ Project creation failed or no redirect occurred")
                        # Take screenshot for debugging
                        page.screenshot(path="/tmp/project_creation_failed.png")

                        # Check for error messages
                        page_text = page.query_selector("body").inner_text()
                        if "error" in page_text.lower():
                            print(f"Error message: {page_text}")

                else:
                    print("❌ Create button not found or disabled")
            else:
                print("❌ Could not find radio button")

        except Exception as e:
            print(f"Test error: {e}")
            page.screenshot(path="/tmp/test_error.png")

        finally:
            browser.close()

if __name__ == "__main__":
    test_complete_project_creation()