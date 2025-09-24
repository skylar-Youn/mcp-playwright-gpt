from playwright.sync_api import sync_playwright
import time

def test_edit_save_behavior():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, slow_mo=1000)
        page = browser.new_page()

        try:
            # Go to the translator page
            page.goto("http://localhost:8000/translator")
            page.wait_for_load_state('networkidle')

            print("=== Testing Edit/Save Button Behavior ===")

            # Wait for page to load
            time.sleep(2)

            # Check for any existing projects or create one
            segments = page.locator('.segment-item')
            segment_count = segments.count()

            if segment_count == 0:
                print("No segments found. Page is showing creation view.")

                # Look for download items to select
                download_radios = page.locator('input[name="source"]')
                radio_count = download_radios.count()
                print(f"Found {radio_count} download options")

                if radio_count > 0:
                    # Select first option
                    download_radios.first.click()
                    print("Selected first download option")

                    # Fill and submit form
                    page.wait_for_selector('#creation-form')
                    page.locator('#creation-form button[type="submit"]').click()
                    print("Submitted creation form")

                    # Wait for redirect/project creation
                    page.wait_for_timeout(5000)

                    # Check again for segments
                    segments = page.locator('.segment-item')
                    segment_count = segments.count()
                    print(f"After creation, found {segment_count} segments")

            if segment_count > 0:
                print(f"Found {segment_count} segments to test")

                # Test the first segment's first edit button
                first_segment = segments.first
                edit_buttons = first_segment.locator('.btn-edit-text')
                edit_count = edit_buttons.count()

                print(f"Found {edit_count} edit buttons in first segment")

                if edit_count > 0:
                    first_edit_btn = edit_buttons.first

                    # Get initial button text
                    initial_text = first_edit_btn.text_content()
                    print(f"Initial button text: '{initial_text}'")

                    # Take screenshot before clicking
                    page.screenshot(path="/home/sk/ws/mcp-playwright/before_edit_click.png")
                    print("Before click screenshot saved")

                    # Click the edit button
                    first_edit_btn.click()
                    time.sleep(1)

                    # Get button text after click
                    after_click_text = first_edit_btn.text_content()
                    print(f"After click button text: '{after_click_text}'")

                    # Take screenshot after clicking
                    page.screenshot(path="/home/sk/ws/mcp-playwright/after_edit_click.png")
                    print("After click screenshot saved")

                    # Check if input field is now visible
                    text_edit = first_segment.locator('.text-edit').first
                    is_input_visible = text_edit.is_visible()
                    print(f"Text input visible: {is_input_visible}")

                    if after_click_text == "저장" and is_input_visible:
                        print("✓ SUCCESS: Edit mode activated - Save button is now visible!")

                        # Test the save functionality
                        current_value = text_edit.input_value()
                        print(f"Current input value: '{current_value}'")

                        # Modify text
                        new_text = current_value + " [테스트 수정]"
                        text_edit.fill(new_text)
                        print(f"Modified text to: '{new_text}'")

                        # Click save
                        first_edit_btn.click()
                        print("Clicked save button")

                        # Wait and check result
                        time.sleep(3)
                        final_text = first_edit_btn.text_content()
                        print(f"Final button text: '{final_text}'")

                        # Take final screenshot
                        page.screenshot(path="/home/sk/ws/mcp-playwright/after_save_click.png")
                        print("After save screenshot saved")

                    else:
                        print(f"✗ ISSUE: Button should show '저장' but shows '{after_click_text}', input visible: {is_input_visible}")

            else:
                print("No segments available to test")

            time.sleep(5)  # Keep browser open for observation

        except Exception as e:
            print(f"Error during test: {e}")
            page.screenshot(path="/home/sk/ws/mcp-playwright/error_edit_test.png")

        finally:
            browser.close()

if __name__ == "__main__":
    test_edit_save_behavior()