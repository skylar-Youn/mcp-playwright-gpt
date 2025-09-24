from playwright.sync_api import sync_playwright
import time

def test_save_timestamp():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, slow_mo=500)
        page = browser.new_page()

        try:
            print("=== Testing Save Timestamp Display ===")

            # Navigate to translator page with cache busting
            cache_buster = int(time.time() * 1000)
            page.goto(f"http://localhost:8000/translator?cb={cache_buster}")
            page.wait_for_load_state('networkidle')

            # Wait for content to load
            time.sleep(2)

            # Check for existing segments
            segments = page.locator('.segment-item')
            segment_count = segments.count()
            print(f"Found {segment_count} segments")

            if segment_count == 0:
                # Create a project first
                print("Creating new project...")
                download_radios = page.locator('input[name="source"]')
                if download_radios.count() > 0:
                    download_radios.first.click()
                    page.locator('#creation-form button[type="submit"]').click()
                    page.wait_for_timeout(5000)

                    # Refresh segment count
                    segments = page.locator('.segment-item')
                    segment_count = segments.count()
                    print(f"After creation: {segment_count} segments")

            if segment_count > 0:
                # Test with first segment
                first_segment = segments.first

                # Look for last-modified elements
                last_modified_elements = first_segment.locator('.last-modified')
                last_modified_count = last_modified_elements.count()
                print(f"Found {last_modified_count} last-modified elements in first segment")

                # Test first edit button
                edit_buttons = first_segment.locator('.btn-edit-text')
                if edit_buttons.count() > 0:
                    first_edit_btn = edit_buttons.first
                    text_content_div = first_edit_btn.locator('..').locator('..')  # Get parent text-content div

                    print("Before edit - taking screenshot...")
                    page.screenshot(path="/home/sk/ws/mcp-playwright/before_timestamp_test.png")

                    # Check initial state of last-modified div
                    last_modified = text_content_div.locator('.last-modified').first
                    initial_text = last_modified.text_content()
                    print(f"Initial last-modified text: '{initial_text}'")

                    # Click edit
                    print("Clicking edit button...")
                    first_edit_btn.click()
                    time.sleep(1)

                    button_text = first_edit_btn.text_content()
                    print(f"After edit click, button text: '{button_text}'")

                    if button_text == "저장":
                        # Get the text input and modify it
                        text_input = text_content_div.locator('.text-edit').first
                        current_value = text_input.input_value()
                        new_value = current_value + " [타임스탬프 테스트]"

                        print(f"Changing text from '{current_value}' to '{new_value}'")
                        text_input.fill(new_value)

                        # Click save
                        print("Clicking save button...")
                        first_edit_btn.click()

                        # Wait for save to complete
                        time.sleep(3)

                        # Check final button text
                        final_button_text = first_edit_btn.text_content()
                        print(f"Final button text: '{final_button_text}'")

                        # Check if timestamp appeared
                        final_last_modified_text = last_modified.text_content()
                        print(f"Final last-modified text: '{final_last_modified_text}'")

                        # Take final screenshot
                        page.screenshot(path="/home/sk/ws/mcp-playwright/after_timestamp_test.png")
                        print("After save screenshot taken")

                        if "마지막 저장:" in final_last_modified_text:
                            print("✅ SUCCESS: Timestamp is now visible!")
                        else:
                            print("❌ ISSUE: Timestamp not visible")

                            # Debug: check HTML source
                            html_content = text_content_div.inner_html()
                            print("HTML content of text-content div:")
                            print(html_content)

                    else:
                        print(f"❌ Button didn't change to '저장', shows: '{button_text}'")

            time.sleep(5)  # Keep browser open for inspection

        except Exception as e:
            print(f"Error: {e}")
            page.screenshot(path="/home/sk/ws/mcp-playwright/error_timestamp_test.png")

        finally:
            browser.close()

if __name__ == "__main__":
    test_save_timestamp()