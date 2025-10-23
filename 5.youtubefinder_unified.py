#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
YouTube Hot Finder (통합 버전)
- API 키 사용/미사용 모두 지원
- 설정에서 선택 가능
"""

import sys
import json
import os
import csv
import subprocess
import webbrowser
from datetime import datetime, timedelta
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                             QHBoxLayout, QTabWidget, QLabel, QLineEdit,
                             QPushButton, QTableWidget, QTableWidgetItem,
                             QComboBox, QSpinBox, QDoubleSpinBox,
                             QTextEdit, QGroupBox, QGridLayout, QMessageBox,
                             QHeaderView, QProgressBar, QRadioButton, QButtonGroup,
                             QFileDialog)
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtGui import QFont
import time

# 라이브러리 가용성 확인
try:
    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError
    GOOGLE_API_AVAILABLE = True
except ImportError:
    GOOGLE_API_AVAILABLE = False

try:
    import yt_dlp
    YT_DLP_AVAILABLE = True
except ImportError:
    YT_DLP_AVAILABLE = False


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


class YouTubeScraperWorker(QThread):
    """yt-dlp를 사용한 YouTube 검색 (API 키 불필요)"""
    progress = pyqtSignal(str)
    result = pyqtSignal(list)
    error = pyqtSignal(str)

    def __init__(self, search_params):
        super().__init__()
        self.search_params = search_params

    def run(self):
        try:
            results = []
            query = self.search_params['query']
            max_results = self.search_params.get('max_results', 20)

            self.progress.emit(f"'{query}' 검색 중... (yt-dlp 사용)")

            ydl_opts = {
                'quiet': True,
                'no_warnings': True,
                'extract_flat': False,
                'skip_download': True,
                'format': 'best',
            }

            search_url = f"ytsearch{max_results}:{query}"

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                self.progress.emit("영상 정보 수집 중...")
                info = ydl.extract_info(search_url, download=False)

                if 'entries' in info:
                    for idx, entry in enumerate(info['entries'][:max_results]):
                        try:
                            if not entry:
                                continue

                            upload_date = entry.get('upload_date', '')
                            if upload_date:
                                try:
                                    published_at = datetime.strptime(upload_date, '%Y%m%d')
                                except:
                                    published_at = datetime.now()
                            else:
                                published_at = datetime.now()

                            view_count = entry.get('view_count', 0) or 0
                            hours_since_published = max(1, (datetime.now() - published_at).total_seconds() / 3600)
                            views_per_hour = view_count / hours_since_published

                            subscriber_count = entry.get('channel_follower_count', 0) or 0
                            views_per_subscriber = view_count / subscriber_count if subscriber_count > 0 else 0

                            # 영상 길이
                            duration = entry.get('duration', 0) or 0

                            # 필터링
                            if view_count < self.search_params.get('min_views', 0):
                                continue
                            if views_per_hour < self.search_params.get('min_views_per_hour', 0):
                                continue

                            # 영상 길이 필터링
                            video_length_filter = self.search_params.get('video_length_filter', 'all')
                            if video_length_filter == 'shorts':
                                # 숏폼만
                                if duration > self.search_params.get('shorts_max_duration', 60):
                                    continue
                            elif video_length_filter == 'long':
                                # 롱폼만
                                if duration < self.search_params.get('long_min_duration', 600):
                                    continue

                            results.append({
                                'channel_name': entry.get('uploader', entry.get('channel', 'Unknown')),
                                'title': entry.get('title', 'No Title'),
                                'video_id': entry.get('id', ''),
                                'published_at': published_at.strftime('%Y-%m-%d %H:%M'),
                                'view_count': view_count,
                                'views_per_hour': round(views_per_hour, 2),
                                'subscriber_count': subscriber_count,
                                'views_per_subscriber': round(views_per_subscriber, 4),
                                'like_count': entry.get('like_count', 0) or 0,
                                'comment_count': entry.get('comment_count', 0) or 0,
                                'duration': duration
                            })

                            self.progress.emit(f"처리 중... {idx+1}/{max_results}")

                        except Exception as e:
                            self.progress.emit(f"영상 처리 중 오류: {str(e)}")
                            continue

                results.sort(key=lambda x: x['views_per_hour'], reverse=True)

            self.result.emit(results)

        except Exception as e:
            self.error.emit(f"오류 발생: {str(e)}")


class YouTubeHotFinderUnified(QMainWindow):
    def __init__(self):
        super().__init__()
        self.config_file = 'youtube_finder_unified_config.json'
        self.load_config()
        self.init_ui()

    def load_config(self):
        """설정 파일 로드"""
        default_config = {
            'api_keys': [],
            'current_api_key_index': 0,
            'search_mode': 'auto',  # 'api', 'scraper', 'auto'
            'max_results_per_search': 20,
            'min_views_per_hour': 600.0,
            'min_views': 20000,
            'target_country': 'KR',
            'language': 'ko',
            'video_length_filter': 'all',  # 'all', 'shorts', 'long'
            'shorts_max_duration': 60,  # 숏폼 최대 길이 (초)
            'long_min_duration': 600  # 롱폼 최소 길이 (초, 10분)
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
        self.setWindowTitle('YouTube Hot Finder (통합 버전)')
        self.setGeometry(100, 100, 1400, 800)

        # 메인 위젯
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        layout = QVBoxLayout(main_widget)

        # 라이브러리 상태 표시
        status_text = []
        if GOOGLE_API_AVAILABLE:
            status_text.append("✅ Google API 사용 가능")
        else:
            status_text.append("❌ Google API 미설치 (pip install google-api-python-client)")

        if YT_DLP_AVAILABLE:
            status_text.append("✅ yt-dlp 사용 가능")
        else:
            status_text.append("❌ yt-dlp 미설치 (pip install yt-dlp)")

        status_label = QLabel(" | ".join(status_text))
        status_label.setStyleSheet("background-color: #f0f0f0; padding: 5px; font-size: 10px;")
        layout.addWidget(status_label)

        # 탭 위젯
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)

        # 각 탭 생성
        self.create_keyword_tab()
        self.create_settings_tab()
        self.create_results_tab()

        # 상태바
        self.statusBar().showMessage('준비 (통합 버전)')

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
                "한글날 한국어",
                "해외감동사연",
                "한국 역사"
            ],
            "💡 자기계발/지식": [
                "AI 인공지능",
                "ChatGPT AI",
                "동기부여 스피치",
                "TED 강연",
                "신기술 트렌드",
                "미래 기술",
                "자기계발 성공",
                "생산성 향상"
            ],
            "🔮 초자연 미스테리 외계인": [
                "UFO 목격",
                "외계인 영상",
                "초능력 실험",
                "귀신 영상",
                "괴담 실화",
                "미스터리 사건",
                "미제 사건",
                "도시전설"
            ],
            "🛸 UFO & Mystery (Global)": [
                "UFO sighting",
                "alien footage",
                "psychic powers",
                "ghost caught on camera",
                "paranormal activity",
                "unsolved mystery",
                "conspiracy theory",
                "urban legend",
                "supernatural phenomena"
            ],
            "👴 시니어": [
                "건강 정보 노인",
                "스마트폰 사용법 초보",
                "연금 노후 준비",
                "손자녀 육아팁",
                "시니어 여행 추천"
            ],
            "📱 쇼츠 (한국)": [
                "동물 쇼츠",
                "강아지 쇼츠",
                "고양이 쇼츠",
                "펫 쇼츠",
                "웃긴 동물 영상",
                "동물 먹방 쇼츠",
                "댄스 쇼츠",
                "요리 쇼츠 레시피",
                "로봇 쇼츠",
                "웃긴 순간",
                "만족 영상"
            ],
            "🌍 Shorts (Global)": [
                "animal shorts",
                "cute dog shorts",
                "funny cat shorts",
                "pet compilation",
                "baby animals shorts",
                "dance challenge shorts",
                "cooking shorts recipe",
                "robot shorts",
                "robotics shorts",
                "life hacks shorts",
                "funny moments shorts",
                "satisfying shorts"
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

        # 검색 모드 선택
        mode_group = QGroupBox("🔧 검색 방식 선택")
        mode_layout = QVBoxLayout()

        self.mode_button_group = QButtonGroup()

        self.auto_radio = QRadioButton("자동 선택 (API 키가 있으면 API 사용, 없으면 yt-dlp 사용)")
        self.api_radio = QRadioButton("Google API 강제 사용 (빠르지만 할당량 제한)")
        self.scraper_radio = QRadioButton("yt-dlp 강제 사용 (느리지만 무제한)")

        self.mode_button_group.addButton(self.auto_radio, 0)
        self.mode_button_group.addButton(self.api_radio, 1)
        self.mode_button_group.addButton(self.scraper_radio, 2)

        # 현재 설정 불러오기
        if self.config['search_mode'] == 'api':
            self.api_radio.setChecked(True)
        elif self.config['search_mode'] == 'scraper':
            self.scraper_radio.setChecked(True)
        else:
            self.auto_radio.setChecked(True)

        mode_layout.addWidget(self.auto_radio)
        mode_layout.addWidget(self.api_radio)
        mode_layout.addWidget(self.scraper_radio)

        # 라이브러리 상태에 따라 비활성화
        if not GOOGLE_API_AVAILABLE:
            self.api_radio.setEnabled(False)
            self.api_radio.setText(self.api_radio.text() + " [미설치]")

        if not YT_DLP_AVAILABLE:
            self.scraper_radio.setEnabled(False)
            self.scraper_radio.setText(self.scraper_radio.text() + " [미설치]")

        mode_group.setLayout(mode_layout)
        layout.addWidget(mode_group)

        # API 키 설정
        api_group = QGroupBox("🔑 Google API 키 관리 (선택사항)")
        api_layout = QVBoxLayout()

        key_input_layout = QHBoxLayout()
        key_input_layout.addWidget(QLabel("API 키:"))
        self.api_key_input = QLineEdit()
        self.api_key_input.setPlaceholderText("YouTube Data API v3 키 (없으면 yt-dlp 사용)")
        key_input_layout.addWidget(self.api_key_input)

        add_key_btn = QPushButton("추가")
        add_key_btn.clicked.connect(self.add_api_key)
        key_input_layout.addWidget(add_key_btn)

        api_layout.addLayout(key_input_layout)

        self.api_key_list = QTextEdit()
        self.api_key_list.setReadOnly(True)
        self.api_key_list.setMaximumHeight(80)
        api_layout.addWidget(QLabel("등록된 API 키:"))
        api_layout.addWidget(self.api_key_list)
        self.update_api_key_list()

        api_group.setLayout(api_layout)
        layout.addWidget(api_group)

        # 검색 설정
        search_group = QGroupBox("🔍 검색 설정")
        search_layout = QGridLayout()

        row = 0
        search_layout.addWidget(QLabel("최대 검색 결과 수:"), row, 0)
        self.max_results = QSpinBox()
        self.max_results.setRange(1, 50)
        self.max_results.setValue(self.config['max_results_per_search'])
        search_layout.addWidget(self.max_results, row, 1)

        search_layout.addWidget(QLabel("최소 조회수:"), row, 2)
        self.min_views = QSpinBox()
        self.min_views.setRange(0, 10000000)
        self.min_views.setValue(self.config['min_views'])
        search_layout.addWidget(self.min_views, row, 3)

        row += 1
        search_layout.addWidget(QLabel("최소 시간당 조회수:"), row, 0)
        self.min_views_per_hour = QDoubleSpinBox()
        self.min_views_per_hour.setRange(0, 1000000)
        self.min_views_per_hour.setValue(self.config['min_views_per_hour'])
        search_layout.addWidget(self.min_views_per_hour, row, 1)

        search_layout.addWidget(QLabel("대상 국가:"), row, 2)
        self.country_input = QComboBox()
        countries = [
            ('🇰🇷 한국', 'KR'),
            ('🇺🇸 미국', 'US'),
            ('🇯🇵 일본', 'JP'),
            ('🇮🇳 인도', 'IN'),
            ('🇨🇳 중국', 'CN'),
            ('🇬🇧 영국', 'GB'),
            ('🇩🇪 독일', 'DE'),
            ('🇫🇷 프랑스', 'FR'),
            ('🇮🇹 이탈리아', 'IT'),
            ('🇪🇸 스페인', 'ES'),
            ('🇨🇦 캐나다', 'CA'),
            ('🇦🇺 호주', 'AU'),
            ('🇧🇷 브라질', 'BR'),
            ('🇲🇽 멕시코', 'MX'),
            ('🇷🇺 러시아', 'RU'),
            ('🇹🇭 태국', 'TH'),
            ('🇻🇳 베트남', 'VN'),
            ('🇸🇬 싱가포르', 'SG'),
            ('🇹🇼 대만', 'TW')
        ]
        for name, code in countries:
            self.country_input.addItem(name, code)
        # 현재 설정된 국가 선택
        current_idx = self.country_input.findData(self.config['target_country'])
        if current_idx >= 0:
            self.country_input.setCurrentIndex(current_idx)
        search_layout.addWidget(self.country_input, row, 3)

        row += 1
        search_layout.addWidget(QLabel("언어:"), row, 0)
        self.language_input = QComboBox()
        languages = [
            ('한국어', 'ko'),
            ('English', 'en'),
            ('日本語', 'ja'),
            ('中文', 'zh'),
            ('Español', 'es'),
            ('Français', 'fr'),
            ('Deutsch', 'de'),
            ('हिन्दी', 'hi'),
            ('Português', 'pt'),
            ('Русский', 'ru'),
            ('Italiano', 'it'),
            ('العربية', 'ar'),
            ('ไทย', 'th'),
            ('Tiếng Việt', 'vi'),
            ('Bahasa Indonesia', 'id'),
            ('Türkçe', 'tr')
        ]
        for name, code in languages:
            self.language_input.addItem(name, code)
        # 현재 설정된 언어 선택
        lang_idx = self.language_input.findData(self.config['language'])
        if lang_idx >= 0:
            self.language_input.setCurrentIndex(lang_idx)
        search_layout.addWidget(self.language_input, row, 1)

        search_group.setLayout(search_layout)
        layout.addWidget(search_group)

        # 영상 길이 필터 설정
        length_group = QGroupBox("📏 영상 길이 필터")
        length_layout = QGridLayout()

        row = 0
        length_layout.addWidget(QLabel("영상 유형:"), row, 0)
        self.video_length_combo = QComboBox()
        self.video_length_combo.addItems(['전체', '숏폼만 (짧은 영상)', '롱폼만 (긴 영상)'])

        # 현재 설정 불러오기
        if self.config['video_length_filter'] == 'shorts':
            self.video_length_combo.setCurrentIndex(1)
        elif self.config['video_length_filter'] == 'long':
            self.video_length_combo.setCurrentIndex(2)
        else:
            self.video_length_combo.setCurrentIndex(0)

        length_layout.addWidget(self.video_length_combo, row, 1)

        length_layout.addWidget(QLabel("숏폼 최대 길이 (초):"), row, 2)
        self.shorts_duration = QSpinBox()
        self.shorts_duration.setRange(10, 300)
        self.shorts_duration.setValue(self.config['shorts_max_duration'])
        self.shorts_duration.setSuffix("초")
        length_layout.addWidget(self.shorts_duration, row, 3)

        row += 1
        length_layout.addWidget(QLabel("롱폼 최소 길이 (초):"), row, 0)
        self.long_duration = QSpinBox()
        self.long_duration.setRange(60, 3600)
        self.long_duration.setValue(self.config['long_min_duration'])
        self.long_duration.setSuffix("초")
        length_layout.addWidget(self.long_duration, row, 1)

        # 도움말
        help_label = QLabel("💡 숏폼: YouTube 쇼츠 같은 짧은 영상 | 롱폼: 긴 영상 (기본 10분 이상)")
        help_label.setStyleSheet("color: #666; font-size: 10px;")
        length_layout.addWidget(help_label, row, 2, 1, 2)

        length_group.setLayout(length_layout)
        layout.addWidget(length_group)

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
        self.results_table.setColumnCount(12)
        self.results_table.setHorizontalHeaderLabels([
            '채널명', '제목', '업로드일', '조회수', '시간당 조회수',
            '구독자수', '조회수/구독자수', '좋아요', '댓글', 'URL', '바로가기', '다운로드'
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

        export_btn = QPushButton("💾 내보내기 (CSV)")
        export_btn.clicked.connect(self.export_results)
        btn_layout.addWidget(export_btn)

        import_btn = QPushButton("📂 불러오기 (CSV)")
        import_btn.clicked.connect(self.import_results)
        btn_layout.addWidget(import_btn)

        clear_results_btn = QPushButton("🗑️ 결과 지우기")
        clear_results_btn.clicked.connect(self.clear_results)
        btn_layout.addWidget(clear_results_btn)

        btn_layout.addStretch()

        # YouTube 링크 직접 다운로드
        btn_layout.addWidget(QLabel("YouTube 링크:"))
        self.download_url_input = QLineEdit()
        self.download_url_input.setPlaceholderText("https://www.youtube.com/watch?v=...")
        self.download_url_input.setFixedWidth(300)
        btn_layout.addWidget(self.download_url_input)

        direct_download_btn = QPushButton("⬇️ 다운로드")
        direct_download_btn.clicked.connect(self.download_from_input)
        btn_layout.addWidget(direct_download_btn)

        layout.addLayout(btn_layout)

        self.tabs.addTab(tab, "결과")

    def search_keyword(self):
        """키워드 검색"""
        keyword = self.keyword_input.text().strip()

        if not keyword:
            QMessageBox.warning(self, "경고", "검색 키워드를 입력하세요")
            return

        # 검색 모드 결정
        search_mode = self.determine_search_mode()

        if search_mode == 'api':
            if not self.config['api_keys']:
                QMessageBox.warning(self, "경고", "API 키를 등록하거나 설정에서 yt-dlp 모드로 변경하세요")
                return
            self.search_with_api(keyword)
        elif search_mode == 'scraper':
            if not YT_DLP_AVAILABLE:
                QMessageBox.critical(self, "오류", "yt-dlp가 설치되어 있지 않습니다.\n\n터미널에서 다음 명령을 실행하세요:\npip install yt-dlp")
                return
            self.search_with_scraper(keyword)
        else:
            QMessageBox.critical(self, "오류", "사용 가능한 검색 방법이 없습니다.\nAPI 키를 등록하거나 yt-dlp를 설치하세요.")

    def determine_search_mode(self):
        """검색 모드 결정"""
        # 수동 선택
        if self.api_radio.isChecked():
            return 'api'
        elif self.scraper_radio.isChecked():
            return 'scraper'

        # 자동 선택
        if self.config['api_keys'] and GOOGLE_API_AVAILABLE:
            return 'api'
        elif YT_DLP_AVAILABLE:
            return 'scraper'
        else:
            return None

    def search_with_api(self, keyword):
        """Google API로 검색"""
        search_params = {
            'query': keyword,
            'max_results': self.max_results.value(),
            'order': 'relevance',
            'region': self.country_input.currentData(),
            'language': self.language_input.currentData(),
            'min_views': self.min_views.value(),
            'min_views_per_hour': self.min_views_per_hour.value()
        }

        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)
        self.statusBar().showMessage(f"'{keyword}' 검색 중... (Google API 사용)")

        api_key = self.config['api_keys'][self.config['current_api_key_index']]
        self.worker = YouTubeAPIWorker(api_key, search_params)
        self.worker.progress.connect(self.on_progress)
        self.worker.result.connect(self.on_search_complete)
        self.worker.error.connect(self.on_search_error)
        self.worker.start()

    def search_with_scraper(self, keyword):
        """yt-dlp로 검색"""
        search_params = {
            'query': keyword,
            'max_results': self.max_results.value(),
            'min_views': self.min_views.value(),
            'min_views_per_hour': self.min_views_per_hour.value(),
            'video_length_filter': self.config['video_length_filter'],
            'shorts_max_duration': self.config['shorts_max_duration'],
            'long_min_duration': self.config['long_min_duration']
        }

        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)
        self.statusBar().showMessage(f"'{keyword}' 검색 중... (yt-dlp 사용)")

        self.worker = YouTubeScraperWorker(search_params)
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

        self.display_results(results)
        self.statusBar().showMessage(f"검색 완료 - {len(results)}개 결과")
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

            # 바로가기 버튼 추가
            open_btn = QPushButton("🔗 열기")
            open_btn.clicked.connect(lambda checked, u=url: webbrowser.open(u))
            self.results_table.setCellWidget(row, 10, open_btn)

            # 다운로드 버튼 추가
            download_btn = QPushButton("⬇️ 다운로드")
            download_btn.clicked.connect(lambda checked, u=url: self.download_video(u))
            self.results_table.setCellWidget(row, 11, download_btn)

        # 결과가 있으면 자동 저장
        if len(results) > 0:
            self.auto_save_results()

    def auto_save_results(self):
        """결과 자동 저장"""
        try:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f'youtube_results_{timestamp}.csv'

            with open(filename, 'w', encoding='utf-8-sig') as f:
                headers = []
                for col in range(self.results_table.columnCount() - 1):  # 바로가기 버튼 제외
                    headers.append(self.results_table.horizontalHeaderItem(col).text())
                f.write(','.join(headers) + '\n')

                for row in range(self.results_table.rowCount()):
                    row_data = []
                    for col in range(self.results_table.columnCount() - 1):  # 바로가기 버튼 제외
                        item = self.results_table.item(row, col)
                        row_data.append(f'"{item.text()}"' if item else '""')
                    f.write(','.join(row_data) + '\n')

            self.statusBar().showMessage(f"결과가 자동으로 저장되었습니다: {filename}", 3000)
        except Exception as e:
            print(f"자동 저장 중 오류: {str(e)}")

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
            self.api_key_list.setText("등록된 API 키가 없습니다 (yt-dlp 사용)")

    def save_settings(self):
        """설정 저장"""
        if self.auto_radio.isChecked():
            self.config['search_mode'] = 'auto'
        elif self.api_radio.isChecked():
            self.config['search_mode'] = 'api'
        else:
            self.config['search_mode'] = 'scraper'

        self.config['max_results_per_search'] = self.max_results.value()
        self.config['min_views_per_hour'] = self.min_views_per_hour.value()
        self.config['min_views'] = self.min_views.value()
        self.config['target_country'] = self.country_input.currentData()
        self.config['language'] = self.language_input.currentData()

        # 영상 길이 필터 설정
        if self.video_length_combo.currentIndex() == 1:
            self.config['video_length_filter'] = 'shorts'
        elif self.video_length_combo.currentIndex() == 2:
            self.config['video_length_filter'] = 'long'
        else:
            self.config['video_length_filter'] = 'all'

        self.config['shorts_max_duration'] = self.shorts_duration.value()
        self.config['long_min_duration'] = self.long_duration.value()

        self.save_config()
        QMessageBox.information(self, "알림", "설정이 저장되었습니다")
        self.statusBar().showMessage("설정 저장 완료")

    def load_settings(self):
        """설정 불러오기"""
        self.load_config()

        if self.config['search_mode'] == 'api':
            self.api_radio.setChecked(True)
        elif self.config['search_mode'] == 'scraper':
            self.scraper_radio.setChecked(True)
        else:
            self.auto_radio.setChecked(True)

        self.max_results.setValue(self.config['max_results_per_search'])
        self.min_views_per_hour.setValue(self.config['min_views_per_hour'])
        self.min_views.setValue(self.config['min_views'])

        # 국가 선택 설정
        country_idx = self.country_input.findData(self.config['target_country'])
        if country_idx >= 0:
            self.country_input.setCurrentIndex(country_idx)

        # 언어 선택 설정
        lang_idx = self.language_input.findData(self.config['language'])
        if lang_idx >= 0:
            self.language_input.setCurrentIndex(lang_idx)

        # 영상 길이 필터 설정 불러오기
        if self.config['video_length_filter'] == 'shorts':
            self.video_length_combo.setCurrentIndex(1)
        elif self.config['video_length_filter'] == 'long':
            self.video_length_combo.setCurrentIndex(2)
        else:
            self.video_length_combo.setCurrentIndex(0)

        self.shorts_duration.setValue(self.config['shorts_max_duration'])
        self.long_duration.setValue(self.config['long_min_duration'])

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
                headers = []
                for col in range(self.results_table.columnCount()):
                    headers.append(self.results_table.horizontalHeaderItem(col).text())
                f.write(','.join(headers) + '\n')

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

    def download_from_input(self):
        """입력란의 YouTube 링크로 다운로드"""
        url = self.download_url_input.text().strip()

        if not url:
            QMessageBox.warning(self, "경고", "YouTube 링크를 입력하세요")
            return

        if "youtube.com" not in url and "youtu.be" not in url:
            QMessageBox.warning(self, "경고", "유효한 YouTube 링크를 입력하세요")
            return

        self.download_video(url)
        self.download_url_input.clear()

    def download_video(self, url):
        """YouTube 비디오 다운로드"""
        # 다운로드 디렉토리 선택
        download_dir = QFileDialog.getExistingDirectory(
            self,
            "다운로드 폴더 선택",
            os.path.expanduser("~/Downloads")
        )

        if not download_dir:
            return

        try:
            # yt-dlp 명령어 실행
            self.statusBar().showMessage(f"다운로드 중: {url}")

            cmd = [
                'yt-dlp',
                '-o', os.path.join(download_dir, '%(title)s.%(ext)s'),
                url
            ]

            result = subprocess.run(cmd, capture_output=True, text=True)

            if result.returncode == 0:
                QMessageBox.information(self, "성공", f"다운로드 완료!\n폴더: {download_dir}")
                self.statusBar().showMessage("다운로드 완료")
            else:
                QMessageBox.critical(self, "오류", f"다운로드 실패:\n{result.stderr}")
                self.statusBar().showMessage("다운로드 실패")

        except FileNotFoundError:
            QMessageBox.critical(self, "오류", "yt-dlp가 설치되어 있지 않습니다.\n터미널에서 'pip install yt-dlp'를 실행하세요.")
        except Exception as e:
            QMessageBox.critical(self, "오류", f"다운로드 중 오류:\n{str(e)}")

    def import_results(self):
        """결과 불러오기"""
        filename, _ = QFileDialog.getOpenFileName(
            self,
            "결과 파일 불러오기",
            "",
            "CSV Files (*.csv);;All Files (*)"
        )

        if not filename:
            return

        try:
            with open(filename, 'r', encoding='utf-8-sig') as f:
                reader = csv.reader(f)
                headers = next(reader)  # 헤더 읽기

                # 테이블 초기화
                self.results_table.setRowCount(0)

                # 데이터 읽어서 테이블에 추가
                rows = list(reader)
                self.results_table.setRowCount(len(rows))

                for row_idx, row_data in enumerate(rows):
                    # URL 가져오기 (9번째 열)
                    url = row_data[9].strip('"') if len(row_data) > 9 else ""

                    for col_idx, cell_data in enumerate(row_data):
                        if col_idx == 10:  # 바로가기 열
                            open_btn = QPushButton("🔗 열기")
                            open_btn.clicked.connect(lambda checked, u=url: webbrowser.open(u))
                            self.results_table.setCellWidget(row_idx, col_idx, open_btn)
                        elif col_idx == 11:  # 다운로드 열
                            download_btn = QPushButton("⬇️ 다운로드")
                            download_btn.clicked.connect(lambda checked, u=url: self.download_video(u))
                            self.results_table.setCellWidget(row_idx, col_idx, download_btn)
                        else:
                            # 따옴표 제거
                            clean_data = cell_data.strip('"')
                            self.results_table.setItem(row_idx, col_idx, QTableWidgetItem(clean_data))

                    # CSV에 11번째 열이 없는 경우 다운로드 버튼 추가
                    if len(row_data) <= 11:
                        download_btn = QPushButton("⬇️ 다운로드")
                        download_btn.clicked.connect(lambda checked, u=url: self.download_video(u))
                        self.results_table.setCellWidget(row_idx, 11, download_btn)

            QMessageBox.information(self, "알림", f"결과를 {filename}에서 불러왔습니다")
            self.statusBar().showMessage(f"결과 불러오기 완료: {filename}")
        except Exception as e:
            QMessageBox.critical(self, "오류", f"파일 불러오기 중 오류: {str(e)}")


def main():
    app = QApplication(sys.argv)

    # 폰트 설정
    font = QFont("맑은 고딕", 9)
    app.setFont(font)

    window = YouTubeHotFinderUnified()
    window.show()

    sys.exit(app.exec_())


if __name__ == '__main__':
    main()
