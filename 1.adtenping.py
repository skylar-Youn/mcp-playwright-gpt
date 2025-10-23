#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from playwright.sync_api import sync_playwright
import json
import pandas as pd


def scrape_campaign_list():
    """
    https://tenping.kr/Home/List 페이지에서 캠페인 목록을 스크래핑
    """
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        try:
            # 페이지 로드
            page.goto('https://tenping.kr/Home/List?Campaign_Category=0&CampaignType=578&FavoriteStatus=8702', wait_until='networkidle')

            # 동적 콘텐츠 로딩 대기
            page.wait_for_timeout(2000)

            # 캠페인 목록 가져오기
            campaigns = []

            # 캠페인 리스트 아이템 찾기
            campaign_items = page.locator('#campaign-list li').all()

            for item in campaign_items:
                try:
                    campaign_data = {}

                    # 전체 텍스트 가져오기
                    full_text = item.inner_text()

                    # "참여" 타입만 수집
                    if not full_text.startswith("참여"):
                        continue

                    # 텍스트를 줄 단위로 분리
                    lines = [line.strip() for line in full_text.split('\n') if line.strip()]

                    if len(lines) < 3:
                        continue

                    # 첫 번째 줄 파싱: "참여 리빙 2025 메가주 일산(하)"
                    first_line_parts = lines[0].split(None, 2)  # 최대 3개로 분리
                    if len(first_line_parts) >= 3:
                        campaign_data['campaign_type'] = first_line_parts[0]  # "참여"
                        campaign_data['category'] = first_line_parts[1]  # "리빙"
                        campaign_data['title'] = first_line_parts[2]  # "2025 메가주 일산(하)"
                    elif len(first_line_parts) == 2:
                        campaign_data['campaign_type'] = first_line_parts[0]
                        campaign_data['title'] = first_line_parts[1]

                    # 두 번째 줄: 설명
                    if len(lines) > 1 and not lines[1].startswith("오늘 단가"):
                        campaign_data['description'] = lines[1]

                    # 오늘 단가 및 잔여 건수 찾기
                    for line in lines:
                        if "오늘 단가" in line:
                            # "오늘 단가 2,200원  오늘 잔여 880건" 또는 "오늘 단가 24,000원  잔여 무제한"
                            if "오늘 잔여" in line:
                                parts = line.split("오늘 잔여")
                                price_part = parts[0].replace("오늘 단가", "").strip()
                                remaining_part = parts[1].strip()
                                campaign_data['price'] = price_part
                                campaign_data['remaining'] = remaining_part
                            elif "잔여 무제한" in line:
                                parts = line.split("잔여 무제한")
                                price_part = parts[0].replace("오늘 단가", "").strip()
                                campaign_data['price'] = price_part
                                campaign_data['remaining'] = "무제한"

                    # 이미지 URL
                    img = item.locator('img').first
                    if img.count() > 0:
                        img_src = img.get_attribute('src')
                        # 상대 경로를 절대 경로로 변환
                        if img_src:
                            if img_src.startswith('//'):
                                img_src = 'https:' + img_src
                            elif img_src.startswith('/'):
                                img_src = 'https://tenping.kr' + img_src
                            campaign_data['image_url'] = img_src

                    # 링크 URL (소문정보, 랜딩페이지)
                    links = item.locator('a').all()
                    for link in links:
                        link_text = link.inner_text().strip()
                        href = link.get_attribute('href')
                        if "소문정보" in link_text or "소문 정보" in link_text:
                            if href:
                                campaign_data['info_url'] = href
                        elif "랜딩페이지" in link_text:
                            if href:
                                campaign_data['landing_url'] = href

                    # 데이터가 있는 항목만 추가
                    if 'title' in campaign_data:
                        campaigns.append(campaign_data)

                except Exception as e:
                    continue

            # 중복 제거 (이미지 URL 기준)
            seen = set()
            unique_campaigns = []
            for campaign in campaigns:
                if 'image_url' in campaign:
                    if campaign['image_url'] not in seen:
                        seen.add(campaign['image_url'])
                        unique_campaigns.append(campaign)
                elif 'title' in campaign:
                    if campaign['title'] not in seen:
                        seen.add(campaign['title'])
                        unique_campaigns.append(campaign)

            return unique_campaigns

        except Exception as e:
            print(f"페이지 로드 오류: {e}")
            return []

        finally:
            browser.close()


def main():
    print("텐핑 캠페인 목록 스크래핑 시작...")
    campaigns = scrape_campaign_list()

    print(f"\n총 {len(campaigns)}개의 캠페인을 찾았습니다.\n")

    # JSON 형식으로 출력
    print(json.dumps(campaigns, ensure_ascii=False, indent=2))

    # JSON 파일로 저장
    with open('adtenping_campaigns.json', 'w', encoding='utf-8') as f:
        json.dump(campaigns, f, ensure_ascii=False, indent=2)

    print("\n결과가 'adtenping_campaigns.json' 파일로 저장되었습니다.")

    # 엑셀 파일로 저장
    if campaigns:
        df = pd.DataFrame(campaigns)
        excel_filename = 'adtenping_campaigns.xlsx'
        df.to_excel(excel_filename, index=False, engine='openpyxl')
        print(f"결과가 '{excel_filename}' 파일로도 저장되었습니다.")


if __name__ == "__main__":
    main()
