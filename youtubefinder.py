#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
YouTube Hot Finder - 인기 YouTube 영상 검색 도구
"""

import sys
import json
import os
from datetime import datetime, timedelta
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                             QHBoxLayout, QTabWidget, QLabel, QLineEdit,
                             QPushButton, QTableWidget, QTableWidgetItem,
                             QComboBox, QCheckBox, QSpinBox, QDoubleSpinBox,
                             QTextEdit, QGroupBox, QGridLayout, QMessageBox,
                             QHeaderView, QProgressBar)
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtGui import QFont
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
import time

class YouTubeAPIWorker(QThread):
    """YouTube API 작업을 별도 스레드에서 처리"""
    progress = pyqtSignal(str)
    result = pyqtSignal(list)
    error = pyqtSignal(str)

    def __init__(self, api_key, search_params):
        super().__init__()
        self.api_key = api_key
        self.search_params = search_params

    def run(self):
        try:
            youtube = build('youtube', 'v3', developerKey=self.api_key)
            results = []

            # 키워드 검색
            if self.search_params['mode'] == 'keyword':
                self.progress.emit("키워드로 영상 검색 중...")
                search_response = youtube.search().list(
                    q=self.search_params['query'],
                    part='snippet',
                    maxResults=self.search_params['max_results'],
                    type='video',
                    order=self.search_params.get('order', 'relevance'),
                    regionCode=self.search_params.get('region', 'KR'),
                    relevanceLanguage=self.search_params.get('language', 'ko')
                ).execute()

                video_ids = [item['id']['videoId'] for item in search_response.get('items', [])]

            # 채널 검색
            elif self.search_params['mode'] == 'channel':
                self.progress.emit("채널 영상 검색 중...")
                channel_response = youtube.search().list(
                    channelId=self.search_params['channel_id'],
                    part='snippet',
                    maxResults=self.search_params['max_results'],
                    type='video',
                    order='date'
                ).execute()

                video_ids = [item['id']['videoId'] for item in channel_response.get('items', [])]

            # 영상 상세 정보 가져오기
            if video_ids:
                self.progress.emit(f"{len(video_ids)}개 영상의 상세 정보 수집 중...")
                videos_response = youtube.videos().list(
                    part='snippet,statistics,contentDetails',
                    id=','.join(video_ids)
                ).execute()

                for video in videos_response.get('items', []):
                    try:
                        # 채널 정보 가져오기
                        channel_id = video['snippet']['channelId']
                        channel_response = youtube.channels().list(
                            part='statistics',
                            id=channel_id
                        ).execute()

                        if channel_response['items']:
                            subscriber_count = int(channel_response['items'][0]['statistics'].get('subscriberCount', 0))
                        else:
                            subscriber_count = 0

                        # 조회수 및 시간당 조회수 계산
                        view_count = int(video['statistics'].get('viewCount', 0))
                        published_at = datetime.strptime(video['snippet']['publishedAt'], '%Y-%m-%dT%H:%M:%SZ')
                        hours_since_published = max(1, (datetime.utcnow() - published_at).total_seconds() / 3600)
                        views_per_hour = view_count / hours_since_published

                        # 조회수/구독자수 비율
                        views_per_subscriber = view_count / subscriber_count if subscriber_count > 0 else 0

                        # 필터링
                        if view_count < self.search_params.get('min_views', 0):
                            continue
                        if views_per_hour < self.search_params.get('min_views_per_hour', 0):
                            continue

                        results.append({
                            'channel_name': video['snippet']['channelTitle'],
                            'title': video['snippet']['title'],
                            'video_id': video['id'],
                            'published_at': published_at.strftime('%Y-%m-%d %H:%M'),
                            'view_count': view_count,
                            'views_per_hour': round(views_per_hour, 2),
                            'subscriber_count': subscriber_count,
                            'views_per_subscriber': round(views_per_subscriber, 4),
                            'like_count': int(video['statistics'].get('likeCount', 0)),
                            'comment_count': int(video['statistics'].get('commentCount', 0))
                        })

                    except Exception as e:
                        self.progress.emit(f"영상 처리 중 오류: {str(e)}")
                        continue

                # 시간당 조회수 기준으로 정렬
                results.sort(key=lambda x: x['views_per_hour'], reverse=True)

            self.result.emit(results)

        except HttpError as e:
            self.error.emit(f"YouTube API 오류: {str(e)}")
        except Exception as e:
            self.error.emit(f"오류 발생: {str(e)}")


class YouTubeHotFinder(QMainWindow):
    def __init__(self):
        super().__init__()
        self.config_file = 'youtube_finder_config.json'
        self.load_config()
        self.init_ui()

    def load_config(self):
        """설정 파일 로드"""
        default_config = {
            'api_keys': [],
            'current_api_key_index': 0,
            'execution_mode': '종류',
            'videos_per_channel': 10,
            'max_searches_per_keyword': 10,
            'min_views_per_hour': 600.0,
            'api_wait_time': 30,
            'target_country': 'KR',
            'max_results_per_search': 50,
            'show_popular_by_channel': False,
            'language': 'ko',
            'min_views': 20000
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

    def init_ui(self):
        """UI 초기화"""
        self.setWindowTitle('YouTube Hot Finder')
        self.setGeometry(100, 100, 1400, 800)

        # 메인 위젯
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        layout = QVBoxLayout(main_widget)

        # 탭 위젯
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)

        # 각 탭 생성
        self.create_channel_tab()
        self.create_keyword_tab()
        self.create_settings_tab()
        self.create_results_tab()

        # 상태바
        self.statusBar().showMessage('준비')

    def create_channel_tab(self):
        """채널명등명 탭"""
        tab = QWidget()
        layout = QVBoxLayout(tab)

        # 채널 입력
        input_group = QGroupBox("채널 등록")
        input_layout = QGridLayout()

        input_layout.addWidget(QLabel("채널 ID 또는 URL:"), 0, 0)
        self.channel_input = QLineEdit()
        self.channel_input.setPlaceholderText("채널 ID 또는 URL을 입력하세요")
        input_layout.addWidget(self.channel_input, 0, 1)

        add_btn = QPushButton("채널 추가")
        add_btn.clicked.connect(self.add_channel)
        input_layout.addWidget(add_btn, 0, 2)

        input_group.setLayout(input_layout)
        layout.addWidget(input_group)

        # 등록된 채널 목록
        list_group = QGroupBox("등록된 채널")
        list_layout = QVBoxLayout()

        self.channel_list = QTextEdit()
        self.channel_list.setReadOnly(True)
        list_layout.addWidget(self.channel_list)

        btn_layout = QHBoxLayout()
        search_channel_btn = QPushButton("선택한 채널 검색")
        search_channel_btn.clicked.connect(self.search_channels)
        btn_layout.addWidget(search_channel_btn)

        clear_btn = QPushButton("목록 초기화")
        clear_btn.clicked.connect(self.clear_channels)
        btn_layout.addWidget(clear_btn)

        list_layout.addLayout(btn_layout)
        list_group.setLayout(list_layout)
        layout.addWidget(list_group)

        self.tabs.addTab(tab, "채널명등명")

    def create_keyword_tab(self):
        """키워드입력 탭"""
        tab = QWidget()
        layout = QVBoxLayout(tab)

        # 검색 예제 선택
        example_group = QGroupBox("🎯 인기 검색 예제 (클릭하여 자동 입력)")
        example_layout = QVBoxLayout()

        # 45개의 검색 예제 (9개 카테고리)
        self.search_examples = {
            "🎮 게임": [
                "스타크래프트 프로게이머",
                "리그오브레전드 하이라이트",
                "마인크래프트 서바이벌",
                "오버워치 플레이",
                "배틀그라운드 꿀팁"
            ],
            "📚 교육": [
                "파이썬 기초 강의",
                "영어회화 공부",
                "주식 투자 초보",
                "포토샵 튜토리얼",
                "엑셀 함수 정리"
            ],
            "🍳 요리": [
                "간단한 요리 레시피",
                "다이어트 식단",
                "백종원 요리",
                "홈베이킹 디저트",
                "한식 요리법"
            ],
            "🎵 음악": [
                "커버곡 노래",
                "버스킹 공연",
                "힙합 랩 메이킹",
                "기타 연주",
                "K-POP 댄스"
            ],
            "💪 운동/건강": [
                "홈트레이닝 루틴",
                "다이어트 운동",
                "요가 스트레칭",
                "헬스 초보 가이드",
                "러닝 마라톤"
            ],
            "💰 재테크": [
                "부동산 투자",
                "코인 비트코인",
                "재테크 노하우",
                "주식 차트 분석",
                "경제 뉴스 해설"
            ],
            "🎬 엔터테인먼트": [
                "예능 클립 모음",
                "영화 리뷰 평론",
                "드라마 명장면",
                "웹예능 콘텐츠",
                "유튜버 브이로그"
            ],
            "🇰🇷 국뽕": [
                "외국인 한국 반응",
                "K-POP 세계 반응",
                "한국 문화 자랑",
                "한국 음식 리뷰",
                "한글날 한국어"
            ],
            "👴 시니어": [
                "건강 정보 노인",
                "스마트폰 사용법 초보",
                "연금 노후 준비",
                "손자녀 육아팁",
                "시니어 여행 추천"
            ]
        }

        # 카테고리별 버튼 생성
        for category, keywords in self.search_examples.items():
            category_widget = QWidget()
            category_layout = QHBoxLayout(category_widget)
            category_layout.setContentsMargins(0, 5, 0, 5)

            category_label = QLabel(category)
            category_label.setFixedWidth(150)
            category_label.setStyleSheet("font-weight: bold; font-size: 11px;")
            category_layout.addWidget(category_label)

            for keyword in keywords:
                btn = QPushButton(keyword)
                btn.setMaximumWidth(150)
                btn.setStyleSheet("""
                    QPushButton {
                        background-color: #f0f0f0;
                        border: 1px solid #ccc;
                        border-radius: 4px;
                        padding: 5px 10px;
                        font-size: 10px;
                    }
                    QPushButton:hover {
                        background-color: #e0e0e0;
                        border-color: #999;
                    }
                    QPushButton:pressed {
                        background-color: #d0d0d0;
                    }
                """)
                btn.clicked.connect(lambda checked, k=keyword: self.set_keyword(k))
                category_layout.addWidget(btn)

            category_layout.addStretch()
            example_layout.addWidget(category_widget)

        example_group.setLayout(example_layout)
        layout.addWidget(example_group)

        # 키워드 입력
        input_group = QGroupBox("키워드 검색")
        input_layout = QGridLayout()

        input_layout.addWidget(QLabel("검색 키워드:"), 0, 0)
        self.keyword_input = QLineEdit()
        self.keyword_input.setPlaceholderText("검색할 키워드를 입력하세요 (위 예제 버튼 클릭 또는 직접 입력)")
        input_layout.addWidget(self.keyword_input, 0, 1)

        search_btn = QPushButton("검색 시작")
        search_btn.clicked.connect(self.search_keyword)
        search_btn.setStyleSheet("background-color: #4CAF50; color: white; padding: 8px; font-weight: bold;")
        input_layout.addWidget(search_btn, 0, 2)

        input_group.setLayout(input_layout)
        layout.addWidget(input_group)

        # 정렬 옵션
        sort_group = QGroupBox("정렬 기준")
        sort_layout = QHBoxLayout()

        sort_layout.addWidget(QLabel("정렬:"))
        self.sort_combo = QComboBox()
        self.sort_combo.addItems(['관련성', '업로드 날짜', '조회수', '평점'])
        sort_layout.addWidget(self.sort_combo)
        sort_layout.addStretch()

        sort_group.setLayout(sort_layout)
        layout.addWidget(sort_group)

        # 진행 상황
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

        self.progress_label = QLabel("")
        layout.addWidget(self.progress_label)

        layout.addStretch()

        self.tabs.addTab(tab, "키워드입력")

    def set_keyword(self, keyword):
        """검색 예제 버튼 클릭 시 키워드 설정"""
        self.keyword_input.setText(keyword)
        self.statusBar().showMessage(f"키워드 선택됨: {keyword}")

    def create_settings_tab(self):
        """설정 탭"""
        tab = QWidget()
        layout = QVBoxLayout(tab)

        # 실행 설정
        exec_group = QGroupBox("실행 설정")
        exec_layout = QGridLayout()

        row = 0
        exec_layout.addWidget(QLabel("실행모드:"), row, 0)
        self.exec_mode_combo = QComboBox()
        self.exec_mode_combo.addItems(['지속', '쇼츠/숏폼', '종류'])
        exec_layout.addWidget(self.exec_mode_combo, row, 1)

        exec_layout.addWidget(QLabel("소츠/숏폼:"), row, 2)
        self.shorts_combo = QComboBox()
        self.shorts_combo.addItems(['종류', '쇼츠', '숏폼'])
        exec_layout.addWidget(self.shorts_combo, row, 3)

        exec_layout.addWidget(QLabel("쇼츠 기준(초):"), row, 4)
        self.shorts_duration = QSpinBox()
        self.shorts_duration.setRange(1, 600)
        self.shorts_duration.setValue(180)
        exec_layout.addWidget(self.shorts_duration, row, 5)

        row += 1
        exec_layout.addWidget(QLabel("정교 박르간의 영상을 분석까요:"), row, 0)
        self.videos_per_channel = QSpinBox()
        self.videos_per_channel.setRange(1, 100)
        self.videos_per_channel.setValue(self.config['videos_per_channel'])
        exec_layout.addWidget(self.videos_per_channel, row, 1)

        exec_layout.addWidget(QLabel("대상국가:"), row, 2)
        self.country_input = QLineEdit(self.config['target_country'])
        exec_layout.addWidget(self.country_input, row, 3)

        exec_layout.addWidget(QLabel("언어:"), row, 4)
        self.language_input = QLineEdit(self.config['language'])
        exec_layout.addWidget(self.language_input, row, 5)

        row += 1
        exec_layout.addWidget(QLabel("경명당 최대 검색 수:"), row, 0)
        self.max_searches = QSpinBox()
        self.max_searches.setRange(1, 100)
        self.max_searches.setValue(self.config['max_searches_per_keyword'])
        exec_layout.addWidget(self.max_searches, row, 1)

        exec_layout.addWidget(QLabel("검색어당 최대 검색 수:"), row, 2)
        self.max_results = QSpinBox()
        self.max_results.setRange(1, 50)
        self.max_results.setValue(self.config['max_results_per_search'])
        exec_layout.addWidget(self.max_results, row, 3)

        exec_layout.addWidget(QLabel("최소 조회수:"), row, 4)
        self.min_views = QSpinBox()
        self.min_views.setRange(0, 10000000)
        self.min_views.setValue(self.config['min_views'])
        exec_layout.addWidget(self.min_views, row, 5)

        row += 1
        exec_layout.addWidget(QLabel("최소 시간당 조회수:"), row, 0)
        self.min_views_per_hour = QDoubleSpinBox()
        self.min_views_per_hour.setRange(0, 1000000)
        self.min_views_per_hour.setValue(self.config['min_views_per_hour'])
        exec_layout.addWidget(self.min_views_per_hour, row, 1)

        self.show_popular_checkbox = QCheckBox("채널별 인기영상 보기")
        self.show_popular_checkbox.setChecked(self.config['show_popular_by_channel'])
        exec_layout.addWidget(self.show_popular_checkbox, row, 2, 1, 2)

        exec_group.setLayout(exec_layout)
        layout.addWidget(exec_group)

        # API 키 설정
        api_group = QGroupBox("API 키 관리")
        api_layout = QVBoxLayout()

        key_input_layout = QHBoxLayout()
        key_input_layout.addWidget(QLabel("API 키:"))
        self.api_key_input = QLineEdit()
        self.api_key_input.setPlaceholderText("YouTube Data API v3 키를 입력하세요")
        key_input_layout.addWidget(self.api_key_input)

        add_key_btn = QPushButton("추가")
        add_key_btn.clicked.connect(self.add_api_key)
        key_input_layout.addWidget(add_key_btn)

        api_layout.addLayout(key_input_layout)

        wait_layout = QHBoxLayout()
        wait_layout.addWidget(QLabel("API 키 쿼터 소진 시 대기시간 (분):"))
        self.api_wait_time = QSpinBox()
        self.api_wait_time.setRange(1, 1440)
        self.api_wait_time.setValue(self.config['api_wait_time'])
        wait_layout.addWidget(self.api_wait_time)
        wait_layout.addStretch()
        api_layout.addLayout(wait_layout)

        self.api_key_list = QTextEdit()
        self.api_key_list.setReadOnly(True)
        self.api_key_list.setMaximumHeight(100)
        api_layout.addWidget(QLabel("등록된 API 키:"))
        api_layout.addWidget(self.api_key_list)
        self.update_api_key_list()

        api_group.setLayout(api_layout)
        layout.addWidget(api_group)

        # 저장 버튼
        save_layout = QHBoxLayout()
        save_layout.addStretch()

        save_btn = QPushButton("설정 저장")
        save_btn.clicked.connect(self.save_settings)
        save_layout.addWidget(save_btn)

        load_btn = QPushButton("설정 불러오기")
        load_btn.clicked.connect(self.load_settings)
        save_layout.addWidget(load_btn)

        layout.addLayout(save_layout)
        layout.addStretch()

        self.tabs.addTab(tab, "설정")

    def create_results_tab(self):
        """결과 탭"""
        tab = QWidget()
        layout = QVBoxLayout(tab)

        # 결과 테이블
        self.results_table = QTableWidget()
        self.results_table.setColumnCount(10)
        self.results_table.setHorizontalHeaderLabels([
            '채널명', '제목', '업로드일', '조회수', '시간당 조회수',
            '구독자수', '조회수/구독자수', '오상 점이', '오상 점2', 'URL'
        ])

        # 테이블 설정
        header = self.results_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        header.setSectionResizeMode(9, QHeaderView.ResizeToContents)

        self.results_table.setAlternatingRowColors(True)
        self.results_table.setSelectionBehavior(QTableWidget.SelectRows)

        layout.addWidget(self.results_table)

        # 버튼
        btn_layout = QHBoxLayout()

        export_btn = QPushButton("결과 내보내기")
        export_btn.clicked.connect(self.export_results)
        btn_layout.addWidget(export_btn)

        clear_results_btn = QPushButton("결과 지우기")
        clear_results_btn.clicked.connect(self.clear_results)
        btn_layout.addWidget(clear_results_btn)

        btn_layout.addStretch()

        layout.addLayout(btn_layout)

        self.tabs.addTab(tab, "결과")

    def add_channel(self):
        """채널 추가"""
        channel = self.channel_input.text().strip()
        if channel:
            current_text = self.channel_list.toPlainText()
            if current_text:
                self.channel_list.setText(current_text + "\n" + channel)
            else:
                self.channel_list.setText(channel)
            self.channel_input.clear()
            self.statusBar().showMessage(f"채널 추가됨: {channel}")

    def clear_channels(self):
        """채널 목록 초기화"""
        self.channel_list.clear()
        self.statusBar().showMessage("채널 목록이 초기화되었습니다")

    def search_channels(self):
        """채널 검색"""
        channels = self.channel_list.toPlainText().strip().split('\n')
        channels = [ch.strip() for ch in channels if ch.strip()]

        if not channels:
            QMessageBox.warning(self, "경고", "검색할 채널이 없습니다")
            return

        if not self.config['api_keys']:
            QMessageBox.warning(self, "경고", "API 키를 먼저 등록해주세요")
            return

        self.statusBar().showMessage("채널 검색 중...")
        # 실제 구현은 여기에 추가

    def search_keyword(self):
        """키워드 검색"""
        keyword = self.keyword_input.text().strip()

        if not keyword:
            QMessageBox.warning(self, "경고", "검색 키워드를 입력하세요")
            return

        if not self.config['api_keys']:
            QMessageBox.warning(self, "경고", "API 키를 먼저 등록해주세요")
            return

        # 정렬 순서 매핑
        sort_order_map = {
            '관련성': 'relevance',
            '업로드 날짜': 'date',
            '조회수': 'viewCount',
            '평점': 'rating'
        }

        search_params = {
            'mode': 'keyword',
            'query': keyword,
            'max_results': self.max_results.value(),
            'order': sort_order_map[self.sort_combo.currentText()],
            'region': self.country_input.text(),
            'language': self.language_input.text(),
            'min_views': self.min_views.value(),
            'min_views_per_hour': self.min_views_per_hour.value()
        }

        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)  # Indeterminate progress
        self.statusBar().showMessage(f"'{keyword}' 검색 중...")

        # API 워커 스레드 시작
        api_key = self.config['api_keys'][self.config['current_api_key_index']]
        self.worker = YouTubeAPIWorker(api_key, search_params)
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
            QMessageBox.information(self, "알림", "검색 결과가 없습니다")
            self.statusBar().showMessage("검색 완료 - 결과 없음")
            return

        # 결과 테이블에 표시
        self.display_results(results)
        self.statusBar().showMessage(f"검색 완료 - {len(results)}개 결과")

        # 결과 탭으로 전환
        self.tabs.setCurrentIndex(3)

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
            self.results_table.setItem(row, 0, QTableWidgetItem(result['channel_name']))
            self.results_table.setItem(row, 1, QTableWidgetItem(result['title']))
            self.results_table.setItem(row, 2, QTableWidgetItem(result['published_at']))
            self.results_table.setItem(row, 3, QTableWidgetItem(f"{result['view_count']:,}"))
            self.results_table.setItem(row, 4, QTableWidgetItem(f"{result['views_per_hour']:.2f}"))
            self.results_table.setItem(row, 5, QTableWidgetItem(f"{result['subscriber_count']:,}"))
            self.results_table.setItem(row, 6, QTableWidgetItem(f"{result['views_per_subscriber']:.4f}"))
            self.results_table.setItem(row, 7, QTableWidgetItem(str(result['like_count'])))
            self.results_table.setItem(row, 8, QTableWidgetItem(str(result['comment_count'])))

            url = f"https://www.youtube.com/watch?v={result['video_id']}"
            self.results_table.setItem(row, 9, QTableWidgetItem(url))

    def add_api_key(self):
        """API 키 추가"""
        api_key = self.api_key_input.text().strip()

        if not api_key:
            QMessageBox.warning(self, "경고", "API 키를 입력하세요")
            return

        if api_key not in self.config['api_keys']:
            self.config['api_keys'].append(api_key)
            self.update_api_key_list()
            self.api_key_input.clear()
            self.statusBar().showMessage("API 키가 추가되었습니다")
        else:
            QMessageBox.information(self, "알림", "이미 등록된 API 키입니다")

    def update_api_key_list(self):
        """API 키 목록 업데이트"""
        if self.config['api_keys']:
            masked_keys = [f"{i+1}. {key[:10]}...{key[-5:]}" for i, key in enumerate(self.config['api_keys'])]
            self.api_key_list.setText('\n'.join(masked_keys))
        else:
            self.api_key_list.setText("등록된 API 키가 없습니다")

    def save_settings(self):
        """설정 저장"""
        self.config['execution_mode'] = self.exec_mode_combo.currentText()
        self.config['videos_per_channel'] = self.videos_per_channel.value()
        self.config['max_searches_per_keyword'] = self.max_searches.value()
        self.config['min_views_per_hour'] = self.min_views_per_hour.value()
        self.config['api_wait_time'] = self.api_wait_time.value()
        self.config['target_country'] = self.country_input.text()
        self.config['max_results_per_search'] = self.max_results.value()
        self.config['show_popular_by_channel'] = self.show_popular_checkbox.isChecked()
        self.config['language'] = self.language_input.text()
        self.config['min_views'] = self.min_views.value()

        self.save_config()
        QMessageBox.information(self, "알림", "설정이 저장되었습니다")
        self.statusBar().showMessage("설정 저장 완료")

    def load_settings(self):
        """설정 불러오기"""
        self.load_config()

        self.exec_mode_combo.setCurrentText(self.config['execution_mode'])
        self.videos_per_channel.setValue(self.config['videos_per_channel'])
        self.max_searches.setValue(self.config['max_searches_per_keyword'])
        self.min_views_per_hour.setValue(self.config['min_views_per_hour'])
        self.api_wait_time.setValue(self.config['api_wait_time'])
        self.country_input.setText(self.config['target_country'])
        self.max_results.setValue(self.config['max_results_per_search'])
        self.show_popular_checkbox.setChecked(self.config['show_popular_by_channel'])
        self.language_input.setText(self.config['language'])
        self.min_views.setValue(self.config['min_views'])

        self.update_api_key_list()

        QMessageBox.information(self, "알림", "설정을 불러왔습니다")
        self.statusBar().showMessage("설정 불러오기 완료")

    def export_results(self):
        """결과 내보내기"""
        if self.results_table.rowCount() == 0:
            QMessageBox.warning(self, "경고", "내보낼 결과가 없습니다")
            return

        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f'youtube_results_{timestamp}.csv'

        try:
            with open(filename, 'w', encoding='utf-8-sig') as f:
                # 헤더
                headers = []
                for col in range(self.results_table.columnCount()):
                    headers.append(self.results_table.horizontalHeaderItem(col).text())
                f.write(','.join(headers) + '\n')

                # 데이터
                for row in range(self.results_table.rowCount()):
                    row_data = []
                    for col in range(self.results_table.columnCount()):
                        item = self.results_table.item(row, col)
                        row_data.append(f'"{item.text()}"' if item else '""')
                    f.write(','.join(row_data) + '\n')

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

    window = YouTubeHotFinder()
    window.show()

    sys.exit(app.exec_())


if __name__ == '__main__':
    main()
