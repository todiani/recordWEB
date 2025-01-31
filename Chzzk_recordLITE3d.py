import importlib
import subprocess
import os
import time
import json
import sys
import asyncio
import re
import shutil
from datetime import datetime

# 필요한 모듈을 설치하는 함수
def install_missing_modules():
    missing_modules = ["httpx", "backoff"]
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

install_missing_modules()

import httpx
import backoff

# 타이틀 출력문구
print("내맘대로 Chzzk 자동녹화 LITE3d_1225")

# 채널 정보 정의
channels = [
    {"id": "45e71a76e949e16a34764deb962f9d9f", "name": "아야츠노 유니", "output_dir": "chzzk"},
    {"id": "b044e3a3b9259246bc92e863e7d3f3b8", "name": "시라유키 히나", "output_dir": "chzzk"},
    {"id": "4515b179f86b67b4981e16190817c580", "name": "네네코 마시로", "output_dir": "chzzk"},
    {"id": "4325b1d5bbc321fad3042306646e2e50", "name": "아카네 리제", "output_dir": "chzzk"},
    {"id": "a6c4ddb09cdb160478996007bff35296", "name": "아라하시 타비", "output_dir": "chzzk"},
    {"id": "64d76089fba26b180d9c9e48a32600d9", "name": "텐코 시부키", "output_dir": "chzzk"},
    {"id": "516937b5f85cbf2249ce31b0ad046b0f", "name": "아오쿠모 린", "output_dir": "chzzk"},
    {"id": "4d812b586ff63f8a2946e64fa860bbf5", "name": "하나코 나나", "output_dir": "chzzk"},
    {"id": "8fd39bb8de623317de90654718638b10", "name": "유즈하 리코", "output_dir": "chzzk"},
    {"id": "cfaee70de33bc9ee2c0a486dcfcff0f4", "name": "이브", "output_dir": "chzzk"}
]

# 녹화파일 저장위치(output_dir) 설정(둘 중 원하는 방법으로 선택)
# (1) 역슬래시 사용시 두번넣어야함    "output_dir": "D:\\chzzk\\kanna"
# (2) 슬래시를 사용할 떄는 한번만     "output_dir": "D:/chzzk/kanna"

# 사용자 설정 옵션
select_plugin = "basic"  # 3가지 플러그인 중 선택 : basic / timemachine / timemachine_plus
timemachine_time_shift = 600  # 타임머신 시간 (초), 최대 600초까지 설정 가능
record_quality = "best"  # 480p / 720p / 1080p / best 중 선택
file_extension = ".ts"   # .ts / .mp4 중 선택
autoPostProcessing = True  # 녹화 완료 후 자동 후처리(원본 스트림복사/열화 인코딩) 기능 (True=사용 / False=사용안함)
deleteAfterPostProcessing = True  # 후처리 후 원본 파일 삭제 (True=사용 / False=사용안함)
removeFixedPrefix = True  # 후처리 후 fixed_ 접두사 제거 (True=사용 / False=사용안함)
moveAfterProcessingEnabled = False  # 후처리 최종완료 후 파일이동 기능 사용 (True=사용 / False=사용안함)
moveAfterProcessing = "D:/test"  # 후처리 최종완료 후 이동할 경로(예시:"D:/test")
dscMinimize = False  # 후처리 명령창이 새창으로 나올 때 최소화 모드로 실행 (True=사용 / False=사용안함)
recheckInterval = 60  # 방송 재탐색 주기(초)
filenamePattern = "[{start_time}] {channel_name} {safe_live_title} {record_quality}{frame_rate}{file_extension}"  # 파일명 생성 규칙
autoStopInterval = 0  # 분할녹화 시간 (초), 0 으로 설정시 분할 없이 연속녹화(예시: 1시간 입력방법 : 3600 혹은 60 * 60)


# 플러그인 선택 참조
# basic : 기본 치지직 녹화 플러그인
# timemachine : 녹화시작 시간 기준 최대 10분전 영상부터 녹화가 가능한 플러그인 
# timemachine_plus : 타임머신 기능 + 8시간 30분 이상 연속녹화 가능한 플러그인

# 타임머신 시간조정 = 최대 10분(600초) 이내에서 사용자가 원하는 시점부터 녹화되도록 지정할 수 있음

# 파일명 생성 규칙 예제
# {recording_time} = 녹화시작시간(형식 : 240801_183507)
# {start_time} = 치지직 방송시작날짜(형식 : 2024-08-01)
# {safe_live_title} = 방송제목 
# {channel_name} = 스트리머 채널명
# {record_quality} = 녹화 해상도
# {frame_rate} = 녹화 프레임
# {file_extension} = 확장자

# 기본값 예시 
# "[{recording_time}] {channel_name} {safe_live_title} {record_quality}{frame_rate}{file_extension}"
# "[240528_180530] 시라유키 히나 갑자기 싱크룸 하기!!!!! (W. 시로 타비) 1080p60.ts"

# 기본값 예시2 
# "[{start_time}] {channel_name} {safe_live_title} {record_quality}{frame_rate}{file_extension}"
# "[2024-05-28] 시라유키 히나 갑자기 싱크룸 하기!!!!! (W. 시로 타비) 1080p60.ts"


# 사용자 설정 옵션
stream_copy = True  # True = 후처리를 스트림복사로 설정, False = 열화 인코딩으로 설정.
video_codec = 'libx264'  # 사용 가능한 값: 'libx264', 'h264_qsv', 'h264_nvenc', 'h264_amf', 'copy'
preset = 'fast'  # 프리셋 설정은 아래 코덱별 목록 참조
use_bitrate_mode = True  # True: 비트레이트 모드 사용, False: 퀄리티 모드 사용
video_quality = 33  # 비디오 퀄리티 모드 사용시 설정, 코덱에 따라 다름
video_bitrate = '1000k'  # 비디오 비트레이트 모드 사용시 설정 (kbps)
audio_codec = 'aac'  # 오디오 코덱 설정: 'aac', 'mp3'
audio_bitrate = '128k'  # 오디오 비트레이트 설정: '64k', '96k', '128k', '160k', '192k', '224k', '256k', '320k'


# 인코딩 명령어 구성
# 스트림복사와 열화인코딩 : 원본 그대로 유지 = 스트림복사 / 용량절약을 위한 열화 인코딩 중 선택
# 하드웨어 가속(libx264: CPU만 사용 / h264_qsv: 인텔 가속 / h264_nvenc: 엔비디아 가속 / h264_amf: AMD 가속)
# 프리셋 설정(코덱별 사용가능 프리셋 참조)
# 비디오 퀄리티 설정(23: 원본대비 약간의 열화, 26~28: 약간의 용량절약, 32~35: 낮은 품질, 용량절약, ※ 원본 해상도/비트레이트/코덱에 따라 값이 달라짐)
# 오디오 코덱 설정(mp3 / aac)
# 오디오 비트레이트 설정(64 / 96 / 128 / 160 / 192 / 224 /256 / 320kbps)


# h264 코덱별 사용가능한 프리셋 목록 :
#  'libx264': ['ultrafast', 'superfast', 'veryfast', 'faster', 'fast', 'medium', 'slow', 'slower', 'veryslow', 'placebo'],
#  'h264_qsv': ['veryfast', 'faster', 'fast', 'balanced', 'slow'],
#  'h264_nvenc': ['fast', 'medium', 'slow', 'hq', 'bd', 'll', 'llhq', 'llhp', 'lossless', 'losslesshp'],
#  'h264_amf': ['balanced', 'fast', 'quality']



# ffmpeg 경로를 가져오는 함수
def get_ffmpeg_path():
    current_dir = os.path.dirname(__file__)  # 현재 스크립트의 위치
    ffmpeg_path = os.path.join(current_dir, 'dependent', 'ffmpeg', 'bin', 'ffmpeg.exe')  # ffmpeg 실행 파일 위치
    return os.path.abspath(ffmpeg_path)  # 절대 경로 반환

# streamlink 경로를 가져오는 함수
def get_streamlink_path():
    current_dir = os.path.dirname(__file__)  # 현재 스크립트의 위치
    streamlink_path = os.path.join(current_dir, 'dependent', 'streamlink', 'bin', 'streamlink.exe')  # streamlink 실행 파일 위치
    return os.path.abspath(streamlink_path)  # 절대 경로 반환

# 쿠키값 불러오기 함수
def get_session_cookies():
    base_directory = os.path.dirname(os.path.abspath(__file__))
    json_directory = os.path.join(base_directory, 'json')
    cookie_file_path = os.path.join(json_directory, 'cookie.json')
    try:
        with open(cookie_file_path, 'r') as cookie_file:
            cookies = json.load(cookie_file)
        return cookies
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"쿠키 파일을 읽는 중 오류 발생: {e}")
        return {}

# 헤더에 세션 정보를 추가하는 함수
def get_auth_headers(cookies):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)',
        'Cookie': f'NID_AUT={cookies.get("NID_AUT", "")}; NID_SES={cookies.get("NID_SES", "")}'
    }
    return headers

# 메타데이터 정보를 가져오는 함수
@backoff.on_exception(backoff.expo, httpx.HTTPError, max_tries=5, giveup=lambda e: e.response.status_code < 500)
async def get_live_metadata(channel, cookies):
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            headers = get_auth_headers(cookies)
            url = f"https://api.chzzk.naver.com/service/v3/channels/{channel['id']}/live-detail"
            response = await client.get(url, headers=headers)
            response.raise_for_status()
            metadata_content = response.json().get("content")

            if not metadata_content:
                print(f"{channel['name']} 채널의 메타데이터가 없습니다 (content가 None).")
                return None

            # 사용자 설정 옵션에서 해당 채널의 quality 값을 가져옴
            print(f"녹화 품질 설정: {record_quality}")

            # API 응답에서 가장 적절한 해상도와 프레임 레이트 선택
            frame_rate = "알 수 없는 프레임 레이트"
            record_quality_result = "알 수 없는 품질"
            encoding_tracks = json.loads(metadata_content["livePlaybackJson"])["media"]
            max_resolution = 0

            for track in encoding_tracks:
                for encoding in track["encodingTrack"]:
                    resolution = int(encoding["videoWidth"]) * int(encoding["videoHeight"])
                    if (record_quality == "best" and resolution > max_resolution) or (record_quality != "best" and encoding["encodingTrackId"] == record_quality):
                        max_resolution = resolution
                        record_quality_result = encoding["encodingTrackId"]
                        frame_rate = str(int(float(encoding["videoFrameRate"])))

            print(f"녹화 품질: {record_quality_result}, 프레임 레이트: {frame_rate}")

            metadata_content["record_quality"] = record_quality_result
            metadata_content["frame_rate"] = frame_rate

            # 방송 시작 시간 포맷을 변환
            open_date = metadata_content["openDate"]
            start_time = datetime.strptime(open_date, "%Y-%m-%d %H:%M:%S").strftime("%Y-%m-%d")
            metadata_content["start_time"] = start_time

            return metadata_content
    except httpx.HTTPStatusError as e:
        print(f"HTTP 오류 발생: {e.response.status_code}")
    except httpx.RequestError as e:
        print(f"요청 오류 발생: {e.request.url}")
    return None



# 파일명 중복 방지 함수
def get_unique_filename(output_dir, filename, add_suffix=True):
    base, ext = os.path.splitext(filename)
    counter = 1
    unique_filename = filename if not add_suffix else f"{base} ({counter}){ext}"

    while os.path.exists(os.path.join(output_dir, unique_filename)):
        counter += 1
        unique_filename = f"{base} ({counter}){ext}"

    return unique_filename


# 녹화 명령을 생성하는 함수
def buildCommand(channel, metadata, cookies, recording_time):
    script_dir = os.path.dirname(os.path.realpath(__file__))
    output_dir_abs_path = os.path.join(script_dir, channel['output_dir'])
    plugin_dir = os.path.join(script_dir, 'dependent', 'plugin', select_plugin)
    stream_url = f"https://chzzk.naver.com/live/{channel['id']}"
    cookie_value = f"NID_SES={cookies['NID_SES']}; NID_AUT={cookies['NID_AUT']}" if cookies else ""
    ffmpeg_path = get_ffmpeg_path()
    streamlink_path = get_streamlink_path()


    if metadata:
        live_title = metadata["liveTitle"].strip().replace('\n', '')
        safe_live_title = re.sub(r'[\\/*?:"<>|+]', '_', live_title)[:55]
        start_time = metadata.get('start_time', 'UnknownTime')
        filename = filenamePattern.format(
			recording_time=recording_time, 
            start_time=start_time,
            safe_live_title=safe_live_title,
            channel_name=channel['name'],
            record_quality=metadata.get('record_quality', 'Unknown Quality'),
            frame_rate=metadata.get('frame_rate', 'Unknown Frame Rate'),
            file_extension=file_extension
        )
    else:
        filename = f"[{recording_time}] {channel['name']}{file_extension}"
    
    unique_filename = get_unique_filename(output_dir_abs_path, filename, add_suffix=False)
    output_path = os.path.join(output_dir_abs_path, unique_filename)

    channel['output_path'] = output_path

    cmd_list = [
        streamlink_path, "--ffmpeg-copyts",
        "--plugin-dirs", plugin_dir,
        stream_url, record_quality,
        "-o", output_path,
        "--ffmpeg-ffmpeg", ffmpeg_path
    ]

    if cookie_value:
        cmd_list.extend(["--http-header", f"Cookie={cookie_value}"])

    cmd_list.extend([
        "--hls-live-restart",
        "--stream-segment-timeout", "5",
        "--stream-segment-attempts", "5"
    ])

    # 타임머신/타임머신 플러스 플러그인 시간 설정
    if select_plugin in ["timemachine", "timemachine_plus"]:
        cmd_list.extend(["--hls-start-offset", str(timemachine_time_shift)])

    return cmd_list


# 녹화 명령을 생성 및 실행하는 함수
async def start_recording(channel, cookies):
    while True:
        metadata = await get_live_metadata(channel, cookies)
        if metadata is None:
            print(f"{channel['name']} 채널의 메타데이터를 가져오는 데 실패했습니다. 재시도합니다.")
            await asyncio.sleep(recheckInterval)  # 방송 재탐색 주기(초)
            continue
        
        if metadata.get("status") == "OPEN":
            print(f"{channel['name']} 채널은 방송중입니다. 녹화를 시작합니다.")
            # 녹화 시작 시간 가져오기
            recording_time = datetime.now().strftime("%y%m%d_%H%M%S")
            cmd = buildCommand(channel, metadata, cookies, recording_time)
            try:
                proc = await asyncio.create_subprocess_exec(*cmd)
                
                if autoStopInterval > 0:
                    await asyncio.wait_for(proc.wait(), timeout=autoStopInterval)
                else:
                    await proc.wait()

                if proc.returncode is None:
                    proc.terminate()
                    await proc.wait()
                    print(f"{channel['name']} 채널 녹화가 {autoStopInterval}초 후 자동으로 종료되었습니다.")
                else:
                    print(f"{channel['name']} 채널 녹화가 정상 종료되었습니다.")
            except asyncio.TimeoutError:
                proc.terminate()
                await proc.wait()
                print(f"{channel['name']} 채널 녹화가 {autoStopInterval}초 후 자동으로 종료되었습니다.")
            except Exception as e:
                print(f"{channel['name']} 채널 녹화 중 오류 발생: {e}")

            if autoPostProcessing:
                asyncio.create_task(copy_stream(channel)) 
        else:
            print(f"{channel['name']} 채널은 방송중이 아닙니다.")
            await asyncio.sleep(recheckInterval)  # 방송 재탐색 주기(초)



# 녹화 종료 후 자동 후처리 로직
async def copy_stream(channel):
    input_path = channel['output_path']
    output_path = os.path.join(os.path.dirname(input_path), f"fixed_{os.path.basename(input_path)}")
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, copy_specific_file, input_path, output_path, deleteAfterPostProcessing, removeFixedPrefix, dscMinimize)
    print(f"{channel['name']}의 스트림이 {input_path}에서 {output_path}로 복사되었습니다.")

    # 원본 파일 삭제 및 fixed_ 접두사 제거 기능
    await handle_file_operations(input_path, output_path, deleteAfterPostProcessing, removeFixedPrefix)


# 녹화파일을 인코딩하는 함수
def copy_specific_file(input_path, output_path, del_after_dsc, removeFixedPrefix, minimize=False):
    ffmpeg_path = get_ffmpeg_path()  # ffmpeg 경로 가져오기

    # 인코딩 또는 스트림복사 명령어 구성
    cmd = [
        ffmpeg_path,
        '-i', input_path,
        '-y'  # 기존 파일 덮어쓰기
    ]

    if stream_copy:
        # 스트림 복사 모드
        cmd.extend(['-c:v', 'copy', '-c:a', 'copy'])
    else:
        # 열화 인코딩 모드
        cmd.extend(['-preset', preset])

        if use_bitrate_mode:
            # 비트레이트 모드
            cmd.extend(['-b:v', video_bitrate, '-c:a', audio_codec, '-b:a', audio_bitrate])
        else:
            # 퀄리티 모드
            if video_codec == 'h264_qsv':
                cmd.extend(['-c:v', 'h264_qsv', '-global_quality', str(video_quality), '-look_ahead', '1'])
            elif video_codec == 'h264_nvenc':  
                cmd.extend(['-c:v', 'h264_nvenc', '-cq', str(video_quality)])
            elif video_codec == 'h264_amf':  
                cmd.extend(['-c:v', 'h264_amf', '-rc', 'qvbr', '-qvbr_quality_level', str(video_quality)])
            else:
                cmd.extend(['-c:v', 'libx264', '-crf', str(video_quality)])

        # 오디오 코덱 및 비트레이트 설정
        cmd.extend(['-c:a', audio_codec, '-b:a', audio_bitrate])

    cmd.append(output_path)

    try:
        print(f"[디버그] 명령어 실행: {' '.join(cmd)}")
        startupinfo = None
        if minimize:
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = 2  # 2는 SW_MINIMIZE

        process = subprocess.Popen(cmd, startupinfo=startupinfo, creationflags=subprocess.CREATE_NEW_CONSOLE)
        process.wait()  # 프로세스가 종료될 때까지 대기

        if process.returncode != 0:  # 프로세스 종료 코드 검사
            raise subprocess.CalledProcessError(process.returncode, cmd)
    
        print(f"{input_path}의 스트림이 {output_path}로 복사 또는 인코딩되었습니다.")

    except subprocess.CalledProcessError as e:
        print(f"{input_path} 파일의 스트림 복사 또는 인코딩이 강제로 종료되었습니다.")
    except Exception as e:
        print(f"{input_path} 파일의 스트림 복사 또는 인코딩 중 예상치 못한 오류가 발생했습니다. 오류: {e}")




# 파일 작업을 처리하는 함수
async def handle_file_operations(input_path, output_path, deleteAfterPostProcessing, removeFixedPrefix):
    if deleteAfterPostProcessing:
        try:
            await asyncio.sleep(5)  # 5초 딜레이
            os.remove(input_path)
            print(f"원본 파일 {input_path}가 삭제되었습니다.")
        except OSError as e:
            print(f"파일 {input_path}를 삭제하는 중 오류 발생: {e}")

    if removeFixedPrefix:
        try:
            await asyncio.sleep(5)  # 5초 딜레이
            final_output_path = os.path.join(os.path.dirname(output_path), os.path.basename(output_path).replace("fixed_", ""))
            os.rename(output_path, final_output_path)
            print(f"{output_path}가 {final_output_path}로 이름이 변경되었습니다.")
            output_path = final_output_path  
        except OSError as e:
            print(f"파일 {output_path}를 {final_output_path}로 이름 변경 중 오류 발생: {e}")

    if moveAfterProcessingEnabled:
        await asyncio.sleep(5)  # 5초 딜레이
        print(f"[디버그] 파일 이동 경로: {moveAfterProcessing}")
        move_file_to_directory(output_path, moveAfterProcessing)


# 후처리 후 파일 이동 함수
def move_file_to_directory(file_path, destination_directory):
    try:
        print(f"[디버그] 이동할 파일: {file_path}")
        print(f"[디버그] 이동할 경로: {destination_directory}")
        if not os.path.exists(destination_directory):
            os.makedirs(destination_directory)
        destination_path = os.path.join(destination_directory, os.path.basename(file_path))
        shutil.move(file_path, destination_path)
        print(f"파일 {file_path}가 {destination_path}로 이동되었습니다.")
    except Exception as e:
        print(f"파일 {file_path}를 {destination_directory}로 이동하는 중 오류 발생: {e}")


# 메인 함수
async def main():
    cookies = get_session_cookies()
    tasks = [start_recording(channel, cookies) for channel in channels]
    await asyncio.gather(*tasks)

if __name__ == "__main__":
    asyncio.run(main())