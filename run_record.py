import importlib
import subprocess
import os
import json
import sys
import traceback
import asyncio
from datetime import datetime, timedelta
from functools import partial
from concurrent.futures import ThreadPoolExecutor, as_completed
import time
import multiprocessing
import threading # 추가

# 모듈 설치 확인 및 설치 함수
def install_missing_modules():
    missing_modules = ["requests", "PyQt5", "httpx", "qasync", "pyperclip", "selenium", "webdriver_manager","websocket-client"]
    installed_modules = []

    # 각 모듈을 시도하여 불러오고, 실패하면 설치 리스트에 추가
    for module in missing_modules:
        try:
            importlib.import_module(module)
        except ImportError:
            installed_modules.append(module)
            print(f"모듈 확인: {module} - 설치 필요")

    # 설치가 필요한 모듈이 있는 경우
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

# 모듈 설치 함수 호출
install_missing_modules()

import httpx
import qasync
from qasync import asyncSlot
from PyQt5 import sip
from PyQt5.QtWidgets import QApplication, QMainWindow, QWidget, QVBoxLayout, QPushButton, QScrollArea, QLabel, QHBoxLayout, QLineEdit, QFileDialog, QMessageBox, QDialog, QSizePolicy, QFrame, QInputDialog, QSystemTrayIcon, QMenu, QComboBox
from PyQt5.QtNetwork import QNetworkAccessManager, QNetworkRequest
from PyQt5.QtCore import Qt, QUrl, QTimer, pyqtSignal, pyqtSlot, QMetaObject, Q_ARG, QEvent, QEventLoop
from PyQt5.QtGui import QPixmap, QPalette, QColor, QIcon

# 현재 디렉토리 경로를 가져와 sys.path에 추가
current_dir = os.path.dirname(os.path.realpath(__file__))
sys.path.append(current_dir)

# 'module' 디렉토리를 sys.path에 추가
module_path = os.path.join(current_dir, 'module')
sys.path.append(module_path)

from Live_recorder import LiveRecorder
from settings_window import SettingsWindow
from channel_manager import load_channels, save_channels, load_config, save_config
from VOD_downloader import VODDownloaderApp  # VODDownloaderApp import

# # run.py 파일의 run_chat_process 함수를 import합니다.
from run import run_chat_process

class CustomEvent(QEvent):
    def __init__(self, eventType, data=None):
        super().__init__(eventType)
        self.data = data

CHANNEL_ADDED_EVENT = QEvent.Type(QEvent.User + 1)
CHANNEL_REMOVED_EVENT = QEvent.Type(QEvent.User + 2)

class RunRecordApp(QMainWindow):
    icon_path = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'dependent', 'img', 'default_icon.png')
    update_ui_signal = pyqtSignal(object, object)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("내맘대로 치지직 자동녹화 v0.9d_1106")
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

        self.retryLimit = 3
        self.currentRetry = {}
        self.retryDelay = 5000 

        self.url_to_label_mapping = {}

        #  채팅 프로세스 관리를 위한 딕셔너리
        self.chat_processes = {}
        self.is_recording = False  # 녹화 중 여부 플래그
        self.is_vod_downloading = False # vod 다운로드 여부 플래그
        self.mutex = threading.Lock() # 뮤텍스 객체 생성

        self.initUI()
        
        self.updateTimer = QTimer(self)
        self.updateTimer.timeout.connect(self.updateRecordingTime)
        self.updateTimer.start(5000)

        self.refreshTimer = QTimer(self)
        self.refreshTimer.timeout.connect(self.fetchAndUpdateMetadata)
        self.refreshTimer.start(300000)

        self.applyAutoRecordMode()

        self.executor = ThreadPoolExecutor(max_workers=4)

        self.liveRecorder.metadata_updated.connect(self.on_metadata_updated)

        self.chat_processes = {}
    async def close_async_client(self):
        if self.client and not self.client.is_closed:
            await self.client.aclose()

    def closeEvent(self, event):
        # # 실행 중인 모든 채팅 프로세스 종료
        for process in self.chat_processes.values():
            if process.is_alive():
                process.terminate()
                process.join()

        reply = QMessageBox.question(self, '종료 확인', '정말로 종료하시겠습니까?', QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply == QMessageBox.Yes:
            asyncio.run_coroutine_threadsafe(self.close_async_client(), asyncio.get_event_loop())
            event.accept()
        else:
            event.ignore()

    def run_background_task(self, func, *args):
        loop = asyncio.get_event_loop()
        return loop.run_in_executor(self.executor, func, *args)

    def fetch_and_update_metadata(self):
        asyncio.run_coroutine_threadsafe(self.fetchAndUpdateMetadata(), asyncio.get_event_loop())

    async def run_app(self):
        print("앱 실행 중...")
        session_cookies = self.liveRecorder.get_session_cookies()
        try:
            self.client = httpx.AsyncClient(cookies=session_cookies)
            await self.fetchAndUpdateMetadata()
        except Exception as e:
            print(f"비동기 작업 실행 중 예외 발생: {e}")
        finally:
            if self.client:
                await self.client.aclose()
            print("httpx 클라이언트 연결 종료")

    def eventFilter(self, source, event):
        if event.type() == CHANNEL_ADDED_EVENT or event.type() == CHANNEL_REMOVED_EVENT:
            self.handleChannelEvent(event)
            return True
        return super().eventFilter(source, event)

    def handleChannelEvent(self, event):
        if event.type() == CHANNEL_ADDED_EVENT:
            channelData = event.data
            self.channels.append(channelData)
            save_channels(self.channels)
            self.addChannelWidget(channelData)
            print(f"채널 '{channelData['name']}'이(가) 추가되었습니다.")
            QTimer.singleShot(0, lambda: asyncio.ensure_future(self.update_widget_later(channelData)))

        elif event.type() == CHANNEL_REMOVED_EVENT:
            channel_id = event.data
            channel_name = self.liveRecorder.findChannelNameById(channel_id)
            self.delete_widget(channel_id)
            self.channels = [channel for channel in self.channels if channel['id'] != channel_id]
            save_channels(self.channels)

            if channel_id in self.channelTimeLabels:
                del self.channelTimeLabels[channel_id]

            print(f"채널 '{channel_name}'이(가) 삭제되었습니다." if channel_name else "알 수 없는 채널이 삭제되었습니다.")

    def delete_widget(self, channel_id):
        if channel_id in self.channel_widgets:
            widget = self.channel_widgets[channel_id]
            widget.deleteLater()
            del self.channel_widgets[channel_id]
            print(f"채널 위젯 삭제: {channel_id}")

    def schedule_update_widget_later(self, channel_id):
        loop = asyncio.get_event_loop()
        loop.create_task(self.update_widget_later(channel_id))

    @asyncSlot(str, object)
    async def on_metadata_updated(self, channel_id, metadata):
        if not hasattr(self, 'metadata_updated_event'):
            self.metadata_updated_event = asyncio.Event()
        else:
            await self.metadata_updated_event.wait()
            self.metadata_updated_event.clear()

        if not hasattr(self, 'client'):
            await self.initialize_client()
        elif self.client.is_closed:
            await self.initialize_client()

        if channel_id not in self.channel_widgets:
            print(f"[오류] {channel_id}에 대한 채널 위젯을 찾을 수 없습니다. 메타데이터를 업데이트할 수 없습니다.")
            return

        try:
            await self.update_channel_widget(channel_id, metadata, self.client)
        except Exception as e:
            print(f"[오류] {channel_id}의 채널 위젯을 업데이트하는 중 예외가 발생했습니다: {e}")
        finally:
            self.metadata_updated_event.set()

    async def initialize_client(self):
        if not self.client or self.client.is_closed:
            session_cookies = self.liveRecorder.get_session_cookies()
            headers = self.liveRecorder.get_auth_headers(session_cookies)
            self.client = httpx.AsyncClient(headers=headers)

    def create_button(self, text, width, handler):
        button = QPushButton(text, self)
        button.setFixedWidth(width)
        button.clicked.connect(handler)
        return button

    def initUI(self):
        print("UI 초기화 시작")
        self.container = QWidget()
        self.layout = QVBoxLayout(self.container)

        self.buttonsLayout = QHBoxLayout()

        self.addStreamerButton = self.create_button("스트리머 추가", 130, self.addStreamer)
        self.buttonsLayout.addWidget(self.addStreamerButton)

        # VOD 다운로드 버튼 수정
        self.downloadVODButton = self.create_button("VOD 다운로드", 130, self.openVODDownloader)
        self.buttonsLayout.addWidget(self.downloadVODButton)

        self.startAllButton = self.create_button("모두 녹화 시작", 130, self.startAllRecording)
        self.buttonsLayout.addWidget(self.startAllButton)

        self.stopAllButton = self.create_button("모두 녹화 중지", 130, self.stopAllRecording)
        self.buttonsLayout.addWidget(self.stopAllButton)

        self.settingsButton = self.create_button("환경설정", 130, self.openSettingsWindow)
        self.buttonsLayout.addWidget(self.settingsButton)

        self.autoRecordToggleButton = self.create_button("자동 녹화 모드: OFF", 130, self.toggleAutoRecordMode)
        self.autoRecordToggleButton.setCheckable(True)
        self.autoRecordToggleButton.setChecked(self.config.get("auto_record_mode", False))
        self.buttonsLayout.addWidget(self.autoRecordToggleButton)

        self.layout.addLayout(self.buttonsLayout)

        self.scrollArea = QScrollArea(self)
        self.scrollArea.setWidgetResizable(True)
        self.scrollAreaWidget = QWidget()
        self.scrollArea.setWidget(self.scrollAreaWidget)
        self.scrollAreaLayout = QVBoxLayout(self.scrollAreaWidget)

        self.layout.addWidget(self.scrollArea)
        self.setCentralWidget(self.container)

        self.initChannelWidgets()
        print("UI 초기화 완료")

    def openVODDownloader(self):
        if self.mutex.acquire(blocking=False):
                try:
                  print("VOD 다운로드 시작 - 뮤텍스 획득 성공")
                  self.is_vod_downloading = True
                  self.update_download_button_state()  # 다운로드 버튼 비활성화

                # 실행 중인 채팅 프로세스가 있으면 종료
                  for channel_id in self.chat_processes:
                       if self.chat_processes[channel_id]:  # 프로세스가 None이 아닌 경우에만 종료 시도
                            self.chat_processes[channel_id].terminate()
                            self.chat_processes[channel_id].join()
                  self.vodDownloaderApp = VODDownloaderApp()
                  self.vodDownloaderApp.finished.connect(self.vodDownloaderClosed)
                  self.vodDownloaderApp.show()
                except Exception as e:
                  print(f"VOD 다운로드 시작 중 예외 발생: {e}")
                  QMessageBox.critical(self, "VOD 다운로드 시작 오류", f"VOD 다운로드 시작 중 오류가 발생했습니다: {e}")
                finally:
                    self.mutex.release()  # 뮤텍스 해제
        else:
            print("VOD 다운로드 시작 실패 - 뮤텍스 획득 실패, 다른 작업 진행 중")
            QMessageBox.warning(self, "경고", "다른 작업이 진행 중입니다. 잠시 후 다시 시도해주세요.")
            return

    def vodDownloaderClosed(self):
        print("VOD 다운로드 종료 - 뮤텍스 해제")
        self.is_vod_downloading = False
        self.update_download_button_state()  # 다운로드 버튼 활성화
        self.mutex.release()# 뮤텍스 해제

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
            self.startAllRecording()
        else:
            self.autoRecordToggleButton.setText("자동 녹화 모드: OFF")
            self.autoRecordToggleButton.setStyleSheet("")
            self.stopAllRecording()

    def applyAutoRecordMode(self):
        if self.config.get("auto_record_mode", False):
            self.autoRecordToggleButton.setChecked(True)
            self.autoRecordToggleButton.setText("자동 녹화 모드: ON")
            # self.startAllRecording() # 삭제
        else:
            self.autoRecordToggleButton.setChecked(False)
            self.autoRecordToggleButton.setText("자동 녹화 모드: OFF")

    def findLabelForChannel(self, channel_id):
        return self.channelTimeLabels.get(channel_id)

    def updateRecordingTime(self):
        for channel_id, timeLabel in self.channelTimeLabels.items():
            is_recording = self.liveRecorder.isRecording(channel_id)
            is_reserved = self.liveRecorder.reserved_recording.get(channel_id, False)
            start_time_str = self.channelInfos.get(channel_id, {}).get("openDate", "00:00:00")

            if is_reserved:
                timeLabel.setText(f"<b>방송시작:</b> {start_time_str} / <b>예약녹화중</b>")
            elif is_recording:
                recording_duration_str = self.liveRecorder.getRecordingDuration(channel_id)
                
                try:
                    recording_duration = datetime.strptime(recording_duration_str, "%H:%M:%S")
                    total_seconds = (recording_duration - datetime(1900, 1, 1)).total_seconds()
                except ValueError:
                    total_seconds = 0
                
                hours = int(total_seconds // 3600)
                minutes = int((total_seconds % 3600) // 60)
                seconds = int(total_seconds % 60)
                recording_time = f"{hours:02}:{minutes:02}:{seconds:02}"
                timeLabel.setText(f"<b>방송시작:</b> {start_time_str} / <b>녹화시간:</b> {recording_time}")
            else:
                timeLabel.setText(f"<b>방송시작:</b> {start_time_str} / <b>녹화 OFF:</b> 00:00:00")

    async def update_thumbnail(self, thumbnail_url, label, live_status):
        # {type}을 270 해상도로 대체
        thumbnail_url = thumbnail_url.replace("{type}", "270")
        response = await self.client.get(thumbnail_url)
        if response.status_code == 200:
            pixmap = QPixmap()
            pixmap.loadFromData(response.content)
            if live_status:
                label.setPixmap(pixmap.scaled(200, 112, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            else:
                pixmap = self.liveRecorder.effect_thumbnail(pixmap)
                label.setPixmap(pixmap.scaled(200, 112, Qt.KeepAspectRatio, Qt.SmoothTransformation))

    async def update_channel_info(self, channel_id, metadata):
        channel_name = self.liveRecorder.findChannelNameById(channel_id)
        channel_widget = self.channel_widgets.get(channel_id)
        
        if channel_widget is None or sip.isdeleted(channel_widget):
            print(f"[오류] {channel_name}에 대한 위젯을 찾을 수 없거나 삭제되었습니다.")
            return

        try:
            info_label = channel_widget.findChild(QLabel, f"infoLabel_{channel_id}")
            thumbnail_label = channel_widget.findChild(QLabel, f"thumbnail{channel_id}")

            if info_label:
                live_title = metadata.get('live_title', 'Unknown Title')
                current_category = metadata.get('category', 'Unknown Category')
                open_live = "방송중" if metadata.get("open_live") else "방송종료"
                info_label.setText(f"<b>[{open_live}]</b> {live_title}<br><b>[카테고리]</b> {current_category}")

            if thumbnail_label:
                # 여기서 {type}을 270 해상도로 대체하여 썸네일 URL을 업데이트
                thumbnail_url = metadata['thumbnail_url'].replace("{type}", "270")
                await self.update_thumbnail(thumbnail_url, thumbnail_label, metadata.get("open_live"))

            # 방송 시작 시간을 저장합니다.
            self.channelInfos[channel_id] = {"openDate": metadata.get("recording_duration", "00:00:00")}
            self.updateRecordingTime()  # UI를 즉시 업데이트합니다.

        except Exception as e:
            print(f"UI 업데이트 중 예외 발생: {e}")
            raise

    async def load_metadata_and_update_ui(self, client):
        for channel in self.channels:
            try:
                metadata = await self.liveRecorder.get_live_metadata(channel, client)
                await self.update_channel_widget(channel['id'], metadata, client)
            except Exception as e:
                print(f"Error loading metadata for channel {channel['name']}: {str(e)}")

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
            await self.update_channel_widget(channel_id, metadata, client, retries-1)

        except Exception as e:
            print(f"UI 업데이트 중 예외 발생: {e}. 재시도 횟수: {retries}")
            await asyncio.sleep(5)
            await self.update_channel_widget(channel_id, metadata, client, retries-1)

    @asyncSlot()
    async def update_widget_later(self, channel):
        print(f"{channel['name']} 채널의 메타데이터를 업데이트 중입니다")
        metadata = await self.liveRecorder.get_live_metadata(channel, self.client)
        if metadata is not None:
            print(f"{channel['name']} 채널의 메타데이터를 가져왔습니다: {metadata}")
            await self.update_channel_widget(channel['id'], metadata, self.client)
        else:
            print(f"{channel['name']} 채널의 메타데이터를 가져오지 못했습니다")

    @qasync.asyncSlot()
    async def fetchAndSetMetadataForChannel(self, channel):
        metadata = await self.liveRecorder.get_live_metadata(channel, self.client)
        await self.update_channel_widget(channel['id'], metadata, self.client)

    def set_thumbnail_from_reply(self, reply, label):
        if reply.error() == QNetworkReply.NoError:
            data = reply.readAll()
            pixmap = QPixmap()
            if pixmap.loadFromData(data):
                label.setPixmap(pixmap.scaled(200, 200, Qt.KeepAspectRatio, Qt.SmoothTransformation))
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
        for channel in self.channels:
            self.addChannelWidget(channel)

    def addChannelWidget(self, channel):
        if not channel.get('id'):
            print(f"[오류] 채널에 ID가 없습니다. 위젯을 생성할 수 없습니다.")
            return

        channel_name = channel.get('name', 'Unknown')  # 채널 이름 가져오기, 없으면 'Unknown'
        channel_id = channel.get('id')  # 채널 ID 가져오기, 없으면 None
        channel_output_dir = channel.get('output_dir', '')
        channel_extension = channel.get('extension', '.ts')

        if channel_id in self.channel_widgets:
            print(f"채널 '{channel_name}'의 위젯이 이미 존재합니다.")
            return

        channelWidget = QWidget()
        channelLayout = QHBoxLayout(channelWidget)

        thumbnailLabel = QLabel()
        thumbnailLabel.setObjectName(f"thumbnail{channel_id}")
        thumbnailLabel.setFixedWidth(200)
        thumbnailLabel.setStyleSheet("border: 1px solid #ccc;")

        defaultThumbnail = QPixmap(self.liveRecorder.default_thumbnail_path)
        thumbnailLabel.setPixmap(defaultThumbnail.scaled(200, 112, Qt.KeepAspectRatio))

        channelLayout.addWidget(thumbnailLabel)

        infoAndButtonsLayout = QVBoxLayout()

        info_text = "로딩 중"
        infoLabel = QLabel(info_text)
        infoLabel.setObjectName(f"infoLabel_{channel_id}")
        infoLabel.setWordWrap(True)
        infoLabel.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)
        infoLabel.setAlignment(Qt.AlignLeft)  # 텍스트 왼쪽 정렬
        infoAndButtonsLayout.addWidget(infoLabel)

        timeLabel = QLabel("방송시작 : 00:00:00 / 녹화시간 : 00:00:00")
        self.channelTimeLabels[channel_id] = timeLabel
        timeLabel.setAlignment(Qt.AlignLeft)  # 텍스트 왼쪽 정렬
        timeLabel.setStyleSheet("margin-top: 5px;")  # 위쪽 여백 설정
        infoAndButtonsLayout.addWidget(timeLabel)

        buttonsLayout = QHBoxLayout()

        startButton = QPushButton(f"{channel_name} 녹화 시작")
        startButton.setFixedWidth(160)
        if channel_id:
           startButton.clicked.connect(self.createStartButtonClickedHandler(channel_id))
        buttonsLayout.addWidget(startButton)

        stopButton = QPushButton(f"{channel_name} 녹화 중지")
        stopButton.setFixedWidth(160)
        stopButton.clicked.connect(self.createStopButtonClickedHandler(channel_id))
        buttonsLayout.addWidget(stopButton)

        settingsButton = QPushButton("설정")
        settingsButton.setFixedWidth(40)
        settingsButton.clicked.connect(partial(self.openChannelSettings, channel_id))
        buttonsLayout.addWidget(settingsButton)

        openfolderButton = QPushButton(f"열기")
        openfolderButton.setFixedWidth(40)
        openfolderButton.clicked.connect(partial(self.openRecordedFolder, channel_output_dir))
        buttonsLayout.addWidget(openfolderButton)

        deleteButton = QPushButton("삭제")
        deleteButton.setFixedWidth(40)
        deleteButton.clicked.connect(lambda _, channel=channel, channels=self.channels, channel_id=channel['id']: self.deleteChannel(channel['id']))
        buttonsLayout.addWidget(deleteButton)

        infoAndButtonsLayout.addLayout(buttonsLayout)

        # infoAndButtonsLayout에 정렬 및 여백 설정 (위젯 추가 후, channelLayout에 추가 전)
        infoAndButtonsLayout.setAlignment(Qt.AlignLeft)
        infoAndButtonsLayout.setContentsMargins(10, 10, 10, 10)

        channelLayout.addLayout(infoAndButtonsLayout)

        self.channel_widgets[channel_id] = channelWidget
        self.scrollAreaLayout.addWidget(channelWidget)
        self.scrollAreaLayout.setSpacing(20)
        print(f"채널 위젯 추가: {channel_name}")
 
    def createStartButtonClickedHandler(self, channel_id):
        def handler():
            if channel_id is None:
                print(f"createStartButtonClickedHandler: {channel_id} 가 유효하지 않아서 녹화 시작을 진행하지 않습니다.")
                return # channel_id 가 유효하지 않으면 None 반환
            if self.mutex.acquire(blocking=False): # 뮤텍스 획득 시도
                try:
                    # 녹화 시작 버튼을 눌렀을 때
                    self.liveRecorder.startBackgroundRecording(channel_id)
                    # 채팅 활성화
                    self.liveRecorder.setChatEnabled(channel_id, True)
                    # 채팅 프로세스 시작
                    channel = next((ch for ch in self.channels if ch['id'] == channel_id), None)
                    if channel:
                        self.start_chat_process(channel_id, channel['output_dir'], channel['name'], channel['extension'])
                    self.is_recording = True
                    self.update_download_button_state()
                except Exception as e:
                    print(f"녹화 시작 중 예외 발생: {e}")
                    QMessageBox.critical(self, "녹화 시작 오류", f"녹화 시작 중 오류가 발생했습니다: {e}")
                finally:
                    self.mutex.release()  # 뮤텍스 해제
            else:
                print("녹화 시작 실패 - 뮤텍스 획득 실패, 다른 작업 진행 중")
                QMessageBox.warning(self, "경고", "다른 작업이 진행 중입니다. 잠시 후 다시 시도해주세요.")
            return handler

    def createStopButtonClickedHandler(self, channel_id):
        def handler():
            if self.mutex.acquire(blocking=False):  # 뮤텍스 획득 시도
                try:
                    # 녹화 중지 버튼을 눌렀을 때
                    self.liveRecorder.stopRecording(channel_id, force_stop=True)
                    # 채팅 비활성화
                    self.liveRecorder.setChatEnabled(channel_id, False)
                    # 채팅 프로세스 종료 (더 이상 사용하지 않으므로 주석 처리)
                    if channel_id in self.chat_processes:
                        if self.chat_processes[channel_id].is_alive():
                            self.chat_processes[channel_id].terminate()
                            self.chat_processes[channel_id].join()
                        del self.chat_processes[channel_id]
                except Exception as e:
                    print(f"녹화 중지 중 예외 발생: {e}")
                    QMessageBox.critical(self, "녹화 중지 오류", f"녹화 중지 중 오류가 발생했습니다: {e}")
                finally:
                    self.is_recording = False
                    self.update_download_button_state()
                    self.mutex.release()  # 뮤텍스 해제
            else:
                print("녹화 중지 실패 - 뮤텍스 획득 실패, 다른 작업 진행 중")
                QMessageBox.warning(self, "경고", "다른 작업이 진행 중입니다. 잠시 후 다시 시도해주세요.")
        return handler

    def openRecordedFolder(self, output_dir):
        if os.path.exists(output_dir):
            os.startfile(output_dir)
        else:
            QMessageBox.warning(self, "경고", "폴더가 존재하지 않습니다.")

    def deleteChannel(self, channel_id):
        channel_name = self.liveRecorder.findChannelNameById(channel_id)
        channel = next((ch for ch in self.channels if ch['id'] == channel_id), None)
        if channel is None:
            QMessageBox.warning(self, "경고", f"'{channel_name}' 채널을 찾을 수 없습니다.")
            return

        reply = QMessageBox.question(self, "채널 삭제", f"'{channel['name']}' 채널을 삭제하시겠습니까?",
                                     QMessageBox.Yes | QMessageBox.No, QMessageBox.No)

        if reply == QMessageBox.Yes:
            # 채널 삭제 시 해당 채팅 프로세스도 종료 (더 이상 사용하지 않으므로 주석 처리)
            if channel_id in self.chat_processes:
                if self.chat_processes[channel_id].is_alive():
                    self.chat_processes[channel_id].terminate()
                    self.chat_processes[channel_id].join()
                del self.chat_processes[channel_id]

            self.channels.remove(channel)
            save_channels(self.channels)
            QApplication.postEvent(self, CustomEvent(CHANNEL_REMOVED_EVENT, data=channel['id']))

    @asyncSlot()
    async def fetchAndUpdateMetadata(self):
        if not self.client or self.client.is_closed:
            session_cookies = self.liveRecorder.get_session_cookies()
            self.client = httpx.AsyncClient(cookies=session_cookies)

        try:
            await self.liveRecorder.fetch_metadata_for_all_channels()
        except Exception as e:
            print(f"메타데이터 업데이트 중 예외 발생: {e}")
        finally:
            if hasattr(self, 'metadata_updated_event') and not self.metadata_updated_event.is_set():
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
        if self.mutex.acquire(blocking=False):  # 뮤텍스 획득 시도
            print("녹화 시작 - 뮤텍스 획득 성공")
            self.is_recording = True
            self.run_background_task(self.liveRecorder.startRecording, channel_id)
            self.update_download_button_state()
        else:
            print("녹화 시작 실패 - 뮤텍스 획득 실패, 다른 작업 진행 중")
            QMessageBox.warning(self, "경고", "다른 작업이 진행 중입니다. 잠시 후 다시 시도해주세요.")
            return


    def stopRecording(self, channel_id):
        if self.mutex.acquire(blocking=False):
            print("녹화 중지 - 뮤텍스 해제")
            self.is_recording = False
            self.run_background_task(self.liveRecorder.stopRecording, channel_id, True)
            self.update_download_button_state()
            self.mutex.release()
        else:
            print("녹화 중지 실패 - 뮤텍스 획득 실패, 다른 작업 진행 중")
            QMessageBox.warning(self, "경고", "다른 작업이 진행 중입니다. 잠시 후 다시 시도해주세요.")
          

    def startAllRecording(self):
        print("모든 채널의 녹화가 잠시 후에 시작됩니다.")
        QTimer.singleShot(5000, self.delayedStartAllRecording)

    def delayedStartAllRecording(self):
        for channel in self.channels:
            self.startRecording(channel['id'])

    def stopAllRecording(self):
        for channel in self.channels:
            self.stopRecording(channel['id'])

    def openSettingsWindow(self):
        self.settingsWindow = SettingsWindow(self)
        self.settingsWindow.show()

    def addStreamer(self):
        self.dialog = QDialog(self)
        self.dialog.setWindowTitle("스트리머 추가")
        self.dialog.setFixedWidth(250)
        layout = QVBoxLayout(self.dialog)

        uidLabel = QLabel("스트리머 UID:")
        self.uidEdit = QLineEdit()
        nameLabel = QLabel("채널명:")
        self.nameEdit = QLineEdit()
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
        layout.addWidget(nameLabel)
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

    def onAddChannelButtonClick(self):
        uid = self.uidEdit.text()
        name = self.nameEdit.text()
        directory = self.directoryEdit.text()
        quality = self.qualityCombo.currentText()
        extension = self.extensionCombo.currentText()

        if uid and name and directory and quality and extension:
            absolute_directory = os.path.abspath(directory)
            
            channelData = {"id": uid, "name": name, "output_dir": absolute_directory, "quality": quality, "extension": extension}
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
        channel = next((ch for ch in self.channels if ch['id'] == channel_id), None)
        if not channel:
            QMessageBox.warning(self,"경고", "채널을 찾을 수 없습니다.")
            return
        dialog = QDialog(self)
        dialog.setWindowTitle("채널 설정 수정")
        dialog.setFixedWidth(250)
        layout = QVBoxLayout(dialog)

        uidLabel = QLabel("스트리머 UID:")
        uidEdit = QLineEdit(channel['id'])
        nameLabel = QLabel("채널명:")
        nameEdit = QLineEdit(channel['name'])
        directoryLabel = QLabel("저장 폴더:")
        directoryEdit = QLineEdit(channel['output_dir'])
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
        saveButton.clicked.connect(lambda: self.confirmChannelSettings(dialog, uidEdit.text(), nameEdit.text(), directoryEdit.text(), qualityCombo.currentText(), extensionCombo.currentText(), channel))

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

    def confirmChannelSettings(self, dialog, uid, name, directory, quality, extension, originalChannel):
        if uid and name and directory and quality and extension:
            originalChannel['id'] = uid
            originalChannel['name'] = name
            originalChannel['output_dir'] = directory
            originalChannel['quality'] = quality
            originalChannel['extension'] = extension
            save_channels(self.channels)
            self.fetch_metadata_task = self.fetchAndUpdateMetadata()
            dialog.accept()
        else:
            QMessageBox.warning(dialog, "경고", "모든 필드를 채워주세요.")

    def selectDirectory(self, directoryEdit):
        directory = QFileDialog.getExistingDirectory(self, "저장 폴더 선택")
        if directory:
            directoryEdit.setText(directory)

    def update_download_button_state(self):
         if self.is_recording or self.is_vod_downloading:
            self.downloadVODButton.setEnabled(False)
            print("VOD 다운로드 버튼 비활성화")
         else:
            self.downloadVODButton.setEnabled(True)
            print("VOD 다운로드 버튼 활성화")

    def start_chat_process(self, channel_id, output_dir, channel_name, extension):
      # 이미 실행 중인 채팅 프로세스가 있는지 확인 후, 있다면 종료
        if channel_id in self.chat_processes and self.chat_processes[channel_id].is_alive():
            self.chat_processes[channel_id].terminate()
            self.chat_processes[channel_id].join()

      # Live_recorder.py에서 사용하는 녹화 파일명 생성 로직을 참고하여 로그 파일명 생성
        metadata = self.liveRecorder.live_metadata.get(channel_id, {})
        live_title = metadata.get("live_title", "")
        record_quality = metadata.get("record_quality", "")
        frame_rate = metadata.get("frame_rate", "")

        # 새로운 콘솔 창에서 run.py 실행
        run_py_path = os.path.join(os.path.dirname(__file__), "module", "run.py")
        process = subprocess.Popen([
             sys.executable, run_py_path,
             channel_id,
             output_dir,
             channel_name,
             live_title,
             record_quality,
             frame_rate,
             extension
        ], creationflags=subprocess.CREATE_NEW_CONSOLE)

      # 프로세스 ID를 저장하여 나중에 종료할 수 있도록 함
        self.chat_processes[channel_id] = process
        print(f"채팅 로깅 시작: {channel_name}, 로그 파일: {live_title}.log")

if __name__ == "__main__":
        # multiprocessing 사용 시 필요
        import multiprocessing

        multiprocessing.freeze_support()

        app = QApplication(sys.argv) # 추가
        loop = qasync.QEventLoop(app)
        asyncio.set_event_loop(loop)

        css_file_path = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'style.css')

        try:
            with open(css_file_path, "r", encoding="utf-8") as file:
                app.setStyleSheet(file.read())
        except Exception as e:
            print(f"스타일 시트 불러오기 실패: {e}")

        window = RunRecordApp()
        window.show()

        if not hasattr(window, 'fetch_metadata_task') or window.fetch_metadata_task.done():
            window.fetch_metadata_task = window.fetchAndUpdateMetadata()
        loop.run_forever()