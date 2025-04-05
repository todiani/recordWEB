
import importlib
import subprocess
import os
import json
import sys
import traceback
import asyncio
import webbrowser
import re

from datetime import datetime, timedelta
from functools import partial
from concurrent.futures import ThreadPoolExecutor, as_completed


def install_missing_modules():
    missing_modules = [
        "requests",
        "PyQt5",
        "httpx",
        "qasync",
        "pyperclip",
        "selenium",
        "webdriver_manager",
        "chzzkpy",  # chzzkpy 추가
    ]
    installed_modules = []

    for module in missing_modules:
        try:
            importlib.import_module(module)
        except ImportError:
            installed_modules.append(module)

    if installed_modules:
        print("필수 모듈을 자동으로 설치합니다...")
        for module in installed_modules:
            try:
                subprocess.check_call([sys.executable, "-m", "pip", "install", module])
                print(f"'{module}' 모듈 설치 완료.")
            except subprocess.CalledProcessError as e:
                print(f"모듈 설치 중 오류 발생: {e}")

        print("필수 모듈 설치가 완료되었습니다.")
    else:
        print("필수 모듈이 이미 설치되어 있습니다.")


install_missing_modules()

import httpx
import qasync
from qasync import asyncSlot
from PyQt5 import sip
from PyQt5.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QGridLayout,
    QPushButton,
    QScrollArea,
    QLabel,
    QHBoxLayout,
    QLineEdit,
    QFileDialog,
    QMessageBox,
    QDialog,
    QSizePolicy,
    QFrame,
    QInputDialog,
    QSystemTrayIcon,
    QMenu,
    QComboBox,
    QCheckBox,
    QTextEdit,
    QStackedLayout,
    QLayout,
)
from PyQt5.QtNetwork import QNetworkAccessManager, QNetworkRequest
from PyQt5.QtCore import (
    QThread,
    Qt,
    QUrl,
    QTimer,
    pyqtSignal,
    pyqtSlot,
    QMetaObject,
    Q_ARG,
    QEvent,
    QEventLoop,
    QObject,
)
from PyQt5.QtGui import QPixmap, QPalette, QColor, QIcon


# 현재 디렉토리 경로를 가져와 sys.path에 추가
current_dir = os.path.dirname(os.path.realpath(__file__))
sys.path.append(current_dir)

# 'module' 디렉토리를 sys.path에 추가
module_path = os.path.join(current_dir, "module")
sys.path.append(module_path)

from module.api import (
    fetch_userIdHash,
    fetch_chatChannelId,
    fetch_channelName,
    load_cookies,
    get_headers,
)
from module.Live_recorder import LiveRecorder
from module.settings_window import SettingsWindow
from module.channel_manager import load_channels, save_channels, load_config, save_config


class CustomEvent(QEvent):  # 사용자 정의 이벤트
    def __init__(self, eventType, data=None):
        super().__init__(eventType)
        self.data = data


CHANNEL_ADDED_EVENT = QEvent.Type(QEvent.User + 1)  # 채널 추가 이벤트
CHANNEL_REMOVED_EVENT = QEvent.Type(QEvent.User + 2)  # 채널 제거 이벤트


class ChannelWidget(QWidget):  # 썸네일 + 버튼 묶음 위젯
    def __init__(self, channel, parent):
        super().__init__()
        self.channel = channel
        self.parent = parent
        self.is_recording = False  # 녹화 상태
        self.is_chatting = False   # 채팅 상태
        self.initUI()
        self.set_initial_overlay() # 추가: 초기 오버레이 설정

    def initUI(self):
        layout = QGridLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)  # 이 값은 유지 (위젯 간 간격)
        layout.setHorizontalSpacing(0)  # 썸네일-버튼 사이 간격

        # 썸네일 컨테이너
        self.thumbnailContainer = QFrame()
        self.thumbnailContainer.setFrameShape(QFrame.Box)
        self.thumbnailContainer.setFixedSize(200, 112)
        thumbnailLayout = QVBoxLayout(self.thumbnailContainer)
        thumbnailLayout.setContentsMargins(0, 0, 0, 0)
        thumbnailLayout.setSpacing(0)

        self.thumbnailLabel = QLabel()
        self.thumbnailLabel.setFixedSize(200, 112)
        self.thumbnailLabel.setStyleSheet("border: 1px solid #ccc;")
        defaultThumbnail = QPixmap(self.parent.liveRecorder.default_thumbnail_path)
        self.thumbnailLabel.setPixmap(defaultThumbnail.scaled(200, 112, Qt.KeepAspectRatio))
        thumbnailLayout.addWidget(self.thumbnailLabel)

        self.overlayLabel = QLabel()
        self.overlayLabel.setAlignment(Qt.AlignBottom | Qt.AlignLeft)
        self.overlayLabel.setStyleSheet(
            """
            color: white;
            font-weight: bold;
            background-color: rgba(0, 0, 0, 128);
            padding: 5px;
            """
        )
        thumbnailLayout.addWidget(self.overlayLabel)
        layout.addWidget(self.thumbnailContainer, 0, 0, 3, 1)  # 썸네일 위치 유지

        # 버튼 + 정보 레이아웃을 담을 위젯 (크기 고정)
        rightWidget = QWidget()
        rightWidget.setFixedSize(200, 112)
        rightWidget.setContentsMargins(0, 0, 0, 0)
        rightLayout = QVBoxLayout(rightWidget)
        rightLayout.setSpacing(0)
        rightLayout.setContentsMargins(0, 0, 0, 0)
        rightLayout.setAlignment(Qt.AlignTop | Qt.AlignLeft)

        # 버튼 레이아웃 (왼쪽 정렬)
        buttonsLayout = QGridLayout()
        buttonsLayout.setContentsMargins(0, 0, 0, 0)
        buttonsLayout.setSpacing(0)
        buttonsLayout.setAlignment(Qt.AlignTop | Qt.AlignLeft)

        # 버튼 스타일 (내부 여백 제거, 최소 크기 설정)
        buttonStyle = """
            QPushButton {
                padding: 0px;
                min-width: 60px;
                min-height: 25px;
            }
        """

        self.recordButton = QPushButton("녹화 시작")
        self.recordButton.setStyleSheet(buttonStyle)
        self.recordButton.clicked.connect(self.toggle_recording)
        buttonsLayout.addWidget(self.recordButton, 0, 0)

        self.chatButton = QPushButton("채팅 시작")
        self.chatButton.setStyleSheet(buttonStyle)
        self.chatButton.clicked.connect(self.toggle_chat)
        buttonsLayout.addWidget(self.chatButton, 0, 1)

        self.settingsButton = QPushButton("설정")
        self.settingsButton.setStyleSheet(buttonStyle)
        self.settingsButton.clicked.connect(
            lambda: self.parent.openChannelSettings(self.channel["id"])
        )
        buttonsLayout.addWidget(self.settingsButton, 0, 2)

        self.gotoButton = QPushButton("바로가기")
        self.gotoButton.setStyleSheet(buttonStyle)
        self.gotoButton.clicked.connect(
            lambda: self.parent.open_chzzk_channel(self.channel["id"])
        )
        buttonsLayout.addWidget(self.gotoButton, 1, 0)

        self.openfolderButton = QPushButton("열기")
        self.openfolderButton.setStyleSheet(buttonStyle)
        self.openfolderButton.clicked.connect(
            lambda: self.parent.openRecordedFolder(self.channel["output_dir"])
        )
        buttonsLayout.addWidget(self.openfolderButton, 1, 1)

        self.deleteButton = QPushButton("삭제")
        self.deleteButton.setStyleSheet(buttonStyle)
        self.deleteButton.clicked.connect(
            lambda: self.parent.deleteChannel(self.channel["id"])
        )
        buttonsLayout.addWidget(self.deleteButton, 1, 2)
        rightLayout.addLayout(buttonsLayout)  # buttonsLayout을 rightLayout에 추가
        rightLayout.addStretch(1)  # buttonsLayout과 infoLayout 사이에 stretch 추가


        # 정보 레이아웃 (왼쪽 정렬)
        infoLayout = QGridLayout()
        infoLayout.setContentsMargins(0, 5, 0, 0)  # 왼쪽 여백은 조금 유지
        infoLayout.setSpacing(5)
        infoLayout.setAlignment(Qt.AlignBottom | Qt.AlignLeft)  # 왼쪽 아래

        labelStyle = """
            QLabel {
                padding: 0px;
            }
        """

        self.startTimeLabel = QLabel("방송시작 : 0000-00-00 00:00:00")  # 가장 긴 텍스트로 초기화
        self.startTimeLabel.setStyleSheet(labelStyle)
        font_metrics = self.startTimeLabel.fontMetrics()
        text_width = font_metrics.horizontalAdvance("방송시작 : 0000-00-00 00:00:00") # 가장 긴 텍스트 기준
        self.startTimeLabel.setMinimumWidth(text_width + 5)
        infoLayout.addWidget(self.startTimeLabel, 0, 0)

        self.recordingTimeLabel = QLabel("녹화시간 : 00:00:00")
        self.recordingTimeLabel.setStyleSheet(labelStyle)
        infoLayout.addWidget(self.recordingTimeLabel, 1, 0)

        # QCheckBox 스타일 (내부 여백 제거)
        checkBoxStyle = """
            QCheckBox {
                padding: 0px;
                spacing: 2px; 
            }
        """

        self.reserveCheckBox = QCheckBox("예약 녹화")
        self.reserveCheckBox.setChecked(self.channel.get("record_enabled", False))
        self.reserveCheckBox.setStyleSheet(checkBoxStyle)  # 스타일 적용
        self.reserveCheckBox.stateChanged.connect(
            lambda state, channel_id=self.channel["id"]: self.parent.set_channel_record_enabled(
                channel_id, state == Qt.Checked
            )
        )
        infoLayout.addWidget(self.reserveCheckBox, 1, 1)
        rightLayout.addLayout(infoLayout)  # 정보 레이아웃 추가

        # 방송 제목 레이블 (글자 크기에 맞게 높이 자동 조절)
        self.liveTitleLabel = QLabel("방송 제목:")
        self.liveTitleLabel.setWordWrap(False)
        self.liveTitleLabel.setFixedWidth(410)
        self.liveTitleLabel.setFixedHeight(15)
        layout.addWidget(self.liveTitleLabel, 3, 0, 1, 2)

        # rightWidget을 레이아웃에 추가
        layout.addWidget(rightWidget, 0, 1)
        layout.setColumnStretch(0, 0)
        layout.setColumnStretch(1, 0)
        self.setLayout(layout)

    def update_thumbnail(self, pixmap):
        self.thumbnailLabel.setPixmap(
            pixmap.scaled(200, 112, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        )

    def set_initial_overlay(self): # 추가: 초기 오버레이 설정 함수
        """
        채널 위젯 생성 시 기본 오버레이 텍스트를 설정합니다.
        """
        overlay_text = (
            f"<span style='font-size: 16pt; font-weight: bold; text-shadow: -1px -1px 0 black, 1px -1px 0 black, -1px 1px 0 black, 1px 1px 0 black;'>{self.channel['name']}</span> "
            f"<span style='color: blue;'>[방송종료]</span>"  # 기본값: 방송종료
        )
        self.overlayLabel.setText(overlay_text)

    def update_info(self, metadata):
        live_title = metadata.get("live_title", "Unknown Title")
        # 카테고리가 없는 경우를 처리 (빈 문자열로 설정)
        current_category = metadata.get("category", "")  
        open_live = "방송중" if metadata.get("open_live") else "방송종료"

        if metadata.get("open_live"):
            status_color = "red"
        else:
            status_color = "blue"

        # 카테고리가 있으면 표시, 없으면 채널 이름만 표시
        if current_category:
            overlay_text = (
                f"<span style='color: yellow;'>{current_category}</span><br>"  # 카테고리 노란색
                f"<span style='font-size: 13pt; font-weight: bold; text-shadow: -1px -1px 0 black, 1px -1px 0 black, -1px 1px 0 black, 1px 1px 0 black;'>{self.channel['name']}</span> "
                f"<span style='color: {status_color};'>[{open_live}]</span>"
            )
        else:
            overlay_text = (
                f"<span style='font-size: 13pt; font-weight: bold;text-shadow: -1px -1px 0 black, 1px -1px 0 black, -1px 1px 0 black, 1px 1px 0 black;'>{self.channel['name']}</span> "
                f"<span style='color: {status_color};'>[{open_live}]</span>"
            )

        self.overlayLabel.setText(overlay_text)

        # 방송 제목 레이블 업데이트 (일반 텍스트, 잘림 처리)
        elided_title = self.elide_text(self.liveTitleLabel, live_title)
        self.liveTitleLabel.setText(elided_title)
        self.liveTitleLabel.setToolTip(live_title)  # 전체 제목은 마우스 오버 시 표시

    def elide_text(self, label, text):
        """
        QLabel의 너비에 맞게 텍스트를 자르고 ...을 추가합니다.
        """
        font_metrics = label.fontMetrics()
        elided_text = font_metrics.elidedText(text, Qt.ElideRight, label.width())
        return elided_text
    
    def toggle_recording(self):
        if self.is_recording:
            self.parent.stopRecording(self.channel["id"])
            self.recordButton.setText("녹화 시작")
            self.recordButton.setStyleSheet("")
            if self.is_chatting:
                self.toggle_chat()
        else:
            self.parent.startRecording(self.channel["id"])
            self.recordButton.setText("녹화중")
            self.recordButton.setStyleSheet("background-color: red; color: white;")
            # 채팅도 시작 (녹화 시작 시)
            if not self.is_chatting:
                self.toggle_chat()
        self.is_recording = not self.is_recording

    def toggle_chat(self):
        if self.is_chatting:
            self.parent.stopChat(self.channel["id"])
            self.chatButton.setText("채팅 시작")
            self.chatButton.setStyleSheet("")
        else:
            self.parent.startChat(self.channel["id"])
            self.chatButton.setText("채팅중")
            self.chatButton.setStyleSheet("background-color: blue; color: white;")
        self.is_chatting = not self.is_chatting

    def update_time_info(self, start_time_str, recording_time, chat_status):
        self.startTimeLabel.setText(f"<b>방송시작:</b> {start_time_str}")
        self.recordingTimeLabel.setText(f"<b>녹화시간:</b> {recording_time}")
        # self.chatStatusLabel.setText(f"<b>채팅:</b> {chat_status}") # 제거

    def elide_text(self, label, text):
        """
        QLabel의 너비에 맞게 텍스트를 자르고 ...을 추가합니다.
        """
        font_metrics = label.fontMetrics()
        elided_text = font_metrics.elidedText(text, Qt.ElideRight, label.width())
        return elided_text

class RunRecordApp(QMainWindow):
    icon_path = os.path.join(
        os.path.dirname(os.path.realpath(__file__)),
        "dependent",
        "img",
        "default_icon.png",
    )
    update_ui_signal = pyqtSignal(object, object)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("치지직 자동녹화 v1.0_0308")
        self.setMinimumSize(800, 600)
        self.setWindowIcon(QIcon(self.icon_path))
        self.config = load_config()

        self.installEventFilter(self)

        self.network_manager = QNetworkAccessManager()
        self.network_manager.finished.connect(self.onImageLoadFinished)
        self.channel_thumbnails = {}
        self.url_to_channel = {}

        self.client = None
        self.channel_widgets = {}
        self.channels = load_channels()
        self.liveRecorder = LiveRecorder(self.channels)

        self.channelInfos = {}
        self.channelTimeLabels = {}
        self.chat_status = {}

        self.retryLimit = 3
        self.currentRetry = {}
        self.retryDelay = 5000

        self.url_to_label_mapping = {}
        self.initUI()

        self.liveRecorder.metadata_updated.connect(self.on_metadata_updated)

        self.liveRecorder.recording_started.connect(self.on_recording_started)
        self.liveRecorder.recording_finished.connect(self.on_recording_finished)
        self.liveRecorder.chat_started.connect(self.on_chat_started)
        self.liveRecorder.chat_stopped.connect(self.on_chat_stopped)

        self.liveRecorder.metadata_updated.connect(self.on_metadata_updated)

        QTimer.singleShot(0, self.fetchAndUpdateMetadata)

        self.updateTimer = QTimer(self)
        self.updateTimer.timeout.connect(self.updateRecordingTime)
        self.updateTimer.start(1000)

        self.refreshTimer = QTimer(self)
        self.refreshTimer.timeout.connect(self.fetchAndUpdateMetadata)
        self.refreshTimer.start(300000)

        self.applyAutoRecordMode()
        self.executor = ThreadPoolExecutor(max_workers=4)

    async def run_app_async(self):
        print("앱 실행 중...")
        session_cookies = load_cookies()
        try:
            self.client = httpx.AsyncClient(cookies=session_cookies)
            await self.fetchAndUpdateMetadata()
        except Exception as e:
            print(f"비동기 작업 실행 중 예외 발생: {e}")
        finally:
            if self.client is not None:
                await self.client.aclose()
            print("httpx 클라이언트 연결 종료")

    async def close_async_client(self):
        if self.client and not self.client.is_closed:
            await self.client.aclose()

    @pyqtSlot(str)
    def on_recording_started(self, channel_id):
        """녹화 시작 시그널 처리"""
        channel_widget = self.channel_widgets.get(channel_id)
        if channel_widget:
            channel_widget.is_recording = True
            channel_widget.recordButton.setText("녹화중")
            channel_widget.recordButton.setStyleSheet(
                "background-color: red; color: white;"
            )
            # 자동 채팅 시작 (필요한 경우)
            if not channel_widget.is_chatting:
                channel_widget.toggle_chat()

    @pyqtSlot(str)
    def on_recording_finished(self, channel_id):
        """녹화 종료 시그널 처리"""
        channel_widget = self.channel_widgets.get(channel_id)
        if channel_widget:
            channel_widget.is_recording = False
            channel_widget.recordButton.setText("녹화 시작")
            channel_widget.recordButton.setStyleSheet("")

            # 채팅 버튼 상태도 함께 변경 (녹화 종료 시 채팅도 종료되므로)
            if channel_widget.is_chatting: # 채팅중이면,
              channel_widget.is_chatting = False  # 상태변경
              channel_widget.chatButton.setText("채팅 시작")
              channel_widget.chatButton.setStyleSheet("")

    def closeEvent(self, event):
        reply = QMessageBox.question(
            self,
            "종료 확인",
            "정말로 종료하시겠습니까?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            # for channel_id in list(self.liveRecorder.chat_processes.keys()):
            #     self.liveRecorder.stop_chat_background(channel_id) # 더이상 여기서 처리하지 않음.

            for channel_id in list(self.liveRecorder.recording_processes.keys()):
                self.liveRecorder.stopRecording(channel_id)

            asyncio.run_coroutine_threadsafe(
                self.close_async_client(), asyncio.get_event_loop()
            )

            event.accept()
        else:
            event.ignore()

    def run_background_task(self, func, *args):
        loop = asyncio.get_event_loop()
        return loop.run_in_executor(self.executor, func, *args)

    async def run_app(self):
        print("앱 실행 중...")
        session_cookies = self.liveRecorder.get_session_cookies()
        try:
            self.client = httpx.AsyncClient(cookies=session_cookies)
            await self.fetchAndUpdateMetadata()
        except Exception as e:
            print(f"비동기 작업 실행 중 예외 발생: {e}")
        finally:
            await self.client.aclose()
            print("httpx 클라이언트 연결 종료")

    def eventFilter(self, source, event):
        if (
            event.type() == CHANNEL_ADDED_EVENT
            or event.type() == CHANNEL_REMOVED_EVENT
        ):
            self.handleChannelEvent(event)
            return True
        return super().eventFilter(source, event)

    def handleChannelEvent(self, event):
        if event.type() == CHANNEL_ADDED_EVENT:
            channelData = event.data
            self.channels.append(channelData)
            save_channels(self.channels)
            self.add_channel_grid_layout(channelData)
            QTimer.singleShot(
                0, lambda: asyncio.ensure_future(self.update_widget_later(channelData))
            )

        elif event.type() == CHANNEL_REMOVED_EVENT:
            channel_id = event.data
            channel_name = self.liveRecorder.findChannelNameById(channel_id)
            self.delete_widget(channel_id)
            self.channels = [
                channel for channel in self.channels if channel["id"] != channel_id
            ]
            save_channels(self.channels)

            if channel_id in self.channelTimeLabels:
                del self.channelTimeLabels[channel_id]

            print(
                f"채널 삭제: '{channel_name}'"
                if channel_name
                else "알 수 없는 채널 삭제"
            )

    def add_channel_grid_layout(self, channelData):
        """
        새 채널 위젯을 생성하고 그리드 레이아웃에 추가합니다.
        """
        widget = ChannelWidget(channelData, self)
        self.channel_widgets[channelData["id"]] = widget
        row = self.gridLayout.rowCount()
        col = 0

        # 이미 있는 위젯들을 검사하여 열 위치 결정
        for i in range(self.gridLayout.count()):
            item = self.gridLayout.itemAt(i)
            if item:  # item이 None이 아닐 때만
                item_row, item_col, row_span, col_span = self.gridLayout.getItemPosition(i) # 수정된 부분
                if item_row == row:
                    col = max(col,item_col + col_span)  # 수정: 현재 열 + 열 span

        # 한 행에 최대 4개의 위젯 배치
        if col >= 4:
            row += 1
            col = 0

        self.gridLayout.addWidget(widget, row, col)

    def delete_widget(self, channel_id):
        """
        채널 위젯을 제거하고 레이아웃에서 삭제합니다.
        """
        if channel_id in self.channel_widgets:
            widget = self.channel_widgets[channel_id]

            self.gridLayout.removeWidget(widget)
            widget.deleteLater()
            del self.channel_widgets[channel_id]
            print(f"채널 위젯 삭제: {channel_id}")

            self.rearrange_grid_layout()

    def rearrange_grid_layout(self):
        """
        채널 위젯이 제거된 후 그리드 레이아웃을 재정렬합니다.
        """
        for i in reversed(range(self.gridLayout.count())):
            widget = self.gridLayout.itemAt(i).widget()
            if widget is not None:
                self.gridLayout.removeWidget(widget)

        row = 0
        col = 0
        for channel_id, widget in self.channel_widgets.items():
            self.gridLayout.addWidget(widget, row, col)
            col += 1
            if col > 3:
                col = 0
                row += 1

    def schedule_update_widget_later(self, channel_id):
        loop = asyncio.get_event_loop()
        loop.create_task(self.update_widget_later(channel_id))

    @asyncSlot(str, object)
    async def on_metadata_updated(self, channel_id, metadata):
        if not hasattr(self, "metadata_updated_event"):
            self.metadata_updated_event = asyncio.Event()
        else:
            await self.metadata_updated_event.wait()
            self.metadata_updated_event.clear()

        if not hasattr(self, "client"):
            await self.initialize_client()
        elif self.client.is_closed:
            await self.initialize_client()

        if channel_id not in self.channel_widgets:
            print(
                f"[오류] {channel_id}에 대한 채널 위젯을 찾을 수 없습니다. 메타데이터를 업데이트할 수 없습니다."
            )
            return

        try:
            await self.update_channel_widget(channel_id, metadata, self.client)
        except Exception as e:
            print(f"[오류] {channel_id}의 채널 위젯을 업데이트하는 중 예외가 발생했습니다: {e}")
        finally:
            self.metadata_updated_event.set()

    async def initialize_client(self):
        if not self.client or self.client.is_closed:
            headers = get_headers(load_cookies())
            self.client = httpx.AsyncClient(headers=headers, timeout=30.0)  # 예: 30초로 늘림

    def create_button(self, text, width, handler):
        button = QPushButton(text, self)
        button.setFixedWidth(width)
        button.clicked.connect(handler)
        return button

    def initUI(self):
        print("UI 초기화 시작")  # UI 초기화 메시지 (한 번만 출력)
        self.container = QWidget()
        self.layout = QVBoxLayout(self.container)

        self.buttonsLayout = QHBoxLayout()
        self.addStreamerButton = self.create_button("스트리머 추가", 130, self.addStreamer)
        self.buttonsLayout.addWidget(self.addStreamerButton)
        self.downloadVODButton = self.create_button("VOD 다운로드", 130, self.downloadVOD)
        self.buttonsLayout.addWidget(self.downloadVODButton)

        self.startAllButton = self.create_button("모두 녹화 시작", 130, self.startAllRecording)
        self.buttonsLayout.addWidget(self.startAllButton)

        self.stopAllButton = self.create_button("모두 녹화 중지", 130, self.stopAllRecording)
        self.buttonsLayout.addWidget(self.stopAllButton)

        self.settingsButton = self.create_button("환경설정", 130, self.openSettingsWindow)
        self.buttonsLayout.addWidget(self.settingsButton)

        self.autoRecordToggleButton = self.create_button(
            "자동 녹화 모드: OFF", 130, self.toggleAutoRecordMode
        )
        self.autoRecordToggleButton.setCheckable(True)
        self.buttonsLayout.addWidget(self.autoRecordToggleButton)

        self.startAllChatButton = self.create_button("모두 채팅 시작", 130, self.startAllChat)
        self.buttonsLayout.addWidget(self.startAllChatButton)

        self.stopAllChatButton = self.create_button("모두 채팅 중지", 130, self.stopAllChat)
        self.buttonsLayout.addWidget(self.stopAllChatButton)

        self.layout.addLayout(self.buttonsLayout)

        self.scrollArea = QScrollArea(self)
        self.scrollArea.setWidgetResizable(True)  # 중요: True로 설정
        self.scrollAreaWidget = QWidget()
        self.gridLayout = QGridLayout(self.scrollAreaWidget)
        self.gridLayout.setSpacing(10)  # 위젯 간 간격 (원하는 값으로)
        self.gridLayout.setContentsMargins(10, 10, 10, 10)  # 스크롤 영역 내부 여백
        self.gridLayout.setSizeConstraint(QLayout.SetFixedSize) # 중요: 고정 크기

        self.scrollArea.setWidget(self.scrollAreaWidget)
        self.layout.addWidget(self.scrollArea)

        self.setCentralWidget(self.container)
        self.initChannelWidgets()
        print("UI 초기화 완료")

        # 최소 크기 설정 (선택 사항)
        self.setMinimumSize(720, 480)  # 적절한 최소 크기

    def downloadVOD(self):
        current_dir = os.path.dirname(os.path.realpath(__file__))
        vod_downloader_path = os.path.join(current_dir, "module", "VOD_downloader.py")
        try:
            subprocess.Popen(
                [sys.executable, vod_downloader_path],
                creationflags=subprocess.CREATE_NEW_CONSOLE,
            )
        except subprocess.CalledProcessError:
            QMessageBox.critical(self, "실행 실패", "VOD_downloader 실행 중 오류가 발생했습니다.")

    def toggleAutoRecordMode(self):
        is_checked = self.autoRecordToggleButton.isChecked()
        self.config["auto_record_mode"] = is_checked
        save_config(self.config)

        if is_checked:
            self.autoRecordToggleButton.setText("자동 녹화 모드: ON")
            self.autoRecordToggleButton.setStyleSheet(
                "QPushButton {"
                "background-color: black;"
                "border: 1px solid #555;"
                "border-radius: 5px;"
                "padding: 5px;"
                "text-align: center;"
                "color: white;"
                "}"
                "QPushButton:pressed {"
                "background-color: #333;"
                "}"
            )
        else:
            self.autoRecordToggleButton.setText("자동 녹화 모드: OFF")
            self.autoRecordToggleButton.setStyleSheet("")

    def applyAutoRecordMode(self):
        if self.config.get("auto_record_mode", False):
            self.autoRecordToggleButton.setChecked(True)
            self.autoRecordToggleButton.setText("자동 녹화 모드: ON")

        else:
            self.autoRecordToggleButton.setChecked(False)
            self.autoRecordToggleButton.setText("자동 녹화 모드: OFF")

    def findLabelForChannel(self, channel_id):
        return self.channelTimeLabels.get(channel_id)

    def updateRecordingTime(self):
        for channel in self.liveRecorder.channels:
            channel_id = channel["id"]
            channel_widget = self.channel_widgets.get(channel_id)
            if not channel_widget:
                continue

            is_recording = self.liveRecorder.recording_status.get(channel_id, False)
            metadata = self.liveRecorder.live_metadata.get(channel_id, {})

            if channel_id not in self.channelInfos:
                start_time_str = metadata.get("openDate", "00:00:00")
                if start_time_str == "00:00:00":
                    start_time_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                self.channelInfos[channel_id] = {"openDate": start_time_str}

            start_time_str = self.channelInfos[channel_id]["openDate"]

            chat_status = (
                "ON" if self.liveRecorder.chat_status.get(channel_id, False) else "OFF"
            )

            if is_recording:
                try:
                    start_time = datetime.strptime(start_time_str, "%Y-%m-%d %H:%M:%S")
                    elapsed_time = datetime.now() - start_time
                    elapsed_time = max(
                        timedelta(0), elapsed_time - timedelta(seconds=3)
                    )  # 3초 보정
                    total_seconds = int(elapsed_time.total_seconds())

                except ValueError as e:
                    print(f"Error parsing start time: {start_time_str} - {e}")
                    recording_time = "00:00:00"
                    start_time_str = "00:00:00"

                else:
                    hours = int(total_seconds // 3600)
                    minutes = int((total_seconds % 3600) // 60)
                    seconds = int(total_seconds % 60)
                    recording_time = f"{hours:02}:{minutes:02}:{seconds:02}"

                channel_widget.update_time_info(
                    start_time_str, recording_time, chat_status
                )
            else:
                channel_widget.update_time_info(start_time_str, "00:00:00", chat_status)

    async def update_thumbnail(self, thumbnail_url, label, live_status):
        thumbnail_url = thumbnail_url.replace("{type}", "270")
        response = await self.client.get(thumbnail_url)
        if response.status_code == 200:
            pixmap = QPixmap()
            pixmap.loadFromData(response.content)
            if live_status:
                label.setPixmap(
                    pixmap.scaled(200, 112, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                )
            else:
                pixmap = self.liveRecorder.effect_thumbnail(pixmap)
                label.setPixmap(
                    pixmap.scaled(200, 112, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                )

    async def update_channel_info(self, channel_id, metadata):
        channel_widget = self.channel_widgets.get(channel_id)
        if channel_widget is None or sip.isdeleted(channel_widget):
            print(f"[오류] {channel_id}에 대한 위젯을 찾을 수 없거나 삭제되었습니다.")
            return

        retries = 3  # 재시도 횟수 (썸네일 다운로드 실패 시)
        for attempt in range(retries):
            try:
                # 썸네일 업데이트
                if metadata.get("thumbnail_url"):
                    thumbnail_url = metadata["thumbnail_url"].replace("{type}", "270")
                    response = await self.client.get(thumbnail_url)
                    response.raise_for_status()  #  404 Not Found 등 오류 발생 시 예외 발생

                    # 200 OK 응답인 경우에만 썸네일 처리
                    if response.status_code == 200:
                        pixmap = QPixmap()
                        pixmap.loadFromData(response.content)
                        channel_widget.update_thumbnail(pixmap)

                # ... (나머지 정보 업데이트) ...
                channel_widget.update_info(metadata) # 썸네일 + 정보 업데이트

                self.channelInfos[channel_id] = {
                    "openDate": metadata.get("recording_duration", "00:00:00")
                }
                self.updateRecordingTime()
                break  # 썸네일 다운로드 및 UI 업데이트 성공했으면 루프 종료

            except httpx.ReadTimeout: # 타임아웃 예외
                print(f"썸네일 다운로드 시간 초과, 재시도 ({attempt + 1}/{retries})")
                if attempt == retries - 1:  # 마지막 시도였다면,
                    print("썸네일 다운로드 실패, 기본 이미지 사용")
                    channel_widget.update_thumbnail(QPixmap(self.liveRecorder.default_thumbnail_path))  # 기본 이미지
                await asyncio.sleep(5)

            except httpx.HTTPStatusError as e: # 404 Not Found 등 HTTP 상태 코드 에러
                # print(f"썸네일 다운로드 HTTP 오류: {e}")
                if e.response.status_code == 404:
                    # print("썸네일 이미지를 찾을 수 없음, 기본 이미지 사용")
                    channel_widget.update_thumbnail(QPixmap(self.liveRecorder.default_thumbnail_path)) # 기본 썸네일
                    break # 404 에러의 경우, 더이상 URL을 통해 이미지를 가져올 수 없으므로, 재시도 x
                else: #404가 아닌 다른 에러
                    if attempt == retries-1: # 마지막 시도
                        print("썸네일 다운로드 실패, 기본 이미지 사용")
                        channel_widget.update_thumbnail(QPixmap(self.liveRecorder.default_thumbnail_path))
                    else: # 마지막 시도가 아니면
                        await asyncio.sleep(5) # 잠시 후 재시도

            except httpx.RequestError as e:  # 기타 httpx 오류
                print(f"썸네일 다운로드 요청 오류: {e}")
                break

            except Exception as e:
                print(f"UI 업데이트 중 예외 발생 (update_channel_info): {e}, {traceback.format_exc()}")
                break

    async def load_metadata_and_update_ui(self, client):
        for channel in self.channels:
            try:
                metadata = await self.liveRecorder.get_live_metadata(channel, client)
                await self.update_channel_widget(channel["id"], metadata, client)
            except Exception as e:
                print(
                    f"Error loading metadata for channel {channel['name']}: {str(e)}"
                )

    async def update_channel_widget(self, channel_id, metadata, client, retries=3):
        if retries == 0:
            channel_name = self.liveRecorder.findChannelNameById(channel_id)
            print(f"[재시도 실패] {channel_name} 채널의 UI 업데이트에 실패했습니다.")
            return

        try:
            await self.update_channel_info(channel_id, metadata)
        except Exception as e:
            print(f"UI 업데이트 중 예외 발생: {e}. 재시도 횟수: {retries}")
            await asyncio.sleep(5)
            await self.update_channel_widget(channel_id, metadata, client, retries - 1)

    @asyncSlot()
    async def update_widget_later(self, channel):
        print(f"{channel['name']} 채널의 메타데이터를 업데이트 중입니다")
        metadata = await self.liveRecorder.get_live_metadata(channel, self.client)
        if metadata is not None:
            print(f"{channel['name']} 채널의 메타데이터를 가져왔습니다: {metadata}")
            await self.update_channel_widget(channel["id"], metadata, self.client)
        else:
            print(f"{channel['name']} 채널의 메타데이터를 가져오지 못했습니다")

    @qasync.asyncSlot()
    async def fetchAndSetMetadataForChannel(self, channel):
        metadata = await self.liveRecorder.get_live_metadata(channel, self.client)
        await self.update_channel_widget(channel["id"], metadata, self.client)

    def set_thumbnail_from_reply(self, reply, label):
        if reply.error() == QNetworkReply.NoError:
            data = reply.readAll()
            pixmap = QPixmap()
            if pixmap.loadFromData(data):
                label.setPixmap(
                    pixmap.scaled(
                        200, 200, Qt.KeepAspectRatio, Qt.SmoothTransformation
                    )
                )
        reply.deleteLater()

    def loadThumbnail(self, url, label):
        request = QNetworkRequest(QUrl(url))
        self.network_manager.get(request)
        self.url_to_label_mapping[url] = label

    def onImageLoadFinished(self, reply):
        url = reply.request().url().toString()
        if reply.error():
            print(f"Error loading {url}: {reply.errorString()}")
            return

        pixmap = QPixmap()
        if pixmap.loadFromData(reply.readAll()):
            label = self.url_to_label_mapping.get(url)
            if label:
                label.setPixmap(pixmap.scaledToWidth(200))

    def initChannelWidgets(self):
        """
        채널 위젯들을 초기화하고 QGridLayout에 추가합니다.
        """
        row = 0
        col = 0
        for channel in self.channels:
            widget = ChannelWidget(channel, self)  # 사용자 정의 위젯 생성
            self.channel_widgets[channel["id"]] = widget  # 딕셔너리에 저장
            self.gridLayout.addWidget(widget, row, col)  # 그리드 레이아웃에 추가
            col += 1
            if col > 3:  # 한 줄에 4개씩 배치
                col = 0
                row += 1

    def addChannelWidget(self, channel):  # 더 이상 사용하지 않음
        channel_name = channel["name"]
        channel_id = channel["id"]

        if channel_id in self.channel_widgets:
            print(f"채널 위젯 추가: 채널 '{channel_name}'의 위젯이 이미 존재합니다.")
            return

        channelWidget = QWidget()
        channelLayout = QHBoxLayout(channelWidget)

        # 썸네일 이미지
        thumbnailLabel = QLabel()
        thumbnailLabel.setObjectName(f"thumbnail{channel['id']}")
        thumbnailLabel.setFixedWidth(200)
        thumbnailLabel.setStyleSheet("border: 1px solid #ccc;")
        defaultThumbnail = QPixmap(self.liveRecorder.default_thumbnail_path)
        thumbnailLabel.setPixmap(
            defaultThumbnail.scaled(200, 112, Qt.KeepAspectRatio)
        )
        channelLayout.addWidget(thumbnailLabel)

        infoAndButtonsLayout = QVBoxLayout()

        channelNameLabel = QLabel(f"<b>{channel['name']}</b>")
        channelNameLabel.setAlignment(Qt.AlignCenter)
        channelNameLabel.setFixedWidth(200)
        infoAndButtonsLayout.addWidget(channelNameLabel)

        info_text = "로딩 중"
        infoLabel = QLabel(info_text)
        infoLabel.setObjectName(f"infoLabel_{channel['id']}")
        infoLabel.setWordWrap(True)
        infoLabel.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)
        infoAndButtonsLayout.addWidget(infoLabel)

        timeLabel = QLabel("방송시작 : 00:00:00 / 녹화시간 : 00:00:00 / 채팅: OFF")
        self.channelTimeLabels[channel["id"]] = timeLabel
        infoAndButtonsLayout.addWidget(timeLabel)

        reserveCheckBox = QCheckBox("예약 녹화")
        reserveCheckBox.setChecked(channel.get("record_enabled", False))
        reserveCheckBox.stateChanged.connect(
            lambda state, channel_id=channel_id: self.set_channel_record_enabled(
                channel_id, state == Qt.Checked
            )
        )
        infoAndButtonsLayout.addWidget(reserveCheckBox)


        buttonsLayout = QHBoxLayout()

        startButton = QPushButton("녹화 시작")
        startButton.setFixedWidth(110)
        startButton.clicked.connect(self.createStartButtonClickedHandler(channel["id"]))
        buttonsLayout.addWidget(startButton)

        stopButton = QPushButton("녹화 중지")
        stopButton.setFixedWidth(110)
        stopButton.clicked.connect(self.createStopButtonClickedHandler(channel["id"]))
        buttonsLayout.addWidget(stopButton)

        startChatButton = QPushButton("채팅 시작")
        startChatButton.setFixedWidth(110)
        startChatButton.clicked.connect(
            lambda _, ch_id=channel["id"]: self.startChat(ch_id)
        )
        buttonsLayout.addWidget(startChatButton)

        stopChatButton = QPushButton("채팅 중지")
        stopChatButton.setFixedWidth(110)
        stopChatButton.clicked.connect(
            lambda _, ch_id=channel["id"]: self.stopChat(ch_id)
        )
        buttonsLayout.addWidget(stopChatButton)

        gotoButton = QPushButton("바로가기")
        gotoButton.setFixedWidth(80)
        gotoButton.clicked.connect(
            lambda _, channel_id=channel_id: self.open_chzzk_channel(channel_id)
        )
        buttonsLayout.addWidget(gotoButton)

        settingsButton = QPushButton("설정")
        settingsButton.setFixedWidth(40)
        settingsButton.clicked.connect(partial(self.openChannelSettings, channel["id"]))
        buttonsLayout.addWidget(settingsButton)

        openfolderButton = QPushButton("열기")
        openfolderButton.setFixedWidth(40)
        openfolderButton.clicked.connect(
            partial(self.openRecordedFolder, channel["output_dir"])
        )
        buttonsLayout.addWidget(openfolderButton)

        deleteButton = QPushButton("삭제")
        deleteButton.setFixedWidth(40)
        deleteButton.clicked.connect(
            lambda _, channel=channel: self.deleteChannel(channel["id"])
        )
        buttonsLayout.addWidget(deleteButton)

        infoAndButtonsLayout.addLayout(buttonsLayout)
        channelLayout.addWidget(thumbnailLabel)
        channelLayout.addLayout(infoAndButtonsLayout)

        self.channel_widgets[channel["id"]] = channelWidget
        self.scrollAreaLayout.addWidget(channelWidget)
        self.scrollAreaLayout.setSpacing(20)
        self.chat_status[channel_id] = "OFF"

    def startChat(self, channel_id):
        """채팅 시작 함수 (UI 연결)"""
        if not self.liveRecorder.chat_status.get(channel_id, False):
            # asyncio.run_coroutine_threadsafe( # 더이상 사용하지 않음.
            #     self.liveRecorder.start_chat_background(channel_id),
            #     asyncio.get_event_loop(),
            # )
            print(f"채팅 시작 (채널 ID: {channel_id})")
        else:
            print(f"채팅이 이미 실행 중입니다 (채널 ID: {channel_id})")

    def stopChat(self, channel_id):
        """채팅 중지 함수 (UI 연결)"""
        if self.liveRecorder.chat_status.get(channel_id, False):
            # self.liveRecorder.stop_chat_background(channel_id) # 더이상 사용하지 않음
            self.liveRecorder.chat_status[channel_id] = False
            print(f"채팅 중지 (채널 ID: {channel_id})")
        else:
            print(f"채팅이 실행 중이 아닙니다 (채널 ID: {channel_id})")

    def createStartButtonClickedHandler(self, channel_id):
        def handler():
            self.liveRecorder.startBackgroundRecording(channel_id)

        return handler

    def createStopButtonClickedHandler(self, channel_id):
        def handler():
            try:
                self.liveRecorder.stopRecording(channel_id, force_stop=True)
            except Exception as e:
                print(f"녹화 중지 중 예외 발생: {e}")
                QMessageBox.critical(
                    self, "녹화 중지 오류", f"녹화 중지 중 오류가 발생했습니다: {e}"
                )

        return handler

    @pyqtSlot(str)  # 추가
    def on_chat_started(self, channel_id):
        channel_widget = self.channel_widgets.get(channel_id)
        if channel_widget:
            channel_widget.is_chatting = True  # 올바른 위치로 이동
            channel_widget.chatButton.setText("채팅중")
            channel_widget.chatButton.setStyleSheet("background-color: blue; color: white;")

    @pyqtSlot(str)  # 추가
    def on_chat_stopped(self, channel_id):
        channel_widget = self.channel_widgets.get(channel_id)
        if channel_widget:
            channel_widget.is_chatting = False  # 올바른 위치로 이동
            channel_widget.chatButton.setText("채팅 시작")
            channel_widget.chatButton.setStyleSheet("")


    def open_chzzk_channel(self, channel_id):
        url = f"https://chzzk.naver.com/live/{channel_id}"
        try:
            webbrowser.open(url)
        except Exception as e:
            QMessageBox.critical(self, "오류", f"URL 열기 실패: {e}")

    def openRecordedFolder(self, output_dir):
        if os.path.exists(output_dir):
            os.startfile(output_dir)
        else:
            QMessageBox.warning(self, "경고", "폴더가 존재하지 않습니다.")

    def deleteChannel(self, channel_id):
        channel_name = self.liveRecorder.findChannelNameById(channel_id)
        channel = next((ch for ch in self.channels if ch["id"] == channel_id), None)
        if channel is None:
            QMessageBox.warning(self, "경고", f"'{channel_name}' 채널을 찾을 수 없습니다.")
            return

        reply = QMessageBox.question(
            self,
            "채널 삭제",
            f"'{channel['name']}' 채널을 삭제하시겠습니까?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )

        if reply == QMessageBox.Yes:
            self.channels.remove(channel)
            save_channels(self.channels)
            QApplication.postEvent(
                self, CustomEvent(CHANNEL_REMOVED_EVENT, data=channel["id"])
            )

    @asyncSlot()
    async def fetchAndUpdateMetadata(self):
        if not self.client or self.client.is_closed:
            session_cookies = load_cookies()
            self.client = httpx.AsyncClient(cookies=session_cookies)

        try:
            self.liveRecorder.fetch_metadata_for_all_channels()
        except Exception as e:
            print(f"메타데이터 업데이트 중 예외 발생: {e}")

        finally:
            if (
                hasattr(self, "metadata_updated_event")
                and not self.metadata_updated_event.is_set()
            ):
                self.metadata_updated_event.set()

    def refreshChannelWidgets(self):
        self.clearLayout(self.scrollAreaLayout)
        self.fetch_and_update_metadata()
        self.initChannelWidgets()

    def clearLayout(self, layout):
        if layout is not None:
            while layout.count():
                item = layout.takeAt(0)
                widget = item.widget()
                if widget is not None:
                    widget.deleteLater()
                else:
                    self.clearLayout(item.layout())

    def startRecording(self, channel_id):
        self.channels = load_channels()
        self.liveRecorder.startBackgroundRecording(channel_id)
        if not self.config.get("auto_record_mode", False):
            self.startChat(channel_id)

    def stopRecording(self, channel_id):
        self.liveRecorder.stopRecording(channel_id, force_stop=True)

    def startAllRecording(self):
        print("모든 채널 즉시 녹화 시작")
        for channel in self.channels:
            self.liveRecorder.startBackgroundRecording(channel["id"])
            self.startChat(channel["id"])  # 채팅 자동 시작

    def stopAllRecording(self):
        for channel in self.channels:
            self.stopRecording(channel["id"])

    def startAllChat(self):
        for channel in self.channels:
            self.startChat(channel["id"])

    def stopAllChat(self):
        for channel_id in list(self.liveRecorder.chat_processes.keys()):
            self.stopChat(channel_id)

    def openSettingsWindow(self):
        self.settingsWindow = SettingsWindow(self)
        self.settingsWindow.show()

    async def fetch_channel_name_async(self, uid):
        try:
            channel_name = await fetch_channelName(uid)
            return channel_name
        except Exception as e:
            print(f"채널 이름 가져오기 실패 (UID: {uid}): {e}")
            return None

    def addStreamer(self):
        self.dialog = QDialog(self)
        self.dialog.setWindowTitle("스트리머 추가")
        self.dialog.setFixedWidth(250)
        layout = QVBoxLayout(self.dialog)

        uidLabel = QLabel("스트리머 UID:")
        self.uidEdit = QLineEdit()
        nameLabel = QLabel("채널명:")
        self.nameEdit = QLineEdit()

        autofillButton = QPushButton("자동 채우기")
        autofillButton.clicked.connect(self.autofillChannelInfo)
        autofillLayout = QHBoxLayout()
        autofillLayout.addWidget(nameLabel)
        autofillLayout.addWidget(autofillButton)

        directoryLabel = QLabel("저장 폴더:")
        self.directoryEdit = QLineEdit()
        browseButton = QPushButton("폴더 선택")

        browseButton.clicked.connect(lambda: self.selectDirectory(self.directoryEdit))

        qualityLabel = QLabel("녹화 품질:")
        self.qualityCombo = QComboBox()
        self.qualityCombo.setEditable(True)
        self.qualityCombo.addItems(["best", "1080p", "720p", "480p", "360p", "144p"])

        extensionLabel = QLabel("파일 확장자:")
        self.extensionCombo = QComboBox()
        self.extensionCombo.addItems([".ts", ".mp4"])

        addButton = QPushButton("추가")
        addButton.clicked.connect(self.onAddChannelButtonClick)

        layout.addWidget(uidLabel)
        layout.addWidget(self.uidEdit)
        layout.addLayout(autofillLayout)
        layout.addWidget(self.nameEdit)
        layout.addWidget(directoryLabel)
        layout.addWidget(self.directoryEdit)
        layout.addWidget(browseButton)
        layout.addWidget(qualityLabel)
        layout.addWidget(self.qualityCombo)
        layout.addWidget(extensionLabel)
        layout.addWidget(self.extensionCombo)
        layout.addWidget(addButton)

        self.dialog.exec_()

    async def autofillChannelInfo(self):
        uid = self.uidEdit.text()
        if uid:
            channel_name = await self.fetch_channel_name_async(uid)
            if channel_name:
                self.nameEdit.setText(channel_name)
            else:
                QMessageBox.warning(self.dialog, "오류", "채널 이름을 가져오는 데 실패했습니다.")

    def onAddChannelButtonClick(self):
        uid = self.uidEdit.text()
        name = self.nameEdit.text()
        directory = self.directoryEdit.text()
        quality = self.qualityCombo.currentText()
        extension = self.extensionCombo.currentText()

        if uid and name and directory and quality and extension:
            absolute_directory = os.path.abspath(directory)

            channelData = {
                "id": uid,
                "name": name,
                "output_dir": absolute_directory,
                "quality": quality,
                "extension": extension,
                "record_enabled": False,  # "예약 녹화"를 False로 설정
            }
            customEvent = CustomEvent(CHANNEL_ADDED_EVENT, data=channelData)
            QApplication.postEvent(self, customEvent)
            self.dialog.accept()
        else:
            QMessageBox.warning(self, "경고", "모든 필드를 채워주세요.")

    async def add_channel(self, channel):
        self.channels.append(channel)
        save_channels(self.channels)
        print("채널 추가됨:", channel)
        await self.add_channel_update(channel)

    async def add_channel_update(self, channel):
        self.addChannelWidget(channel)
        print("UI에 채널 추가됨:", channel)

    def openChannelSettings(self, channel_id):
        channel = next((ch for ch in self.channels if ch["id"] == channel_id), None)
        if not channel:
            QMessageBox.warning(self, "경고", "채널을 찾을 수 없습니다.")
            return
        dialog = QDialog(self)
        dialog.setWindowTitle("채널 설정 수정")
        dialog.setFixedWidth(250)
        layout = QVBoxLayout(dialog)

        uidLabel = QLabel("스트리머 UID:")
        uidEdit = QLineEdit(channel["id"])
        nameLabel = QLabel("채널명:")
        nameEdit = QLineEdit(channel["name"])
        directoryLabel = QLabel("저장 폴더:")
        directoryEdit = QLineEdit(channel["output_dir"])
        browseButton = QPushButton("폴더 선택")
        browseButton.clicked.connect(lambda: self.selectDirectory(directoryEdit))

        qualityLabel = QLabel("녹화 품질:")
        qualityCombo = QComboBox()
        qualityCombo.setEditable(True)
        qualityCombo.addItems(["best", "1080p", "720p", "480p", "360p", "144p"])
        qualityCombo.setCurrentText(channel.get("quality", "best"))

        extensionLabel = QLabel("파일 확장자:")
        extensionCombo = QComboBox()
        extensionCombo.addItems([".ts", ".mp4"])
        extensionCombo.setCurrentText(channel.get("extension", ".ts"))

        saveButton = QPushButton("저장")
        saveButton.clicked.connect(
            lambda: self.confirmChannelSettings(
                dialog,
                uidEdit.text(),
                nameEdit.text(),
                directoryEdit.text(),
                qualityCombo.currentText(),
                extensionCombo.currentText(),
                channel,
            )
        )

        layout.addWidget(uidLabel)
        layout.addWidget(uidEdit)
        layout.addWidget(nameLabel)
        layout.addWidget(nameEdit)
        layout.addWidget(directoryLabel)
        layout.addWidget(directoryEdit)
        layout.addWidget(browseButton)
        layout.addWidget(qualityLabel)
        layout.addWidget(qualityCombo)
        layout.addWidget(extensionLabel)
        layout.addWidget(extensionCombo)
        layout.addWidget(saveButton)

        dialog.exec_()

    def confirmChannelSettings(
        self,
        dialog,
        uid,
        name,
        directory,
        quality,
        extension,
        originalChannel,
    ):
        if uid and name and directory and quality and extension:
            originalChannel["id"] = uid
            originalChannel["name"] = name
            originalChannel["output_dir"] = directory
            originalChannel["quality"] = quality
            originalChannel["extension"] = extension
            save_channels(self.channels)
            self.fetch_metadata_task = self.fetchAndUpdateMetadata()
            dialog.accept()
        else:
            QMessageBox.warning(dialog, "경고", "모든 필드를 채워주세요.")

    def selectDirectory(self, directoryEdit):
        directory = QFileDialog.getExistingDirectory(self, "저장 폴더 선택")
        if directory:
            directoryEdit.setText(directory)

    def set_channel_record_enabled(self, channel_id, enabled):
        channel = next((ch for ch in self.channels if ch["id"] == channel_id), None)
        if channel:
            channel["record_enabled"] = enabled
            save_channels(self.channels)
            print(
                f"채널 {channel['name']}의 record_enabled 설정이 {enabled}로 변경되었습니다."
            )
        else:
            print(f"set_channel_record_enabled: 채널 {channel_id}를 찾을 수 없음")


if __name__ == "__main__":
    app = QApplication(sys.argv)
    loop = qasync.QEventLoop(app)
    asyncio.set_event_loop(loop)

    css_file_path = os.path.join(
        os.path.dirname(os.path.realpath(__file__)), "style.css"
    )

    try:
        with open(css_file_path, "r", encoding="utf-8") as file:
            app.setStyleSheet(file.read())
    except Exception as e:
        print(f"스타일 시트 불러오기 실패: {e}")

    window = RunRecordApp()
    window.show()

    if (
        not hasattr(window, "fetch_metadata_task")
        or window.fetch_metadata_task.done()
    ):
        window.fetch_metadata_task = window.fetchAndUpdateMetadata()
    loop.run_forever()