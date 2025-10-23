#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
YouTube Hot Finder (API 키 불필요 버전) - yt-dlp 사용
"""

import sys
import json
import os
import subprocess
from datetime import datetime, timedelta
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                             QHBoxLayout, QTabWidget, QLabel, QLineEdit,
                             QPushButton, QTableWidget, QTableWidgetItem,
                             QComboBox, QCheckBox, QSpinBox, QDoubleSpinBox,
                             QTextEdit, QGroupBox, QGridLayout, QMessageBox,
                             QHeaderView, QProgressBar)
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtGui import QFont
import time
import re

# yt-dlp가 설치되어 있는지 확인
try:
    import yt_dlp
    YT_DLP_AVAILABLE = True
except ImportError:
    YT_DLP_AVAILABLE = False


class YouTubeSearchWorker(QThread):
    """YouTube 검색 작업을 별도 스레드에서 처리 (API 키 불필요)"""
    progress = pyqtSignal(str)
    result = pyqtSignal(list)
    error = pyqtSignal(str)

    def __init__(self, search_params):
        super().__init__()
        self.search_params = search_params

    def run(self):
        try:
            if not YT_DLP_AVAILABLE:
                self.error.emit("yt-dlp가 설치되어 있지 않습니다. 'pip install yt-dlp'를 실행하세요.")
                return

            results = []
            query = self.search_params['query']
            max_results = self.search_params.get('max_results', 20)

            self.progress.emit(f"'{query}' 검색 중...")

            # yt-dlp 옵션 설정
            ydl_opts = {
                'quiet': True,
                'no_warnings': True,
                'extract_flat': False,  # 상세 정보 추출
                'skip_download': True,
                'format': 'best',
            }

            # YouTube 검색 URL
            search_url = f"ytsearch{max_results}:{query}"

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                self.progress.emit("영상 정보 수집 중...")
                info = ydl.extract_info(search_url, download=False)

                if 'entries' in info:
                    for idx, entry in enumerate(info['entries'][:max_results]):
                        try:
                            if not entry:
                                continue

                            # 업로드 날짜 파싱
                            upload_date = entry.get('upload_date', '')
                            if upload_date:
                                try:
                                    published_at = datetime.strptime(upload_date, '%Y%m%d')
                                except:
                                    published_at = datetime.now()
                            else:
                                published_at = datetime.now()

                            # 조회수 및 시간당 조회수 계산
                            view_count = entry.get('view_count', 0) or 0
                            hours_since_published = max(1, (datetime.now() - published_at).total_seconds() / 3600)
                            views_per_hour = view_count / hours_since_published

                            # 구독자 수 (채널 정보)
                            subscriber_count = entry.get('channel_follower_count', 0) or 0

                            # 조회수/구독자수 비율
                            views_per_subscriber = view_count / subscriber_count if subscriber_count > 0 else 0

                            # 필터링
                            if view_count < self.search_params.get('min_views', 0):
                                continue
                            if views_per_hour < self.search_params.get('min_views_per_hour', 0):
                                continue

                            # 영상 길이 필터 (쇼츠/숏폼)
                            duration = entry.get('duration', 0) or 0
                            video_type = "일반"
                            if duration <= 60:
                                video_type = "쇼츠"
                            elif duration <= 180:
                                video_type = "숏폼"

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
                                'duration': duration,
                                'video_type': video_type
                            })

                            self.progress.emit(f"처리 중... {idx+1}/{max_results}")

                        except Exception as e:
                            self.progress.emit(f"영상 처리 중 오류: {str(e)}")
                            continue

                # 시간당 조회수 기준으로 정렬
                results.sort(key=lambda x: x['views_per_hour'], reverse=True)

            self.result.emit(results)

        except Exception as e:
            self.error.emit(f"오류 발생: {str(e)}")


class YouTubeHotFinderNoAPI(QMainWindow):
    def __init__(self):
        super().__init__()
        self.config_file = 'youtube_finder_no_api_config.json'
        self.load_config()
        self.init_ui()

    def load_config(self):
        """설정 파일 로드"""
        default_config = {
            'execution_mode': '종류',
            'videos_per_channel': 10,
            'max_searches_per_keyword': 10,
            'min_views_per_hour': 600.0,
            'target_country': 'KR',
            'max_results_per_search': 20,
            'show_popular_by_channel': False,
            'language': 'ko',
            'min_views': 20000,
            'shorts_duration': 60,
            'short_form_duration': 180
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
        self.setWindowTitle('YouTube Hot Finder (API 키 불필요)')
        self.setGeometry(100, 100, 1400, 800)

        # 메인 위젯
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        layout = QVBoxLayout(main_widget)

        # yt-dlp 확인 메시지
        if not YT_DLP_AVAILABLE:
            warning_label = QLabel("⚠️ yt-dlp가 설치되어 있지 않습니다. 'pip install yt-dlp'를 실행하세요.")
            warning_label.setStyleSheet("background-color: #ffcccc; padding: 10px; color: #cc0000;")
            layout.addWidget(warning_label)

        # 탭 위젯
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)

        # 각 탭 생성
        self.create_keyword_tab()
        self.create_settings_tab()
        self.create_results_tab()

        # 상태바
        self.statusBar().showMessage('준비 (API 키 불필요 버전)')

    def create_keyword_tab(self):
        """키워드입력 탭"""
        tab = QWidget()
        layout = QVBoxLayout(tab)

        # 안내 메시지
        info_label = QLabel("✨ 이 버전은 API 키가 필요 없습니다!\nyt-dlp를 사용하여 YouTube에서 직접 정보를 가져옵니다.")
        info_label.setStyleSheet("background-color: #e6f3ff; padding: 10px; border-radius: 5px;")
        layout.addWidget(info_label)

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

        # 진행 상황
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

        self.progress_label = QLabel("")
        layout.addWidget(self.progress_label)

        # 팁
        tip_label = QLabel(
            "💡 팁:\n"
            "• 검색 속도는 API 버전보다 느릴 수 있습니다\n"
            "• 하지만 할당량 제한이 없어 무제한 검색 가능합니다\n"
            "• 최대 50개까지 검색할 수 있습니다"
        )
        tip_label.setStyleSheet("background-color: #fffacd; padding: 10px; border-radius: 5px;")
        layout.addWidget(tip_label)

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
        exec_group = QGroupBox("검색 설정")
        exec_layout = QGridLayout()

        row = 0
        exec_layout.addWidget(QLabel("영상 유형 필터:"), row, 0)
        self.video_type_combo = QComboBox()
        self.video_type_combo.addItems(['전체', '쇼츠만', '숏폼만', '일반 영상만'])
        exec_layout.addWidget(self.video_type_combo, row, 1)

        exec_layout.addWidget(QLabel("쇼츠 기준(초):"), row, 2)
        self.shorts_duration = QSpinBox()
        self.shorts_duration.setRange(1, 600)
        self.shorts_duration.setValue(self.config['shorts_duration'])
        exec_layout.addWidget(self.shorts_duration, row, 3)

        row += 1
        exec_layout.addWidget(QLabel("숏폼 기준(초):"), row, 0)
        self.short_form_duration = QSpinBox()
        self.short_form_duration.setRange(1, 600)
        self.short_form_duration.setValue(self.config['short_form_duration'])
        exec_layout.addWidget(self.short_form_duration, row, 1)

        exec_layout.addWidget(QLabel("최대 검색 결과 수:"), row, 2)
        self.max_results = QSpinBox()
        self.max_results.setRange(1, 50)
        self.max_results.setValue(self.config['max_results_per_search'])
        exec_layout.addWidget(self.max_results, row, 3)

        row += 1
        exec_layout.addWidget(QLabel("최소 조회수:"), row, 0)
        self.min_views = QSpinBox()
        self.min_views.setRange(0, 10000000)
        self.min_views.setValue(self.config['min_views'])
        exec_layout.addWidget(self.min_views, row, 1)

        exec_layout.addWidget(QLabel("최소 시간당 조회수:"), row, 2)
        self.min_views_per_hour = QDoubleSpinBox()
        self.min_views_per_hour.setRange(0, 1000000)
        self.min_views_per_hour.setValue(self.config['min_views_per_hour'])
        exec_layout.addWidget(self.min_views_per_hour, row, 3)

        exec_group.setLayout(exec_layout)
        layout.addWidget(exec_group)

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
        self.results_table.setColumnCount(11)
        self.results_table.setHorizontalHeaderLabels([
            '채널명', '제목', '업로드일', '조회수', '시간당 조회수',
            '구독자수', '조회수/구독자수', '좋아요', '댓글', '영상길이(초)', 'URL'
        ])

        # 테이블 설정
        header = self.results_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        header.setSectionResizeMode(10, QHeaderView.ResizeToContents)

        self.results_table.setAlternatingRowColors(True)
        self.results_table.setSelectionBehavior(QTableWidget.SelectRows)

        layout.addWidget(self.results_table)

        # 버튼
        btn_layout = QHBoxLayout()

        export_btn = QPushButton("결과 내보내기 (CSV)")
        export_btn.clicked.connect(self.export_results)
        btn_layout.addWidget(export_btn)

        clear_results_btn = QPushButton("결과 지우기")
        clear_results_btn.clicked.connect(self.clear_results)
        btn_layout.addWidget(clear_results_btn)

        btn_layout.addStretch()

        layout.addLayout(btn_layout)

        self.tabs.addTab(tab, "결과")

    def search_keyword(self):
        """키워드 검색"""
        keyword = self.keyword_input.text().strip()

        if not keyword:
            QMessageBox.warning(self, "경고", "검색 키워드를 입력하세요")
            return

        if not YT_DLP_AVAILABLE:
            QMessageBox.critical(self, "오류", "yt-dlp가 설치되어 있지 않습니다.\n\n터미널에서 다음 명령을 실행하세요:\npip install yt-dlp")
            return

        search_params = {
            'query': keyword,
            'max_results': self.max_results.value(),
            'min_views': self.min_views.value(),
            'min_views_per_hour': self.min_views_per_hour.value()
        }

        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)  # Indeterminate progress
        self.statusBar().showMessage(f"'{keyword}' 검색 중...")

        # 워커 스레드 시작
        self.worker = YouTubeSearchWorker(search_params)
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
            self.results_table.setItem(row, 9, QTableWidgetItem(str(result['duration'])))

            url = f"https://www.youtube.com/watch?v={result['video_id']}"
            self.results_table.setItem(row, 10, QTableWidgetItem(url))

    def save_settings(self):
        """설정 저장"""
        self.config['max_results_per_search'] = self.max_results.value()
        self.config['min_views_per_hour'] = self.min_views_per_hour.value()
        self.config['min_views'] = self.min_views.value()
        self.config['shorts_duration'] = self.shorts_duration.value()
        self.config['short_form_duration'] = self.short_form_duration.value()

        self.save_config()
        QMessageBox.information(self, "알림", "설정이 저장되었습니다")
        self.statusBar().showMessage("설정 저장 완료")

    def load_settings(self):
        """설정 불러오기"""
        self.load_config()

        self.max_results.setValue(self.config['max_results_per_search'])
        self.min_views_per_hour.setValue(self.config['min_views_per_hour'])
        self.min_views.setValue(self.config['min_views'])
        self.shorts_duration.setValue(self.config['shorts_duration'])
        self.short_form_duration.setValue(self.config['short_form_duration'])

        QMessageBox.information(self, "알림", "설정을 불러왔습니다")
        self.statusBar().showMessage("설정 불러오기 완료")

    def export_results(self):
        """결과 내보내기"""
        if self.results_table.rowCount() == 0:
            QMessageBox.warning(self, "경고", "내보낼 결과가 없습니다")
            return

        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f'youtube_results_no_api_{timestamp}.csv'

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

    window = YouTubeHotFinderNoAPI()
    window.show()

    sys.exit(app.exec_())


if __name__ == '__main__':
    main()
