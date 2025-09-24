from playwright.sync_api import sync_playwright
import time

def test_source_selection():
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

        print("1. Checking downloaded items...")
        downloads = page.query_selector_all(".download-item")
        print(f"Found {len(downloads)} download items")

        if downloads:
            print("2. Selecting first radio button...")
            first_radio = page.query_selector('input[name="source"]')
            if first_radio:
                # Click the radio button
                first_radio.click()
                time.sleep(2)
                print("Radio button clicked")

                # Check if AI commentary section updated
                print("3. Checking AI commentary section...")
                video_name = page.query_selector("#selected-video-name")
                subtitle_name = page.query_selector("#selected-subtitle-name")

                if video_name and subtitle_name:
                    video_text = video_name.inner_text()
                    subtitle_text = subtitle_name.inner_text()
                    print(f"Video: {video_text}")
                    print(f"Subtitle: {subtitle_text}")

                    if "프로젝트에서 소스 정보를 가져오는 중" not in video_text:
                        print("✅ Source selection working!")

                        # Check if create button is enabled
                        print("4. Checking create project button...")
                        create_btn = page.query_selector("#create-project-btn")
                        if create_btn:
                            is_enabled = not create_btn.is_disabled()
                            print(f"Create button enabled: {is_enabled}")

                            if is_enabled:
                                print("5. Testing project creation...")
                                create_btn.click()
                                time.sleep(5)

                                # Check result
                                current_url = page.url
                                print(f"URL after creation: {current_url}")

                                if "/translator" in current_url and "project_id=" in current_url:
                                    print("✅ Project creation successful!")
                                else:
                                    print("❌ Project creation may have failed")
                    else:
                        print("❌ Source selection not working - still showing placeholder text")
                else:
                    print("❌ Could not find AI commentary elements")
            else:
                print("❌ Could not find radio button")
        else:
            print("❌ No download items found")

        # Take screenshot
        page.screenshot(path="/tmp/source_selection_test.png")
        print("Screenshot saved to /tmp/source_selection_test.png")

        browser.close()

if __name__ == "__main__":
    test_source_selection()