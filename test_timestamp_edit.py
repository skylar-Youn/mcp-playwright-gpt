from playwright.sync_api import sync_playwright
import time

def test_timestamp_edit():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, slow_mo=1000)
        page = browser.new_page()

        try:
            print("=== Testing Timestamp Edit Feature ===")

            # Navigate with cache buster
            cache_buster = int(time.time() * 1000)
            page.goto(f"http://localhost:8000/translator?cb={cache_buster}")
            page.wait_for_load_state('networkidle')

            # Wait for content
            time.sleep(2)

            # Check for segments
            segments = page.locator('.segment-item')
            segment_count = segments.count()
            print(f"Found {segment_count} segments")

            if segment_count == 0:
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
                # Test with first segment
                first_segment = segments.first

                # Look for time display
                time_displays = first_segment.locator('.time-display')
                time_display_count = time_displays.count()
                print(f"Found {time_display_count} time displays")

                if time_display_count > 0:
                    # Take before screenshot
                    page.screenshot(path="/home/sk/ws/mcp-playwright/before_timestamp_edit.png")
                    print("Before timestamp edit screenshot taken")

                    first_time_display = time_displays.first

                    # Get current time text
                    current_time_text = first_time_display.text_content()
                    print(f"Current timestamp: '{current_time_text}'")

                    # Click to edit
                    print("Clicking timestamp to edit...")
                    first_time_display.click()
                    time.sleep(1)

                    # Look for edit inputs
                    time_edit_div = first_segment.locator('.time-edit').first
                    if time_edit_div.is_visible():
                        print("✓ Time edit interface is visible")

                        start_input = time_edit_div.locator('.start-input')
                        end_input = time_edit_div.locator('.end-input')

                        start_value = start_input.input_value()
                        end_value = end_input.input_value()
                        print(f"Current values - Start: {start_value}s, End: {end_value}s")

                        # Modify values slightly
                        new_start = float(start_value) + 0.1
                        new_end = float(end_value) + 0.2

                        start_input.fill(str(new_start))
                        end_input.fill(str(new_end))
                        print(f"Modified to - Start: {new_start}s, End: {new_end}s")

                        # Take during edit screenshot
                        page.screenshot(path="/home/sk/ws/mcp-playwright/during_timestamp_edit.png")
                        print("During edit screenshot taken")

                        # Try to save (will fail without backend API, but we can see UI)
                        save_btn = time_edit_div.locator('.btn-save-time')
                        if save_btn.is_visible():
                            print("Clicking save button...")
                            save_btn.click()
                            time.sleep(2)

                            # Check if any changes occurred
                            final_time_text = first_time_display.text_content()
                            print(f"Final timestamp: '{final_time_text}'")

                        # Take final screenshot
                        page.screenshot(path="/home/sk/ws/mcp-playwright/after_timestamp_edit.png")
                        print("After timestamp edit screenshot taken")

                    else:
                        print("❌ Time edit interface not visible")

                        # Debug: check what happened
                        html_content = first_segment.inner_html()
                        print("Segment HTML snippet:")
                        print(html_content[:500] + "...")

            time.sleep(5)  # Keep browser open

        except Exception as e:
            print(f"Error: {e}")
            page.screenshot(path="/home/sk/ws/mcp-playwright/error_timestamp_edit.png")

        finally:
            browser.close()

if __name__ == "__main__":
    test_timestamp_edit()