from playwright.sync_api import sync_playwright
import time

def test_project_creation_correct_selector():
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

                print("2. Looking for submit button...")
                # Look for submit button with correct selector
                submit_btn = page.query_selector('button[type="submit"]')
                if submit_btn:
                    print(f"✅ Found submit button: '{submit_btn.inner_text()}'")
                    print(f"Button enabled: {not submit_btn.is_disabled()}")

                    if not submit_btn.is_disabled():
                        print("3. Clicking submit button...")
                        submit_btn.click()
                        print("Submit button clicked, waiting for response...")

                        # Wait for navigation or response
                        time.sleep(8)

                        current_url = page.url
                        print(f"Current URL: {current_url}")

                        if "project_id=" in current_url:
                            print("✅ SUCCESS! Project created and redirected to project page")
                            page.screenshot(path="/tmp/project_success.png")
                        else:
                            print("❌ No redirect occurred, checking for errors...")
                            page_text = page.query_selector("body").inner_text()
                            print(f"Page content (first 500 chars): {page_text[:500]}")
                            page.screenshot(path="/tmp/no_redirect.png")

                    else:
                        print("❌ Submit button is disabled")
                        page.screenshot(path="/tmp/disabled_button.png")
                else:
                    print("❌ Submit button not found")
                    # Debug: list all buttons
                    all_buttons = page.query_selector_all("button")
                    print(f"Found {len(all_buttons)} buttons:")
                    for i, btn in enumerate(all_buttons):
                        print(f"  {i}: '{btn.inner_text()}' - disabled: {btn.is_disabled()}")

            else:
                print("❌ Could not find radio button")

        except Exception as e:
            print(f"Test error: {e}")
            page.screenshot(path="/tmp/test_error.png")

        finally:
            browser.close()

if __name__ == "__main__":
    test_project_creation_correct_selector()