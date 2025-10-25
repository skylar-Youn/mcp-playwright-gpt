#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
쿠팡 크롤러 웹 버전
- Flask 웹 인터페이스
- 실시간 에러 트래킹
- 로그 표시 기능
"""

from flask import Flask, render_template, request, jsonify, send_file
from flask_socketio import SocketIO, emit
import asyncio
import json
import os
import csv
import traceback
from datetime import datetime
from threading import Thread
import logging
from logging.handlers import RotatingFileHandler

try:
    from playwright.async_api import async_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False

try:
    from playwright_stealth import Stealth
    STEALTH_AVAILABLE = True
except ImportError:
    STEALTH_AVAILABLE = False

# Flask 앱 설정
app = Flask(__name__)
app.config['SECRET_KEY'] = 'coupang-crawler-secret-key'
socketio = SocketIO(app, cors_allowed_origins="*")

# 로깅 설정
if not os.path.exists('logs'):
    os.makedirs('logs')

file_handler = RotatingFileHandler('logs/coupang_crawler.log', maxBytes=10240000, backupCount=10)
file_handler.setFormatter(logging.Formatter(
    '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
))
file_handler.setLevel(logging.INFO)
app.logger.addHandler(file_handler)
app.logger.setLevel(logging.INFO)
app.logger.info('쿠팡 크롤러 웹 시작')

# 설정 파일
CONFIG_FILE = 'coupang_wing_config.json'

# 전역 변수
scraping_results = []
is_scraping = False


def load_config():
    """설정 로드"""
    default_config = {
        'max_results': 20,
        'min_price': 0,
        'max_price': 999999999,
        'exclude_rocket': True,
        'exclude_rocket_direct': True,
        'headless': True,
        'use_proxy': False,
        'proxy_server': '',
        'min_delay': 2.0,
        'max_delay': 5.0,
        'scroll_delay': 1.5,
        'initial_wait': 3.0,
        'use_stealth': True  # 스텔스 모드 기본값
    }

    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                return {**default_config, **json.load(f)}
        except Exception as e:
            app.logger.error(f'설정 로드 오류: {str(e)}')
            return default_config
    return default_config


def save_config(config):
    """설정 저장"""
    try:
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        app.logger.error(f'설정 저장 오류: {str(e)}')
        return False


def emit_log(level, message):
    """로그 전송"""
    log_data = {
        'level': level,
        'message': message,
        'timestamp': datetime.now().strftime('%H:%M:%S')
    }
    socketio.emit('log', log_data)

    # 파일 로그도 기록
    if level == 'error':
        app.logger.error(message)
    elif level == 'warning':
        app.logger.warning(message)
    else:
        app.logger.info(message)


async def smooth_scroll(page, start=0, end=None, steps=10):
    """사람처럼 부드럽게 스크롤하는 함수"""
    import random

    if end is None:
        end = await page.evaluate("() => document.body.scrollHeight")

    step_size = (end - start) / steps
    current = start

    for _ in range(steps):
        # 약간의 랜덤성을 추가하여 자연스러운 스크롤 구현
        current += step_size + random.uniform(-100, 100)
        current = min(current, end)
        await page.evaluate(f"window.scrollTo(0, {current})")
        await asyncio.sleep(random.uniform(0.3, 0.7))


async def scrape_coupang(search_params):
    """쿠팡 스크래핑 (개선된 버전 - 봇 감지 회피)"""
    global scraping_results, is_scraping
    import random

    results = []
    query = search_params['query']
    max_results = search_params.get('max_results', 20)

    emit_log('info', f"'{query}' 검색 시작...")

    try:
        async with async_playwright() as p:
            emit_log('info', 'Playwright 초기화 중...')

            # 브라우저 실행 (안티봇 우회 설정)
            try:
                browser = await p.chromium.launch(
                    headless=search_params.get('headless', True),
                    args=[
                        '--disable-blink-features=AutomationControlled',
                        '--disable-dev-shm-usage',
                        '--no-sandbox',
                        '--disable-http2',  # HTTP/2 비활성화 (프로토콜 오류 방지)
                        '--disable-gpu',
                        '--window-size=1920,1080',
                        '--disable-extensions',
                        '--disable-setuid-sandbox',
                        '--disable-web-security',
                        '--disable-features=IsolateOrigins,site-per-process',
                        '--incognito'  # 시크릿 모드
                    ]
                )
                emit_log('success', '브라우저 실행 완료 (시크릿 모드, HTTP/2 비활성화)')
            except Exception as e:
                emit_log('error', f'브라우저 실행 실패: {str(e)}')
                raise

            # 컨텍스트 설정
            context_options = {
                'viewport': {'width': 1920, 'height': 1080},
                'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'locale': 'ko-KR',
                'timezone_id': 'Asia/Seoul'
            }

            # 프록시 설정
            if search_params.get('use_proxy') and search_params.get('proxy_server'):
                proxy_server = search_params.get('proxy_server')
                emit_log('info', f'프록시 사용: {proxy_server}')
                context_options['proxy'] = {'server': proxy_server}

            try:
                context = await browser.new_context(**context_options)
                emit_log('success', '브라우저 컨텍스트 생성 완료')
            except Exception as e:
                emit_log('error', f'컨텍스트 생성 실패: {str(e)}')
                await browser.close()
                raise

            # 스텔스 모드 적용 (봇 감지 우회) - context에 적용
            if search_params.get('use_stealth', True) and STEALTH_AVAILABLE:
                stealth_config = Stealth(
                    navigator_languages_override=('ko-KR', 'ko'),
                    navigator_user_agent_override=None  # 자동 설정
                )
                await stealth_config.apply_stealth_async(context)
                emit_log('success', '스텔스 모드 활성화 완료')
            elif search_params.get('use_stealth', True) and not STEALTH_AVAILABLE:
                emit_log('warning', 'playwright-stealth 미설치 (기본 모드)')
            else:
                emit_log('info', '스텔스 모드 비활성화 (사용자 설정)')

            page = await context.new_page()

            try:
                # 검색 URL 구성
                import urllib.parse
                encoded_query = urllib.parse.quote(query)
                search_url = f"https://www.coupang.com/np/search?component=&q={encoded_query}&channel=user"

                emit_log('info', f'검색 페이지 접속 중: {query}')

                # 쿠키 삭제
                await context.clear_cookies()

                # 사람처럼 랜덤한 대기 시간 추가
                await asyncio.sleep(random.uniform(2, 4))

                # 여러 번 시도 (재시도 로직)
                max_retries = 3
                for attempt in range(max_retries):
                    try:
                        await page.goto(
                            search_url,
                            wait_until='domcontentloaded',
                            timeout=60000
                        )
                        emit_log('success', '검색 페이지 접속 완료')
                        break
                    except Exception as e:
                        if attempt < max_retries - 1:
                            emit_log('warning', f'접속 실패 (시도 {attempt + 1}/{max_retries}), 재시도 중...')
                            await asyncio.sleep(3)
                        else:
                            emit_log('error', f'최대 재시도 횟수 초과: {str(e)}')
                            raise

                # 페이지 로드 후 자연스러운 대기
                await asyncio.sleep(random.uniform(3, 5))

                # 페이지 로드 상태 확인
                page_state = await page.evaluate('document.readyState')
                emit_log('info', f'페이지 로드 상태: {page_state}')

                # 봇 탐지 확인
                page_content = await page.content()
                if "보안 검사 중입니다" in page_content or "캡차" in page_content:
                    emit_log('warning', '봇 탐지 감지됨. 잠시 대기 후 재시도...')
                    await asyncio.sleep(random.uniform(15, 30))

                # 자연스러운 스크롤 동작
                viewport_height = await page.evaluate("window.innerHeight")
                total_height = await page.evaluate("document.body.scrollHeight")

                emit_log('info', '자연스러운 스크롤 시작...')

                # 중간 중간 멈추면서 스크롤
                current_position = 0
                while current_position < total_height:
                    # 다음 스크롤 위치 계산 (랜덤성 추가)
                    scroll_amount = random.randint(300, 700)
                    next_position = min(current_position + scroll_amount, total_height)

                    # 부드럽게 스크롤
                    await smooth_scroll(page, current_position, next_position)

                    # 스크롤 후 잠시 대기 (컨텐츠 로딩 대기)
                    await asyncio.sleep(random.uniform(0.5, 1.5))

                    # 가끔 위로 살짝 스크롤 (사람처럼 보이게)
                    if random.random() < 0.2:  # 20% 확률
                        back_scroll = random.randint(100, 300)
                        await page.evaluate(f"window.scrollBy(0, -{back_scroll})")
                        await asyncio.sleep(random.uniform(0.3, 0.7))

                    current_position = next_position

                emit_log('success', '스크롤 완료')

                # 요소 찾기 전 자연스러운 대기
                await asyncio.sleep(random.uniform(1, 2))

                # 제품 목록 대기
                emit_log('info', '제품 목록 로드 대기 중...')
                try:
                    await page.wait_for_selector('li.search-product', timeout=30000)
                except:
                    emit_log('warning', '상품 목록을 찾을 수 없습니다.')
                    await browser.close()
                    return results

                # 제품 수집
                emit_log('info', '제품 정보 수집 중...')
                products = await page.query_selector_all('li.search-product')
                emit_log('info', f'{len(products)}개 제품 발견')

                if not products:
                    emit_log('warning', '검색 결과가 없습니다')
                    await browser.close()
                    return results

                # 제품 처리 (광고 제외)
                non_ad_rank = 0
                ad_count = 0

                for idx, product in enumerate(products):
                    try:
                        # 광고 상품 체크
                        class_attr = await product.get_attribute('class')
                        is_ad = 'search-product__ad' in (class_attr or '')

                        if is_ad:
                            ad_count += 1
                            emit_log('info', f'광고 상품 발견: {ad_count}번째 광고')
                            continue

                        non_ad_rank += 1

                        # 제품 정보 추출
                        name_elem = await product.query_selector('.name')
                        name = await name_elem.inner_text() if name_elem else "제목 없음"

                        price_elem = await product.query_selector('.price-value')
                        price_text = await price_elem.inner_text() if price_elem else "0"
                        price = int(price_text.replace(',', '').replace('원', '').strip())

                        # 가격 필터링
                        min_price = search_params.get('min_price', 0)
                        max_price = search_params.get('max_price', 999999999)
                        if price < min_price or price > max_price:
                            continue

                        # 필터링
                        is_rocket = await product.query_selector('.badge.rocket') is not None
                        is_rocket_direct = await product.query_selector('.badge.rocket-direct') is not None
                        is_rocket_global = await product.query_selector('.badge.rocket-global') is not None
                        is_rocket_fresh = await product.query_selector('.badge.rocket-fresh') is not None

                        if search_params.get('exclude_rocket', True) and is_rocket:
                            continue
                        if search_params.get('exclude_rocket_direct', True) and (is_rocket_direct or is_rocket_global or is_rocket_fresh):
                            continue

                        # URL
                        link_elem = await product.query_selector('a.search-product-link')
                        product_url = ""
                        if link_elem:
                            href = await link_elem.get_attribute('href')
                            if href:
                                product_url = f"https://www.coupang.com{href}" if href.startswith('/') else href

                        # 평점
                        rating_elem = await product.query_selector('.rating')
                        rating = await rating_elem.inner_text() if rating_elem else "N/A"

                        # 리뷰 수
                        review_elem = await product.query_selector('.rating-total-count')
                        review_count = await review_elem.inner_text() if review_elem else "0"

                        # 판매자 정보
                        seller_type = "일반 판매자"
                        if is_rocket:
                            seller_type = "로켓배송"
                        elif is_rocket_direct:
                            seller_type = "로켓직구"
                        elif is_rocket_global:
                            seller_type = "로켓글로벌"
                        elif is_rocket_fresh:
                            seller_type = "로켓프레시"

                        results.append({
                            'rank': non_ad_rank,  # 광고 제외 순위
                            'name': name.strip(),
                            'price': price,
                            'seller_type': seller_type,
                            'rating': rating.strip(),
                            'review_count': review_count.strip(),
                            'url': product_url
                        })

                        emit_log('info', f'처리 중... {len(results)}개 제품 발견 (광고 제외 순위: {non_ad_rank})')

                        # 실시간 결과 전송
                        socketio.emit('result_update', {
                            'count': len(results),
                            'latest': results[-1]
                        })

                        if len(results) >= max_results:
                            break

                    except Exception as e:
                        emit_log('warning', f'제품 처리 중 오류: {str(e)}')
                        continue

                # 가격 순 정렬
                results.sort(key=lambda x: x['price'])
                emit_log('success', f'검색 완료! 총 {len(results)}개 제품 수집 (광고 {ad_count}개 제외)')

            except Exception as e:
                emit_log('error', f'페이지 처리 중 오류: {str(e)}\n{traceback.format_exc()}')
                raise
            finally:
                await browser.close()
                emit_log('info', '브라우저 종료')

    except Exception as e:
        emit_log('error', f'스크래핑 오류: {str(e)}\n{traceback.format_exc()}')
        raise

    return results


def run_scraper(search_params):
    """스크래퍼 실행 (별도 스레드)"""
    global scraping_results, is_scraping

    try:
        is_scraping = True
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        scraping_results = loop.run_until_complete(scrape_coupang(search_params))
        loop.close()

        # 완료 알림
        socketio.emit('scraping_complete', {
            'success': True,
            'count': len(scraping_results),
            'results': scraping_results
        })

    except Exception as e:
        socketio.emit('scraping_complete', {
            'success': False,
            'error': str(e),
            'traceback': traceback.format_exc()
        })
    finally:
        is_scraping = False


@app.route('/')
def index():
    """메인 페이지"""
    config = load_config()
    return render_template('index.html', config=config, playwright_available=PLAYWRIGHT_AVAILABLE)


@app.route('/api/config', methods=['GET', 'POST'])
def api_config():
    """설정 API"""
    if request.method == 'GET':
        return jsonify(load_config())
    else:
        config = request.json
        if save_config(config):
            return jsonify({'success': True})
        else:
            return jsonify({'success': False, 'error': '설정 저장 실패'}), 500


@app.route('/api/search', methods=['POST'])
def api_search():
    """검색 API"""
    global is_scraping

    if is_scraping:
        return jsonify({'success': False, 'error': '이미 검색 중입니다'}), 400

    if not PLAYWRIGHT_AVAILABLE:
        return jsonify({'success': False, 'error': 'Playwright가 설치되지 않았습니다'}), 500

    search_params = request.json

    # 백그라운드 스레드에서 실행
    thread = Thread(target=run_scraper, args=(search_params,))
    thread.daemon = True
    thread.start()

    return jsonify({'success': True, 'message': '검색 시작'})


@app.route('/api/results', methods=['GET'])
def api_results():
    """결과 API"""
    return jsonify(scraping_results)


@app.route('/api/export', methods=['POST'])
def api_export():
    """CSV 내보내기"""
    if not scraping_results:
        return jsonify({'success': False, 'error': '결과가 없습니다'}), 400

    try:
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f'coupang_results_{timestamp}.csv'

        with open(filename, 'w', encoding='utf-8-sig', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=['name', 'price', 'seller_type', 'rating', 'review_count', 'url'])
            writer.writeheader()
            writer.writerows(scraping_results)

        return send_file(filename, as_attachment=True)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/logs', methods=['GET'])
def api_logs():
    """로그 조회"""
    try:
        with open('logs/coupang_crawler.log', 'r', encoding='utf-8') as f:
            logs = f.readlines()[-100:]  # 최근 100줄
        return jsonify({'success': True, 'logs': logs})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@socketio.on('connect')
def handle_connect():
    """WebSocket 연결"""
    emit_log('info', '클라이언트 연결됨')


@socketio.on('disconnect')
def handle_disconnect():
    """WebSocket 연결 해제"""
    app.logger.info('클라이언트 연결 해제')


if __name__ == '__main__':
    print('=' * 60)
    print('🚀 쿠팡 크롤러 웹 버전 시작')
    print('=' * 60)
    print(f'📡 서버 주소: http://localhost:5000')
    print(f'📊 Playwright: {"✅ 설치됨" if PLAYWRIGHT_AVAILABLE else "❌ 미설치"}')
    print('=' * 60)
    print('\n브라우저에서 http://localhost:5000 을 열어주세요\n')

    socketio.run(app, host='0.0.0.0', port=5000, debug=True, allow_unsafe_werkzeug=True)
