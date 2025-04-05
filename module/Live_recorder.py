import subprocess
import sys
import os
import shutil
import json
import time
import threading
import re
import tempfile
import asyncio
import httpx
from datetime import datetime
from PyQt5.QtWidgets import (
    QLabel,
    QApplication,
    QMainWindow,
    QPushButton,
    QVBoxLayout,
    QWidget,
    QMessageBox,
)
from PyQt5.QtCore import QTimer, QThread, pyqtSignal, QObject, pyqtSlot, Qt
from PyQt5.QtGui import QPixmap, QPainter, QColor, QBrush, QFont

from channel_manager import (
    load_channels,
    save_channels,
    load_config,
    save_config,
)
from copy_streams import copy_specific_file
from path_config import (
    base_directory,
    getFFmpeg,
    getStreamlink,
)  # getFFmpeg, getStreamlink 임포트

# api.py 관련 import
from api import load_cookies, get_headers, fetch_channelName
import run

class RecordingThread(QThread):
    """
    개별 채널의 녹화를 담당하는 스레드입니다.
    """
    recordingStarted = pyqtSignal(str)  # 녹화 시작 시그널
    recordingFailed = pyqtSignal(str, str)  # 녹화 실패 시그널
    recordingFinished = pyqtSignal(str)  # 녹화 종료 시그널

    def __init__(self, channel, liveRecorder, parent=None):
        super().__init__(parent)
        self.channel = channel  # 녹화할 채널 정보
        self.liveRecorder = liveRecorder  # LiveRecorder 객체
        self.stopRequested = False  # 녹화 중지 요청 플래그
        self.force_stop = False  # 강제 중지 플래그
        self.retryDelay = 5  # 60  # 녹화 종료 후 재시도 대기 시간 (초)
        self.loop = None  # asyncio 이벤트 루프
        self.stop_timer = None  # 자동 중지 타이머
        self.chat_process = None  # 채팅 프로세스
        self.is_chat_running = False  # 채팅 실행 여부
        self.chat_log_path = None  # 채팅 로그 파일 경로
        self.time_shift = 0  # 타임머신 시간 (초)

    @pyqtSlot()
    def run(self):
        """
        녹화 스레드의 메인 루프입니다.
        방송 상태를 주기적으로 확인하고, 방송 중이면 녹화를 시작/유지합니다.
        """
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        client = httpx.AsyncClient()
        try:
            while not self.stopRequested:
                live_info = self.loop.run_until_complete(
                    self.liveRecorder.get_live_metadata(self.channel, client)
                )

                if live_info and live_info.get("open_live"):
                    self.liveRecorder.recording_start_times[
                        self.channel["id"]
                    ] = time.time()

                    cmd_list, output_path, chat_log_path, self.time_shift = self.liveRecorder.buildCommand(  # time_shift 받음
                        self.channel, live_info
                    )
                    if cmd_list is None:
                        print(
                            f"오류: {self.channel['name']} 채널에 대한 명령 목록을 만들 수 없습니다."
                        )
                        return

                    try:
                        process = subprocess.Popen(cmd_list)
                        self.liveRecorder.recording_status[self.channel["id"]] = True
                        self.liveRecorder.recording_processes[self.channel["id"]] = process
                        # 수정: LiveRecorder의 시그널 발생
                        self.liveRecorder.recording_started.emit(
                            self.channel["id"]
                        )  # 녹화 시작 시그널 발생

                        auto_stop_interval = self.liveRecorder.config.get(
                            "autoStopInterval", 0
                        )
                        print(f"분할녹화 시간 간격: {auto_stop_interval} 초")
                        if auto_stop_interval > 0:
                            self.stop_timer = threading.Timer(
                                auto_stop_interval, self.stop
                            )
                            self.stop_timer.start()
                            print(f"{auto_stop_interval}초 후 자동 중지 설정됨")

                        self.start_chat_process(chat_log_path)

                        # 주기적으로 채팅 확인 (타임아웃 제거)
                        while not self.stopRequested:
                            try:
                                process.wait(timeout=10)  # 여기서 10초 대기
                                break  # 프로세스 종료 시 while 루프 종료
                            except subprocess.TimeoutExpired:
                                pass  # 타임아웃 시 아무것도 하지 않음

                        if self.stop_timer:
                            self.stop_timer.cancel()
                        # 수정: LiveRecorder의 시그널 발생
                        self.liveRecorder.onRecordingFinished(
                            self.channel["id"]
                        )  # 녹화 종료

                    except Exception as e:
                        # 수정: LiveRecorder의 시그널 발생
                        self.liveRecorder.onRecordingFailed(
                            self.channel["id"], str(e)
                        )
                        return

                    finally:
                        print(
                            f"{self.channel['name']} 녹화 종료 후 {self.retryDelay}초 대기 중..."
                        )
                        time.sleep(self.retryDelay)  # 동기 sleep
                        if self.force_stop:
                            break

                        live_info = self.loop.run_until_complete(
                            self.liveRecorder.get_live_metadata(self.channel, client)
                        )
                        if (
                            (live_info is None or not live_info.get("open_live"))
                            and self.liveRecorder.config.get("auto_record_mode", False)
                            and self.channel.get("record_enabled", False)
                        ):
                            self.stopRequested = False
                            print(
                                f"{self.channel['name']} 방송이 종료되었습니다. 자동 녹화 모드 + 예약: 예약 녹화 상태로 전환합니다."
                            )

                        elif live_info and live_info.get("open_live"):
                            self.stopRequested = False  # 다시 녹화 재시작
                            continue
                        else:
                            print(f"{self.channel['name']} 방송이 종료되었습니다.")
                            break
                else:  # 방송 중이 아닐 때
                    asyncio.run_coroutine_threadsafe(
                        asyncio.sleep(self.liveRecorder.recheck_interval), self.loop
                    )

        finally:
            self.loop.run_until_complete(client.aclose())
            self.loop.close()

    def start_chat_process(self, new_chat_log_path):
        """채팅 프로세스 시작 (RecordingThread)"""
        if not self.is_chat_running:
            try:
                self.chat_log_path = new_chat_log_path

                # run.py를 별도의 콘솔 창에서 실행
                command = [
                    sys.executable,
                    os.path.join(base_directory, "module", "run.py"),
                    "--streamer_id",
                    self.channel['id'],
                    "--log_path",
                    self.chat_log_path,
                    "--time_shift",  # <-- 타임머신 시간 인자 추가
                    str(self.time_shift),  # <-- 타임머신 시간 값(초) 추가
                ]

                # CREATE_NEW_CONSOLE 플래그 사용
                self.chat_process = subprocess.Popen(
                    command, creationflags=subprocess.CREATE_NEW_CONSOLE
                )

                self.is_chat_running = True
                self.liveRecorder.chat_processes[self.channel["id"]] = (
                    self.chat_process
                )  # 프로세스 객체 저장
                self.liveRecorder.chat_log_paths[self.channel["id"]] = (
                    self.chat_log_path
                )  # 로그파일 저장
                self.liveRecorder.chat_status[self.channel["id"]] = True  # 채팅 상태 업데이트
                print(f"채팅 저장 시작: {self.channel['name']}")
                self.liveRecorder.chat_started.emit(
                    self.channel["id"]
                )  # 채팅 시작 시그널 발생

            except Exception as e:
                print(f"채팅 시작 오류: {e}")

    def stop_chat_process(self):
        if self.chat_process and self.is_chat_running:
            try:
                self.chat_process.terminate()
                try:
                    self.chat_process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    self.chat_process.kill()
            except Exception as e:
                print(f"채팅 프로세스 종료 중 오류 발생: {e}")
            finally:
                self.is_chat_running = False
                # LiveRecorder의 슬롯 직접 호출 대신 시그널 발생
                self.liveRecorder.chat_stopped.emit(
                    self.channel["id"]
                )  # 채팅 종료 시그널
                print(f"채팅 저장 중지: {self.channel['name']}")
                self.chat_process = None  # 추가

    def stop(self, force_stop=False):
        """
        녹화 중지 (RecordingThread).
        force_stop=True: 강제 중지 (자동 녹화 재시작 대기 없이 즉시 종료)
        """
        try:
            self.stopRequested = True
            self.force_stop = force_stop
            if self.isRunning():
                channel_id = self.channel["id"]
                process = self.liveRecorder.recording_processes.get(channel_id)
                if process:
                    process.terminate()
                    # 5초 후에 강제 종료 시도
                    QTimer.singleShot(
                        5000, lambda: self.forceTerminateProcess(process)
                    )

                # 채팅 스레드/프로세스 종료
                self.stop_chat_process()  # RecordingThread 내에서 호출

                QTimer.singleShot(100, self.checkStopRequest)  # 정리작업
        except Exception as e:
            print(f"녹화 중지 중 예외 발생: {e}")

    def forceTerminateProcess(self, process):
        """
        프로세스를 강제 종료합니다.
        """
        try:
            if not process.poll():  # 아직 프로세스가 종료되지 않았으면
                process.kill()  # 강제 종료
        except Exception as e:
            print(f"프로세스 강제 종료 중 예외 발생: {e}")

    def checkStopRequest(self):
        """
        녹화 중지 요청 처리 후 정리 작업을 수행합니다.
        """
        if self.stopRequested and not self.liveRecorder.recording_processes:
            self.liveRecorder.cleanupAfterRecording(self.channel["id"], self.force_stop)
            self.stopRequested = False


class LiveRecorder(QObject):
    instance = None
    metadata_updated = pyqtSignal(str, object)  # 메타데이터 업데이트 시그널
    recording_finished = pyqtSignal(str)  # <-- 녹화 종료 시그널 추가
    recording_started = pyqtSignal(str)  # 녹화 시작 시그널 추가
    chat_started = pyqtSignal(str)  # 채팅 시작 시그널 추가
    chat_stopped = pyqtSignal(str)  # 채팅 중지 시그널 추가

    def __init__(self, channels, default_thumbnail_path=None):
        super().__init__()
        LiveRecorder.instance = self
        self.recordingThreads = {}  # 채널별 녹화 스레드 관리
        self.recording_processes = {}  # 채널별 녹화 프로세스 관리
        self.recording_start_times = {}  # 채널별 녹화 시작 시간
        self.recording_requested = {}  # 녹화 요청 상태 (더 이상 사용하지 않음)
        self.recording_status = {}  # 채널별 녹화 상태 (True/False)
        self.recording_filenames = {}  # 채널별 녹화 파일명
        self.live_metadata = {}  # 채널별 메타데이터 저장
        self.channels = channels  # 채널 목록
        self.config = load_config()  # 설정 불러오기
        self.recheck_interval = int(
            self.config.get("recheckInterval", 60)
        )  # 메타데이터 확인 간격
        self.auto_stop_interval = int(
            self.config.get("autoStopInterval", 0)
        )  # 자동 중지 간격
        self.show_message_box = self.config.get("showMessageBox", True)  # 메시지 박스 표시 여부
        self.auto_dsc = self.config.get("autoPostProcessing", False)  # 자동 후처리 여부
        self.filename_pattern = self.config.get(  # 파일 이름 패턴
            "filenamePattern",
            "[{start_time}] {channel_name} {safe_live_title} {record_quality}{frame_rate}{file_extension}",
        )
        self.deleteAfterPostProcessing = self.config.get(  # 후처리 후 삭제 여부
            "deleteAfterPostProcessing", False
        )
        self.post_processing_output_dir = self.config.get(
            "postProcessingOutputDir", ""
        )  # 후처리 출력 폴더
        self.chat_processes = {}  # 채팅 프로세스 저장
        self.chat_log_paths = {}  # 채팅 로그 경로 <--- 이제 사용안함.
        self.chat_status = {}  # 채널별 채팅 상태
        self.fixed_file_paths = {}

        if default_thumbnail_path is None:  # 기본 썸네일 이미지 경로
            self.default_thumbnail_path = os.path.join(
                os.path.dirname(os.path.dirname(os.path.realpath(__file__))),
                "dependent",
                "img",
                "default_thumbnail.png",
            )
        else:
            self.default_thumbnail_path = default_thumbnail_path

        # 모든 채널에 대해 chat_status를 False로 초기화
        for channel in self.channels:
            self.chat_status[channel["id"]] = False

    def findChannelNameById(self, channel_id):
        """채널 ID를 이용하여 채널 이름을 찾습니다."""
        for channel in self.channels:
            if channel["id"] == channel_id:
                return channel["name"]
        return None

    # 설정에 따라 메시지 박스 표시 여부 결정
    def auto_close_message_box(self, title, text, timeout=5000):
        if not self.show_message_box:
            # print(f"{title}: {text}") # 메시지 박스 대신 콘솔 출력
            return  # 메시지 박스 표시 설정이 꺼져 있으면 아무것도 하지 않음
        # QMessageBox 호출을 메인 스레드에 전달
        QTimer.singleShot(
            0, lambda: self.show_message_box_helper(title, text, timeout)
        )

    def show_message_box_helper(self, title, text, timeout):
        msgBox = QMessageBox()
        msgBox.setWindowTitle(title)
        msgBox.setText(text)
        msgBox.setStandardButtons(QMessageBox.Ok)
        QTimer.singleShot(timeout, msgBox.accept)
        msgBox.exec_()

    async def get_live_metadata(self, channel, client, retries=3, delay=3):
        """
        주어진 채널의 라이브 메타데이터를 가져옵니다.
        """
        # print(f"get_live_metadata called for channel: {channel['name']}")  # 함수 호출 확인
        timeout = httpx.Timeout(30.0, read=60.0)  # 연결 30초, 읽기 60초
        client.timeout = timeout  # 타임아웃 설정
        for attempt in range(retries):
            try:
                cookies = load_cookies()  # api.load_cookies() 사용
                if cookies is None:  # 쿠키 로드 실패 처리
                    # print(
                    #     f"Error: Could not load cookies. Metadata fetch failed for {channel['name']}."
                    # )
                    return None
                headers = get_headers(cookies)  # api.get_headers() 사용
                url = f"https://api.chzzk.naver.com/service/v3/channels/{channel['id']}/live-detail"

                # print(f"Requesting URL: {url}")  # URL 확인
                # print(f"Headers: {headers}")    # 헤더 확인

                response = await client.get(url, headers=headers)
                response.raise_for_status()

                data = response.json()
                # print(f"Response data: {data}")   # 응답 데이터 확인
                metadata_content = data.get("content")
                if metadata_content is None:
                    return None

                try:
                    thumbnail_url = (
                        metadata_content.get("liveImageUrl", "")
                        .format(type="270")
                        .replace("\\", "")
                        if metadata_content.get("liveImageUrl")
                        else self.default_thumbnail_path
                    )
                except Exception as e:
                    print(f"썸네일 URL 처리 중 예외 발생: {e}, 기본 썸네일 이미지 사용")
                    thumbnail_url = self.default_thumbnail_path

                record_quality_setting = channel.get("quality", "best")

                frame_rate = "알 수 없는 프레임 속도"
                record_quality = "알 수 없는 품질"

                live_playback_json = metadata_content.get("livePlaybackJson")
                if live_playback_json:
                    try:
                        live_playback_json = json.loads(live_playback_json)
                        encoding_tracks = live_playback_json.get("media", [])
                    except (TypeError, json.JSONDecodeError) as e:
                        print(f"livePlaybackJson 파싱 오류: {e}")
                        encoding_tracks = []
                else:
                    encoding_tracks = []

                max_resolution = 0

                for track in encoding_tracks:
                    if "encodingTrack" in track:
                        for encoding in track["encodingTrack"]:
                            try:  # videoWidth, videoHeight, videoFrameRate 키에 대한 오류 처리
                                resolution = int(encoding.get("videoWidth", 0)) * int(
                                    encoding.get("videoHeight", 0)
                                )
                                if (
                                    record_quality_setting == "best"
                                    and resolution > max_resolution
                                ) or (
                                    record_quality_setting != "best"
                                    and encoding["encodingTrackId"]
                                    == record_quality_setting
                                ):
                                    max_resolution = resolution
                                    record_quality = encoding["encodingTrackId"]
                                    frame_rate = str(
                                        int(float(encoding.get("videoFrameRate", "30")))
                                    )  # 기본값 30
                            except KeyError as e:
                                print(f"인코딩 정보 KeyError: {e}, 기본값 사용")
                                continue  # 해당 인코딩 트랙 건너뛰기

                parsed_metadata = {
                    "thumbnail_url": thumbnail_url,
                    "live_title": metadata_content.get("liveTitle", "알 수 없는 제목"),
                    "channel_name": metadata_content["channel"].get(
                        "channelName", "알 수 없는 채널"
                    )
                    if "channel" in metadata_content
                    and "channelName" in metadata_content["channel"]
                    else "알 수 없는 채널",
                    "recording_duration": metadata_content.get("openDate", "00:00:00"),
                    "open_live": metadata_content.get("status", "") == "OPEN",  # 수정: livePlaybackJson 파싱 전 원래 상태
                    "category": metadata_content.get(
                        "liveCategoryValue", "알 수 없는 카테고리"
                    ),
                    "record_quality": record_quality,  # livePlaybackJson에서 가져옴
                    "frame_rate": frame_rate,  # livePlaybackJson에서 가져옴
                }

                # print(f"parsed_metadata: {parsed_metadata}")  # 메타데이터 확인

                self.live_metadata[channel["id"]] = parsed_metadata
                return parsed_metadata

            except httpx.HTTPStatusError as e:
                print(f"HTTP 오류 발생: {e.response.status_code} - {e.response.text}")
                if e.response.status_code == 400:
                    print("400 Bad Request 에러가 발생했습니다. 쿠키가 만료되었거나 채널 정보가 변경되었을 수 있습니다.")
                    return None
                if 500 <= e.response.status_code < 600:
                    print(f"서버 오류 ({e.response.status_code}). {attempt + 1}회 재시도...")
                    await asyncio.sleep(delay)
                    continue
                else:
                    return None

            except httpx.RequestError as e:
                print(f"요청 오류 발생: {e}")
                return None

            except Exception as e:
                print(f"[재시도] {attempt + 1}회 시도 실패. 오류: {e}")
                if attempt + 1 < retries:
                    await asyncio.sleep(delay)
                else:
                    print(f"[오류] {channel['name']}: 메타데이터를 가져오는 도중 오류가 발생하였습니다")
                    return None

    def effect_thumbnail(self, pixmap):
        effect_pixmap = QPixmap(pixmap.size())
        effect_pixmap.fill(Qt.transparent)

        painter = QPainter(effect_pixmap)
        painter.drawPixmap(0, 0, pixmap)
        painter.fillRect(pixmap.rect(), QBrush(QColor(0, 0, 0, 127)))  # 반투명 검은색 오버레이
        painter.setPen(Qt.white)
        painter.setFont(QFont("Arial", 20, QFont.Bold))
        text_rect = pixmap.rect()
        text = "Off the Air"  # 텍스트
        painter.drawText(
            text_rect, Qt.AlignCenter, text
        )  # 가운데 정렬하여 텍스트 그리기
        painter.end()

        current_dir = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
        output_path = os.path.join(
            current_dir, "dependent", "img", "debug_image.png"
        )
        effect_pixmap.save(output_path)

        return effect_pixmap

    async def close_client(self):
        if hasattr(self, "client") and not self.client.is_closed:
            await self.client.aclose()

    def buildCommand(self, channel, metadata=None, output_path=None, append=False):
        record_quality = channel.get("quality", "best")
        file_extension = channel.get("extension", ".ts")  # <-- 이 줄은 유지 (필요)
        current_dir = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
        selected_plugin = self.config.get("plugin", "기본 플러그인")
        if selected_plugin == "기본 플러그인":
            plugin_folder_name = "basic"
        elif selected_plugin == "타임머신 플러그인":
            plugin_folder_name = "timemachine"
        elif selected_plugin == "타임머신 플러스 플러그인":
            plugin_folder_name = "timemachine_plus"
        else:
            plugin_folder_name = "basic"  # 기본 플러그인

        plugin_dir = os.path.join(current_dir, "dependent", "plugin", plugin_folder_name)
        streamlink_path = getStreamlink()  # Streamlink 경로 가져오기
        ffmpeg_path = getFFmpeg()  # FFmpeg 경로 가져오기
        cookies = load_cookies()  # 수정: api.get_cookies() 사용

        # 타임머신 기능을 사용할 때 시작 시점을 설정합니다 (예: 1분 전)
        time_shift = 0  # 기본값
        if selected_plugin in ["타임머신 플러그인", "타임머신 플러스 플러그인"]:
            time_shift = self.config.get("time_shift", 0)  # 설정에서 가져온 값 사용 (기본값 0)
            time_shift_option = f"--hls-start-offset={time_shift}"  # seconds
        else:
            time_shift_option = ""

        if not output_path and metadata:  # output_path가 None이고 metadata가 제공된 경우
            filename = self._create_filename(channel['id'], metadata,file_extension)
            if filename is None:
                print(f"오류: {channel['name']} 채널에 대한 파일 이름을 만들 수 없습니다.")
                return None

            output_dir_abs_path = os.path.abspath(channel["output_dir"])
            if not os.path.exists(output_dir_abs_path):
                os.makedirs(output_dir_abs_path)
            output_path = os.path.join(output_dir_abs_path, filename)  #확장자 포함

            chat_log_path = os.path.splitext(output_path)[0] + ".log"  # 채팅 로그 파일명

        elif not output_path and not metadata:  # output_path, metadata 둘다 없는경우
            print("필요한 정보를 불러오지 못했습니다.")
            filename = f"{channel['name']}.ts"  # 메타데이터가 없을 경우 기본 파일명
            output_dir_abs_path = os.path.abspath(channel["output_dir"])
            output_path = os.path.join(
                output_dir_abs_path, filename
            )  # 메타데이터가 없을 경우의 output_path
            if not os.path.exists(output_dir_abs_path):
                os.makedirs(output_dir_abs_path)
            chat_log_path = os.path.splitext(output_path)[0] + ".log"  # 채팅 로그 파일명

        else:
            chat_log_path = os.path.splitext(output_path)[0] + ".log"  # output_path가 이미 있으면

        self.recording_filenames[channel["id"]] = output_path

        stream_url = f"https://chzzk.naver.com/live/{channel['id']}"
        cookie_value = (
            f"NID_SES={cookies['NID_SES']}; NID_AUT={cookies['NID_AUT']}"
        )
        cmd_list = [
            streamlink_path,
            "--ffmpeg-copyts",
            "--plugin-dirs",
            plugin_dir,
            stream_url,
            record_quality,
            "-o",
            output_path,
            "--ffmpeg-ffmpeg",
            ffmpeg_path,
            "--hls-live-edge",
            "1",  # 버퍼링 최소화 (세그먼트 수)
        ]

        if cookie_value:
            cmd_list.extend(["--http-header", f"Cookie={cookie_value}"])

        # 타임머신 옵션 (플러그인 설정에 따라)
        if time_shift_option:
            cmd_list.extend(time_shift_option.split())  # --hls-start-offset 옵션 추가

        # streamlink 기본 옵션
        cmd_list.extend(
            [
                "--hls-live-restart",  # 방송 재시작시 스트림 다시 시작
                "--stream-segment-timeout",
                "5",  # 세그먼트 타임아웃
                "--stream-segment-attempts",
                "5",  # 세그먼트 재시도 횟수
            ]
        )

        if not output_path:  # output_path와, chat_log_path 둘다 없는 경우.
            return None

        return cmd_list, output_path, chat_log_path, time_shift  # time_shift 반환

    def _create_filename(self, channel_id, metadata, file_extension):  # 수정: file_extension 인자 받음
        """
        채널 ID와 메타데이터를 기반으로 안전한 파일 이름을(확장자 포함) 생성합니다.
        """
        channel = next((ch for ch in self.channels if ch['id'] == channel_id), None)
        if not channel:
            return None

        live_title = metadata.get('live_title', '알 수 없는 제목')
        # 모든 문자 표현을 허용하도록 수정된 정규식
        safe_live_title = re.sub(r'[^\w\s가-힣\u3131-\u3163\uac00-\ud7a3\-\_\.\!\~\*\'\(\)]+', '_', live_title)
        safe_channel_name = channel['name'].replace(" ", "_")
        safe_channel_name = "".join(c for c in safe_channel_name if c.isalnum() or c == '_')

        filename = self.config.get(
            "filenamePattern",
            "[{start_time}] {channel_name} {safe_live_title} {record_quality}{frame_rate}{file_extension}",
        ).format(
            recording_time=datetime.now().strftime('%y%m%d_%H%M%S'),
            start_time=datetime.now().strftime('%Y-%m-%d_%H%M%S'),
            safe_live_title=safe_live_title,
            channel_name=safe_channel_name,
            record_quality=metadata.get("record_quality", "알 수 없는 품질"),
            frame_rate=metadata.get("frame_rate", "알 수 없는 프레임 속도"),
            file_extension=file_extension  # <-- file_extension 사용
        )

        # print(f"[파일이름] file_extension={file_extension}, filename={filename}")

        return filename  # <-- filename만 반환

    def onRecordingStarted(self, channel_id):
        channel_name = self.findChannelNameById(channel_id)
        self.recording_status[channel_id] = True
        print(f"녹화 시작: {channel_name} 채널")
        self.recording_started.emit(channel_id)  # 녹화 시작 시그널 발생

    def onRecordingFailed(self, channel_id, reason):
        channel_name = self.findChannelNameById(channel_id)
        QMessageBox.critical(
            None,
            "녹화 시작 오류",
            f"{channel_name} 채널의 녹화 시작 중 오류가 발생했습니다: {reason}",
        )
        print(f"{channel_name} 채널의 녹화 시작 중 오류가 발생했습니다: {reason}")

    def onRecordingFinished(self, channel_id):
        """녹화 종료 시 호출됩니다."""
        channel_name = self.findChannelNameById(channel_id)
        print(f"{channel_name} 채널 녹화가 종료되었습니다.")
        if channel_id in self.recording_start_times:
            del self.recording_start_times[channel_id]
        self.recording_status[channel_id] = False  # 녹화 상태를 False로 설정
        self.recording_finished.emit(channel_name) # 수정: 녹화 종료 시그널 발생

        if self.auto_dsc:
            # self.startStreamCopy(channel_id) # 제거
            # fixed_file_path 생성 및 저장
            if channel_id in self.recording_filenames: # 파일 이름 확인
                file_path = self.recording_filenames[channel_id]
                post_processing_output_dir = self.config.get("postProcessingOutputDir")

                if post_processing_output_dir:
                    fixed_file_path = os.path.join(
                        post_processing_output_dir, f"fixed_{os.path.basename(file_path)}"
                    )
                else:
                    fixed_file_path = os.path.join(
                        os.path.dirname(file_path), f"fixed_{os.path.basename(file_path)}"
                    )
                file_path = os.path.normpath(file_path)
                fixed_file_path = os.path.normpath(fixed_file_path)

                self.fixed_file_paths[channel_id] = fixed_file_path # 저장!
                asyncio.create_task(self.runPostProcessing(channel_id, file_path, fixed_file_path, self.config))

    async def runPostProcessing(self, channel_id, input_path, output_path, config): #async로 변경
        loop = asyncio.get_running_loop()
        try:
            post_processing_delay = self.config.get("postProcessingDelay", 0)
            await asyncio.sleep(post_processing_delay)

            output_path = await loop.run_in_executor(
                None,
                copy_specific_file,
                input_path,
                output_path,
                self.deleteAfterPostProcessing,
                config.get("removeFixedPrefix", False),
                self.config.get("minimizePostProcessing", False),
                config,
            )

            # 파일 이동 설정 (moveAfterProcessingEnabled가 True인 경우)
            if self.config.get("moveAfterProcessingEnabled", False):
                move_after_processing_path = self.config.get("moveAfterProcessing", "")
                if move_after_processing_path:
                    await asyncio.sleep(5)  # 5초 대기 (파일 안정화)
                    await loop.run_in_executor(
                        None,
                        self.moveFileAfterProcessing,
                        output_path,
                        move_after_processing_path,
                    )

        except Exception as e:
            print(f"후처리 실패: {e}")

    def moveFileAfterProcessing(self, src, dst):
        try:
            final_dst = os.path.join(os.path.normpath(dst), os.path.basename(src))
            base, ext = os.path.splitext(final_dst)
            counter = 1
            # 파일 이름 중복 체크
            while os.path.exists(final_dst):
                final_dst = f"{base} ({counter}){ext}"
                counter += 1

            # print(f"[DEBUG] Preparing to move {src} to {final_dst}")
            shutil.move(os.path.normpath(src), final_dst)
            print(f"{src} 파일이 {final_dst} 폴더로 이동되었습니다.")
        except Exception as e:
            print(f"파일 이동 중 오류 발생: {e}")

    def closeEvent(self, event):
        for thread in self.recordingThreads.values():
            if thread.isRunning():
                thread.quit()
                thread.wait()
        event.accept()

    def startRecording(self, channel_id):
        """개별 채널의 녹화를 시작합니다. 자동/수동 모드에 관계없이 호출됩니다."""
        self.channels = load_channels()  # 채널 목록 다시 불러옴
        self.startBackgroundRecording(channel_id)

    def stopRecording(self, channel_id, force_stop=False):
        if channel_id in self.recordingThreads:
            recording_thread = self.recordingThreads[channel_id]
            recording_thread.stop(force_stop)  # 여기서 채팅도 종료됨
            process = self.recording_processes.get(channel_id)
            if process:
                self.terminateRecordingProcess(process)
                del self.recording_processes[channel_id]

            # 후처리 (fixed_file_paths에서 경로 가져옴)
            if self.auto_dsc and channel_id in self.recording_filenames:
                file_path = self.recording_filenames[channel_id]
                fixed_file_path = self.fixed_file_paths.get(channel_id)  # 가져옴
                if fixed_file_path:
                    asyncio.create_task(
                        self.runStreamCopy(channel_id, file_path, fixed_file_path, self.config)
                    )

            self.cleanupAfterRecording(channel_id, force_stop)

            # 사용한 fixed_file_path는 제거
            if channel_id in self.fixed_file_paths:
                del self.fixed_file_paths[channel_id]

    def terminateRecordingProcess(self, process):
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()

    def cleanupAfterRecording(self, channel_id, force_stop=False):
        """녹화 종료 후 정리 작업을 수행합니다."""
        try:
            channel_name = self.findChannelNameById(channel_id)
            message = f"{channel_name} 채널의 녹화가 중지되었습니다."

            # 자동 녹화 모드이고, record_enabled=True, 강제종료가 아닐 때만 메시지 변경.
            channel = next((ch for ch in self.channels if ch["id"] == channel_id), None)
            if (
                self.config.get("auto_record_mode", False)
                and channel.get("record_enabled", False)
                and not force_stop
            ):
                message = f"{channel_name} 채널이 녹화 대기 상태로 전환되었습니다."

            if channel_id in self.recordingThreads:
                del self.recordingThreads[channel_id]
            if channel_id in self.recording_start_times:
                del self.recording_start_times[channel_id]
            self.recording_status[channel_id] = False  # 녹화 상태를 False로 설정

            self.recording_finished.emit(channel_name)  # 녹화 종료 시그널 발생

        except Exception as e:
            print(f"녹화 후 정리 작업 중 예외 발생: {e}")

    def startBackgroundRecording(self, channel_id):
        """녹화 스레드를 시작합니다."""
        channel_name = self.findChannelNameById(channel_id)
        if (
            channel_id in self.recordingThreads
            and self.recordingThreads[channel_id].isRunning()
        ):
            return

        channel = next((ch for ch in self.channels if ch["id"] == channel_id), None)
        if channel is None:
            print(f"{channel_name} 채널 정보를 찾을 수 없습니다.")
            return

        # RecordingThread 객체를 먼저 생성하고 딕셔너리에 추가
        recordingThread = RecordingThread(channel, self)
        self.recordingThreads[channel_id] = recordingThread  # 먼저 딕셔너리에 추가

        recordingThread.recordingStarted.connect(self.onRecordingStarted)
        recordingThread.recordingFailed.connect(self.onRecordingFailed)
        recordingThread.recordingFinished.connect(self.onRecordingFinished)

        # buildCommand 호출
        cmd_list, output_path, chat_log_path, time_shift = self.buildCommand(
            channel, self.live_metadata.get(channel_id)
        )
        if cmd_list is None:  # buildCommand 실패 처리
            print(f"오류: {channel_name} 채널에 대한 명령 목록을 만들 수 없습니다.")
            return

        print(f"{channel_name} 채널의 녹화가 시작되었습니다.({output_path})")  # output_path 사용
        recordingThread.start()  # 스레드 시작은 print *후*에

        # 스레드 시작 *후*에 채팅 프로세스 시작 (그래야 thread 내에서 self.is_chat_running = True 됨)
        if cmd_list is not None:  # buildCommand 성공했을 때만
            recordingThread.start_chat_process(chat_log_path)

    def fetch_metadata_for_all_channels(self):
        """
        채널 목록에서 각 채널에 대한 메타데이터를 가져오고, UI를 업데이트합니다.
        자동 녹화 모드(auto_record_mode)가 켜져 있으면, record_enabled가 True인 채널만 메타데이터를 가져옵니다.
        꺼져 있으면 모든 채널의 메타데이터를 가져옵니다.
        """
        if not hasattr(self, "client") or self.client.is_closed:
            cookies = load_cookies()
            headers = get_headers(cookies)
            self.client = httpx.AsyncClient(headers=headers)

        # 모든 채널에 대해 메타데이터 가져오기
        tasks = [
            self.get_live_metadata(channel, self.client) for channel in self.channels
        ]

        async def gather_results():  # 내부 함수로 정의
            try:
                results = await asyncio.gather(*tasks, return_exceptions=True)
            except Exception as e:
                print(f"gather_results 중 오류 발생: {e}")
                return []

            for channel, result in zip(self.channels, results):
                if isinstance(result, Exception) or result is None:
                    print(
                        f"[오류] {channel['name']}: 메타데이터 가져오기 중 오류 발생 - {result}"
                    )
                    QTimer.singleShot(
                        5000, partial(self.schedule_metadata_retry, channel)
                    )
                else:
                    # *항상* metadata_updated 시그널 발생 (UI 업데이트)
                    # self.metadata_updated.emit(channel['id'], result)  # <--  이 부분이 중요!

                    # 자동 녹화 시작 여부 결정 (UI 업데이트와는 별개)
                    if result.get("open_live") is not None:
                        self.metadata_updated.emit(channel['id'], result)

                        # 자동 녹화 모드 OFF일 때는 LiveRecorder에서 녹화 시작 X
                        if (
                            result.get("open_live")
                            and self.config.get("auto_record_mode", False)
                            and channel.get("record_enabled", False)
                        ):
                            self.startRecording(channel["id"])

                    else:
                        print(f"{channel['name']} 채널은 현재 방송 중이 아닙니다.")
            return []  # gather_result는 빈 리스트 반환

        asyncio.run_coroutine_threadsafe(
            gather_results(), asyncio.get_event_loop()
        )

    async def start_chat_background(self, channel_id):
        """채팅 시작 (LiveRecorder) -> 이제 채팅 프로세스 실행 안함."""
        channel_name = self.findChannelNameById(channel_id)
        try:
            channel = next(
                (ch for ch in self.channels if ch["id"] == channel_id), None
            )
            if channel is None:
                print(f"{channel_name} 채널 정보를 찾을 수 없습니다.")
                return
            if self.chat_status.get(channel_id, False):  # 이미 실행 중이면 중복 실행 방지
                print(f"{channel_name} 채널의 채팅 저장이 이미 실행 중입니다.")
                return

            # 로그 파일 이름 생성 (이제 여기서 로그 파일 이름/경로 생성 안함)
            # log_filename = self._create_filename(channel_id, metadata, ".log")
            # if log_filename is None:
            #     print(f"Error: Could not create log filename for {channel_name}.")
            #     return

            # log_path = os.path.join(channel.get("output_dir", "."), log_filename)

            # # 새로운 콘솔 창에서 run.py 실행  <-- 이 부분 제거
            # command = [
            #     sys.executable,
            #     os.path.join(base_directory, "module", "run.py"),
            #     "--streamer_id",
            #     channel_id,
            #     "--log_path",
            #     log_path
            # ]
            # process = subprocess.Popen(command, creationflags=subprocess.CREATE_NEW_CONSOLE)

            # self.chat_processes[channel_id] = process
            # self.chat_log_paths[channel_id] = log_path  # <-- 제거
            self.chat_status[channel_id] = True  # 채팅 상태만 True로 설정
            print(f"채팅 저장 시작: {channel_name} (독립 실행)")  # 메시지 변경

        except Exception as e:
            print(f"startChat 함수에서 예외 발생: {e}")
            return
