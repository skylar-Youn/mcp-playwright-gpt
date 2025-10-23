#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from playwright.sync_api import sync_playwright
import json
import pandas as pd
from datetime import datetime


def extract_keywords(title):
    """제목에서 주요 키워드 추출"""
    keywords = []

    # 주요 키워드 목록
    keyword_patterns = [
        '이사', '이삿짐', '포장이사', '용달', '원룸이사',
        '키성장', '성장판', '키크기', '성장',
        '과외', '학원', '교육', '공부방',
        '건강', '병원', '의원', '한의원', '침향',
        '홈페이지', '웹사이트', '랜딩페이지', '온라인',
        '렌탈', '대여', '구독',
        '비교', '견적', '상담',
        '비대면', '온라인상담'
    ]

    for keyword in keyword_patterns:
        if keyword in title:
            keywords.append(keyword)

    return ', '.join(keywords) if keywords else ''


def scrape_cpa_list():
    """
    https://dbsense.kr/pc/camp/camp_cpa.html 페이지에서 CPA 캠페인 목록을 스크래핑
    """
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        try:
            # 페이지 로드
            page.goto('https://dbsense.kr/pc/camp/camp_cpa.html', wait_until='networkidle')

            # 캠페인 카드 목록 가져오기
            campaigns = []

            # 전체 페이지의 텍스트 가져와서 확인
            page_content = page.content()

            # 캠페인 링크 요소들 찾기
            campaign_links = page.locator('a[href*="camp_view.html"]').all()

            for link in campaign_links:
                try:
                    campaign_data = {}

                    # 스크래핑 날짜/시간
                    campaign_data['scraped_at'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

                    # 캠페인 ID 추출
                    href = link.get_attribute('href')
                    if href and 'idx=' in href:
                        campaign_data['campaign_id'] = href.split('idx=')[1].split('&')[0]

                    # 링크의 전체 텍스트 가져오기
                    full_text = link.inner_text().strip()

                    # 이미지 URL
                    img = link.locator('img').first
                    if img.count() > 0:
                        img_src = img.get_attribute('src')
                        # 상대 경로를 절대 경로로 변환
                        if img_src and img_src.startswith('/'):
                            img_src = 'https://dbsense.kr' + img_src
                        campaign_data['image_url'] = img_src

                        # 이미지의 alt 속성에서 제목 가져오기
                        alt_text = img.get_attribute('alt')
                        if alt_text:
                            campaign_data['title'] = alt_text.strip()
                            campaign_data['keywords'] = extract_keywords(alt_text)

                    # 카테고리
                    category = link.locator('.category, [class*="category"]').first
                    if category.count() > 0:
                        campaign_data['category'] = category.inner_text().strip()

                    # 제목 (여러 방법으로 시도)
                    if 'title' not in campaign_data:
                        # 방법 1: .title 클래스
                        title = link.locator('.title, [class*="title"]').first
                        if title.count() > 0:
                            title_text = title.inner_text().strip()
                            campaign_data['title'] = title_text
                            campaign_data['keywords'] = extract_keywords(title_text)
                        # 방법 2: strong 태그
                        elif link.locator('strong').count() > 0:
                            title_text = link.locator('strong').first.inner_text().strip()
                            campaign_data['title'] = title_text
                            campaign_data['keywords'] = extract_keywords(title_text)
                        # 방법 3: 전체 텍스트에서 추출
                        elif full_text:
                            lines = full_text.split('\n')
                            for line in lines:
                                line = line.strip()
                                if line and 'CPA' not in line and '오늘잔여' not in line and '평균' not in line and '격려금' not in line:
                                    if line != campaign_data.get('category', ''):
                                        campaign_data['title'] = line
                                        campaign_data['keywords'] = extract_keywords(line)
                                        break

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


def scrape_cpc_list():
    """
    https://dbsense.kr/pc/camp/camp_cpc.html 페이지에서 CPC 캠페인 목록을 스크래핑
    """
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        try:
            # 페이지 로드
            page.goto('https://dbsense.kr/pc/camp/camp_cpc.html', wait_until='networkidle')

            # 캠페인 카드 목록 가져오기
            campaigns = []

            # 캠페인 링크 요소들 찾기
            campaign_links = page.locator('a[href*="camp_view.html"]').all()

            for link in campaign_links:
                try:
                    campaign_data = {}

                    # 스크래핑 날짜/시간
                    campaign_data['scraped_at'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

                    # 캠페인 ID 추출
                    href = link.get_attribute('href')
                    if href and 'idx=' in href:
                        campaign_data['campaign_id'] = href.split('idx=')[1].split('&')[0]

                    # 링크의 전체 텍스트 가져오기
                    full_text = link.inner_text().strip()

                    # 이미지 URL
                    img = link.locator('img').first
                    if img.count() > 0:
                        img_src = img.get_attribute('src')
                        # 상대 경로를 절대 경로로 변환
                        if img_src and img_src.startswith('/'):
                            img_src = 'https://dbsense.kr' + img_src
                        campaign_data['image_url'] = img_src

                        # 이미지의 alt 속성에서 제목 가져오기
                        alt_text = img.get_attribute('alt')
                        if alt_text:
                            campaign_data['title'] = alt_text.strip()
                            campaign_data['keywords'] = extract_keywords(alt_text)

                    # 카테고리
                    category = link.locator('.category, [class*="category"]').first
                    if category.count() > 0:
                        campaign_data['category'] = category.inner_text().strip()

                    # 제목 (여러 방법으로 시도)
                    if 'title' not in campaign_data:
                        # 방법 1: .title 클래스
                        title = link.locator('.title, [class*="title"]').first
                        if title.count() > 0:
                            title_text = title.inner_text().strip()
                            campaign_data['title'] = title_text
                            campaign_data['keywords'] = extract_keywords(title_text)
                        # 방법 2: strong 태그
                        elif link.locator('strong').count() > 0:
                            title_text = link.locator('strong').first.inner_text().strip()
                            campaign_data['title'] = title_text
                            campaign_data['keywords'] = extract_keywords(title_text)
                        # 방법 3: 전체 텍스트에서 추출
                        elif full_text:
                            lines = full_text.split('\n')
                            for line in lines:
                                line = line.strip()
                                if line and 'CPC' not in line and '오늘잔여' not in line and '평균' not in line:
                                    if line != campaign_data.get('category', ''):
                                        campaign_data['title'] = line
                                        campaign_data['keywords'] = extract_keywords(line)
                                        break

                    # CPC 가격
                    cpc_price = link.locator('text=/CPC\\s*[+\\d,]+원/').first
                    if cpc_price.count() > 0:
                        price_text = cpc_price.inner_text().strip()
                        campaign_data['cpc_price'] = price_text

                    # 오늘 잔여
                    remaining = link.locator('text=/오늘잔여\\s*\\d+/').first
                    if remaining.count() > 0:
                        campaign_data['remaining_today'] = remaining.inner_text().strip()

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
    import sys

    # 명령행 인수로 스크래핑 타입 선택 (기본값: both)
    scrape_type = sys.argv[1] if len(sys.argv) > 1 else 'both'

    cpa_campaigns = []
    cpc_campaigns = []

    if scrape_type in ['cpa', 'both']:
        print("CPA 캠페인 목록 스크래핑 시작...")
        cpa_campaigns = scrape_cpa_list()
        print(f"총 {len(cpa_campaigns)}개의 CPA 캠페인을 찾았습니다.\n")

    if scrape_type in ['cpc', 'both']:
        print("CPC 캠페인 목록 스크래핑 시작...")
        cpc_campaigns = scrape_cpc_list()
        print(f"총 {len(cpc_campaigns)}개의 CPC 캠페인을 찾았습니다.\n")

    # 날짜별 파일명 생성
    date_str = datetime.now().strftime('%Y%m%d_%H%M%S')

    # JSON 파일로 저장
    if cpa_campaigns:
        json_filename = f'cpa_campaigns_{date_str}.json'
        with open(json_filename, 'w', encoding='utf-8') as f:
            json.dump(cpa_campaigns, f, ensure_ascii=False, indent=2)
        print(f"CPA 결과가 '{json_filename}' 파일로 저장되었습니다.")

    if cpc_campaigns:
        json_filename = f'cpc_campaigns_{date_str}.json'
        with open(json_filename, 'w', encoding='utf-8') as f:
            json.dump(cpc_campaigns, f, ensure_ascii=False, indent=2)
        print(f"CPC 결과가 '{json_filename}' 파일로 저장되었습니다.")

    # 엑셀 파일로 저장 (CPA는 Sheet1, CPC는 Sheet2)
    excel_filename = f'campaigns_{date_str}.xlsx'
    with pd.ExcelWriter(excel_filename, engine='openpyxl') as writer:
        if cpa_campaigns:
            df_cpa = pd.DataFrame(cpa_campaigns)
            # 컬럼 순서 조정: 스크래핑 날짜, 키워드를 앞으로
            cols = ['scraped_at', 'keywords', 'title', 'category', 'campaign_id', 'cpa_price',
                    'avg_conversion_rate', 'remaining_today', 'incentive', 'image_url']
            cols = [c for c in cols if c in df_cpa.columns]
            df_cpa = df_cpa[cols]
            df_cpa.to_excel(writer, sheet_name='CPA', index=False)
            print(f"CPA 결과가 '{excel_filename}' 파일의 'CPA' 시트에 저장되었습니다.")

        if cpc_campaigns:
            df_cpc = pd.DataFrame(cpc_campaigns)
            # 컬럼 순서 조정: 스크래핑 날짜, 키워드를 앞으로
            cols = ['scraped_at', 'keywords', 'title', 'category', 'campaign_id', 'cpc_price',
                    'remaining_today', 'image_url']
            cols = [c for c in cols if c in df_cpc.columns]
            df_cpc = df_cpc[cols]
            df_cpc.to_excel(writer, sheet_name='CPC', index=False)
            print(f"CPC 결과가 '{excel_filename}' 파일의 'CPC' 시트에 저장되었습니다.")


if __name__ == "__main__":
    main()
