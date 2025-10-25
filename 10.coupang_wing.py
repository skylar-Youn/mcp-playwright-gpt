#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
쿠팡 일반 판매자 제품 찾기
- 로켓배송이 아닌 일반 판매자의 제품을 검색
- Playwright를 사용한 웹 스크래핑
"""

import sys
import json
import os
import csv
import asyncio
import webbrowser
import random
from datetime import datetime
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                             QHBoxLayout, QTabWidget, QLabel, QLineEdit,
                             QPushButton, QTableWidget, QTableWidgetItem,
                             QComboBox, QSpinBox, QTextEdit, QGroupBox,
                             QGridLayout, QMessageBox, QHeaderView,
                             QProgressBar, QCheckBox, QFileDialog)
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtGui import QFont

try:
    from playwright.async_api import async_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False


class CoupangScraperWorker(QThread):
    """쿠팡 스크래핑 작업을 별도 스레드에서 처리"""
    progress = pyqtSignal(str)
    result = pyqtSignal(list)
    error = pyqtSignal(str)

    def __init__(self, search_params):
        super().__init__()
        self.search_params = search_params

    def run(self):
        """스크래핑 실행"""
        try:
            # asyncio 이벤트 루프 생성 및 실행
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            results = loop.run_until_complete(self.scrape_coupang())
            loop.close()

            self.result.emit(results)
        except Exception as e:
            self.error.emit(f"오류 발생: {str(e)}")

    async def random_delay(self, min_sec=None, max_sec=None):
        """사람처럼 보이기 위한 랜덤 딜레이"""
        if min_sec is None:
            min_sec = self.search_params.get('min_delay', 2.0)
        if max_sec is None:
            max_sec = self.search_params.get('max_delay', 5.0)
        delay = random.uniform(min_sec, max_sec)
        await asyncio.sleep(delay)

    async def smooth_scroll(self, page, scroll_amount=300):
        """부드러운 스크롤 시뮬레이션"""
        for _ in range(3):
            await page.evaluate(f'window.scrollBy(0, {scroll_amount})')
            await asyncio.sleep(random.uniform(0.3, 0.7))

    async def human_like_mouse_move(self, page):
        """사람처럼 마우스를 움직임"""
        width = await page.evaluate('window.innerWidth')
        height = await page.evaluate('window.innerHeight')
        x = random.randint(100, width - 100)
        y = random.randint(100, height - 100)
        await page.mouse.move(x, y)
        await asyncio.sleep(random.uniform(0.1, 0.3))

    async def scrape_coupang(self):
        """쿠팡 웹사이트 스크래핑 - 사람처럼 행동"""
        results = []
        query = self.search_params['query']
        max_results = self.search_params.get('max_results', 20)
        exclude_rocket = self.search_params.get('exclude_rocket', True)
        exclude_rocket_direct = self.search_params.get('exclude_rocket_direct', True)
        min_price = self.search_params.get('min_price', 0)
        max_price = self.search_params.get('max_price', 999999999)

        self.progress.emit(f"'{query}' 검색 중...")

        async with async_playwright() as p:
            # 브라우저 실행 - 실제 브라우저처럼 설정
            browser = await p.chromium.launch(
                headless=self.search_params.get('headless', True),
                args=[
                    '--disable-blink-features=AutomationControlled',
                    '--disable-dev-shm-usage',
                    '--no-sandbox'
                ]
            )

            # 프록시 설정
            context_options = {
                'viewport': {'width': 1920, 'height': 1080},
                'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'locale': 'ko-KR',
                'timezone_id': 'Asia/Seoul'
            }

            # 프록시 사용 시
            if self.search_params.get('use_proxy', False) and self.search_params.get('proxy_server'):
                proxy_server = self.search_params.get('proxy_server')
                self.progress.emit(f"프록시 사용: {proxy_server}")
                context_options['proxy'] = {'server': proxy_server}

            # 새 컨텍스트 생성 - 실제 사용자처럼
            context = await browser.new_context(**context_options)

            # 웹드라이버 감지 방지
            await context.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined
                });

                window.navigator.chrome = {
                    runtime: {}
                };

                Object.defineProperty(navigator, 'plugins', {
                    get: () => [1, 2, 3, 4, 5]
                });

                Object.defineProperty(navigator, 'languages', {
                    get: () => ['ko-KR', 'ko', 'en-US', 'en']
                });
            """)

            page = await context.new_page()

            try:
                # 쿠팡 메인 페이지 먼저 방문 (실제 사용자처럼)
                self.progress.emit("쿠팡 메인 페이지 접속 중...")
                await page.goto("https://www.coupang.com", timeout=60000)

                # 초기 대기 시간 (IP 차단 방지)
                initial_wait = self.search_params.get('initial_wait', 3.0)
                self.progress.emit(f"페이지 로딩 대기 중... ({initial_wait:.1f}초)")
                await asyncio.sleep(initial_wait)
                await self.random_delay()

                # 마우스 움직임 시뮬레이션
                await self.human_like_mouse_move(page)

                # 검색 페이지로 이동
                search_url = f"https://www.coupang.com/np/search?q={query}"
                self.progress.emit(f"'{query}' 검색 중...")

                await page.goto(search_url, wait_until='domcontentloaded', timeout=60000)
                await self.random_delay()  # 설정된 딜레이 사용

                # 페이지를 천천히 스크롤 (실제 사람처럼)
                self.progress.emit("페이지 스크롤 중...")
                scroll_delay = self.search_params.get('scroll_delay', 1.5)
                await self.smooth_scroll(page, 200)
                await asyncio.sleep(scroll_delay)

                # 제품 목록이 로딩될 때까지 대기
                await page.wait_for_selector('li.search-product', timeout=30000)

                self.progress.emit("제품 정보 수집 중...")

                # 제품 목록 가져오기
                products = await page.query_selector_all('li.search-product')

                if not products:
                    self.progress.emit("검색 결과가 없습니다.")
                    await browser.close()
                    return results

                self.progress.emit(f"{len(products)}개 제품 발견. 필터링 중...")

                for idx, product in enumerate(products[:max_results * 2]):  # 필터링을 고려해 더 많이 수집
                    try:
                        # 각 제품을 볼 때마다 짧은 딜레이 (사람처럼)
                        if idx % 5 == 0 and idx > 0:
                            await self.random_delay(0.5, 1.5)
                            # 가끔 마우스 움직임
                            await self.human_like_mouse_move(page)
                        # 로켓배송 체크
                        is_rocket = await product.query_selector('.badge.rocket') is not None
                        is_rocket_direct = await product.query_selector('.badge.rocket-direct') is not None
                        is_rocket_global = await product.query_selector('.badge.rocket-global') is not None
                        is_rocket_fresh = await product.query_selector('.badge.rocket-fresh') is not None

                        # 필터링 조건 체크
                        if exclude_rocket and is_rocket:
                            continue
                        if exclude_rocket_direct and (is_rocket_direct or is_rocket_global or is_rocket_fresh):
                            continue

                        # 제품 정보 추출
                        name_elem = await product.query_selector('.name')
                        name = await name_elem.inner_text() if name_elem else "제목 없음"

                        price_elem = await product.query_selector('.price-value')
                        price_text = await price_elem.inner_text() if price_elem else "0"
                        price = int(price_text.replace(',', '').replace('원', '').strip())

                        # 가격 필터링
                        if price < min_price or price > max_price:
                            continue

                        # 링크 추출
                        link_elem = await product.query_selector('a.search-product-link')
                        product_url = ""
                        if link_elem:
                            href = await link_elem.get_attribute('href')
                            if href:
                                product_url = f"https://www.coupang.com{href}" if href.startswith('/') else href

                        # 평점 추출
                        rating_elem = await product.query_selector('.rating')
                        rating = await rating_elem.inner_text() if rating_elem else "N/A"

                        # 리뷰 수 추출
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
                            'name': name.strip(),
                            'price': price,
                            'seller_type': seller_type,
                            'rating': rating.strip(),
                            'review_count': review_count.strip(),
                            'url': product_url
                        })

                        self.progress.emit(f"처리 중... {len(results)}개 일반 판매자 제품 발견")

                        # 목표 개수 달성 시 중단
                        if len(results) >= max_results:
                            break

                    except Exception as e:
                        self.progress.emit(f"제품 처리 중 오류: {str(e)}")
                        continue

                # 가격 순으로 정렬
                results.sort(key=lambda x: x['price'])

            except Exception as e:
                self.progress.emit(f"페이지 처리 중 오류: {str(e)}")
            finally:
                await browser.close()

        return results


class CoupangWingFinder(QMainWindow):
    def __init__(self):
        super().__init__()
        self.config_file = 'coupang_wing_config.json'
        self.load_config()
        self.init_ui()

    def load_config(self):
        """설정 파일 로드"""
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
            'initial_wait': 3.0
        }

        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    self.config = {**default_config, **json.load(f)}
            except:
                self.config = default_config
        else:
            self.config = default_config

    def save_config(self):
        """설정 파일 저장"""
        with open(self.config_file, 'w', encoding='utf-8') as f:
            json.dump(self.config, f, ensure_ascii=False, indent=2)

    def update_proxy_status_display(self):
        """프록시 상태 표시 업데이트"""
        if self.config.get('use_proxy', False) and self.config.get('proxy_server'):
            proxy_server = self.config.get('proxy_server')
            # 프록시 서버 주소 마스킹 (보안)
            if len(proxy_server) > 30:
                display_proxy = proxy_server[:20] + '...' + proxy_server[-10:]
            else:
                display_proxy = proxy_server

            self.proxy_status_label.setText(f"🔒 프록시 사용 중: {display_proxy}")
            self.proxy_status_label.setStyleSheet("background-color: #cfe2ff; padding: 5px; color: #084298;")
        else:
            self.proxy_status_label.setText("⚠️ 프록시 미사용 (IP 차단 위험)")
            self.proxy_status_label.setStyleSheet("background-color: #fff3cd; padding: 5px; color: #664d03;")

    def init_ui(self):
        """UI 초기화"""
        self.setWindowTitle('쿠팡 일반 판매자 제품 찾기')
        self.setGeometry(100, 100, 1200, 700)

        # 메인 위젯
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        layout = QVBoxLayout(main_widget)

        # 상태 표시 영역
        status_widget = QWidget()
        status_layout = QVBoxLayout(status_widget)
        status_layout.setContentsMargins(0, 0, 0, 0)
        status_layout.setSpacing(5)

        # Playwright 상태 표시
        if PLAYWRIGHT_AVAILABLE:
            playwright_label = QLabel("✅ Playwright 사용 가능")
            playwright_label.setStyleSheet("background-color: #d4edda; padding: 5px; color: #155724;")
        else:
            playwright_label = QLabel("❌ Playwright 미설치 (pip install playwright && playwright install chromium)")
            playwright_label.setStyleSheet("background-color: #f8d7da; padding: 5px; color: #721c24;")
        status_layout.addWidget(playwright_label)

        # 프록시 상태 표시
        self.proxy_status_label = QLabel()
        self.update_proxy_status_display()
        status_layout.addWidget(self.proxy_status_label)

        layout.addWidget(status_widget)

        # 탭 위젯
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)

        # 각 탭 생성
        self.create_search_tab()
        self.create_settings_tab()
        self.create_results_tab()

        # 상태바
        self.statusBar().showMessage('준비')

    def create_search_tab(self):
        """검색 탭"""
        tab = QWidget()
        layout = QVBoxLayout(tab)

        # 검색 입력
        search_group = QGroupBox("🔍 제품 검색")
        search_layout = QGridLayout()

        search_layout.addWidget(QLabel("검색 키워드:"), 0, 0)
        self.keyword_input = QLineEdit()
        self.keyword_input.setPlaceholderText("검색할 제품을 입력하세요 (예: 무선 이어폰, 노트북, 텀블러)")
        search_layout.addWidget(self.keyword_input, 0, 1)

        search_btn = QPushButton("검색 시작")
        search_btn.clicked.connect(self.search_products)
        search_btn.setStyleSheet("background-color: #4CAF50; color: white; padding: 10px; font-weight: bold; font-size: 14px;")
        search_layout.addWidget(search_btn, 0, 2)

        search_group.setLayout(search_layout)
        layout.addWidget(search_group)

        # 빠른 검색 예제
        examples_group = QGroupBox("💡 빠른 검색 예제")
        examples_layout = QVBoxLayout()

        example_categories = {
            "전자제품": ["무선 이어폰", "블루투스 스피커", "보조배터리", "USB 케이블", "마우스"],
            "생활용품": ["텀블러", "물티슈", "휴지", "세제", "샴푸"],
            "식품": ["과자", "라면", "커피", "견과류", "초콜릿"],
            "패션": ["양말", "목도리", "장갑", "모자", "가방"],
            "문구/사무": ["볼펜", "노트", "파일", "포스트잇", "책상정리함"]
        }

        for category, keywords in example_categories.items():
            category_widget = QWidget()
            category_layout = QHBoxLayout(category_widget)
            category_layout.setContentsMargins(0, 5, 0, 5)

            category_label = QLabel(f"{category}:")
            category_label.setFixedWidth(100)
            category_label.setStyleSheet("font-weight: bold;")
            category_layout.addWidget(category_label)

            for keyword in keywords:
                btn = QPushButton(keyword)
                btn.setMaximumWidth(120)
                btn.setStyleSheet("""
                    QPushButton {
                        background-color: #f0f0f0;
                        border: 1px solid #ccc;
                        border-radius: 4px;
                        padding: 5px 10px;
                    }
                    QPushButton:hover {
                        background-color: #e0e0e0;
                    }
                """)
                btn.clicked.connect(lambda checked, k=keyword: self.set_keyword(k))
                category_layout.addWidget(btn)

            category_layout.addStretch()
            examples_layout.addWidget(category_widget)

        examples_group.setLayout(examples_layout)
        layout.addWidget(examples_group)

        # 진행 상황
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

        self.progress_label = QLabel("")
        layout.addWidget(self.progress_label)

        layout.addStretch()

        self.tabs.addTab(tab, "검색")

    def set_keyword(self, keyword):
        """검색 키워드 설정"""
        self.keyword_input.setText(keyword)
        self.statusBar().showMessage(f"키워드 선택: {keyword}")

    def create_settings_tab(self):
        """설정 탭"""
        tab = QWidget()
        layout = QVBoxLayout(tab)

        # 필터 설정
        filter_group = QGroupBox("🎯 필터 설정")
        filter_layout = QGridLayout()

        row = 0
        filter_layout.addWidget(QLabel("최대 결과 수:"), row, 0)
        self.max_results_spin = QSpinBox()
        self.max_results_spin.setRange(1, 100)
        self.max_results_spin.setValue(self.config['max_results'])
        filter_layout.addWidget(self.max_results_spin, row, 1)

        row += 1
        self.exclude_rocket_check = QCheckBox("로켓배송 제외")
        self.exclude_rocket_check.setChecked(self.config['exclude_rocket'])
        filter_layout.addWidget(self.exclude_rocket_check, row, 0)

        self.exclude_rocket_direct_check = QCheckBox("로켓직구/글로벌/프레시 제외")
        self.exclude_rocket_direct_check.setChecked(self.config['exclude_rocket_direct'])
        filter_layout.addWidget(self.exclude_rocket_direct_check, row, 1)

        row += 1
        filter_layout.addWidget(QLabel("최소 가격:"), row, 0)
        self.min_price_spin = QSpinBox()
        self.min_price_spin.setRange(0, 10000000)
        self.min_price_spin.setValue(self.config['min_price'])
        self.min_price_spin.setSuffix(" 원")
        filter_layout.addWidget(self.min_price_spin, row, 1)

        row += 1
        filter_layout.addWidget(QLabel("최대 가격:"), row, 0)
        self.max_price_spin = QSpinBox()
        self.max_price_spin.setRange(0, 10000000)
        self.max_price_spin.setValue(self.config['max_price'] if self.config['max_price'] < 10000000 else 10000000)
        self.max_price_spin.setSuffix(" 원")
        filter_layout.addWidget(self.max_price_spin, row, 1)

        filter_group.setLayout(filter_layout)
        layout.addWidget(filter_group)

        # 고급 설정
        advanced_group = QGroupBox("⚙️ 고급 설정")
        advanced_layout = QVBoxLayout()

        self.headless_check = QCheckBox("백그라운드 실행 (브라우저 숨김)")
        self.headless_check.setChecked(self.config['headless'])
        self.headless_check.setToolTip("체크 해제 시 브라우저가 화면에 표시됩니다.")
        advanced_layout.addWidget(self.headless_check)

        info_label = QLabel("💡 백그라운드 실행 해제 시 스크래핑 과정을 직접 볼 수 있습니다.")
        info_label.setStyleSheet("color: #666; font-size: 10px;")
        advanced_layout.addWidget(info_label)

        advanced_group.setLayout(advanced_layout)
        layout.addWidget(advanced_group)

        # IP 차단 방지 설정
        ip_protection_group = QGroupBox("🛡️ IP 차단 방지 설정")
        ip_layout = QGridLayout()

        row = 0
        # 프록시 설정
        self.use_proxy_check = QCheckBox("프록시 사용")
        self.use_proxy_check.setChecked(self.config.get('use_proxy', False))
        ip_layout.addWidget(self.use_proxy_check, row, 0)

        ip_layout.addWidget(QLabel("프록시 서버:"), row, 1)
        self.proxy_input = QLineEdit()
        self.proxy_input.setText(self.config.get('proxy_server', ''))
        self.proxy_input.setPlaceholderText("예: http://proxy.example.com:8080 또는 socks5://1.2.3.4:1080")
        ip_layout.addWidget(self.proxy_input, row, 2)

        row += 1
        # 딜레이 설정
        from PyQt5.QtWidgets import QDoubleSpinBox

        ip_layout.addWidget(QLabel("최소 딜레이 (초):"), row, 0)
        self.min_delay_spin = QDoubleSpinBox()
        self.min_delay_spin.setRange(0.5, 30.0)
        self.min_delay_spin.setValue(self.config.get('min_delay', 2.0))
        self.min_delay_spin.setSuffix(" 초")
        self.min_delay_spin.setDecimals(1)
        ip_layout.addWidget(self.min_delay_spin, row, 1)

        ip_layout.addWidget(QLabel("최대 딜레이 (초):"), row, 2)
        self.max_delay_spin = QDoubleSpinBox()
        self.max_delay_spin.setRange(1.0, 60.0)
        self.max_delay_spin.setValue(self.config.get('max_delay', 5.0))
        self.max_delay_spin.setSuffix(" 초")
        self.max_delay_spin.setDecimals(1)
        ip_layout.addWidget(self.max_delay_spin, row, 3)

        row += 1
        ip_layout.addWidget(QLabel("스크롤 딜레이 (초):"), row, 0)
        self.scroll_delay_spin = QDoubleSpinBox()
        self.scroll_delay_spin.setRange(0.5, 10.0)
        self.scroll_delay_spin.setValue(self.config.get('scroll_delay', 1.5))
        self.scroll_delay_spin.setSuffix(" 초")
        self.scroll_delay_spin.setDecimals(1)
        ip_layout.addWidget(self.scroll_delay_spin, row, 1)

        ip_layout.addWidget(QLabel("초기 대기 시간 (초):"), row, 2)
        self.initial_wait_spin = QDoubleSpinBox()
        self.initial_wait_spin.setRange(1.0, 30.0)
        self.initial_wait_spin.setValue(self.config.get('initial_wait', 3.0))
        self.initial_wait_spin.setSuffix(" 초")
        self.initial_wait_spin.setDecimals(1)
        ip_layout.addWidget(self.initial_wait_spin, row, 3)

        row += 1
        # 안내 메시지
        protection_info = QLabel(
            "💡 IP 차단 방지 팁:\n"
            "• 딜레이를 길게 설정할수록 안전합니다 (권장: 최소 2초, 최대 5초 이상)\n"
            "• 프록시를 사용하면 IP 차단 위험이 줄어듭니다\n"
            "• 한 번에 너무 많은 제품을 검색하지 마세요 (권장: 20개 이하)\n"
            "• 짧은 시간에 반복 검색을 피하세요 (최소 5분 간격 권장)"
        )
        protection_info.setStyleSheet("color: #555; font-size: 10px; padding: 5px; background-color: #fff3cd; border-radius: 3px;")
        protection_info.setWordWrap(True)
        ip_layout.addWidget(protection_info, row, 0, 1, 4)

        ip_protection_group.setLayout(ip_layout)
        layout.addWidget(ip_protection_group)

        # 저장 버튼
        save_btn = QPushButton("설정 저장")
        save_btn.clicked.connect(self.save_settings)
        layout.addWidget(save_btn)

        layout.addStretch()

        self.tabs.addTab(tab, "설정")

    def create_results_tab(self):
        """결과 탭"""
        tab = QWidget()
        layout = QVBoxLayout(tab)

        # 결과 테이블
        self.results_table = QTableWidget()
        self.results_table.setColumnCount(7)
        self.results_table.setHorizontalHeaderLabels([
            '제품명', '가격', '판매자 유형', '평점', '리뷰 수', 'URL', '바로가기'
        ])

        # 테이블 설정
        header = self.results_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(5, QHeaderView.ResizeToContents)

        self.results_table.setAlternatingRowColors(True)
        self.results_table.setSelectionBehavior(QTableWidget.SelectRows)

        layout.addWidget(self.results_table)

        # 버튼
        btn_layout = QHBoxLayout()

        export_btn = QPushButton("💾 CSV로 내보내기")
        export_btn.clicked.connect(self.export_results)
        btn_layout.addWidget(export_btn)

        clear_btn = QPushButton("🗑️ 결과 지우기")
        clear_btn.clicked.connect(self.clear_results)
        btn_layout.addWidget(clear_btn)

        btn_layout.addStretch()

        layout.addLayout(btn_layout)

        self.tabs.addTab(tab, "결과")

    def search_products(self):
        """제품 검색"""
        if not PLAYWRIGHT_AVAILABLE:
            QMessageBox.critical(
                self,
                "오류",
                "Playwright가 설치되어 있지 않습니다.\n\n다음 명령을 실행하세요:\n"
                "pip install playwright\n"
                "playwright install chromium"
            )
            return

        keyword = self.keyword_input.text().strip()
        if not keyword:
            QMessageBox.warning(self, "경고", "검색 키워드를 입력하세요")
            return

        search_params = {
            'query': keyword,
            'max_results': self.max_results_spin.value(),
            'exclude_rocket': self.exclude_rocket_check.isChecked(),
            'exclude_rocket_direct': self.exclude_rocket_direct_check.isChecked(),
            'min_price': self.min_price_spin.value(),
            'max_price': self.max_price_spin.value(),
            'headless': self.headless_check.isChecked(),
            'use_proxy': self.use_proxy_check.isChecked(),
            'proxy_server': self.proxy_input.text().strip(),
            'min_delay': self.min_delay_spin.value(),
            'max_delay': self.max_delay_spin.value(),
            'scroll_delay': self.scroll_delay_spin.value(),
            'initial_wait': self.initial_wait_spin.value()
        }

        # 프록시 정보 표시
        if search_params.get('use_proxy') and search_params.get('proxy_server'):
            proxy_info = f"프록시 사용: {search_params.get('proxy_server')}"
            self.statusBar().showMessage(f"'{keyword}' 검색 중... ({proxy_info})")
        else:
            self.statusBar().showMessage(f"'{keyword}' 검색 중... (프록시 미사용)")

        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)

        self.worker = CoupangScraperWorker(search_params)
        self.worker.progress.connect(self.on_progress)
        self.worker.result.connect(self.on_search_complete)
        self.worker.error.connect(self.on_search_error)
        self.worker.start()

    def on_progress(self, message):
        """진행 상황 업데이트"""
        self.progress_label.setText(message)
        self.statusBar().showMessage(message)

    def on_search_complete(self, results):
        """검색 완료"""
        self.progress_bar.setVisible(False)
        self.progress_label.setText("")

        if not results:
            QMessageBox.information(self, "알림", "검색 조건에 맞는 일반 판매자 제품이 없습니다")
            self.statusBar().showMessage("검색 완료 - 결과 없음")
            return

        self.display_results(results)
        self.statusBar().showMessage(f"검색 완료 - {len(results)}개 일반 판매자 제품 발견")
        self.tabs.setCurrentIndex(2)

    def on_search_error(self, error_msg):
        """검색 오류"""
        self.progress_bar.setVisible(False)
        self.progress_label.setText("")
        QMessageBox.critical(self, "오류", error_msg)
        self.statusBar().showMessage("검색 실패")

    def display_results(self, results):
        """결과를 테이블에 표시"""
        self.results_table.setRowCount(len(results))

        for row, result in enumerate(results):
            self.results_table.setItem(row, 0, QTableWidgetItem(result['name']))
            self.results_table.setItem(row, 1, QTableWidgetItem(f"{result['price']:,}원"))
            self.results_table.setItem(row, 2, QTableWidgetItem(result['seller_type']))
            self.results_table.setItem(row, 3, QTableWidgetItem(result['rating']))
            self.results_table.setItem(row, 4, QTableWidgetItem(result['review_count']))
            self.results_table.setItem(row, 5, QTableWidgetItem(result['url']))

            # 바로가기 버튼
            open_btn = QPushButton("🔗 열기")
            open_btn.clicked.connect(lambda checked, u=result['url']: webbrowser.open(u))
            self.results_table.setCellWidget(row, 6, open_btn)

        # 자동 저장
        self.auto_save_results()

    def auto_save_results(self):
        """결과 자동 저장"""
        try:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f'coupang_results_{timestamp}.csv'

            with open(filename, 'w', encoding='utf-8-sig', newline='') as f:
                writer = csv.writer(f)

                # 헤더
                headers = []
                for col in range(self.results_table.columnCount() - 1):
                    headers.append(self.results_table.horizontalHeaderItem(col).text())
                writer.writerow(headers)

                # 데이터
                for row in range(self.results_table.rowCount()):
                    row_data = []
                    for col in range(self.results_table.columnCount() - 1):
                        item = self.results_table.item(row, col)
                        row_data.append(item.text() if item else "")
                    writer.writerow(row_data)

            self.statusBar().showMessage(f"결과가 자동으로 저장되었습니다: {filename}", 3000)
        except Exception as e:
            print(f"자동 저장 중 오류: {str(e)}")

    def save_settings(self):
        """설정 저장"""
        self.config['max_results'] = self.max_results_spin.value()
        self.config['exclude_rocket'] = self.exclude_rocket_check.isChecked()
        self.config['exclude_rocket_direct'] = self.exclude_rocket_direct_check.isChecked()
        self.config['min_price'] = self.min_price_spin.value()
        self.config['max_price'] = self.max_price_spin.value()
        self.config['headless'] = self.headless_check.isChecked()

        # IP 차단 방지 설정
        self.config['use_proxy'] = self.use_proxy_check.isChecked()
        self.config['proxy_server'] = self.proxy_input.text().strip()
        self.config['min_delay'] = self.min_delay_spin.value()
        self.config['max_delay'] = self.max_delay_spin.value()
        self.config['scroll_delay'] = self.scroll_delay_spin.value()
        self.config['initial_wait'] = self.initial_wait_spin.value()

        self.save_config()
        self.update_proxy_status_display()  # 프록시 상태 표시 업데이트
        QMessageBox.information(self, "알림", "설정이 저장되었습니다")
        self.statusBar().showMessage("설정 저장 완료")

    def export_results(self):
        """결과 내보내기"""
        if self.results_table.rowCount() == 0:
            QMessageBox.warning(self, "경고", "내보낼 결과가 없습니다")
            return

        filename, _ = QFileDialog.getSaveFileName(
            self,
            "CSV 파일로 저장",
            f"coupang_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
            "CSV Files (*.csv)"
        )

        if not filename:
            return

        try:
            with open(filename, 'w', encoding='utf-8-sig', newline='') as f:
                writer = csv.writer(f)

                # 헤더
                headers = []
                for col in range(self.results_table.columnCount() - 1):
                    headers.append(self.results_table.horizontalHeaderItem(col).text())
                writer.writerow(headers)

                # 데이터
                for row in range(self.results_table.rowCount()):
                    row_data = []
                    for col in range(self.results_table.columnCount() - 1):
                        item = self.results_table.item(row, col)
                        row_data.append(item.text() if item else "")
                    writer.writerow(row_data)

            QMessageBox.information(self, "알림", f"결과가 {filename}로 저장되었습니다")
            self.statusBar().showMessage(f"결과 내보내기 완료: {filename}")
        except Exception as e:
            QMessageBox.critical(self, "오류", f"파일 저장 중 오류: {str(e)}")

    def clear_results(self):
        """결과 지우기"""
        self.results_table.setRowCount(0)
        self.statusBar().showMessage("결과가 지워졌습니다")


def main():
    app = QApplication(sys.argv)

    # 폰트 설정
    font = QFont("맑은 고딕", 9)
    app.setFont(font)

    window = CoupangWingFinder()
    window.show()

    sys.exit(app.exec_())


if __name__ == '__main__':
    main()
