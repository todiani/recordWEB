import datetime
import logging
import json
import api
import os
import re
import time
import sys

from websocket import WebSocket # WebSocketConnectionClosedError 삭제
from cmd_type import CHZZK_CHAT_CMD

class ChzzkChat:

    def __init__(self, streamer, cookies, logger, log_filename):

        self.streamer = streamer
        self.cookies  = cookies
        self.logger   = logger
        self.log_filename = log_filename

        self.sid           = None
        self.userIdHash    = None
        self.chatChannelId = None
        self.channelName   = None
        self.accessToken   = None
        self.extraToken    = None
        self.sock          = None

        self.connect_retry_count = 0
        self.max_retries = 5
        self.retry_delay = 5

        self.connect()

    def connect(self):
        while self.connect_retry_count < self.max_retries:
            try:
                self.chatChannelId = api.fetch_chatChannelId(self.streamer, self.cookies)
                self.accessToken, self.extraToken = api.fetch_accessToken(self.chatChannelId, self.cookies)

                # print(f"chatChannelId: {self.chatChannelId}")
                # print(f"accessToken: {self.accessToken}")
                # print(f"extraToken: {self.extraToken}")

                if self.accessToken is not None:
                    self.userIdHash = api.fetch_userIdHash(self.cookies)
                #     print(f"userIdHash: {self.userIdHash}")
                else:
                    print("accessToken이 None입니다. 사용자 ID를 가져올 수 없습니다.")
                    raise ValueError("accessToken이 None입니다.")

                # WebSocket 객체 생성
                sock = WebSocket()
                # 타임아웃 설정 (예: 10초)
                sock.connect('wss://kr-ss1.chat.naver.com/chat', timeout=10)
                self.channelName = api.fetch_channelName(self.streamer)
                # print(f'{self.channelName} 채팅창에 연결 중 .', end="") # 삭제

                default_dict = {
                    "ver": "2",
                    "svcid": "game",
                    "cid": self.chatChannelId,
                }

                send_dict = {
                    "cmd": CHZZK_CHAT_CMD['connect'],
                    "tid": 1,
                    "bdy": {
                        "uid": self.userIdHash,
                        "devType": 2001,
                        "accTkn": self.accessToken,
                        "auth": "SEND"
                    }
                }

                # 요청 전송
                sock.send(json.dumps(dict(send_dict, **default_dict)))

                # 응답 받기
                sock_response = json.loads(sock.recv())
                # print(f"서버 응답: {sock_response}")

                if 'bdy' in sock_response and 'sid' in sock_response['bdy']:
                    self.sid = sock_response['bdy']['sid']
                    # print(f'\r{self.channelName} 채팅창에 연결 중 ..', end="") # 삭제

                    send_dict = {
                        "cmd": CHZZK_CHAT_CMD['request_recent_chat'],
                        "tid": 2,
                        "sid": self.sid,
                        "bdy": {
                            "recentMessageCount": 50
                        }
                    }

                    sock.send(json.dumps(dict(send_dict, **default_dict)))
                    sock.recv()
                    # print(f'\r{self.channelName} 채팅창에 연결 중 ...') # 삭제

                    self.sock = sock
                    if self.sock.connected:
                        # print('연결 완료') # 삭제
                        self.connect_retry_count = 0
                        return
                    else:
                        raise ValueError('오류 발생')
                else:
                    print(f"서버 응답에 'bdy' 키 또는 'sid' 키가 없습니다. 서버 응답을 확인하세요.")
                    raise ValueError("서버 응답에 'bdy' 키 또는 'sid' 키가 없습니다.")

            except Exception as e:
                print(f"connect 중 오류 발생: {e}")
                self.connect_retry_count += 1
                print(f"재연결 시도 ({self.connect_retry_count}/{self.max_retries})...")
                time.sleep(self.retry_delay)

        print(f"최대 재연결 시도 횟수({self.max_retries})를 초과했습니다. 프로그램을 종료합니다.")
        sys.exit(1)

    def send(self, message:str):

        default_dict = {
            "ver"   : 2,
            "svcid" : "game",
            "cid"   : self.chatChannelId,
        }

        extras = {
            "chatType"          : "STREAMING",
            "emojis"            : "",
            "osType"            : "PC",
            "extraToken"        : self.extraToken,
            "streamingChannelId": self.chatChannelId
        }

        send_dict = {
            "tid"   : 3,
            "cmd"   : CHZZK_CHAT_CMD['send_chat'],
            "retry" : False,
            "sid"   : self.sid,
            "bdy"   : {
                "msg"           : message,
                "msgTypeCode"   : 1,
                "extras"        : json.dumps(extras),
                "msgTime"       : int(datetime.datetime.now().timestamp())
            }
        }

        self.sock.send(json.dumps(dict(send_dict, **default_dict)))

    def run(self):
        while True:
            if self.sock is None:
                # print("연결이 설정되지 않았습니다. 재연결을 시도합니다.") # 삭제
                self.connect()
                time.sleep(5)  # 재연결 전 대기 시간
                continue

            try:
                try:
                    raw_message = self.sock.recv()
                except Exception as e: # WebSocketConnectionClosedError 대신 Exception으로 처리
                   #  print("연결이 끊어졌습니다. 재연결을 시도합니다.") # 삭제
                    self.connect()
                    continue
                except KeyboardInterrupt:
                    break

                raw_message = json.loads(raw_message)
                chat_cmd    = raw_message['cmd']

                # __ 치지직 채팅 메시지 형식 확인을 위한 임시 코드 추가
                # print(f"수신 메시지: {raw_message}")

                if chat_cmd == CHZZK_CHAT_CMD['ping']:

                    self.sock.send(
                        json.dumps({
                            "ver" : "2",
                            "cmd" : CHZZK_CHAT_CMD['pong']
                        })
                    )

                    if self.chatChannelId != api.fetch_chatChannelId(self.streamer, self.cookies): # 방송 시작시 chatChannelId가 달라지는 문제
                        self.connect()

                    continue

                if chat_cmd == CHZZK_CHAT_CMD['chat'] or chat_cmd == CHZZK_CHAT_CMD['donation']:
                    chat_type = '채팅' if chat_cmd == CHZZK_CHAT_CMD['chat'] else '후원'

                    # 'bdy' 키가 존재하는지 확인
                    if 'bdy' not in raw_message:
                        print(f"오류: 메시지에 'bdy' 키가 없습니다: {raw_message}")
                        continue

                    for chat_data in raw_message['bdy']:
                        # 'profile' 키와 'msg' 키가 존재하는지 확인
                        if 'profile' not in chat_data or 'msg' not in chat_data:
                            print(f"오류: 메시지에 'profile' 또는 'msg' 키가 없습니다: {chat_data}")
                            continue

                        if chat_data['uid'] == 'anonymous':
                            nickname = '익명의 후원자'
                            # userIdHash = ''  # 익명 사용자는 userIdHash가 없음
                        else:
                            try:
                                profile_data = json.loads(chat_data['profile'])
                                nickname = profile_data["nickname"]
                                userIdHash = profile_data.get("userIdHash", "")  # userIdHash 가져오기, 없으면 빈 문자열
                            except (json.JSONDecodeError, KeyError):
                                print(f"오류: 'profile' 데이터를 파싱할 수 없습니다: {chat_data}")
                                continue

                        now = datetime.datetime.fromtimestamp(chat_data['msgTime']/1000)
                        now = now.strftime('%Y-%m-%d %H:%M:%S')

                        # __ userIdHash를 포함하여 로그 메시지 수정
                        if self.logger:
                            log_message = f'[{now}][{chat_type}] {nickname}'
                            if userIdHash:
                                log_message += f'({userIdHash})'
                            log_message += f' : {chat_data["msg"]}'
                            self.logger.info(log_message)
                        else:
                            print("오류: 로거가 설정되지 않았습니다.")

                else:
                    print(f"알 수 없는 메시지 유형: {chat_cmd}")

            except ConnectionResetError:
                print("서버와의 연결이 재설정되었습니다. 재연결을 시도합니다.")
                self.connect()
            except Exception as e:
                print(f"Error in run: {e}")
                time.sleep(1)  # 오류 발생 시 잠시 대기 후 다시 시도

def get_logger(log_filename):

    formatter = logging.Formatter('%(message)s')

    logger = logging.getLogger(log_filename)
    logger.setLevel(logging.INFO)

    file_handler = logging.FileHandler(log_filename, mode="a", encoding="utf-8")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)

    return logger

def run_chat_process(streamer_id, output_dir, cookies, channel_name, live_title="Unknown", record_quality="Unknown", frame_rate="Unknown", file_extension=".ts"):
    # Live_recorder.py의 buildCommand 함수의 filename 생성 로직 참고
    recording_time = datetime.datetime.now().strftime('%y%m%d_%H%M%S')
    start_time = datetime.datetime.now().strftime('%Y-%m-%d')

    # live_title 정제
    live_title_raw = live_title
    live_title = live_title_raw.strip().replace('\n', '')
    safe_live_title = re.sub(r'[\\/*?:"<>|+]', '_', live_title)[:55]
    safe_live_title = re.sub(r'[^\w\s\u3040-\u30FF\u4E00-\u9FFF가-힣]', '_', safe_live_title)

    # config.json 파일 경로 수정 (run_record.py 기준 상대 경로로 계산)
    run_record_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    config_path = os.path.join(run_record_path, 'json', 'config.json')

    # config.json에서 filename_pattern 가져오기
    try:
        with open(config_path) as f:
            config = json.load(f)
        filename_pattern = config.get('filenamePattern', '[{start_time}] {channel_name} {safe_live_title} {record_quality}{frame_rate}{file_extension}')
    except FileNotFoundError:
        print(f"config.json 파일을 찾을 수 없습니다: {config_path}")
        return
    except json.JSONDecodeError:
        print(f"config.json 파일 파싱 중 오류 발생: {config_path}")
        return
    # 로그 파일명 생성
    filename = filename_pattern.format(
        recording_time=recording_time,
        start_time=start_time,
        safe_live_title=safe_live_title,
        channel_name=channel_name,
        record_quality=record_quality,
        frame_rate=frame_rate,
        file_extension='.log' # 로그 파일 확장자 .log로 고정
    )

    # 로그 파일 경로 생성 (Live_recorder.py와 동일하게)
    output_dir_abs_path = os.path.abspath(output_dir)
    base_output_path = os.path.join(output_dir_abs_path, filename)
    output_path = base_output_path
    counter = 1
    while os.path.exists(output_path):
        name, ext = os.path.splitext(base_output_path)
        output_path = f"{name} ({counter}){ext}"
        counter += 1

    log_filename = output_path

    logger = get_logger(log_filename)
    chzzkchat = ChzzkChat(streamer_id, cookies, logger, log_filename)
    chzzkchat.run()

if __name__ == '__main__':
    import sys

    if len(sys.argv) < 8:
        print("Usage: python run.py <streamer_id> <output_dir> <channel_name> <live_title> <record_quality> <frame_rate> <file_extension>")
        sys.exit(1)

    streamer_id = sys.argv[1]
    output_dir = sys.argv[2]
    channel_name = sys.argv[3]
    live_title = sys.argv[4]
    record_quality = sys.argv[5]
    frame_rate = sys.argv[6]
    file_extension = sys.argv[7]

    # run.py 파일이 실행될 때 cookie.json에서 쿠키 정보를 읽어옵니다.
    # cookie.json 파일은 run_record.py 파일과 동일한 디렉토리에 있는 'json' 폴더에 있어야 합니다.
    run_record_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    cookie_file_path = os.path.join(run_record_path, 'json', 'cookie.json')

    try:
        with open(cookie_file_path, 'r') as f:
            cookies = json.load(f)
    except FileNotFoundError:
        print(f"Error: cookie.json not found at {cookie_file_path}")
        sys.exit(1)
    except json.JSONDecodeError:
        print(f"Error: Invalid JSON format in cookie.json")
        sys.exit(1)

    run_chat_process(streamer_id, output_dir, cookies, channel_name, live_title, record_quality, frame_rate, file_extension)