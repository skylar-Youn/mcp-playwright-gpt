from playwright.sync_api import sync_playwright
import time

def test_video_edit_button():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()

        try:
            # 대시보드 페이지 로드
            page.goto("http://localhost:8000")
            page.wait_for_load_state('networkidle')

            # 콘솔 로그 캐치
            page.on("console", lambda msg: print(f"Console: {msg.text}"))

            # 프로젝트 카드 요소들 확인
            project_cards = page.locator('.project-card')
            count = project_cards.count()
            print(f"Found {count} project cards")

            # 각 프로젝트 카드 검사
            for i in range(count):
                card = project_cards.nth(i)

                # 카드가 보이도록 스크롤
                card.scroll_into_view_if_needed()
                page.wait_for_timeout(500)  # 짧은 대기

                title = card.locator('h3').text_content()
                status = card.locator('.project-status').text_content()

                # 영상편집 버튼 확인
                video_edit_buttons = card.locator('.btn-video-edit')
                button_count = video_edit_buttons.count()

                print(f"Project {i+1}: {title}")
                print(f"Status: {status}")
                print(f"Video edit buttons: {button_count}")

                if button_count > 0:
                    button_text = video_edit_buttons.first.text_content()
                    print(f"Button text: {button_text}")
                    print("✓ 영상편집 버튼 발견!")

                    # 버튼 클릭 테스트
                    print("버튼 클릭 테스트...")
                    video_edit_buttons.first.click()
                    page.wait_for_timeout(2000)

                    # 모달이 열렸는지 확인
                    modal = page.locator('#video-editor-modal')
                    if modal.is_visible():
                        print("✓ 영상편집 모달이 열렸습니다!")

                        # 영상 선택 드롭다운 확인
                        video_select = page.locator('#video-file-select')
                        video_options = video_select.locator('option')
                        option_count = video_options.count()
                        print(f"영상 선택 옵션 수: {option_count}")

                        if option_count > 1:
                            print("✓ 영상 파일 목록이 로드되었습니다!")
                            for i in range(1, min(4, option_count)):  # 처음 3개 옵션 확인
                                option_text = video_options.nth(i).text_content()
                                print(f"  - {option_text}")
                        else:
                            print("✗ 영상 파일 목록이 비어있습니다.")

                        # 자막 미리보기 확인
                        subtitle_preview = page.locator('#subtitle-preview')
                        subtitle_text = subtitle_preview.text_content().strip()
                        print(f"자막 미리보기 길이: {len(subtitle_text)} 글자")

                        if len(subtitle_text) > 10:
                            print("✓ 자막 미리보기가 로드되었습니다!")
                            print(f"자막 미리보기: {subtitle_text[:100]}...")
                        else:
                            print("✗ 자막 미리보기가 비어있습니다.")

                        # 모달 닫기
                        page.locator('.modal-close').click()
                    else:
                        print("✗ 영상편집 모달이 열리지 않았습니다.")

                else:
                    print("✗ 영상편집 버튼 없음")
                print("-" * 50)

            # 페이지 소스 확인 (btn-video-edit 포함 여부)
            html = page.content()
            if 'btn-video-edit' in html:
                print("✓ HTML에 btn-video-edit 클래스 존재")
            else:
                print("✗ HTML에 btn-video-edit 클래스 없음")

            # 스크린샷 촬영
            page.screenshot(path="/home/sk/ws/mcp-playwright/dashboard_screenshot.png")
            print("스크린샷 저장: dashboard_screenshot.png")

            time.sleep(2)

        except Exception as e:
            print(f"Error: {e}")
            page.screenshot(path="/home/sk/ws/mcp-playwright/error_screenshot.png")
        finally:
            browser.close()

if __name__ == "__main__":
    test_video_edit_button()