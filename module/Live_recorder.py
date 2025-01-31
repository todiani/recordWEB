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
from PyQt5.QtWidgets import QLabel, QApplication, QMainWindow, QPushButton, QVBoxLayout, QWidget, QMessageBox
from PyQt5.QtCore import QTimer, QThread, pyqtSignal, QObject, pyqtSlot, Qt
from PyQt5.QtGui import QPixmap, QPainter, QColor, QBrush, QFont

from channel_manager import load_channels, save_channels, load_config, save_config
from copy_streams import copy_specific_file

class RecordingThread(QThread):
    recordingStarted = pyqtSignal(str)
    recordingFailed = pyqtSignal(str, str)
    recordingFinished = pyqtSignal(str)

    def __init__(self, channel, liveRecorder, parent=None):
        super().__init__(parent)
        self.channel = channel
        self.liveRecorder = liveRecorder
        self.stopRequested = False
        self.force_stop = False
        self.retryDelay = 60  # 녹화 종료 후 강제 딜레이 시간(초)
        self.loop = None  
        self.stop_timer = None  # 타이머를 인스턴스 변수로 선언
        self.session_cookies = self.liveRecorder.get_session_cookies()

    @pyqtSlot()
    def run(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        client = httpx.AsyncClient()
        try:
            while not self.stopRequested:
                live_info = self.loop.run_until_complete(self.liveRecorder.get_live_metadata(self.channel, client))
                if live_info and live_info.get("open_live"):
                    self.liveRecorder.recording_start_times[self.channel['id']] = time.time()
                    cmd_list = self.liveRecorder.buildCommand(self.channel, live_info)
                    try:
                        process = subprocess.Popen(cmd_list)
                        self.liveRecorder.recording_status[self.channel['id']] = True
                        self.liveRecorder.recording_processes[self.channel['id']] = process
                        self.recordingStarted.emit(self.channel['id'])

                        auto_stop_interval = self.liveRecorder.config.get('autoStopInterval', 0)
                        print(f"분할녹화 시간 간격: {auto_stop_interval} 초")  
                        if auto_stop_interval > 0:
                            self.stop_timer = threading.Timer(auto_stop_interval, self.stop)
                            self.stop_timer.start()

                        process.wait()
                        if self.stop_timer:
                            self.stop_timer.cancel()
                        self.recordingFinished.emit(self.channel['id'])  # 녹화 종료 이벤트 발생
                    except Exception as e:
                        self.recordingFailed.emit(self.channel['id'], str(e))
                        return
                    finally:
                        print(f"{self.channel['name']} 녹화 종료 후 {self.retryDelay}초 대기 중...")
                        self.loop.run_until_complete(asyncio.sleep(self.retryDelay))  # 녹화 종료 후 강제 대기 시간
                        if self.force_stop:
                            break  
                        live_info = self.loop.run_until_complete(self.liveRecorder.get_live_metadata(self.channel, client))
                        if live_info and live_info.get("open_live"):
                            self.stopRequested = False  # 분할 녹화 후 다시 예약 녹화 상태로 설정
                            continue  # 방송이 종료되지 않았으면 루프 반복
                        else:
                            self.liveRecorder.reserved_recording[self.channel['id']] = True  # 예약 녹화 상태로 설정
                            self.stopRequested = False  # 예약 녹화 후 다시 예약 녹화 상태로 설정
                            print(f"{self.channel['name']} 방송이 종료되었습니다. 예약 녹화 상태로 전환합니다.")
                else:
                    self.liveRecorder.reserved_recording[self.channel['id']] = True
                    self.loop.run_until_complete(asyncio.sleep(self.liveRecorder.recheck_interval))
        finally:
            self.loop.run_until_complete(client.aclose())
            self.loop.close()

    def stop(self, force_stop=False):
        try:
            self.stopRequested = True
            self.force_stop = force_stop  # force_stop 상태 설정
            if self.isRunning():
                channel_id = self.channel['id']
                process = self.liveRecorder.recording_processes.get(channel_id)
                if process:
                    process.terminate()
                    QTimer.singleShot(5000, lambda: self.forceTerminateProcess(process))
                QTimer.singleShot(100, self.checkStopRequest)
        except Exception as e:
            print(f"녹화 중지 중 예외 발생: {e}")

    def forceTerminateProcess(self, process):
        try:
            if not process.poll():
                process.kill()
        except Exception as e:
            print(f"프로세스 강제 종료 중 예외 발생: {e}")

    def checkStopRequest(self):
        if self.stopRequested and not self.liveRecorder.recording_processes:
            self.liveRecorder.cleanupAfterRecording(self.channel['id'], self.force_stop)
            self.stopRequested = False

class LiveRecorder(QObject):
    metadata_updated = pyqtSignal(str, object)

    def __init__(self, channels, default_thumbnail_path=None):
        super().__init__()
        self.recordingThreads = {}
        self.recording_processes = {}
        self.recording_start_times = {}
        self.recording_requested = {}
        self.recording_status = {}
        self.reserved_recording = {}
        self.recording_filenames = {}
        self.live_metadata = {}
        self.channels = channels
        self.session_cookies = self.get_session_cookies()
        self.config = load_config()
        self.recheck_interval = int(self.config.get('recheckInterval', 60))
        self.auto_stop_interval = int(self.config.get('autoStopInterval', 0))
        self.show_message_box = self.config.get('showMessageBox', True)
        self.auto_dsc = self.config.get('autoPostProcessing', False)
        self.filename_pattern = self.config.get('filenamePattern', '[{start_time}] {channel_name} {safe_live_title} {record_quality}{frame_rate}{file_extension}')
        self.deleteAfterPostProcessing = self.config.get('deleteAfterPostProcessing', False)
        self.post_processing_output_dir = self.config.get('postProcessingOutputDir', '')
        # +++
        self.chat_enabled = {}  # 추가: 채널별 채팅 활성화/비활성화 상태를 저장하기 위한 딕셔너리

        if default_thumbnail_path is None:
            self.default_thumbnail_path = os.path.join(
                os.path.dirname(os.path.dirname(os.path.realpath(__file__))), 'dependent', 'img', 'default_thumbnail.png')
        else:
            self.default_thumbnail_path = default_thumbnail_path

    # +++
    def setChatEnabled(self, channel_id, enabled):
        self.chat_enabled[channel_id] = enabled

    # +++
    def isChatEnabled(self, channel_id):
        return self.chat_enabled.get(channel_id, False)

    # 설정에 따라 메시지 박스 표시 여부 결정
    def auto_close_message_box(self, title, text, timeout=5000):
        if not self.show_message_box: 
            print(title, text)
            return

        msgBox = QMessageBox()
        msgBox.setWindowTitle(title)
        msgBox.setText(text)
        msgBox.setStandardButtons(QMessageBox.Ok)
        QTimer.singleShot(timeout, msgBox.accept)
        msgBox.exec_()

    def startBackgroundRecording(self, channel_id):
        channel_name = self.findChannelNameById(channel_id)
        if channel_id in self.recordingThreads and self.recordingThreads[channel_id].isRunning():
            print(f"{channel_name} 채널의 녹화가 이미 실행 중입니다.")
            return

        channel = next((ch for ch in self.channels if ch['id'] == channel_id), None)
        if channel is None:
            print(f"{channel_name} 채널 정보를 찾을 수 없습니다.")
            return
        # run.py 프로세스가 실행중이면 채팅 로깅을 실행하지 않음
        if not self.chat_enabled.get(channel_id, False) :
            recordingThread = RecordingThread(channel, self)
            recordingThread.recordingStarted.connect(self.onRecordingStarted)
            recordingThread.recordingFailed.connect(self.onRecordingFailed)
            recordingThread.recordingFinished.connect(self.onRecordingFinished)
            recordingThread.start()

            self.recordingThreads[channel_id] = recordingThread
            print(f"{channel_name} 채널의 녹화가 시작되었습니다.")

        else:
            recordingThread = RecordingThread(channel, self)
            recordingThread.recordingStarted.connect(self.onRecordingStarted)
            recordingThread.recordingFailed.connect(self.onRecordingFailed)
            recordingThread.recordingFinished.connect(self.onRecordingFinished)
            recordingThread.start()

            self.recordingThreads[channel_id] = recordingThread
            print(f"{channel_name} 채널의 녹화가 시작되었습니다.")

    def onRecordingStarted(self, channel_id):
        channel_name = self.findChannelNameById(channel_id)
        self.recording_status[channel_id] = True
        self.auto_close_message_box("녹화 시작", f"{channel_name} 채널의 녹화를 시작합니다.")
        print(f"{channel_name} 채널의 녹화를 시작합니다.")

        # 시작 시 채널 ID를 기반으로 채팅 활성화
        self.setChatEnabled(channel_id, True)

    def onRecordingFailed(self, channel_id, reason):
        channel_name = self.findChannelNameById(channel_id)
        QMessageBox.critical(None, "녹화 시작 오류", f"{channel_name} 채널의 녹화 시작 중 오류가 발생했습니다: {reason}")
        print(f"{channel_name} 채널의 녹화 시작 중 오류가 발생했습니다: {reason}")

    def onRecordingFinished(self, channel_id):
        channel_name = self.findChannelNameById(channel_id)
        print(f"{channel_name} 채널 녹화가 종료되었습니다.")
        if channel_id in self.recording_start_times:
            del self.recording_start_times[channel_id]
        self.recording_status[channel_id] = False
        self.auto_close_message_box("녹화 중지", f"{channel_name} 채널의 녹화가 중지되었습니다.")

        if self.auto_dsc:
            self.startStreamCopy(channel_id)

        # 종료 시 채널 ID를 기반으로 채팅 비활성화
        self.setChatEnabled(channel_id, False)

    def startStreamCopy(self, channel_id):
        if channel_id not in self.recording_filenames:
            print(f"{channel_id} 채널의 파일명을 찾을 수 없습니다.")
            return

        file_path = self.recording_filenames[channel_id]
        post_processing_output_dir = self.config.get('postProcessingOutputDir')
        
        if post_processing_output_dir:
            fixed_file_path = os.path.join(post_processing_output_dir, f"fixed_{os.path.basename(file_path)}")
        else:
            fixed_file_path = os.path.join(os.path.dirname(file_path), f"fixed_{os.path.basename(file_path)}")

        file_path = os.path.normpath(file_path)
        fixed_file_path = os.path.normpath(fixed_file_path)

        asyncio.create_task(self.runStreamCopy(file_path, fixed_file_path, self.config))

    async def runStreamCopy(self, input_path, output_path, config):
        loop = asyncio.get_running_loop()
        try:
            print(f"[DEBUG] input_path: {input_path}")
            print(f"[DEBUG] output_path: {output_path}")

            output_path = await loop.run_in_executor(
                None,
                copy_specific_file,
                input_path,
                output_path,
                self.deleteAfterPostProcessing,
                config.get('removeFixedPrefix', False),
                self.config.get('minimizePostProcessing', False),
                config 
            )
            print(f"녹화파일 후처리가 성공적으로 완료되었습니다: {output_path}")

            if self.config.get('moveAfterProcessingEnabled', False):
                move_after_processing_path = self.config.get('moveAfterProcessing', '')
                if move_after_processing_path:
                    await asyncio.sleep(5)
                    await loop.run_in_executor(None, self.moveFileAfterProcessing, output_path, move_after_processing_path)

        except Exception as e:
            print(f"후처리 실패: {e}")

    def moveFileAfterProcessing(self, src, dst):
        try:
            final_dst = os.path.join(os.path.normpath(dst), os.path.basename(src))
            base, ext = os.path.splitext(final_dst)
            counter = 1
            
            while os.path.exists(final_dst):
                final_dst = f"{base} ({counter}){ext}"
                counter += 1
            
            print(f"[DEBUG] Preparing to move {src} to {final_dst}")
            shutil.move(os.path.normpath(src), final_dst)
            print(f"파일 {file_path}가 {destination_path}로 이동되었습니다.")
        except Exception as e:
            print(f"파일 이동 중 오류 발생: {e}")

    def closeEvent(self, event):
        for thread in self.recordingThreads.values():
            if thread.isRunning():
                thread.quit()
                thread.wait()
        event.accept()

    def startRecording(self, channel_id):
        self.channels = load_channels()
        self.recording_requested[channel_id] = True
        self.startBackgroundRecording(channel_id)

    def stopRecording(self, channel_id, force_stop=False):
        self.recording_requested[channel_id] = False
        if channel_id in self.recordingThreads:
            self.recordingThreads[channel_id].stop(force_stop=force_stop)
            process = self.recording_processes.get(channel_id)
            if process:
                self.terminateRecordingProcess(process)
                del self.recording_processes[channel_id]
            self.cleanupAfterRecording(channel_id, force_stop)

    def terminateRecordingProcess(self, process):
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()

    def cleanupAfterRecording(self, channel_id, force_stop=False):
        try:
            channel_name = self.findChannelNameById(channel_id)
            if self.reserved_recording.get(channel_id, False):
                self.auto_close_message_box("녹화 중지", f"{channel_name} 채널의 예약녹화가 중지되었습니다.")
                self.reserved_recording[channel_id] = False
            if channel_id in self.recordingThreads:
                del self.recordingThreads[channel_id]
            if channel_id in self.recording_start_times:
                del self.recording_start_times[channel_id]
            self.recording_status[channel_id] = False
            self.auto_close_message_box("녹화 중지", f"{channel_name} 채널의 녹화가 중지되었습니다.")
            if not force_stop and self.config.get('auto_record_mode', False):
                self.reserved_recording[channel_id] = True  
                print(f"{channel_name} 채널이 예약 녹화 상태로 전환되었습니다.")
        except Exception as e:
            print(f"녹화 후 정리 작업 중 예외 발생: {e}")

    def findChannelNameById(self, channel_id):
        for channel in self.channels:
            if channel['id'] == channel_id:
                return channel['name']
        return None

    def isRecording(self, channel_id):
        return self.recording_status.get(channel_id, False)

    def getRecordingDuration(self, channel_id):
        start_time = self.recording_start_times.get(channel_id)
        if start_time:
            elapsed_time = time.time() - start_time
            adjusted_time = max(0, elapsed_time - 3)
            return time.strftime('%H:%M:%S', time.gmtime(adjusted_time))
        return "00:00:00"

    def get_session_cookies(self):
        # 현재 스크립트의 상위 디렉토리를 찾습니다.
        current_dir = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
        cookie_file_path = os.path.join(current_dir, 'json', 'cookie.json')
        try:
            with open(cookie_file_path, 'r') as cookie_file:
                cookies = json.load(cookie_file)
            return cookies
        except (FileNotFoundError, json.JSONDecodeError) as e:
            print(f"쿠키 파일 읽기 오류: {e}")
            return {}

    def get_auth_headers(self, cookies):
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)',
            'Cookie': f'NID_AUT={cookies.get("NID_AUT", "")}; NID_SES={cookies.get("NID_SES", "")}'
        }
        return headers

    def record_quality_info(self, debug_log):
        quality_match = re.search(r"Opening stream: (\d+p) \(hls-chzzk\)", debug_log)
        if quality_match:
            self.record_quality = quality_match.group(1)
            print(f"현재 녹화 품질 해상도: {self.record_quality}")
        else:
            self.record_quality = "Unknown Quality"
            print("녹화 품질 해상도를 찾을 수 없습니다.")
        return self.record_quality



    async def get_live_metadata(self, channel, client, retries=3, delay=3):
        timeout = httpx.Timeout(10.0, read=30.0)
        client.timeout = timeout
        for attempt in range(retries):
            try:
                print(f"{channel['name']} 채널의 메타데이터 요청 시작, 시도 #{attempt + 1}")
                cookies = self.get_session_cookies()
                headers = self.get_auth_headers(cookies)
                url = f"https://api.chzzk.naver.com/service/v3/channels/{channel['id']}/live-detail"

                response = await client.get(url, headers=headers)
                response.raise_for_status()
                print(f"{channel['name']} 채널의 메타데이터 요청 완료: 상태 코드 {response.status_code}")

                metadata_content = response.json().get("content")
                if metadata_content is None:
                    print(f"{channel['name']} 채널의 메타데이터가 없습니다 (content가 None).")
                    return None

                try:
                    # {type}을 270 해상도로 대체하여 썸네일 URL을 설정
                    thumbnail_url = metadata_content.get("liveImageUrl", "").format(type="270") if metadata_content.get("liveImageUrl") else self.default_thumbnail_path
                    print(f"Thumbnail URL for {channel['name']}: {thumbnail_url}")
                except Exception as e:
                    print(f"썸네일 URL 처리 중 예외 발생: {e}, 기본 썸네일 이미지 사용")
                    thumbnail_url = self.default_thumbnail_path

                # channels.json에서 해당 채널의 quality 값을 가져옴
                record_quality_setting = channel.get('quality', 'best')
                print(f"Record Quality Setting: {record_quality_setting}")

                # API 응답에서 가장 적절한 해상도와 프레임 레이트 선택
                frame_rate = "Unknown Frame Rate"
                record_quality = "Unknown Quality"
                encoding_tracks = json.loads(metadata_content["livePlaybackJson"])["media"]
                max_resolution = 0

                for track in encoding_tracks:
                    for encoding in track["encodingTrack"]:
                        resolution = int(encoding["videoWidth"]) * int(encoding["videoHeight"])
                        if (record_quality_setting == "best" and resolution > max_resolution) or (record_quality_setting != "best" and encoding["encodingTrackId"] == record_quality_setting):
                            max_resolution = resolution
                            record_quality = encoding["encodingTrackId"]
                            frame_rate = str(int(float(encoding["videoFrameRate"])))

                print(f"녹화품질: {record_quality}, 프레임 레이트: {frame_rate}")

                parsed_metadata = {
                    "thumbnail_url": thumbnail_url,
                    "live_title": metadata_content.get("liveTitle", ""),  # 수정: 값이 없으면 빈 문자열 사용
                    "channel_name": metadata_content["channel"]["channelName"] if "channel" in metadata_content and "channelName" in metadata_content["channel"] else "",  # 수정: 값이 없으면 빈 문자열 사용
                    "recording_duration": metadata_content.get("openDate", ""),
                    "open_live": metadata_content.get("status", "") == "OPEN",
                    "category": metadata_content.get("liveCategoryValue", ""),  # 수정: 값이 없으면 빈 문자열 사용
                    "record_quality": record_quality,
                    "frame_rate": frame_rate
                }
                self.live_metadata[channel['id']] = parsed_metadata
                if not parsed_metadata.get("open_live") and self.recording_requested.get(channel['id'], False):
                    self.reserved_recording[channel['id']] = True
                else:
                    self.reserved_recording.pop(channel['id'], None)
                return parsed_metadata
            except Exception as e:
                print(f"[Retry] Attempt {attempt + 1} failed with error: {e}")
                if attempt + 1 < retries:
                    await asyncio.sleep(delay)
                else:
                    print(f"[오류] {channel['name']}: 메타데이터를 가져오는 도중 오류가 발생하였습니다")
                    return None

    async def fetch_metadata_for_all_channels(self):
        if not hasattr(self, 'client') or self.client.is_closed:
            session_cookies = self.get_session_cookies()
            headers = self.get_auth_headers(session_cookies)
            self.client = httpx.AsyncClient(headers=headers)

        tasks = [self.get_live_metadata(channel, self.client) for channel in self.channels]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for channel, result in zip(self.channels, results):
            if isinstance(result, Exception) or result is None:
                print(f"[오류] {channel['name']}: 메타데이터 가져오기 중 오류 발생 - {result}")
                print(f"{channel['name']} 채널의 메타데이터를 가져오는 데 실패했습니다. 재시도합니다.")
                await asyncio.sleep(5)
                self.schedule_metadata_retry(channel)
            else:
                if result.get('open_live') is not None:
                    print(f"{channel['name']} 채널의 메타데이터를 성공적으로 업데이트했습니다.")
                    self.metadata_updated.emit(channel['id'], result)
                else:
                    print(f"{channel['name']} 채널은 현재 방송 중이 아닙니다.")

    def schedule_metadata_retry(self, channel):
        asyncio.create_task(self.get_live_metadata(channel, self.client))

    def effect_thumbnail(self, pixmap):
        effect_pixmap = QPixmap(pixmap.size())
        effect_pixmap.fill(Qt.transparent)

        painter = QPainter(effect_pixmap)
        painter.drawPixmap(0, 0, pixmap)
        painter.fillRect(pixmap.rect(), QBrush(QColor(0, 0, 0, 127)))
        painter.setPen(Qt.white)
        painter.setFont(QFont('Arial', 20, QFont.Bold))
        text_rect = pixmap.rect()
        text = "Off the Air"
        painter.drawText(text_rect, Qt.AlignCenter, text)
        painter.end()

        current_dir = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
        output_path = os.path.join(current_dir, 'dependent', 'img', 'debug_image.png')
        effect_pixmap.save(output_path)

        return effect_pixmap

    async def close_client(self):
        if hasattr(self, 'client') and not self.client.is_closed:
            await self.client.aclose()

    def buildCommand(self, channel, metadata=None):
        record_quality = channel.get('quality', 'best')
        file_extension = channel.get('extension', '.ts')
        current_dir = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
        selected_plugin = self.config.get('plugin', '기본 플러그인')
        if selected_plugin == '기본 플러그인':
            plugin_folder_name = 'basic'
        elif selected_plugin == '타임머신 플러그인':
            plugin_folder_name = 'timemachine'
        elif selected_plugin == '타임머신 플러스 플러그인':
            plugin_folder_name = 'timemachine_plus'
        else:
            plugin_folder_name = 'basic' 

        plugin_dir = os.path.join(current_dir, 'dependent', 'plugin', plugin_folder_name)
        streamlink_path = os.path.join(current_dir, "dependent", "streamlink", "bin", "streamlink.exe")
        ffmpeg_path = os.path.join(current_dir, "dependent", "ffmpeg", "bin", "ffmpeg.exe")
        cookies = self.get_session_cookies()

        # 타임머신 기능을 사용할 때 시작 시점을 설정합니다 (예: 1분 전)
        if selected_plugin in ['타임머신 플러그인', '타임머신 플러스 플러그인']:
            time_shift = self.config.get('time_shift', 0)
            time_shift_option = f"--hls-start-offset={time_shift}" 
        else:
            time_shift_option = ""

        if metadata:
            live_title_raw = metadata["live_title"]
            live_title = live_title_raw.strip().replace('\n', '')
            safe_live_title = re.sub(r'[\\/*?:"<>|+]', '_', live_title)[:55]
            safe_live_title = re.sub(r'[^\w\s\u3040-\u30FF\u4E00-\u9FFF가-힣]', '_', safe_live_title)
            recording_time = datetime.now().strftime('%y%m%d_%H%M%S')
            start_time = datetime.now().strftime('%Y-%m-%d')
            filename = self.filename_pattern.format(
                recording_time=recording_time,
                start_time=start_time,
                safe_live_title=safe_live_title,
                channel_name=channel['name'],
                record_quality=metadata.get('record_quality', 'Unknown Quality'),
                frame_rate=metadata.get('frame_rate', 'Unknown Frame Rate'),
                file_extension=file_extension
            )

            output_dir_abs_path = os.path.abspath(channel['output_dir'])
            if not os.path.exists(output_dir_abs_path):
                os.makedirs(output_dir_abs_path)
            base_output_path = os.path.join(output_dir_abs_path, filename)
            output_path = base_output_path
            counter = 1
            while os.path.exists(output_path):
                name, ext = os.path.splitext(base_output_path)
                output_path = f"{name} ({counter}){ext}"
                counter += 1
        else:
            print("필요한 정보를 불러오지 못했습니다.")
            filename = f"{channel['name']}.ts"
            output_dir_abs_path = os.path.abspath(channel['output_dir'])
            output_path = os.path.join(output_dir_abs_path, filename)
            if not os.path.exists(output_dir_abs_path):
                os.makedirs(output_dir_abs_path)

        self.recording_filenames[channel['id']] = output_path

        stream_url = f"https://chzzk.naver.com/live/{channel['id']}"
        cookie_value = f"NID_SES={cookies['NID_SES']}; NID_AUT={cookies['NID_AUT']}"
        cmd_list = [
            streamlink_path, "--ffmpeg-copyts",
            "--plugin-dirs", plugin_dir,
            stream_url, record_quality,
            "-o", output_path,
            "--ffmpeg-ffmpeg", ffmpeg_path
        ]

        if cookie_value:
            cmd_list.extend(["--http-header", f"Cookie={cookie_value}"])

        if time_shift_option:
            cmd_list.extend(time_shift_option.split())

        cmd_list.extend([
            "--hls-live-restart",
            "--stream-segment-timeout", "5",
            "--stream-segment-attempts", "5"
        ])

        return cmd_list