#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from playwright.sync_api import sync_playwright
import json
import pandas as pd


def scrape_cpa_list():
    """
    https://adpot.kr/pc/camp/camp_cpa.html 페이지에서 CPA 캠페인 목록을 스크래핑
    """
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        try:
            # 페이지 로드
            page.goto('https://adpot.kr/pc/camp/camp_cpa.html', wait_until='networkidle')

            # 캠페인 카드 목록 가져오기
            campaigns = []

            # 캠페인 링크 요소들 찾기
            campaign_links = page.locator('a[href*="camp_view.html"]').all()

            for link in campaign_links:
                try:
                    campaign_data = {}

                    # 캠페인 ID 추출
                    href = link.get_attribute('href')
                    if href and 'idx=' in href:
                        campaign_data['campaign_id'] = href.split('idx=')[1].split('&')[0]

                    # 이미지 URL
                    img = link.locator('img').first
                    if img.count() > 0:
                        img_src = img.get_attribute('src')
                        # 상대 경로를 절대 경로로 변환
                        if img_src and img_src.startswith('/'):
                            img_src = 'https://adpot.kr' + img_src
                        campaign_data['image_url'] = img_src

                    # 카테고리
                    category = link.locator('.category, [class*="category"]').first
                    if category.count() > 0:
                        campaign_data['category'] = category.inner_text().strip()

                    # 제목
                    title = link.locator('.title, [class*="title"]').first
                    if title.count() > 0:
                        campaign_data['title'] = title.inner_text().strip()

                    # CPA 가격
                    cpa_price = link.locator('text=/CPA\\s*[\\d,]+원/').first
                    if cpa_price.count() > 0:
                        price_text = cpa_price.inner_text().strip()
                        campaign_data['cpa_price'] = price_text

                    # 평균 전환율
                    conversion = link.locator('text=/\\[평균\\s*\\d+%\\]/').first
                    if conversion.count() > 0:
                        campaign_data['avg_conversion_rate'] = conversion.inner_text().strip()

                    # 오늘 잔여
                    remaining = link.locator('text=/오늘잔여\\s*\\d+/').first
                    if remaining.count() > 0:
                        campaign_data['remaining_today'] = remaining.inner_text().strip()

                    # 격려금
                    incentive = link.locator('text=/격려금/').first
                    if incentive.count() > 0:
                        campaign_data['incentive'] = incentive.inner_text().strip()

                    campaigns.append(campaign_data)

                except Exception as e:
                    print(f"개별 캠페인 파싱 오류: {e}")
                    continue

            return campaigns

        except Exception as e:
            print(f"페이지 로드 오류: {e}")
            return []

        finally:
            browser.close()


def main():
    print("ADPOT CPA 캠페인 목록 스크래핑 시작...")
    campaigns = scrape_cpa_list()

    print(f"\n총 {len(campaigns)}개의 캠페인을 찾았습니다.\n")

    # JSON 형식으로 출력
    print(json.dumps(campaigns, ensure_ascii=False, indent=2))

    # JSON 파일로 저장
    with open('adpot_cpa_campaigns.json', 'w', encoding='utf-8') as f:
        json.dump(campaigns, f, ensure_ascii=False, indent=2)

    print("\n결과가 'adpot_cpa_campaigns.json' 파일로 저장되었습니다.")

    # 엑셀 파일로 저장
    if campaigns:
        df = pd.DataFrame(campaigns)
        excel_filename = 'adpot_cpa_campaigns.xlsx'
        df.to_excel(excel_filename, index=False, engine='openpyxl')
        print(f"결과가 '{excel_filename}' 파일로도 저장되었습니다.")


if __name__ == "__main__":
    main()
