#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from playwright.sync_api import sync_playwright
import json
import pandas as pd
from datetime import datetime
import re


def clean_text(text):
    """텍스트 정리 - 특수문자 제거, 공백 정리"""
    if not text:
        return ""
    # 여러 공백을 하나로
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


def is_shorts_suitable(title, content=""):
    """
    쇼츠 제작에 적합한 주제인지 판단

    적합 기준:
    - 흥미로운 이슈 (논란, 화제)
    - 시각적 표현 가능 (사진/영상 관련)
    - 감정적 반응 유발 (웃김, 감동, 놀라움)
    - 정보성 (꿀팁, 신기한 사실)
    """

    # 제외할 키워드 (광고성, 스팸성, 민감한 정치 등)
    exclude_keywords = [
        '광고', '홍보', '구매', '판매', '알바', '모집',
        '혐오', '비하', '욕설', '선정적'
    ]

    # 포함하면 좋은 키워드 (쇼츠 적합)
    include_keywords = [
        '썰', '후기', '레전드', '실화', 'ㄷㄷ', 'ㅋㅋ',
        '놀라운', '신기한', '대박', '충격', '화제',
        '최근', '요즘', '근황', 'TMI', '팁', '꿀팁',
        '반응', '인기', 'HOT', '베스트', '개념글',
        '사진', '영상', 'gif', '움짤'
    ]

    title_lower = title.lower()

    # 제외 키워드 체크
    for keyword in exclude_keywords:
        if keyword in title:
            return False

    # 포함 키워드 체크 (가중치)
    score = 0
    for keyword in include_keywords:
        if keyword in title or keyword in title_lower:
            score += 1

    # 이모티콘이나 특수문자가 많으면 감정 표현이 있다고 판단
    emoji_count = len(re.findall(r'[ㅋㅎㄷㄹㅇ!?]', title))
    if emoji_count >= 2:
        score += 1

    # 제목 길이가 적당하면 가산점
    if 10 <= len(title) <= 50:
        score += 1

    return score >= 2


def scrape_dcinside():
    """
    DC인사이드 개념글/실베 스크래핑
    """
    print("\n🔍 DC인사이드 스크래핑 시작...")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        issues = []

        try:
            # 메인 페이지 접속
            page.goto('https://gall.dcinside.com/', wait_until='networkidle', timeout=30000)
            page.wait_for_timeout(2000)

            # 개념글 제목 추출
            titles = page.locator('strong.tit').all()

            for idx, title_elem in enumerate(titles[:30]):  # 최대 30개
                try:
                    title = clean_text(title_elem.inner_text())

                    if not title or len(title) < 5:
                        continue

                    # 부모 요소에서 갤러리명과 날짜 찾기
                    parent = title_elem.locator('xpath=../..').first

                    gallery = ""
                    date = ""

                    # info div에서 갤러리명과 날짜 추출
                    info_divs = parent.locator('.info span').all()
                    if len(info_divs) >= 2:
                        gallery = clean_text(info_divs[0].inner_text())
                        date = clean_text(info_divs[1].inner_text())

                    # 링크 추출 (여러 방법 시도)
                    link = ""

                    # 방법 1: title을 포함한 a 태그 찾기
                    title_parent_link = title_elem.locator('xpath=ancestor::a').first
                    if title_parent_link.count() > 0:
                        href = title_parent_link.get_attribute('href')
                        if href:
                            if href.startswith('http'):
                                link = href
                            elif href.startswith('/'):
                                link = 'https://gall.dcinside.com' + href

                    # 방법 2: parent의 a 태그 찾기
                    if not link:
                        link_elem = parent.locator('a').first
                        if link_elem.count() > 0:
                            href = link_elem.get_attribute('href')
                            if href:
                                if href.startswith('http'):
                                    link = href
                                elif href.startswith('/'):
                                    link = 'https://gall.dcinside.com' + href

                    issue = {
                        'platform': 'DC인사이드',
                        'category': gallery,
                        'title': title,
                        'date': date,
                        'link': link,
                        'shorts_suitable': is_shorts_suitable(title),
                        'scraped_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    }

                    issues.append(issue)

                except Exception as e:
                    print(f"  ⚠️  개별 항목 파싱 오류: {e}")
                    continue

            print(f"✅ DC인사이드: {len(issues)}개 이슈 발견")

        except Exception as e:
            print(f"❌ DC인사이드 스크래핑 오류: {e}")

        finally:
            browser.close()

        return issues


def scrape_fmkorea():
    """
    FM Korea 베스트 게시물 스크래핑
    """
    print("\n🔍 FM Korea 스크래핑 시작...")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        issues = []

        try:
            # 베스트 페이지 접속
            page.goto('https://www.fmkorea.com/best', wait_until='networkidle', timeout=30000)
            page.wait_for_timeout(2000)

            # 게시물 목록 추출
            articles = page.locator('.li_best_wrapper, .fm_best_widget li, article').all()

            for idx, article in enumerate(articles[:30]):  # 최대 30개
                try:
                    # 제목 및 링크 추출 (여러 선택자 시도)
                    title = ""
                    link = ""
                    title_selectors = [
                        '.title a',
                        'a.hx',
                        '.hotdeal_title a',
                        'a[href*="/board/"]',
                        'a[href*="/hot/"]'
                    ]

                    title_link_elem = None
                    for selector in title_selectors:
                        elem = article.locator(selector).first
                        if elem.count() > 0:
                            title = clean_text(elem.inner_text())
                            if title and len(title) >= 5:
                                title_link_elem = elem
                                break

                    if not title or len(title) < 5:
                        continue

                    # 제목 요소에서 링크 추출
                    if title_link_elem:
                        href = title_link_elem.get_attribute('href')
                        if href:
                            if href.startswith('http'):
                                link = href
                            elif href.startswith('/'):
                                link = 'https://www.fmkorea.com' + href

                    # 링크가 없으면 article의 첫 번째 a 태그에서 추출
                    if not link:
                        link_elem = article.locator('a').first
                        if link_elem.count() > 0:
                            href = link_elem.get_attribute('href')
                            if href:
                                if href.startswith('http'):
                                    link = href
                                elif href.startswith('/'):
                                    link = 'https://www.fmkorea.com' + href

                    # 카테고리 추출
                    category = "베스트"
                    category_elem = article.locator('.category, .category_wrapper').first
                    if category_elem.count() > 0:
                        category = clean_text(category_elem.inner_text())

                    # 날짜 추출
                    date = ""
                    date_elem = article.locator('.date, .time, .regdate').first
                    if date_elem.count() > 0:
                        date = clean_text(date_elem.inner_text())

                    issue = {
                        'platform': 'FM Korea',
                        'category': category,
                        'title': title,
                        'date': date,
                        'link': link,
                        'shorts_suitable': is_shorts_suitable(title),
                        'scraped_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    }

                    issues.append(issue)

                except Exception as e:
                    print(f"  ⚠️  개별 항목 파싱 오류: {e}")
                    continue

            print(f"✅ FM Korea: {len(issues)}개 이슈 발견")

        except Exception as e:
            print(f"❌ FM Korea 스크래핑 오류: {e}")

        finally:
            browser.close()

        return issues


def scrape_natepann():
    """
    네이트 판 베스트 게시물 스크래핑
    """
    print("\n🔍 네이트 판 스크래핑 시작...")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        issues = []

        try:
            # 베스트 페이지 접속
            page.goto('https://pann.nate.com/talk', wait_until='networkidle', timeout=30000)
            page.wait_for_timeout(2000)

            # 게시물 목록 추출 (여러 선택자 시도)
            articles = page.locator('.item_best, .best_item, .list_type li, article, .board_list li').all()

            for idx, article in enumerate(articles[:30]):  # 최대 30개
                try:
                    # 제목 및 링크 추출
                    title = ""
                    link = ""
                    title_selectors = [
                        '.tit a',
                        '.subject a',
                        'a.title',
                        'a[href*="/talk/"]',
                        'h4 a',
                        'strong a'
                    ]

                    title_link_elem = None
                    for selector in title_selectors:
                        elem = article.locator(selector).first
                        if elem.count() > 0:
                            title = clean_text(elem.inner_text())
                            if title and len(title) >= 5:
                                title_link_elem = elem
                                break

                    if not title or len(title) < 5:
                        continue

                    # 제목 요소에서 링크 추출
                    if title_link_elem:
                        href = title_link_elem.get_attribute('href')
                        if href:
                            if href.startswith('http'):
                                link = href
                            elif href.startswith('/'):
                                link = 'https://pann.nate.com' + href

                    # 링크가 없으면 article의 첫 번째 a 태그에서 추출
                    if not link:
                        link_elem = article.locator('a').first
                        if link_elem.count() > 0:
                            href = link_elem.get_attribute('href')
                            if href:
                                if href.startswith('http'):
                                    link = href
                                elif href.startswith('/'):
                                    link = 'https://pann.nate.com' + href

                    # 카테고리 추출
                    category = "토크"
                    category_elem = article.locator('.category, .cate, .badge').first
                    if category_elem.count() > 0:
                        category = clean_text(category_elem.inner_text())

                    # 날짜 추출
                    date = ""
                    date_elem = article.locator('.date, .time, .regdate, .write_date').first
                    if date_elem.count() > 0:
                        date = clean_text(date_elem.inner_text())

                    issue = {
                        'platform': '네이트 판',
                        'category': category,
                        'title': title,
                        'date': date,
                        'link': link,
                        'shorts_suitable': is_shorts_suitable(title),
                        'scraped_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    }

                    issues.append(issue)

                except Exception as e:
                    print(f"  ⚠️  개별 항목 파싱 오류: {e}")
                    continue

            print(f"✅ 네이트 판: {len(issues)}개 이슈 발견")

        except Exception as e:
            print(f"❌ 네이트 판 스크래핑 오류: {e}")

        finally:
            browser.close()

        return issues


def scrape_naver_bboom():
    """
    네이버 붐업 인기 게시물 스크래핑
    """
    print("\n🔍 네이버 붐업 스크래핑 시작...")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        issues = []

        try:
            # 붐업 메인 페이지 접속
            page.goto('https://m.bboom.naver.com/', wait_until='networkidle', timeout=30000)
            page.wait_for_timeout(2000)

            # 게시물 목록 추출 (여러 선택자 시도)
            articles = page.locator('.post_item, .item, .list_item, article, li[class*="post"]').all()

            for idx, article in enumerate(articles[:30]):  # 최대 30개
                try:
                    # 제목 및 링크 추출
                    title = ""
                    link = ""
                    title_selectors = [
                        '.post_title a',
                        '.title a',
                        'a.title',
                        '.subject a',
                        'a[href*="/post/"]',
                        'h3 a',
                        'h4 a',
                        'strong a'
                    ]

                    title_link_elem = None
                    for selector in title_selectors:
                        elem = article.locator(selector).first
                        if elem.count() > 0:
                            title = clean_text(elem.inner_text())
                            if title and len(title) >= 5:
                                title_link_elem = elem
                                break

                    if not title or len(title) < 5:
                        continue

                    # 제목 요소에서 링크 추출
                    if title_link_elem:
                        href = title_link_elem.get_attribute('href')
                        if href:
                            if href.startswith('http'):
                                link = href
                            elif href.startswith('/'):
                                link = 'https://m.bboom.naver.com' + href

                    # 링크가 없으면 article의 첫 번째 a 태그에서 추출
                    if not link:
                        link_elem = article.locator('a').first
                        if link_elem.count() > 0:
                            href = link_elem.get_attribute('href')
                            if href:
                                if href.startswith('http'):
                                    link = href
                                elif href.startswith('/'):
                                    link = 'https://m.bboom.naver.com' + href

                    # 카테고리 추출
                    category = "붐업"
                    category_elem = article.locator('.category, .cate, .badge, .tag').first
                    if category_elem.count() > 0:
                        category = clean_text(category_elem.inner_text())

                    # 날짜 추출
                    date = ""
                    date_elem = article.locator('.date, .time, .regdate, .post_date').first
                    if date_elem.count() > 0:
                        date = clean_text(date_elem.inner_text())

                    issue = {
                        'platform': '네이버 붐업',
                        'category': category,
                        'title': title,
                        'date': date,
                        'link': link,
                        'shorts_suitable': is_shorts_suitable(title),
                        'scraped_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    }

                    issues.append(issue)

                except Exception as e:
                    print(f"  ⚠️  개별 항목 파싱 오류: {e}")
                    continue

            print(f"✅ 네이버 붐업: {len(issues)}개 이슈 발견")

        except Exception as e:
            print(f"❌ 네이버 붐업 스크래핑 오류: {e}")

        finally:
            browser.close()

        return issues


def scrape_reddit():
    """
    Reddit 인기 게시물 스크래핑 (r/popular)
    """
    print("\n🔍 Reddit 스크래핑 시작...")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        issues = []

        try:
            # Reddit 인기 페이지 접속
            page.goto('https://www.reddit.com/r/popular/', wait_until='networkidle', timeout=30000)
            page.wait_for_timeout(3000)

            # 게시물 목록 추출
            articles = page.locator('shreddit-post, [data-testid="post-container"], article').all()

            for idx, article in enumerate(articles[:30]):  # 최대 30개
                try:
                    # 제목 추출
                    title = ""
                    title_selectors = [
                        '[slot="title"]',
                        'h3',
                        '[data-testid="post-title"]',
                        'a[slot="full-post-link"]',
                        '.title'
                    ]

                    title_elem = None
                    for selector in title_selectors:
                        elem = article.locator(selector).first
                        if elem.count() > 0:
                            title = clean_text(elem.inner_text())
                            if title and len(title) >= 5:
                                title_elem = elem
                                break

                    if not title or len(title) < 5:
                        continue

                    # 링크 추출
                    link = ""
                    permalink = article.get_attribute('permalink')
                    if permalink:
                        link = 'https://www.reddit.com' + permalink
                    else:
                        # 대체 방법: a 태그에서 추출
                        link_elem = article.locator('a[href*="/r/"]').first
                        if link_elem.count() > 0:
                            href = link_elem.get_attribute('href')
                            if href:
                                if href.startswith('http'):
                                    link = href
                                elif href.startswith('/'):
                                    link = 'https://www.reddit.com' + href

                    # 서브레딧(카테고리) 추출
                    category = "popular"
                    subreddit_selectors = [
                        '[data-testid="subreddit-name"]',
                        'a[href*="/r/"][href*="comments"]',
                        'shreddit-subreddit-text'
                    ]

                    for selector in subreddit_selectors:
                        subreddit_elem = article.locator(selector).first
                        if subreddit_elem.count() > 0:
                            category = clean_text(subreddit_elem.inner_text())
                            if category:
                                break

                    # 날짜/시간 추출
                    date = ""
                    date_selectors = [
                        'faceplate-timeago',
                        '[data-testid="post-timestamp"]',
                        'time'
                    ]

                    for selector in date_selectors:
                        date_elem = article.locator(selector).first
                        if date_elem.count() > 0:
                            date = clean_text(date_elem.inner_text())
                            if not date:
                                # datetime 속성 확인
                                date = date_elem.get_attribute('datetime')
                            if date:
                                break

                    issue = {
                        'platform': 'Reddit',
                        'category': category,
                        'title': title,
                        'date': date,
                        'link': link,
                        'shorts_suitable': is_shorts_suitable(title),
                        'scraped_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    }

                    issues.append(issue)

                except Exception as e:
                    print(f"  ⚠️  개별 항목 파싱 오류: {e}")
                    continue

            print(f"✅ Reddit: {len(issues)}개 이슈 발견")

        except Exception as e:
            print(f"❌ Reddit 스크래핑 오류: {e}")

        finally:
            browser.close()

        return issues


def select_platform():
    """
    사용자가 플랫폼을 선택하도록 함
    """
    print("\n" + "="*60)
    print("📱 쇼츠 제작용 이슈 찾기")
    print("="*60)
    print("\n커뮤니티 플랫폼을 선택하세요:")
    print("1. DC인사이드")
    print("2. FM Korea")
    print("3. 네이트 판")
    print("4. 네이버 붐업")
    print("5. Reddit")
    print("6. 전체 (모든 플랫폼)")
    print("="*60)

    while True:
        choice = input("\n선택 (1-6): ").strip()

        if choice == '1':
            return ['dcinside']
        elif choice == '2':
            return ['fmkorea']
        elif choice == '3':
            return ['natepann']
        elif choice == '4':
            return ['naver_bboom']
        elif choice == '5':
            return ['reddit']
        elif choice == '6':
            return ['dcinside', 'fmkorea', 'natepann', 'naver_bboom', 'reddit']
        else:
            print("❌ 잘못된 선택입니다. 1-6 중에서 선택하세요.")


def main():
    # 플랫폼 선택
    platforms = select_platform()

    all_issues = []

    # 선택한 플랫폼별 스크래핑
    for platform in platforms:
        if platform == 'dcinside':
            issues = scrape_dcinside()
        elif platform == 'fmkorea':
            issues = scrape_fmkorea()
        elif platform == 'natepann':
            issues = scrape_natepann()
        elif platform == 'naver_bboom':
            issues = scrape_naver_bboom()
        elif platform == 'reddit':
            issues = scrape_reddit()
        else:
            continue

        all_issues.extend(issues)

    if not all_issues:
        print("\n❌ 수집된 이슈가 없습니다.")
        return

    # 쇼츠 적합한 주제만 필터링
    suitable_issues = [issue for issue in all_issues if issue['shorts_suitable']]

    print(f"\n📊 총 {len(all_issues)}개 이슈 중 {len(suitable_issues)}개가 쇼츠 제작에 적합합니다.")

    # 상위 10개 선택 (쇼츠 적합한 것 우선)
    top_10_suitable = suitable_issues[:10] if len(suitable_issues) >= 10 else suitable_issues

    # 부족하면 전체에서 채움
    if len(top_10_suitable) < 10:
        remaining = [issue for issue in all_issues if not issue['shorts_suitable']]
        needed = 10 - len(top_10_suitable)
        top_10_suitable.extend(remaining[:needed])

    print(f"\n🎯 쇼츠 제작 추천 주제 TOP {len(top_10_suitable)}:")
    print("="*80)

    for idx, issue in enumerate(top_10_suitable, 1):
        suitable_mark = "⭐" if issue['shorts_suitable'] else "  "
        print(f"\n{idx}. {suitable_mark} {issue['category']}")
        print(f"   📌 제목: {issue['title']}")
        print(f"   📰 출처: {issue['platform']}")
        print(f"   🔗 링크: {issue.get('link', '링크 없음')}")
        if issue.get('date'):
            print(f"   📅 날짜: {issue['date']}")

    # 결과 저장
    date_str = datetime.now().strftime('%Y%m%d_%H%M%S')

    # JSON 저장 (전체)
    json_filename = f'issues_all_{date_str}.json'
    with open(json_filename, 'w', encoding='utf-8') as f:
        json.dump(all_issues, f, ensure_ascii=False, indent=2)
    print(f"\n💾 전체 결과가 '{json_filename}' 파일로 저장되었습니다.")

    # JSON 저장 (TOP 10)
    json_top10_filename = f'issues_top10_{date_str}.json'
    with open(json_top10_filename, 'w', encoding='utf-8') as f:
        json.dump(top_10_suitable, f, ensure_ascii=False, indent=2)
    print(f"💾 TOP 10이 '{json_top10_filename}' 파일로 저장되었습니다.")

    # 엑셀 저장
    excel_filename = f'issues_{date_str}.xlsx'
    with pd.ExcelWriter(excel_filename, engine='openpyxl') as writer:
        # 전체 이슈
        df_all = pd.DataFrame(all_issues)
        cols = ['platform', 'category', 'title', 'date', 'shorts_suitable', 'link', 'scraped_at']
        cols = [c for c in cols if c in df_all.columns]
        df_all = df_all[cols]

        # 컬럼명을 한글로 변경
        df_all = df_all.rename(columns={
            'platform': '출처',
            'category': '카테고리',
            'title': '제목',
            'date': '날짜',
            'shorts_suitable': '쇼츠적합',
            'link': '링크',
            'scraped_at': '수집시간'
        })
        df_all.to_excel(writer, sheet_name='전체', index=False)

        # TOP 10
        df_top10 = pd.DataFrame(top_10_suitable)
        df_top10 = df_top10[cols]
        df_top10 = df_top10.rename(columns={
            'platform': '출처',
            'category': '카테고리',
            'title': '제목',
            'date': '날짜',
            'shorts_suitable': '쇼츠적합',
            'link': '링크',
            'scraped_at': '수집시간'
        })
        df_top10.to_excel(writer, sheet_name='TOP10_쇼츠추천', index=False)

        # 쇼츠 적합만
        if suitable_issues:
            df_suitable = pd.DataFrame(suitable_issues)
            df_suitable = df_suitable[cols]
            df_suitable = df_suitable.rename(columns={
                'platform': '출처',
                'category': '카테고리',
                'title': '제목',
                'date': '날짜',
                'shorts_suitable': '쇼츠적합',
                'link': '링크',
                'scraped_at': '수집시간'
            })
            df_suitable.to_excel(writer, sheet_name='쇼츠적합', index=False)

    print(f"💾 엑셀 결과가 '{excel_filename}' 파일로 저장되었습니다.")
    print("\n✨ 완료!")


if __name__ == "__main__":
    main()
