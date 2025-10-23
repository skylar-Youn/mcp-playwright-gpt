#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from playwright.sync_api import sync_playwright
import json
from datetime import datetime
import time
import os


CAMPAIGNS_FILE = 'saved_campaigns.json'


def load_saved_campaigns():
    """저장된 캠페인 목록 불러오기"""
    if os.path.exists(CAMPAIGNS_FILE):
        with open(CAMPAIGNS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return []


def save_campaign(campaign_info):
    """캠페인 정보 저장"""
    campaigns = load_saved_campaigns()

    # 중복 확인 (URL 기준)
    existing_urls = [c['url'] for c in campaigns]
    if campaign_info['url'] not in existing_urls:
        campaigns.append(campaign_info)
        with open(CAMPAIGNS_FILE, 'w', encoding='utf-8') as f:
            json.dump(campaigns, f, ensure_ascii=False, indent=2)
        print(f"✓ 캠페인이 저장되었습니다. (총 {len(campaigns)}개)")
    else:
        print("⚠ 이미 저장된 캠페인입니다.")


def select_campaign():
    """저장된 캠페인 선택 또는 새 캠페인 입력"""
    campaigns = load_saved_campaigns()

    if not campaigns:
        print("\n저장된 캠페인이 없습니다.")
        url = input("새 캠페인 URL을 입력하세요: ").strip()
        return url

    print("\n저장된 캠페인 목록:")
    print("="*80)
    for i, camp in enumerate(campaigns, 1):
        print(f"{i}. {camp.get('url', 'URL 없음')}")
        print(f"   저장 시간: {camp.get('scraped_at', 'N/A')}")
        if 'full_text' in camp:
            preview = camp['full_text'][:100].replace('\n', ' ')
            print(f"   미리보기: {preview}...")
        print("-"*80)

    print(f"{len(campaigns) + 1}. 새 캠페인 URL 입력")
    print("="*80)

    while True:
        try:
            choice = input(f"\n선택 (1-{len(campaigns) + 1}): ").strip()
            choice_num = int(choice)

            if 1 <= choice_num <= len(campaigns):
                selected = campaigns[choice_num - 1]
                print(f"\n선택된 캠페인: {selected['url']}")
                return selected['url']
            elif choice_num == len(campaigns) + 1:
                url = input("\n새 캠페인 URL을 입력하세요: ").strip()
                return url
            else:
                print(f"1부터 {len(campaigns) + 1} 사이의 숫자를 입력하세요.")
        except ValueError:
            print("올바른 숫자를 입력하세요.")


def fetch_campaign_details(campaign_url, use_existing_browser=True):
    """
    캠페인 상세 페이지에서 정보 추출 (기존 Chrome 디버깅 세션 사용)
    """
    with sync_playwright() as p:
        if use_existing_browser:
            try:
                # 기존에 열려있는 Chrome에 연결
                browser = p.chromium.connect_over_cdp("http://localhost:9222")
                print("✓ 기존 Chrome 브라우저에 연결되었습니다.")
            except Exception as e:
                print(f"⚠ 기존 Chrome 연결 실패: {e}")
                print("새 브라우저를 실행합니다...")
                browser = p.chromium.launch(headless=False)
        else:
            browser = p.chromium.launch(headless=False)

        # 새 컨텍스트 및 페이지 생성
        if use_existing_browser and browser.contexts:
            context = browser.contexts[0]
            page = context.new_page()
        else:
            context = browser.new_context()
            page = context.new_page()

        try:
            page.goto(campaign_url, wait_until='networkidle')
            time.sleep(2)

            # 페이지의 전체 텍스트 가져오기
            full_text = page.inner_text('body')

            # 캠페인 정보 추출
            campaign_info = {
                'url': campaign_url,
                'scraped_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'full_text': full_text
            }

            print("\n캠페인 페이지 내용:")
            print("="*80)
            print(full_text[:500] + "..." if len(full_text) > 500 else full_text)
            print("="*80)

            # 캠페인 정보 저장
            save_campaign(campaign_info)

            return campaign_info

        except Exception as e:
            print(f"페이지 로드 오류: {e}")
            return None

        finally:
            # 연결 모드에서는 브라우저를 닫지 않음
            if not use_existing_browser:
                browser.close()
            else:
                page.close()


def open_chatgpt_and_send_prompt(campaign_info, use_existing_browser=True):
    """
    ChatGPT 웹사이트를 열고 DevTools를 통해 프롬프트 전송 (기존 Chrome 사용)
    """
    with sync_playwright() as p:
        if use_existing_browser:
            try:
                browser = p.chromium.connect_over_cdp("http://localhost:9222")
                print("✓ 기존 Chrome 브라우저에 연결되었습니다.")
                context = browser.contexts[0] if browser.contexts else browser.new_context()
                page = context.new_page()
            except Exception as e:
                print(f"⚠ 기존 Chrome 연결 실패: {e}")
                browser = p.chromium.launch(headless=False, args=['--auto-open-devtools-for-tabs'])
                context = browser.new_context()
                page = context.new_page()
        else:
            browser = p.chromium.launch(headless=False, args=['--auto-open-devtools-for-tabs'])
            context = browser.new_context()
            page = context.new_page()

        try:
            # ChatGPT 웹사이트 열기
            print("\nChatGPT 웹사이트를 여는 중...")
            page.goto('https://chatgpt.com/', wait_until='networkidle')
            time.sleep(3)

            # 광고 콘텐츠 생성을 위한 프롬프트 (간단하게)
            prompt = f"""당근마켓 광고 제목 5개와 간단한 소개를 작성해주세요.

캠페인 정보:
{campaign_info.get('full_text', '')[:500]}

출력 형식:
제목1: (예: 인터넷 바꾸면 48만원 드립니다)
제목2:
제목3:
제목4:
제목5:

간단한 소개:
(2-3문장으로 혜택 설명)"""

            print("\n" + "="*80)
            print("ChatGPT에 전송할 프롬프트:")
            print("="*80)
            print(prompt)
            print("="*80)

            # 프롬프트 자동 입력 시도
            try:
                # 입력 필드 대기
                textarea = page.locator('textarea[name="prompt-textarea"]').first
                textarea.wait_for(timeout=10000)

                # 입력 필드에 포커스
                textarea.focus()
                time.sleep(0.5)

                # 프롬프트 입력
                textarea.fill(prompt)
                time.sleep(0.5)

                print("\n✓ 프롬프트가 자동으로 입력되었습니다!")

                # 전송 버튼 찾아서 클릭 시도
                send_button = page.locator('button[data-testid="send-button"]').first
                if send_button.count() > 0:
                    send_button.click()
                    print("✓ 전송 버튼을 클릭했습니다!")
                else:
                    print("\n전송 버튼을 수동으로 클릭하거나 Enter를 눌러주세요.")

            except Exception as e:
                print(f"\n⚠ 자동 입력 실패: {e}")
                print("\n수동으로 다음 내용을 복사하여 ChatGPT에 입력해주세요:")
                print("-" * 80)
                print(prompt)
                print("-" * 80)

            print("\nChatGPT의 응답을 기다리는 중...")
            input("\nChatGPT 응답 확인 후 Enter를 누르세요...")

            return True

        except Exception as e:
            print(f"ChatGPT 페이지 오류: {e}")
            return False

        finally:
            if not use_existing_browser:
                input("\n브라우저를 닫으려면 Enter를 누르세요...")
                browser.close()
            else:
                input("\n탭을 닫으려면 Enter를 누르세요...")
                page.close()


def automate_daangn_post(use_existing_browser=True):
    """
    당근마켓에 자동으로 광고 게시 (기존 Chrome 사용)
    """
    with sync_playwright() as p:
        if use_existing_browser:
            try:
                browser = p.chromium.connect_over_cdp("http://localhost:9222")
                print("✓ 기존 Chrome 브라우저에 연결되었습니다.")
                context = browser.contexts[0] if browser.contexts else browser.new_context()
                page = context.new_page()
            except Exception as e:
                print(f"⚠ 기존 Chrome 연결 실패: {e}")
                browser = p.chromium.launch(headless=False, args=['--auto-open-devtools-for-tabs'])
                context = browser.new_context()
                page = context.new_page()
        else:
            browser = p.chromium.launch(headless=False, args=['--auto-open-devtools-for-tabs'])
            context = browser.new_context()
            page = context.new_page()

        try:
            # 당근마켓 접속
            page.goto('https://www.daangn.com', wait_until='networkidle')

            print("\n당근마켓 로그인을 수동으로 진행해주세요.")
            input("로그인 완료 후 Enter를 누르세요...")

            print("\n광고를 게시할 준비가 되었습니다.")
            print("ChatGPT에서 생성된 콘텐츠를 복사하여 당근마켓에 게시하세요.")

            input("\n게시 완료 후 Enter를 누르세요...")

            return True

        except Exception as e:
            print(f"당근마켓 게시 오류: {e}")
            return False

        finally:
            if not use_existing_browser:
                browser.close()
            else:
                page.close()


def main():
    import sys

    print("="*80)
    print("당근마켓 광고 자동화 프로그램")
    print("="*80)
    print("\n⚠ 먼저 다음 명령으로 Chrome을 실행하세요:")
    print('google-chrome --remote-debugging-port=9222 --user-data-dir="$HOME/ChromeDebugData"')
    print("="*80)

    # 명령행 인수로 URL이 제공되지 않으면 저장된 캠페인 선택 또는 새 URL 입력
    if len(sys.argv) >= 2:
        campaign_url = sys.argv[1]
    else:
        campaign_url = select_campaign()

        if not campaign_url:
            print("URL이 입력되지 않았습니다. 프로그램을 종료합니다.")
            return

    # 1단계: 캠페인 정보 수집
    print("\n" + "="*80)
    print("1단계: 캠페인 정보 수집 중...")
    print("="*80)
    campaign_info = fetch_campaign_details(campaign_url, use_existing_browser=True)

    if not campaign_info:
        print("캠페인 정보를 가져오지 못했습니다.")
        return

    # 캠페인 정보 저장
    filename = f'campaign_info_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json'
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(campaign_info, f, ensure_ascii=False, indent=2)
    print(f"\n캠페인 정보가 '{filename}' 파일로 저장되었습니다.")

    # 2단계: ChatGPT 웹사이트 열고 프롬프트 전송
    print("\n" + "="*80)
    print("2단계: ChatGPT에서 광고 콘텐츠 생성")
    print("="*80)

    proceed = input("\nChatGPT 웹사이트를 열어 광고 콘텐츠를 생성하시겠습니까? (y/n): ")
    if proceed.lower() == 'y':
        open_chatgpt_and_send_prompt(campaign_info)

    # 3단계: 당근마켓에 게시 (선택사항)
    print("\n" + "="*80)
    print("3단계: 당근마켓에 광고 게시")
    print("="*80)

    proceed = input("\n당근마켓에 게시하시겠습니까? (y/n): ")
    if proceed.lower() == 'y':
        automate_daangn_post()


if __name__ == "__main__":
    main()
