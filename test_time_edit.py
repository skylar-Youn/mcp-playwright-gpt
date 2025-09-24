from playwright.sync_api import sync_playwright
import time

def test_time_edit():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, slow_mo=800)
        page = browser.new_page()

        try:
            print("=== Testing Time Edit Functionality ===")

            # Navigate with cache busting
            cache_buster = int(time.time() * 1000)
            page.goto(f"http://localhost:8000/translator?cb={cache_buster}")
            page.wait_for_load_state('networkidle')
            time.sleep(2)

            # Check for segments
            segments = page.locator('.segment-item')
            segment_count = segments.count()
            print(f"Found {segment_count} segments")

            if segment_count == 0:
                # Create project first
                print("Creating new project...")
                download_radios = page.locator('input[name="source"]')
                if download_radios.count() > 0:
                    download_radios.first.click()
                    page.locator('#creation-form button[type="submit"]').click()
                    page.wait_for_timeout(5000)

                    segments = page.locator('.segment-item')
                    segment_count = segments.count()
                    print(f"After creation: {segment_count} segments")

            if segment_count > 0:
                first_segment = segments.first

                # Find the time display
                time_display = first_segment.locator('.time-display')
                if time_display.count() > 0:
                    original_time = time_display.text_content()
                    print(f"Original time: '{original_time}'")

                    # Take screenshot before edit
                    page.screenshot(path="/home/sk/ws/mcp-playwright/before_time_edit.png")

                    # Click on time to edit
                    print("Clicking on time display...")
                    time_display.click()
                    time.sleep(1)

                    # Check if edit inputs appeared
                    time_edit = first_segment.locator('.time-edit')
                    if time_edit.is_visible():
                        print("✅ Time edit mode activated!")

                        # Get input fields
                        start_input = time_edit.locator('.start-input')
                        end_input = time_edit.locator('.end-input')

                        original_start = start_input.input_value()
                        original_end = end_input.input_value()
                        print(f"Original values: start={original_start}, end={original_end}")

                        # Modify the times
                        new_start = str(float(original_start) + 0.5)
                        new_end = str(float(original_end) + 0.5)

                        print(f"Changing to: start={new_start}, end={new_end}")
                        start_input.fill(new_start)
                        end_input.fill(new_end)

                        # Click save
                        save_button = time_edit.locator('.btn-save-time')
                        print("Clicking save button...")
                        save_button.click()

                        # Wait for save to complete
                        time.sleep(3)

                        # Check if time display was updated
                        updated_time = time_display.text_content()
                        print(f"Updated time: '{updated_time}'")

                        # Take screenshot after save
                        page.screenshot(path="/home/sk/ws/mcp-playwright/after_time_edit.png")

                        if new_start in updated_time and new_end in updated_time:
                            print("✅ SUCCESS: Time was updated successfully!")
                        else:
                            print("❌ Time display not updated correctly")

                    else:
                        print("❌ Time edit mode did not activate")

                        # Debug: check what happened
                        page.screenshot(path="/home/sk/ws/mcp-playwright/debug_time_edit.png")
                        print("Debug screenshot saved")

                else:
                    print("❌ No time display found")

            time.sleep(5)  # Keep browser open for inspection

        except Exception as e:
            print(f"Error: {e}")
            page.screenshot(path="/home/sk/ws/mcp-playwright/error_time_edit.png")

        finally:
            browser.close()

if __name__ == "__main__":
    test_time_edit()