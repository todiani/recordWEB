import json
import os
import shutil
import secrets
import asyncio 
import threading
from datetime import datetime


from module.path_config import base_directory, CONFIG_PATH, CHANNELS_PATH, COOKIE_PATH, yCOOKIE_PATH, LOGIN_PATH

class RecorderManager:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(RecorderManager, cls).__new__(cls)
            cls._instance.__initialized = False
        return cls._instance

    def __init__(self):
        if self.__initialized:
            return
        self.recording_status = {}
        self.recording_filenames = {}
        self.reserved_recording = {}
        self.recording_start_times = {}
        self.recording_processes = {}
        self.stop_requested_channels = set()
        self.processed_channels = set()
        self.sessions = {}
        self.lock = threading.RLock()
        self.chat_processes = {}
        self.chat_log_paths = {}
        self.chat_status = {}
        self.__initialized = True

    def set_recording_status(self, channel_id, status):
        with self.lock:
            self.recording_status[channel_id] = status

    def get_recording_status(self, channel_id):
        with self.lock:
            return self.recording_status.get(channel_id, False)

    def set_recording_filename(self, channel_id, filename):
        with self.lock:
            self.recording_filenames[channel_id] = filename

    def get_recording_filename(self, channel_id):
        with self.lock:
            return self.recording_filenames.get(channel_id)

    def set_reserved_recording(self, channel_id, status):
        with self.lock:
            self.reserved_recording[channel_id] = status

    def remove_recording_filename(self, channel_id):
        with self.lock:
            self.recording_filenames.pop(channel_id, None)

    def get_reserved_recording(self, channel_id):
        with self.lock:
            return self.reserved_recording.get(channel_id, False)

    def set_recording_start_time(self, channel_id):
        with self.lock:
            self.recording_start_times[channel_id] = datetime.now().strftime("%y%m%d_%H%M%S")

    def get_recording_start_time(self, channel_id):
        with self.lock:
            return self.recording_start_times.get(channel_id)

    def remove_recording_start_time(self, channel_id):
        with self.lock:
            self.recording_start_times.pop(channel_id, None)

    # 녹화 경과 시간 계산 함수 (동기)
    def get_recording_duration(self, channel_id):
        with self.lock:
            start_time_str = self.recording_start_times.get(channel_id)
        if start_time_str:
            try:
                start_time = datetime.strptime(start_time_str, "%y%m%d_%H%M%S")
                now = datetime.now()
                elapsed_time = (now - start_time).total_seconds()
                hours, remainder = divmod(int(elapsed_time), 3600)
                minutes, seconds = divmod(remainder, 60)
                return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
            except ValueError:
                print(f"[ERROR] 잘못된 시간 형식: {start_time_str}")
                return "00:00:00"
        return "00:00:00"

    def set_recording_process(self, channel_id, process):
        with self.lock:
            self.recording_processes[channel_id] = process

    def get_recording_process(self, channel_id):
        with self.lock:
            return self.recording_processes.get(channel_id)

    def remove_recording_process(self, channel_id):
        with self.lock:
            self.recording_processes.pop(channel_id, None)

    def add_stop_requested_channel(self, channel_id):
        with self.lock:
            self.stop_requested_channels.add(channel_id)

    def remove_stop_requested_channel(self, channel_id):
        with self.lock:
            self.stop_requested_channels.discard(channel_id)

    def is_stop_requested(self, channel_id):
        with self.lock:
            return channel_id in self.stop_requested_channels

    def add_processed_channel(self, channel_id):
        with self.lock:
            self.processed_channels.add(channel_id)
            print(f"[DEBUG] 플래그 추가: {channel_id} 채널이 후처리됨으로 설정되었습니다.")

    def remove_processed_channel(self, channel_id):
        with self.lock:
            self.processed_channels.discard(channel_id)
            print(f"[DEBUG] 플래그 제거: {channel_id} 채널의 후처리 플래그가 제거되었습니다.")

    def is_channel_processed(self, channel_id):
        with self.lock:
            return channel_id in self.processed_channels
        
    def set_chat_status(self, channel_id, status):
         with self.lock:
            self.chat_status[channel_id] = status
    
    def get_chat_status(self, channel_id):
         with self.lock:
            return self.chat_status.get(channel_id, False)
    
    def set_chat_process(self, channel_id, process):
        with self.lock:
            self.chat_processes[channel_id] = process

    def get_chat_process(self, channel_id):
        with self.lock:
            return self.chat_processes.get(channel_id)

    def remove_chat_process(self, channel_id):
        with self.lock:
            self.chat_processes.pop(channel_id, None)

    def set_chat_log_path(self, channel_id, log_path):
         with self.lock:
            self.chat_log_paths[channel_id] = log_path

    def get_chat_log_path(self, channel_id):
        with self.lock:
            return self.chat_log_paths.get(channel_id)

    def remove_chat_log_path(self, channel_id):
        with self.lock:
             self.chat_log_paths.pop(channel_id, None)


# 계정 불러오기 함수
def loadAccount():
    if os.path.exists(LOGIN_PATH):
        with open(LOGIN_PATH, 'r', encoding='utf-8') as f:
            try:
                data = json.load(f)
                # username과 password가 None이면 계정이 없는 것으로 처리
                if not data.get('username') or not data.get('password'):
                    return None
                return {
                    'username': data.get('username'),
                    'password': data.get('password'),
                    'secret_key': data.get('secret_key', secrets.token_hex(32))  # 없으면 생성
                }
            except json.JSONDecodeError as e:
                print(f"[ERROR] {LOGIN_PATH} 파일을 읽는 중 오류가 발생했습니다: {e}")
                return None
    return None

# 계정 저장 함수
def saveAccount(account):
    if os.path.exists(LOGIN_PATH):
        with open(LOGIN_PATH, 'r+', encoding='utf-8') as f:
            try:
                data = json.load(f)

                # 계정 정보 업데이트
                data['username'] = account.get('username')
                data['password'] = account.get('password')

                # secret_key 유지 (없으면 새로 생성)
                data['secret_key'] = data.get('secret_key', secrets.token_hex(32))

                # 파일 전체를 갱신하여 저장
                f.seek(0)
                json.dump(data, f, ensure_ascii=False, indent=4)
                f.truncate()

            except json.JSONDecodeError as e:
                print(f"[ERROR] {LOGIN_PATH} 파일을 읽는 중 오류가 발생했습니다: {e}")
    else:
        # 파일이 없으면 계정 정보와 secret_key 모두 포함한 새 파일 생성
        with open(LOGIN_PATH, 'w', encoding='utf-8') as f:
            json.dump({
                'username': account.get('username'),
                'password': account.get('password'),
                'secret_key': secrets.token_hex(32)  # 새로운 secret_key 생성
            }, f, ensure_ascii=False, indent=4)



# channels.json 로드 함수 (유튜브와 치지직을 통합)
def loadChannels():
    if os.path.exists(CHANNELS_PATH):
        try:
            with open(CHANNELS_PATH, 'r', encoding='utf-8') as f:
                content = f.read()
                if not content.strip():  # 파일이 비어 있으면 빈 리스트 반환
                    print(f"[DEBUG] {CHANNELS_PATH} 파일이 비어 있습니다. 빈 배열 반환.")
                    return []
                return json.loads(content)
        except json.JSONDecodeError as e:
            print(f"[ERROR] {CHANNELS_PATH} JSON 파일을 읽는 중 오류 발생: {e}")
            return []
    print(f"[DEBUG] {CHANNELS_PATH} 파일이 존재하지 않습니다. 빈 배열 반환.")
    return []


# channels.json 저장 함수 (유튜브와 치지직 통합)
def saveChannels(data):
    try:
        data_to_save = []
        for channel in data:
            channel_copy = {
                "platform": channel.get("platform", "unknown"),
                "id": channel["id"],
                "name": channel["name"],
                "output_dir": channel["output_dir"],
                "quality": channel["quality"],
                "extension": channel["extension"],
                "record_enabled": channel.get("record_enabled", True)
            }
            data_to_save.append(channel_copy)
        
        with open(CHANNELS_PATH, 'w', encoding='utf-8') as f:
            json.dump(data_to_save, f, ensure_ascii=False, indent=4)
        print(f"[DEBUG] {CHANNELS_PATH}에 채널 데이터가 저장되었습니다.")
    except Exception as e:
        print(f"[ERROR] {CHANNELS_PATH} 파일을 저장하는 중 오류가 발생했습니다: {e}")



# cookie.json 전용 로드 함수
def loadCookies():
    if os.path.exists(COOKIE_PATH):
        try:
            with open(COOKIE_PATH, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return data
        except json.JSONDecodeError as e:
            print(f"[ERROR] {COOKIE_PATH} JSON 파일을 읽는 중 오류 발생: {e}")
            return {}
        except Exception as e:
            print(f"[ERROR] {COOKIE_PATH} 파일을 읽는 중 예기치 못한 오류가 발생했습니다: {e}")
            return {}
    print(f"[DEBUG] {COOKIE_PATH} 파일이 존재하지 않습니다. 빈 딕셔너리 반환.")
    return {}


# cookie.json 전용 저장 함수
def saveCookies(data):
    try:
        with open(COOKIE_PATH, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
        print(f"[DEBUG] {COOKIE_PATH}에 쿠키 데이터가 저장되었습니다.")
    except Exception as e:
        print(f"[ERROR] {COOKIE_PATH} 파일을 저장하는 중 오류가 발생했습니다: {e}")


# config.json 파일에서 데이터를 불러오는 함수
def loadConfig():
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return data
        except json.JSONDecodeError as e:
            print(f"[ERROR] {CONFIG_PATH} JSON 파일을 읽는 중 오류 발생: {e}")
            return {}
    print(f"[DEBUG] {CONFIG_PATH} 파일이 존재하지 않습니다. 빈 딕셔너리 반환.")
    return {}


# config.json 파일에서 데이터를 저장하는 함수
def saveConfig(data):
    try:
        with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
        print(f"[DEBUG] {CONFIG_PATH}에 설정 데이터가 저장되었습니다.")
    except Exception as e:
        print(f"[ERROR] {CONFIG_PATH} 파일을 저장하는 중 오류가 발생했습니다: {e}")


# ycookie.txt 불러오는 함수 (유튜브 레코더용)
def yloadCookies():
    ycookie_path = yCOOKIE_PATH
    
    # 파일이 존재하지 않으면 빈 파일로 생성
    if not os.path.exists(ycookie_path):
        print(f"[INFO] {ycookie_path} 파일이 없으므로 새로 생성합니다.")
        with open(ycookie_path, 'w', encoding='utf-8') as f:
            f.write("# Netscape HTTP Cookie File\n")  # 넷스케이프 쿠키 파일 기본 헤더
        return None

    # 파일이 존재하는 경우 넷스케이프 형식으로 로드
    try:
        with open(ycookie_path, 'r', encoding='utf-8') as f:
            data = f.read().strip()
            if not data.startswith('# Netscape'):
                print(f"[ERROR] {ycookie_path} 파일이 넷스케이프 형식이 아닙니다.")
                return None
            return data  # 쿠키 데이터를 텍스트로 반환
    except Exception as e:
        print(f"[ERROR] {ycookie_path} 파일을 읽는 중 예기치 못한 오류가 발생했습니다: {e}")
        return None



# 파일명 중복 방지 함수
def uniqueFilename(output_dir, filename, add_suffix=True):
    base, ext = os.path.splitext(filename)
    counter = 1
    unique_filename = filename if not add_suffix else f"{base} ({counter}){ext}"

    while os.path.exists(os.path.join(output_dir, unique_filename)):
        counter += 1
        unique_filename = f"{base} ({counter}){ext}"

    return unique_filename


# 후처리 후 파일 이동 함수
def moveDirectory(file_path, destination_directory):
    try:
        if not os.path.exists(destination_directory):
            os.makedirs(destination_directory)

        base_name = os.path.basename(file_path)
        name, ext = os.path.splitext(base_name)
        destination_path = os.path.join(destination_directory, base_name)

        counter = 1
        # 동일한 파일명이 존재하는지 확인하고, 존재할 경우 새로운 파일명 생성
        while os.path.exists(destination_path):
            new_name = f"{name}({counter}){ext}"
            destination_path = os.path.join(destination_directory, new_name)
            counter += 1

        shutil.move(file_path, destination_path)
        print(f"파일 {file_path}가 {destination_path}로 이동되었습니다.")

    except Exception as e:
        print(f"파일 {file_path}를 {destination_directory}로 이동하는 중 오류 발생: {e}")
        raise  # 예외를 다시 발생시켜 상위에서 처리하도록 함