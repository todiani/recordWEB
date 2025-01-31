import importlib
import subprocess
import os
import json
import sys
import random
import xml.etree.ElementTree as ET
import asyncio
from datetime import datetime, timedelta
from threading import Thread
from concurrent.futures import ThreadPoolExecutor

# 필수 모듈 설치 함수
def installMissingModules():
    missing_modules = ["PyQt5", "aiohttp"]
    installed_modules = []

    # 각 모듈을 시도하여 불러오고, 실패하면 설치 리스트에 추가
    for module in missing_modules:
        try:
            importlib.import_module(module)
        except ImportError:
            installed_modules.append(module)

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

installMissingModules()

import aiohttp
from PyQt5.QtCore import QThread, pyqtSignal, Qt
from PyQt5.QtWidgets import QApplication, QMainWindow, QWidget, QVBoxLayout, QPushButton, QLineEdit, QFileDialog, QMessageBox, QLabel, QComboBox, QCheckBox

class DownloadThread(QThread):
    finished = pyqtSignal()
    error = pyqtSignal(str)

    def __init__(self, vodNumber, savePath, quality, startTime, endTime, segmentOption, mergeMethod):
        super().__init__()
        self.vodNumber = vodNumber
        self.savePath = savePath
        self.quality = quality
        self.startTime = startTime
        self.endTime = endTime
        self.segmentOption = segmentOption
        self.mergeMethod = mergeMethod

    def run(self):
        downloader = VODDownloader(self.quality, self.savePath)
        try:
            asyncio.run(downloader.authenticateAndDownload(
                self.vodNumber,
                self.savePath,
                self.quality,
                self.startTime,
                self.endTime,
                self.segmentOption,
                self.mergeMethod
            ))
            self.finished.emit()
        except Exception as e:
            self.error.emit(str(e))

class VODDownloaderApp(QMainWindow):
    finished = pyqtSignal() # 추가
    def __init__(self):
        super().__init__()

        BASE_DIR = os.path.dirname(os.path.realpath(__file__))
        BASE_DIR = os.path.dirname(BASE_DIR)  
        self.FFMPEG_PATH = os.path.join(BASE_DIR, "dependent", "ffmpeg", "bin", "ffmpeg.exe").replace("\\", "/")
        self.FFPROBE_PATH = os.path.join(BASE_DIR, "dependent", "ffmpeg", "bin", "ffprobe.exe").replace("\\", "/")

        if not os.path.exists(self.FFMPEG_PATH):
            print(f"FFmpeg 경로를 찾을 수 없습니다: {self.FFMPEG_PATH}")
        else:
            print(f"FFmpeg 경로: {self.FFMPEG_PATH}")
        self.initUI()
        self.check_gpu_support_and_print()

        # 쿠키 정보를 저장할 멤버 변수 추가
        self.cookies = {}
        self.load_cookies()
        self.session = aiohttp.ClientSession()
        self.vodEdit.textChanged.connect(self.updateVodInfo)

    def initUI(self):
        self.setWindowTitle("VOD 다운로더 v0819")
        self.setFixedWidth(400)
        self.layout = QVBoxLayout()
        self.layout.setSpacing(10)

        vodLabel = QLabel("VOD 번호: chzzk.naver.com/video/[VOD번호]")
        self.vodEdit = QLineEdit()
        self.layout.addWidget(vodLabel)
        self.layout.addWidget(self.vodEdit)

        startTimeLabel = QLabel("구간영상 시작시간 (hh:mm:ss):")
        self.startTimeEdit = QLineEdit()
        self.layout.addWidget(startTimeLabel)
        self.layout.addWidget(self.startTimeEdit)

        endTimeLabel = QLabel("구간영상 종료시간 (hh:mm:ss):")
        self.endTimeEdit = QLineEdit()
        self.layout.addWidget(endTimeLabel)
        self.layout.addWidget(self.endTimeEdit)

        segmentLabel = QLabel("분할 횟수(180초 초과 영상만 해당):")
        self.segmentCombo = QComboBox()
        self.segmentCombo.addItems(["분할 안함", "4분할", "8분할", "16분할"])
        self.segmentCombo.setCurrentIndex(3)
        self.layout.addWidget(segmentLabel)
        self.layout.addWidget(self.segmentCombo)

        gpu_support_message = self.check_gpu_support()

        mergeMethodLabel = QLabel("병합시 인코딩 설정: ")
        mergeMethodLabel.setText(mergeMethodLabel.text() + gpu_support_message)
        mergeMethodLabel.setTextFormat(Qt.RichText)

        self.mergeMethodCombo = QComboBox()
        self.mergeMethodCombo.addItems([
            "(1) 스트림복사",
            "(2) 병합 인코딩 CPU",
            "(3) 병합 인코딩 GPU 가속(인텔)", 
            "(4) 병합 인코딩 GPU 가속(AMD)",
            "(5) 병합 인코딩 GPU 가속(엔비디아)",
        ])
        self.layout.addWidget(mergeMethodLabel)
        self.layout.addWidget(self.mergeMethodCombo)

        savePathLabel = QLabel("저장 경로:")
        self.savePathEdit = QLineEdit()
        self.browseButton = QPushButton("폴더 선택")
        self.browseButton.clicked.connect(self.selectDirectory)
        self.layout.addWidget(savePathLabel)
        self.layout.addWidget(self.savePathEdit)
        self.layout.addWidget(self.browseButton)

        qualityLabel = QLabel("해상도 품질 선택: best는 가장 높은품질")
        self.qualityCombo = QComboBox()
        self.qualityCombo.addItems(["best", "1080p", "720p"])
        self.layout.addWidget(qualityLabel)
        self.layout.addWidget(self.qualityCombo)

        downloadButton = QPushButton("다운로드")
        downloadButton.clicked.connect(self.onDownloadButtonClick)
        self.layout.addWidget(downloadButton)

        container = QWidget()
        container.setLayout(self.layout)
        self.setCentralWidget(container)

    def check_gpu_support_and_print(self):
        nvenc_supported = self.check_nvenc_support()
        intel_qsv_supported = self.check_intel_qsv_support()
        amd_amf_supported = self.check_amd_amf_support()

        print(f"NVENC 지원 여부: {nvenc_supported}")
        print(f"Intel QSV 지원 여부: {intel_qsv_supported}")
        print(f"AMD AMF 지원 여부: {amd_amf_supported}")

    def check_nvenc_support(self):
        try:
            result = subprocess.run(
                [
                    self.FFMPEG_PATH,
                    "-init_hw_device", "cuda=hw",
                    "-filter_hw_device", "hw",
                    "-f", "lavfi",
                    "-i", "nullsrc=size=1280x720:rate=30",
                    "-frames:v", "1",
                    "-c:v", "h264_nvenc",
                    "-f", "null", "-"
                ],
                capture_output=True, text=True
            )
            return result.returncode == 0
        except Exception as e:
            print(f"NVENC 지원 확인 중 오류 발생: {e}")
            return False

    def check_intel_qsv_support(self):
        try:
            result = subprocess.run(
                [
                    self.FFMPEG_PATH, 
                    "-init_hw_device", "qsv=hw", 
                    "-filter_hw_device", "hw", 
                    "-f", "lavfi", 
                    "-i", "nullsrc=size=1280x720:rate=30", 
                    "-frames:v", "1", 
                    "-c:v", "h264_qsv", 
                    "-f", "null", "-"
                ],
                capture_output=True, text=True
            )
            return result.returncode == 0
        except Exception as e:
            print(f"Intel QSV 지원 확인 중 오류 발생: {e}")
            return False

    def check_amd_amf_support(self):
        try:
            result = subprocess.run(
                [
                    self.FFMPEG_PATH,
                    "-init_hw_device", "vulkan=hw",
                    "-filter_hw_device", "hw",
                    "-f", "lavfi",
                    "-i", "nullsrc=size=1280x720:rate=30",
                    "-frames:v", "1",
                    "-c:v", "h264_amf",
                    "-f", "null", "-"
                ],
                capture_output=True, text=True
            )
            return result.returncode == 0
        except Exception as e:
            print(f"AMD AMF 지원 확인 중 오류 발생: {e}")
            return False

    def check_gpu_support(self):
        nvenc_supported = self.check_nvenc_support()
        intel_qsv_supported = self.check_intel_qsv_support()
        amd_amf_supported = self.check_amd_amf_support()

        messages = []
        if intel_qsv_supported:
            messages.append('<span style="color: blue; font-weight: bold;">Intel GPU 가속 가능</span>')
        if amd_amf_supported:
            messages.append('<span style="color: red; font-weight: bold;">AMD GPU 가속 가능</span>')
        if nvenc_supported:
            messages.append('<span style="color: green; font-weight: bold;">NVIDIA GPU 가속 가능</span>')

        if not messages:
            messages.append('<span style="color: red; font-weight: bold;">GPU 가속 불가능</span>')

        return " / ".join(messages)

    def selectDirectory(self):
        directory = QFileDialog.getExistingDirectory(self, "저장 폴더 선택")
        if directory:
            self.savePathEdit.setText(directory)

    def onDownloadButtonClick(self):
        vod_number = self.vodEdit.text()
        save_path = self.savePathEdit.text()
        quality = self.qualityCombo.currentText()
        start_time = self.startTimeEdit.text()
        end_time = self.endTimeEdit.text()
        segment_option_index = self.segmentCombo.currentIndex()
        segment_option = [1, 4, 8, 16][segment_option_index]

        merge_method_index = self.mergeMethodCombo.currentIndex()

        # GPU 가속 지원 여부 확인
        if merge_method_index in [2, 3, 4]:
            if merge_method_index == 2 and not self.check_intel_qsv_support():
                QMessageBox.warning(self, "경고", "Intel GPU 가속을 사용할 수 없습니다. CPU 인코딩을 사용합니다.")
                merge_method_index = 1  # CPU 인코딩으로 변경
            elif merge_method_index == 3 and not self.check_amd_amf_support():
                QMessageBox.warning(self, "경고", "AMD GPU 가속을 사용할 수 없습니다. CPU 인코딩을 사용합니다.")
                merge_method_index = 1  # CPU 인코딩으로 변경
            elif merge_method_index == 4 and not self.check_nvenc_support():
                QMessageBox.warning(self, "경고", "NVIDIA GPU 가속을 사용할 수 없습니다. CPU 인코딩을 사용합니다.")
                merge_method_index = 1  # CPU 인코딩으로 변경

        merge_method = merge_method_index

        if vod_number and save_path:
            # 쿠키 정보를 DownloadThread에 전달
            self.downloadThread = DownloadThread(vod_number, save_path, quality, start_time, end_time, segment_option, merge_method)
            self.downloadThread.finished.connect(self.onDownloadFinished)
            self.downloadThread.error.connect(self.onDownloadError)
            self.downloadThread.start()
        else:
            QMessageBox.warning(self, "경고", "모든 필드를 채워주세요.")

    def onDownloadFinished(self):
        QMessageBox.information(self, "다운로드 완료", "VOD 다운로드가 완료되었습니다.")

    def onDownloadError(self, error_message):
        QMessageBox.critical(self, "다운로드 실패", f"VOD 다운로드 중 오류가 발생했습니다: {error_message}")

    def load_cookies(self):
        # 쿠키 파일의 경로를 지정합니다.
        cookie_file_path = os.path.join(os.path.dirname(__file__), '..', 'json', 'cookie.json')
        try:
            with open(cookie_file_path, 'r') as f:
                self.cookies = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError) as e:
            print(f"쿠키 파일 로드 중 오류 발생: {e}")
            self.cookies = {}
            
    async def updateVodInfo(self):
        vod_number = self.vodEdit.text()
        if not vod_number:
            return

        downloader = VODDownloader(None, None)
        try:
            vod_info = await downloader.getVodInfo(vod_number, self.cookies)
            if vod_info:
                live_open_date_str = vod_info.get('content', {}).get('liveOpenDate', 'N/A').split(" ")[0]
                duration_seconds = vod_info.get('content', {}).get('duration', 0)

                # 시작 시간을 liveOpenDate로 설정
                self.startTimeEdit.setText(live_open_date_str.replace('-', ':'))

                # 종료 시간을 liveOpenDate + duration으로 설정
                live_open_datetime = datetime.strptime(live_open_date_str, '%Y-%m-%d')
                end_datetime = live_open_datetime + timedelta(seconds=duration_seconds)
                end_time_str = end_datetime.strftime('%Y-%m-%d')
                self.endTimeEdit.setText(end_time_str.replace('-', ':'))
            else:
                QMessageBox.warning(self, "오류", "VOD 정보를 불러올 수 없습니다.")
        except Exception as e:
            QMessageBox.critical(self, "오류", f"VOD 정보 로드 중 오류 발생: {e}")

    def closeEvent(self, event):
        self.session.close()
        self.finished.emit()  # 창이 닫힐 때 finished 시그널 발생
        event.accept()

class VODDownloader:
    MAX_RETRIES = 3  
    RETRY_INTERVAL = 5  

    CHZZK_VOD_URI_API = "https://apis.naver.com/neonplayer/vodplay/v2/playback/{videoId}?key={inKey}"
    CHZZK_VOD_INFO_API = "https://api.chzzk.naver.com/service/v2/videos/{videoNo}"

    def __init__(self, quality, savePath):
        BASE_DIR = os.path.dirname(os.path.realpath(__file__))
        BASE_DIR = os.path.dirname(BASE_DIR)  
        self.FFMPEG_PATH = os.path.join(BASE_DIR, "dependent", "ffmpeg", "bin", "ffmpeg.exe").replace("\\", "/")
        self.FFPROBE_PATH = os.path.join(BASE_DIR, "dependent", "ffmpeg", "bin", "ffprobe.exe").replace("\\", "/")
        self.savePath = savePath
        self.quality = quality
        self.COOKIE_PATH = os.path.join(BASE_DIR, "json", "cookie.json").replace("\\", "/")


    def getAuthHeaders(self, cookies):
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3'
        }
        if cookies:
            headers['Cookie'] = '; '.join(f'{key}={value}' for key, value in cookies.items())
        return headers

    def getSessionCookies(self):
        if not os.path.exists(self.COOKIE_PATH):
            print(f"쿠키 파일을 찾을 수 없습니다: {self.COOKIE_PATH}")
            return None

        with open(self.COOKIE_PATH, 'r') as cookie_file:
            cookies = json.load(cookie_file)
        return cookies
    
    async def getVodInfo(self, vod_number, cookies):
        async with aiohttp.ClientSession(headers=self.getAuthHeaders(cookies)) as session:
            url = self.CHZZK_VOD_INFO_API.format(videoNo=vod_number)
            async with session.get(url) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    print(f"VOD 정보 가져오기 실패: {response.status}")
                    return None

    async def getFrameRate(self, videoUrl):
        ffprobeCmd = [
            self.FFPROBE_PATH,
            "-v", "error",
            "-select_streams", "v:0",
            "-show_entries", "stream=r_frame_rate",
            "-of", "default=noprint_wrappers=1:nokey=1",
            videoUrl
        ]

        try:
            result = await asyncio.to_thread(subprocess.run, ffprobeCmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
            rate = result.stdout.decode('utf-8').strip()
            num, den = map(int, rate.split('/'))
            return num / den
        except subprocess.CalledProcessError as e:
            print(f"프레임 레이트 가져오기 중 오류 발생: {e}")
            return 30  # 오류 발생 시 기본값으로 30을 반환

    async def getResolution(self, videoFile):
        ffprobeCmd = [
            self.FFPROBE_PATH,
            "-v", "error",
            "-select_streams", "v:0",
            "-show_entries", "stream=width,height",
            "-of", "csv=p=0",
            videoFile
        ]

        try:
            result = await asyncio.to_thread(subprocess.run, ffprobeCmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
            resolution = result.stdout.decode('utf-8').strip()
            width, height = map(int, resolution.split(','))
            return width, height
        except subprocess.CalledProcessError as e:
            print(f"해상도 가져오기 중 오류 발생: {e}")
            return None, None

    def sanitizeFilename(self, filename, maxLength=55):
        invalidChars = '<>:"/\\|?*'
        sanitized = ''.join(c if c not in invalidChars else '_' for c in filename)
        return sanitized[:maxLength]

    async def verifySegment(self, segmentFilename):
        try:
            ffprobeCmd = [
                self.FFPROBE_PATH,
                "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                segmentFilename
            ]
            result = await asyncio.to_thread(subprocess.run, ffprobeCmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
            duration = float(result.stdout.strip())
            if duration <= 0:
                print(f"세그먼트 파일 길이가 비정상적입니다: {segmentFilename}")
                return False
            
            ffprobeCmd = [
                self.FFPROBE_PATH,
                "-v", "error",
                "-select_streams", "v:0",
                "-show_entries", "stream=nb_frames",
                "-of", "default=noprint_wrappers=1:nokey=1",
                segmentFilename
            ]
            result = await asyncio.to_thread(subprocess.run, ffprobeCmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
            nb_frames = int(result.stdout.strip())
            if nb_frames <= 0:
                print(f"세그먼트 파일 프레임 수가 비정상적입니다: {segmentFilename}")
                return False

            ffprobeCmd = [
                self.FFPROBE_PATH,
                "-v", "error",
                "-select_streams", "a:0",
                "-show_entries", "stream=codec_name",
                "-of", "default=noprint_wrappers=1:nokey=1",
                segmentFilename
            ]
            result = await asyncio.to_thread(subprocess.run, ffprobeCmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
            if not result.stdout.strip():
                print(f"세그먼트 파일 오디오 스트림이 비정상적입니다: {segmentFilename}")
                return False

            return True

        except subprocess.CalledProcessError as e:
            print(f"세그먼트 검증 중 오류 발생: {e}")
            return False

    async def downloadSegment(self, videoUrl, savePath, segmentStart, segmentEnd, segmentIndex):
        if not os.path.exists(savePath):
            os.makedirs(savePath.replace("\\", "/"))

        segmentFilename = os.path.join(savePath, f"part{segmentIndex}.mp4").replace("\\", "/")

        if segmentEnd <= segmentStart:
            print(f"세그먼트 종료 시간({segmentEnd})이 세그먼트 시작 시간({segmentStart})보다 작거나 같습니다.")
            return None

        startTimeStr = self.secondsToHhmmss(segmentStart)
        durationStr = self.secondsToHhmmss(segmentEnd - segmentStart)

        ffmpegCmd = [
            self.FFMPEG_PATH.replace("\\", "/"),
            "-y",
            "-ss", startTimeStr,
            "-i", videoUrl,
            "-t", durationStr,
            "-c", "copy",
            segmentFilename
        ]

        print("Executing FFmpeg command for download:")
        print(" ".join(ffmpegCmd))
        print(f"Start time: {startTimeStr}, Duration: {durationStr}")

        try:
            await asyncio.to_thread(subprocess.run, ffmpegCmd, check=True)
            print(f"VOD 세그먼트 다운로드가 완료되었습니다: {segmentFilename}")
            if await self.verifySegment(segmentFilename):
                return segmentFilename
            else:
                print(f"세그먼트 검증 실패: {segmentFilename}")
                return None
        except subprocess.CalledProcessError as e:
            print(f"VOD 세그먼트 다운로드 중 오류 발생: {e}")
            return None

    async def mergeSegments(self, segmentFilenames, outputFilename, mergeMethod=0, quality=None):
        video_bitrate = None
        if self.quality == "1080p" or self.quality == "best":
            video_bitrate = "8000k"  # 1080p
        elif self.quality == "720p":
            video_bitrate = "5000k"  # 720p

        if mergeMethod == 0:  # 스트림 복사
            merge_list_path = os.path.join(os.path.dirname(segmentFilenames[0]), "merge_list.txt").replace("\\", "/")
            try:
                with open(merge_list_path, "w") as f:
                    for segmentFilename in segmentFilenames:
                        segmentFilename = segmentFilename.replace("\\", "/")
                        f.write(f"file '{segmentFilename}'\n")
                print(f"merge_list.txt 파일이 생성되었습니다: {merge_list_path}")
            except Exception as e:
                print(f"merge_list.txt 파일 생성 중 오류 발생: {e}")
                return

            ffmpegCmd = [
                self.FFMPEG_PATH.replace("\\", "/"), "-y",
                "-f", "concat",
                "-safe", "0",
                "-i", merge_list_path,
                "-c", "copy",
                "-fflags", "+genpts",
                "-vsync", "passthrough",
                outputFilename.replace("\\", "/")
            ]

        elif mergeMethod in [1, 2, 3, 4]:  # CPU 인코딩 및 GPU 가속 인코딩
            # 입력 파일들에 대한 명령어 생성
            ffmpegCmd = [self.FFMPEG_PATH.replace("\\", "/"), "-y"]
            for segmentFilename in segmentFilenames:
                ffmpegCmd.extend(["-i", segmentFilename.replace("\\", "/")])

            # 필터 복합명령어 생성
            filter_complex = ''.join([f"[{i}:v:0][{i}:a:0]" for i in range(len(segmentFilenames))])
            filter_complex += f"concat=n={len(segmentFilenames)}:v=1:a=1[v][a]"

            ffmpegCmd.extend([
                "-filter_complex", filter_complex,
                "-map", "[v]", "-map", "[a]"
            ])

            # 각 인코딩 방식에 따른 명령어 추가
            if mergeMethod == 1:  # CPU 인코딩
                ffmpegCmd.extend([
                    "-c:v", "libx264",
                    "-b:v", video_bitrate,
                    "-preset", "veryfast", 
                    "-c:a", "aac",
                    "-b:a", "192k"
                ])
            elif mergeMethod == 2:  # Intel GPU 가속
                ffmpegCmd.extend([
                    "-c:v", "h264_qsv",
                    "-b:v", video_bitrate,
                    "-preset", "veryfast",  
                    "-c:a", "aac",
                    "-b:a", "192k"
                ])
            elif mergeMethod == 3:  # AMD GPU 가속
                ffmpegCmd.extend([
                    "-c:v", "h264_amf",
                    "-b:v", video_bitrate,
                    "-quality", "fast",  
                    "-c:a", "aac",
                    "-b:a", "192k"
                ])
            elif mergeMethod == 4:  # NVIDIA GPU 가속
                ffmpegCmd.extend([
                    "-c:v", "h264_nvenc",
                    "-b:v", video_bitrate,
                    "-preset", "p2", 
                    "-c:a", "aac",
                    "-b:a", "192k"
                ])

            # 출력 파일 경로 추가
            ffmpegCmd.append(outputFilename.replace("\\", "/"))

        print("Executing FFmpeg command for merging:")
        print(" ".join(ffmpegCmd))

        try:
            result = await asyncio.to_thread(subprocess.run, ffmpegCmd, check=True, stderr=subprocess.PIPE, stdout=subprocess.PIPE)
            print(f"VOD 세그먼트 병합이 완료되었습니다: {outputFilename}")
            print(f"FFmpeg output: {result.stdout.decode()}")
            print(f"FFmpeg errors: {result.stderr.decode()}")
        except subprocess.CalledProcessError as e:
            print(f"VOD 세그먼트 병합 중 오류 발생: {e}\nstderr: {e.stderr.decode()}\nstdout: {e.stdout.decode()}")

        # 세그먼트 파일 삭제
        for segmentFilename in segmentFilenames:
            if os.path.exists(segmentFilename):
                print(f"Deleting segment file: {segmentFilename}")
                os.remove(segmentFilename)

        # merge_list.txt 파일 삭제 (스트림 복사 또는 CPU 인코딩일 때만 해당)
        if mergeMethod == 0 and os.path.exists(merge_list_path):
            print(f"Deleting merge list file: {merge_list_path}")
            os.remove(merge_list_path)

        # 임시 폴더 삭제
        temp_folder = os.path.dirname(segmentFilenames[0])
        if os.path.exists(temp_folder):
            print(f"Deleting temporary folder: {temp_folder}")
            os.rmdir(temp_folder)



    async def authenticateAndDownload(self, vodNumber, savePath, quality="best", startTime=None, endTime=None, segmentOption=1, mergeMethod=0):
        # 여기에서 쿠키 정보를 가져옵니다.
        sessionCookies = self.getSessionCookies()

        # 쿠키 정보가 없으면 예외를 발생시킵니다.
        if not sessionCookies:
            raise Exception("쿠키 정보를 가져오지 못했습니다.")

        # headers를 설정할 때 쿠키 정보를 사용합니다.
        headers = self.getAuthHeaders(sessionCookies)

        # aiohttp.ClientSession 객체를 생성할 때 headers를 전달합니다.
        async with aiohttp.ClientSession(headers=headers) as session:
            retries = 0
            while retries < self.MAX_RETRIES:
                try:
                    print(f"VOD 정보 가져오기 시도: {vodNumber}")
                    apiUrl = self.CHZZK_VOD_INFO_API.format(videoNo=vodNumber)
                    async with session.get(apiUrl) as response:
                        if response.status != 200:
                            print(f"VOD 정보 가져오기 실패: {response.status} - {response.reason}")
                            raise Exception(f"VOD 정보를 가져오는데 실패했습니다. 상태 코드: {response.status}, 이유: {response.reason}")

                        try:
                            vodInfo = await response.json()
                        except aiohttp.ContentTypeError as e:
                            print(f"잘못된 컨텐츠 타입으로 JSON 디코딩 실패: {e}")
                            print(f"응답 텍스트: {await response.text()}")
                            raise Exception(f"응답을 JSON으로 디코딩하는데 실패했습니다: {e}")

                    vodInfoContent = vodInfo.get('content', {})
                    if not vodInfoContent or 'videoId' not in vodInfoContent:
                        print("VOD 정보를 가져오는데 실패했습니다.")
                        return

                    vodId = vodInfoContent['videoId']
                    vodInKey = vodInfoContent['inKey']
                    videoTitle = vodInfo['content'].get('videoTitle', 'unknown_title')
                    channelName = vodInfo['content']['channel'].get('channelName', 'unknown_channel')
                    broadcastDate = vodInfo.get('content', {}).get('liveOpenDate', 'unknown_date').split(" ")[0]

                    streamLink, videoRepresentationId, resolution = await self.getDashStreamLink(vodId, vodInKey, quality)
                    if not streamLink:
                        print("스트림링크에서 DASHstream를 가져오는데 실패했습니다.")
                        return

                    frameRate = await self.getFrameRate(streamLink)
                    quality = f"{resolution}p" if quality == "best" else quality

                    print(f"highest_quality: {quality}, frame_rate: {frameRate}")

                    # 임시 파일명을 생성하지 않고 바로 sanitize된 videoTitle을 사용합니다.
                    temp_savePath = os.path.join(savePath, self.sanitizeFilename(videoTitle)).replace("\\", "/")

                    # 임시 저장 경로 생성
                    if not os.path.exists(temp_savePath):
                        os.makedirs(temp_savePath)

                    if segmentOption == 1:
                        segmentStart = self.timeToSeconds(startTime) if startTime else 0
                        segmentEnd = self.timeToSeconds(endTime) if endTime else await self.getVideoDuration(streamLink)

                        segmentFilename = await self.downloadSegment(streamLink, temp_savePath, segmentStart, segmentEnd, 0)
                        if segmentFilename:
                            if startTime and endTime:
                                finalFilename = f"[{broadcastDate}] {self.sanitizeFilename(channelName)} {self.sanitizeFilename(videoTitle)} {quality}{frameRate:.0f}_{startTime.replace(':', '')}_{endTime.replace(':', '')}.mp4"
                            else:
                                finalFilename = f"[{broadcastDate}] {self.sanitizeFilename(channelName)} {self.sanitizeFilename(videoTitle)} {quality}{frameRate:.0f}.mp4"
                            finalSavePath = os.path.join(savePath, finalFilename).replace("\\", "/")
                            os.rename(segmentFilename, finalSavePath)
                    else:
                        duration = await self.getVideoDuration(streamLink)
                        segments = self.calculateSegments(duration, startTime, endTime, segmentOption)
                        downloadedSegments = []

                        tasks = []
                        for index, (segmentStart, segmentEnd) in enumerate(segments):
                            tasks.append(self.downloadSegment(streamLink, temp_savePath, segmentStart, segmentEnd, index))

                        await asyncio.gather(*tasks)

                        if startTime and endTime:
                            finalFilename = f"[{broadcastDate}] {self.sanitizeFilename(channelName)} {self.sanitizeFilename(videoTitle)} {quality}{frameRate:.0f}_{startTime.replace(':', '')}_{endTime.replace(':', '')}.mp4"
                        else:
                            finalFilename = f"[{broadcastDate}] {self.sanitizeFilename(channelName)} {self.sanitizeFilename(videoTitle)} {quality}{frameRate:.0f}.mp4"
                        finalSavePath = os.path.join(savePath, finalFilename)
                        try:
                            await self.mergeSegments([f"{temp_savePath}/part{index}.mp4" for index in range(len(segments))], finalSavePath, mergeMethod, self.quality)
                        except Exception as e:
                            print(f"VOD 병합 중 오류 발생: {e}")
                            raise
                        finally:
                          print("VOD 다운로드가 완료되었습니다.")
                        break
                        
                retries += 1
                print(f"재시도 중 ({retries}/{self.MAX_RETRIES})...")
                await asyncio.sleep(self.RETRY_INTERVAL)

                if retries >= self.MAX_RETRIES:
                    print("재시도 횟수 초과. 다운로드를 중단합니다.")
                    break
    else:
        print("세션 쿠키를 가져오는데 실패했습니다.")

async def getDashStreamLink(self, videoId, inKey, preferredQuality):
    videoUrl = self.CHZZK_VOD_URI_API.format(videoId=videoId, inKey=inKey)
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(videoUrl, headers={"Accept": "application/dash+xml"}) as response:
                text = await response.text()
                root = ET.fromstring(text)
                ns = {"mpd": "urn:mpeg:dash:schema:mpd:2011"}

                self.representationElements = root.findall(".//mpd:Representation", namespaces=ns)
                
                bestRepresentation = None
                highestHeight = 0
                for rep in self.representationElements:
                    height = rep.get("height")
                    if height:
                        if preferredQuality == "best":
                            if int(height) > highestHeight:
                                highestHeight = int(height)
                                bestRepresentation = rep
                        else:
                            if int(height) == int(preferredQuality.replace('p', '')):
                                bestRepresentation = rep
                                break

                if bestRepresentation is None:
                    print(f"{preferredQuality}에 맞는 Representation을 찾을 수 없습니다.")
                    return None, None

                representationId = bestRepresentation.get("id")
                baseUrl = bestRepresentation.find("mpd:BaseURL", namespaces=ns).text

                # base URL, representation ID 및 높이(해상도) 반환
                return baseUrl, representationId, highestHeight if preferredQuality == "best" else int(preferredQuality.replace('p', ''))

        except aiohttp.ClientError as e:
            print("DASHstream XML 로드에 실패했습니다:", str(e))
            return None, None, None
        except ET.ParseError as e:
            print("DASHstream XML 파싱에 실패했습니다:", str(e))
            return None, None, None

async def getVideoDuration(self, videoUrl):
    ffprobeCmd = [
        self.FFPROBE_PATH,
        "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        videoUrl
    ]

    try:
        result = await asyncio.to_thread(subprocess.run, ffprobeCmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
        return float(result.stdout.strip())
    except subprocess.CalledProcessError as e:
        print(f"비디오 길이 가져오기 중 오류 발생: {e}")
        return 0

def timeToSeconds(self, timeStr):
    if not timeStr:
        return 0
    h, m, s = map(int, timeStr.split(':'))
    return h * 3600 + m * 60 + s

def secondsToHhmmss(self, seconds):
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60
    return f"{h:02}:{m:02}:{s:06.3f}"

def generateRandomFilename(self):
    while True:
        random_name = ''.join(random.choices('0123456789', k=6))
        save_path = os.path.join(self.savePath, random_name).replace("\\", "/")
        if not os.path.exists(save_path):
            return random_name


def calculateSegments(self, duration, startTime=None, endTime=None, segmentOption=1):
    startTimeSeconds = self.timeToSeconds(startTime) if startTime else 0
    endTimeSeconds = self.timeToSeconds(endTime) if endTime else duration

    if endTimeSeconds - startTimeSeconds > 180:
        if segmentOption == 1:
            segmentLength = endTimeSeconds - startTimeSeconds
        else:
            segmentLength = (endTimeSeconds - startTimeSeconds) / segmentOption
    else:
        segmentLength = endTimeSeconds - startTimeSeconds

    segments = []
    currentStart = startTimeSeconds
    while currentStart < endTimeSeconds:
        currentEnd = min(currentStart + segmentLength, endTimeSeconds)
        if currentEnd > currentStart:
            segments.append((currentStart, currentEnd))
        currentStart = currentEnd

    if segments and (segments[-1][1] - segments[-1][0] < 1):
        lastSegment = segments.pop()
        if segments:
            previousSegment = segments.pop()
            segments.append((previousSegment[0], lastSegment[1]))

    return segments

if name == "main":
    app = QApplication(sys.argv)
    window = VODDownloaderApp()
    window.show()
    sys.exit(app.exec_())