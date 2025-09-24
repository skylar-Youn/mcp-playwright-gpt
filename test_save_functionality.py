from playwright.sync_api import sync_playwright
import time

def test_save_functionality():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()

        try:
            # Navigate to translator page with a project
            page.goto("http://localhost:8000/translator")
            page.wait_for_load_state('networkidle')

            # Wait a bit for content to load
            time.sleep(2)

            # Check if we're on project view (has segments)
            segments = page.locator('.segment-item')
            segment_count = segments.count()
            print(f"Found {segment_count} segments")

            if segment_count > 0:
                # Look at first segment
                first_segment = segments.first

                # Find edit buttons
                edit_buttons = first_segment.locator('.btn-edit-text')
                edit_count = edit_buttons.count()
                print(f"Found {edit_count} edit buttons in first segment")

                if edit_count > 0:
                    # Test the first edit button
                    first_edit_btn = edit_buttons.first
                    button_text = first_edit_btn.text_content()
                    print(f"First edit button text: '{button_text}'")

                    # Click the edit button
                    first_edit_btn.click()
                    time.sleep(1)

                    # Check if button text changed to "저장"
                    new_button_text = first_edit_btn.text_content()
                    print(f"After click, button text: '{new_button_text}'")

                    if new_button_text == "저장":
                        print("✓ Edit mode activated - Save button visible!")

                        # Check if input field is visible
                        text_edit = first_segment.locator('.text-edit').first
                        if text_edit.is_visible():
                            print("✓ Text input field is visible")

                            # Modify the text
                            current_value = text_edit.input_value()
                            print(f"Current text: '{current_value}'")

                            new_text = current_value + " [수정됨]"
                            text_edit.fill(new_text)

                            # Click save
                            first_edit_btn.click()
                            print("Clicked save button...")

                            # Wait for save to complete
                            time.sleep(3)

                            final_button_text = first_edit_btn.text_content()
                            print(f"Final button text: '{final_button_text}'")

                        else:
                            print("✗ Text input field is not visible")
                    else:
                        print("✗ Button did not change to '저장'")
                else:
                    print("✗ No edit buttons found")
            else:
                print("No segments found - might be on creation view")

            # Take screenshot
            page.screenshot(path="/home/sk/ws/mcp-playwright/save_test_screenshot.png")
            print("Screenshot saved: save_test_screenshot.png")

            time.sleep(3)

        except Exception as e:
            print(f"Error: {e}")
            page.screenshot(path="/home/sk/ws/mcp-playwright/error_save_test.png")
        finally:
            browser.close()

if __name__ == "__main__":
    test_save_functionality()