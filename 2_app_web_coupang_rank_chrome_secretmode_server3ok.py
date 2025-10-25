from gevent import monkey
monkey.patch_all()

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from bs4 import BeautifulSoup
import time
import random
import urllib.parse
import pandas as pd
from datetime import datetime
from flask import Flask, render_template, request, jsonify
from flask_socketio import SocketIO, emit
import sys
sys.setrecursionlimit(10000)
import os
import json
import numpy as np
from apscheduler.schedulers.background import BackgroundScheduler
from gevent.pywsgi import WSGIServer
from geventwebsocket.handler import WebSocketHandler

# Flask 앱과 SocketIO 초기화
app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret!'
socketio = SocketIO(app, 
                   async_mode='gevent', 
                   cors_allowed_origins="*",
                   ping_timeout=60,
                   ping_interval=25)

# 전역 변수 설정
search_active = False
log_messages = []
scheduler = BackgroundScheduler()

def emit_log(message):
    """로그 메시지 전송"""
    try:
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        log_message = f"[{timestamp}] {message}"
        log_messages.append(log_message)
        socketio.emit('log_message', {'message': log_message})
        print(log_message)
    except Exception as e:
        print(f"로그 전송 중 오류: {str(e)}")

@socketio.on('connect')
def handle_connect():
    """클라이언트 연결 시 처리"""
    try:
        emit_log("클라이언트 연결됨")
        # 최근 로그 전송
        recent_logs = log_messages[-100:] if log_messages else []
        for log in recent_logs:
            socketio.emit('log_message', {'message': log})
    except Exception as e:
        print(f"연결 처리 중 오류: {str(e)}")

@socketio.on('disconnect')
def handle_disconnect():
    """클라이언트 연결 해제 시 처리"""
    emit_log("클라이언트 연결 해제")
    if search_active:
        emit_log("검색은 백그라운드에서 계속 진행됩니다.")

def setup_chrome_driver():
    """크롬 드라이버 설정"""
    try:
        # Chrome 옵션 설정
        chrome_options = webdriver.ChromeOptions()
        chrome_options.add_argument('--headless=new')
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--disable-gpu')
        chrome_options.add_argument('--enable-unsafe-swiftshader')
        chrome_options.add_argument('--incognito')
        chrome_options.add_argument('--window-size=1920,1080')
        chrome_options.add_argument('--disable-blink-features=AutomationControlled')
        chrome_options.add_argument('--disable-extensions')
        chrome_options.add_argument('user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
        
        # 로깅 설정
        import logging
        logging.basicConfig(level=logging.DEBUG)
        logger = logging.getLogger('selenium.webdriver.remote.remote_connection')
        logger.setLevel(logging.DEBUG)
        
        # WebDriver Manager를 사용하여 크롬 드라이버 자동 설치
        from selenium.webdriver.chrome.service import Service
        from webdriver_manager.chrome import ChromeDriverManager
        
        # 상세 로그 설정
        service = Service(
            ChromeDriverManager().install(),
            log_path='chromedriver.log',
            service_args=['--verbose']
        )
        
        emit_log("크롬 드라이버 설치 경로: " + service.path)
        
        driver = webdriver.Chrome(service=service, options=chrome_options)
        
        # 페이지 로드 타임아웃 설정
        driver.set_page_load_timeout(30)
        driver.implicitly_wait(10)
        
        emit_log("크롬 드라이버 초기화 성공")
        return driver
        
    except Exception as e:
        emit_log(f"크롬 드라이버 설정 실패: {str(e)}")
        import traceback
        emit_log(f"상세 오류: {traceback.format_exc()}")
        return None

def smooth_scroll(driver, start=0, end=None, steps=10):
    """사람처럼 부드럽게 스크롤하는 함수"""
    if end is None:
        end = driver.execute_script("return document.body.scrollHeight")
    
    step_size = (end - start) / steps
    current = start
    
    for _ in range(steps):
        # 약간의 랜덤성을 추가하여 자연스러운 스크롤 구현
        current += step_size + random.uniform(-100, 100)
        current = min(current, end)
        driver.execute_script(f"window.scrollTo(0, {current});")
        time.sleep(random.uniform(0.3, 0.7))  # 랜덤한 시간 간격으로 스크롤

def human_like_click(driver, element):
    """사람처럼 자연스럽게 클릭하는 함수"""
    # 요소가 화면에 보이도록 스크롤
    driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", element)
    time.sleep(random.uniform(0.5, 1.5))
    
    # 랜덤한 지연 시간 추가
    time.sleep(random.uniform(0.1, 0.3))
    element.click()

def analyze_page(soup, page, product_id):
    """페이지 내용을 분석하여 상품 찾기"""
    products = soup.select('.search-product')
    non_ad_rank = 0
    ad_count = 0
    
    for product in products:
        is_ad = 'search-product__ad' in product.get('class', [])
        
        if is_ad:
            ad_count += 1
            emit_log(f"광고 상품 발견: {ad_count}번째 광고")
            continue
        
        non_ad_rank += 1
        
        product_link = product.select_one('a.search-product-link')
        if not product_link:
            continue
        
        current_name = product.select_one('.name')
        if not current_name:
            continue
        
        current_name = current_name.text.strip()
        current_url = product_link.get('href', '')
        current_id = current_url.split('/')[-1].split('?')[0]
        
        if product_id == current_id:
            emit_log(f"\n[상품 발견!] 페이지: {page}, 순위: {non_ad_rank} (광고 제외), 상품명: {current_name}, 상품 ID: {current_id}")
            return {
                'page': page,
                'rank': non_ad_rank,
                'ad_count': ad_count,
                'name': current_name,
                'id': current_id,
                'url': f"https://www.coupang.com{current_url}"
            }
    
    return None

def search_product(driver, keyword, product_id):
    """쿠팡에서 상품을 검색하고 순위를 찾는 함수"""
    try:
        encoded_keyword = urllib.parse.quote(keyword)
        base_url = f'https://www.coupang.com/np/search?component=&q={encoded_keyword}&channel=user'
        
        page = 1
        
        while page <= 27:
            try:
                emit_log(f"\n{page}페이지 검색 중...")
                url = f"{base_url}&page={page}"
                
                emit_log(f"URL 접속 시도: {url}")
                driver.delete_all_cookies()
                
                # 사람처럼 랜덤한 대기 시간 추가
                time.sleep(random.uniform(2, 4))
                
                driver.get(url)
                
                # 페이지 로드 후 자연스러운 대기
                time.sleep(random.uniform(3, 5))
                
                # 페이지 로드 상태 확인
                page_state = driver.execute_script('return document.readyState;')
                emit_log(f"페이지 로드 상태: {page_state}")
                
                # 자연스러운 스크롤 동작
                viewport_height = driver.execute_script("return window.innerHeight")
                total_height = driver.execute_script("return document.body.scrollHeight")
                
                # 중간 중간 멈추면서 스크롤
                current_position = 0
                while current_position < total_height:
                    # 다음 스크롤 위치 계산 (랜덤성 추가)
                    scroll_amount = random.randint(300, 700)
                    next_position = min(current_position + scroll_amount, total_height)
                    
                    # 부드럽게 스크롤
                    smooth_scroll(driver, current_position, next_position)
                    
                    # 스크롤 후 잠시 대기 (컨텐츠 로딩 대기)
                    time.sleep(random.uniform(0.5, 1.5))
                    
                    # 가끔 위로 살짝 스크롤 (사람처럼 보이게)
                    if random.random() < 0.2:  # 20% 확률
                        back_scroll = random.randint(100, 300)
                        driver.execute_script(f"window.scrollBy(0, -{back_scroll});")
                        time.sleep(random.uniform(0.3, 0.7))
                    
                    current_position = next_position
                
                # 요소 찾기 전 자연스러운 대기
                time.sleep(random.uniform(1, 2))
                
                # 상품 목록 찾기
                selectors = ["search-product", "search-product-link", "search-product-wrap"]
                element_found = False
                
                for selector in selectors:
                    try:
                        elements = WebDriverWait(driver, 10).until(
                            EC.presence_of_all_elements_located((By.CLASS_NAME, selector))
                        )
                        if elements:
                            element_found = True
                            emit_log(f"요소 찾음: {selector}")
                            break
                    except:
                        continue
                
                if not element_found:
                    emit_log("경고: 상품 목록을 찾을 수 없습니다.")
                    continue
                
                # 페이지 소스 분석
                page_source = driver.page_source
                
                # 봇 탐지 확인
                if "보안 검사 중입니다" in page_source or "캡차" in page_source:
                    emit_log("봇 탐지 감지됨. 잠시 대기 후 재시도...")
                    time.sleep(random.uniform(15, 30))  # 더 긴 대기 시간
                    continue
                
                soup = BeautifulSoup(page_source, 'html.parser')
                result = analyze_page(soup, page, product_id)
                
                if result:
                    return result
                
                # 다음 페이지로 이동하기 전 자연스러운 대기
                time.sleep(random.uniform(3, 5))
                page += 1
                
            except Exception as e:
                emit_log(f"페이지 {page} 검색 중 오류: {str(e)}")
                emit_log(f"오류 타입: {type(e).__name__}")
                
                # 브라우저 재시작 전 충분한 대기
                time.sleep(random.uniform(10, 20))
                
                try:
                    driver.quit()
                except:
                    pass
                
                driver = setup_chrome_driver()
                if driver is None:
                    emit_log("드라이버 재초기화 실패")
                    return None
                
                continue
        
        emit_log(f"키워드: {keyword}, 상품 ID: {product_id}, 해당 상품을 찾을 수 없습니다. (27페이지 내)")
        return None
        
    except Exception as e:
        emit_log(f"검색 중 오류 발생: {str(e)}")
        emit_log(f"오류 타입: {type(e).__name__}")
        import traceback
        emit_log(f"상세 오류 추적:\n{traceback.format_exc()}")
        return None

scheduler = None # BackgroundScheduler()
def setup_scheduler():
    """스케줄러 설정"""
    global scheduler  # 전역 변수 사용
    try:
        scheduler = BackgroundScheduler()
        scheduler.add_job(perform_search, 'interval', hours=3, id='periodic_search')
        scheduler.start()
        emit_log("스케줄러 시작: 3시간 간격으로 검색")
    except Exception as e:
        emit_log(f"스케줄러 설정 실패: {str(e)}")

def perform_search():
    """실제 검색을 수행하는 함수"""
    global search_active
    driver = None
    try:
        if not search_active:
            search_active = True
        
        emit_log("검색 프로세스 시작")
        
        # 1. 엑셀 파일 로드
        df = pd.read_excel('coupang_rank.xlsx')
        emit_log(f"데이터 로드 완료: {len(df)}개 항목")
        
        # 크롬 드라이버 설정
        driver = setup_chrome_driver()
        if driver is None:
            emit_log("크롬 드라이버 초기화 실패")
            return
        
        try:
            total_items = len(df)
            for index, row in df.iterrows():
                if not search_active:
                    break
                
                keyword = row['keyword']
                product_id = str(row['product_id'])
                
                emit_log(f"\n검색 시작 [{index + 1}/{total_items}]: {keyword} (상품 ID: {product_id})")
                socketio.emit('search_status', {
                    'status': 'searching',
                    'current': index + 1,
                    'total': total_items,
                    'keyword': keyword,
                    'message': f'검색 중: {keyword}'
                })
                
                # 검색 수행
                result = search_product(driver, keyword, product_id)
                
                if result:
                    df.at[index, 'page'] = result['page']
                    df.at[index, 'rank'] = result['rank']
                    df.at[index, 'ad'] = 'O' if result['ad_count'] > 0 else '0'
                    df.at[index, 'page_rank'] = result['rank']
                    df.at[index, 'date'] = datetime.now().strftime('%Y-%m-%d')
                    df.at[index, 'time'] = datetime.now().strftime('%H:%M:%S')
                    emit_log(f"상품 발견: 페이지 {result['page']}, 순위 {result['rank']}")
                else:
                    df.at[index, 'page'] = 0
                    df.at[index, 'rank'] = 0
                    df.at[index, 'ad'] = '0'
                    df.at[index, 'page_rank'] = 0
                    df.at[index, 'date'] = datetime.now().strftime('%Y-%m-%d')
                    df.at[index, 'time'] = datetime.now().strftime('%H:%M:%S')
                    emit_log(f"상품을 찾을 수 없습니다: {keyword}")
                
                # 결과 저장
                df.to_excel('coupang_rank.xlsx', index=False)
                socketio.emit('refresh_page', {})
                
                # 다음 검색 전 대기
                time.sleep(3)
            
            emit_log("모든 검색이 완료되었습니다.")
            
        finally:
            if driver:
                driver.quit()
            emit_log("크롬 드라이버 종료")
            search_active = False
            socketio.emit('search_status', {
                'status': 'waiting',
                'current': 0,
                'total': 0,
                'keyword': '',
                'message': '검색 완료'
            })
            
    except Exception as e:
        emit_log(f"검색 프로세스 오류: {str(e)}")
        search_active = False
        socketio.emit('search_status', {
            'status': 'error',
            'current': 0,
            'total': 0,
            'keyword': '',
            'message': f'검색 프로세스 오류: {str(e)}'
        })
    finally:
        if driver:
            try:
                driver.quit()
            except:
                pass

@app.route('/')
def index():
    """메인 페이지"""
    try:
        df = pd.read_excel('coupang_rank.xlsx')
        return render_template('template.html', 
                             title='Coupang Rank Checker', 
                             message='쿠팡 순위 체커',
                             data=df.to_dict('records'))
    except Exception as e:
        return f"오류 발생: {str(e)}"

@app.route('/start_search', methods=['POST'])
def start_search():
    """검색 시작"""
    global search_active
    try:
        if not search_active:
            search_active = True
            emit_log("검색 시작")
            # 검색 프로세스를 별도 스레드에서 실행
            from threading import Thread
            search_thread = Thread(target=perform_search)
            search_thread.daemon = True
            search_thread.start()
            return jsonify({"status": "success"})
        return jsonify({"status": "error", "message": "이미 검색이 진행 중입니다."})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})

@app.route('/stop_search', methods=['POST'])
def stop_search():
    """검색 중지"""
    global search_active
    try:
        search_active = False
        emit_log("검색 중지 요청")
        return jsonify({"status": "success"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})

if __name__ == "__main__":
    try:
        # 검색 상태 초기화
        search_active = False
        
        print("""
--------------------------------
    Hello, Rank Search
--------------------------------
        """)
        
        # 스케줄러 시작
        setup_scheduler()
        
        # WebSocket 서버 설정
        http_server = WSGIServer(('222.122.202.122', 5000), 
                               app, 
                               handler_class=WebSocketHandler)
        
        print("Server is running on http://222.122.202.122:5000")
        
        # 서버 시작
        http_server.serve_forever()
        
    except Exception as e:
        print(f"프로그램 실행 중 오류 발생: {str(e)}")
    finally:
        search_active = False
        if scheduler and scheduler.running:
            scheduler.shutdown()
            print("스케줄러 중지 완료")
