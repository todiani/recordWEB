import argparse
import asyncio
import logging
import json
import time
import api
import os
import hashlib
import re

from cmd_type import CHZZK_CHAT_CMD  # module.cmd_type -> cmd_type
from colorama import Fore, Style, init
from datetime import datetime, timezone
from path_config import COOKIE_PATH  # COOKIE_PATH 임포트
import traceback
from websocket import WebSocket  # WebSocket 추가

# colorama 초기화
init()

# 현재 디렉토리 경로 얻기 (run.py 파일 위치)
current_directory = os.path.dirname(os.path.realpath(__file__))

# 로거 설정 함수
def get_logger(streamer, log_path):
    #print(f"get_logger called with log_path: {log_path}")  # log_path 값 확인, 디버깅용 print 제거
    if log_path is None:
        print("[get_logger] 오류: log_path가 None입니다.")
        return None

    logger = logging.getLogger(streamer)
    logger.setLevel(logging.INFO)

    if not logger.hasHandlers():
        file_formatter = logging.Formatter("%(message)s") # 수정: 메시지만
        file_handler = logging.FileHandler(log_path, encoding="utf-8")
        file_handler.setFormatter(file_formatter)
        logger.addHandler(file_handler)

    print(f"[get_logger] 로거 생성됨: {logger}, 핸들러: {logger.handlers}")
    return logger

def get_cookies():
    """Load cookies from file."""
    try:
        with open(COOKIE_PATH, "r", encoding="utf-8") as f:
            cookies = json.load(f)
            return cookies
    except Exception as e:
        print(f"오류: 쿠키 로드 실패: {e}")
        traceback.print_exc()
        return None

# 사용자별 색상 생성 함수
def get_color_for_user(user_id):
    hash_object = hashlib.md5(user_id.encode("utf-8"))
    hex_dig = hash_object.hexdigest()
    colors = [int(hex_dig[i : i + 2], 16) % 156 + 100 for i in range(0, 6, 2)]
    return f"\033[38;2;{';'.join(map(str, colors))}m"


class ChzzkChat:
    def __init__(self, streamer, cookies, log_path, logger, retry_interval=30):
        print(f"[ChzzkChat.__init__] 호출됨: streamer={streamer}, log_path={log_path}") # 한국어
        self.streamer = streamer
        self.cookies = cookies
        self.logger = logger
        self.log_path = log_path
        self.retry_interval = retry_interval
        self.sid = None
        self.userIdHash = api.fetch_userIdHash(self.cookies)
        self.chatChannelId = api.fetch_chatChannelId(self.streamer, self.cookies)
        self.channelName = api.fetch_channelName(self.streamer, self.cookies)
        self.accessToken, self.extraToken = api.fetch_accessToken(
            self.chatChannelId, self.cookies
        )
        self.time_shift = 0  # 타임머신 시간 초기화
        # print(f"[ChzzkChat.__init__] chatChannelId={self.chatChannelId}, accessToken={self.accessToken}") # 제거

    def connect(self): # 비동기 아님
        while True:
            try:
                self.chatChannelId = api.fetch_chatChannelId(self.streamer, self.cookies)
                self.accessToken, self.extraToken = api.fetch_accessToken(
                    self.chatChannelId, self.cookies
                )

                sock = WebSocket() # websocket 객체 생성
                sock.connect("wss://kr-ss1.chat.naver.com/chat")
                print(f"[ChzzkChat.connect] 채팅 서버에 연결됨")  # 한국어


                default_dict = {  # 기본 딕셔너리
                    "ver": "2",
                    "svcid": "game",
                    "cid": self.chatChannelId,
                }
                # connect 메시지 전송
                send_dict = {
                    "cmd": CHZZK_CHAT_CMD["connect"],
                    "tid": 1,
                    "bdy": {
                        "uid": self.userIdHash,
                        "devType": 2001,
                        "accTkn": self.accessToken,
                        "auth": "SEND",
                    },
                }
                sock.send(json.dumps(dict(send_dict, **default_dict)))
                sock_response = json.loads(sock.recv())
                self.sid = sock_response["bdy"]["sid"]

                # recent_chat 메시지 전송
                send_dict = {
                    "cmd": CHZZK_CHAT_CMD["request_recent_chat"],
                    "tid": 2,
                    "sid": self.sid,
                    "bdy": {
                        "recentMessageCount": 50
                    },
                }
                sock.send(json.dumps(dict(send_dict, **default_dict)))
                sock.recv()

                self.sock = sock  # WebSocket 객체
                # print(f"[ChzzkChat.connect] self.sock: {self.sock}") #제거
                print("[ChzzkChat.connect] connect 함수 종료 (성공)")  # 한국어
                return  # 성공했으면 while 루프 종료

            except Exception as e:
                print(
                    f"채팅 서버 연결 오류: {e}, {self.retry_interval}초 후 재시도" # 한국어
                )
                print(traceback.format_exc())  # 예외 발생 시 traceback 출력
                time.sleep(self.retry_interval)
                continue

    def send(self, message: str):
        default_dict = {
            "ver": 2,
            "svcid": "game",
            "cid": self.chatChannelId,
        }

        extras = {
            "chatType": "STREAMING",
            "emojis": "",
            "osType": "PC",
            "extraToken": self.extraToken,
            "streamingChannelId": self.chatChannelId,
        }

        send_dict = {
            "tid": 3,
            "cmd": CHZZK_CHAT_CMD["send_chat"],
            "retry": False,
            "sid": self.sid,
            "bdy": {
                "msg": message,
                "msgTypeCode": 1,
                "extras": json.dumps(extras),
                "msgTime": int(datetime.now().timestamp()),
            },
        }

        self.sock.send(json.dumps(dict(send_dict, **default_dict)))


    def run(self):  # 비동기 아님.
        while True:  # 무한 루프
            try:
                raw_message = self.sock.recv()  # 메시지 받기
            except Exception as e:
                print(f"채팅 수신 오류(재연결 시도 중): {e}")
                self.connect()  # 다시 연결 시도
                continue

            try:  # 메시지 처리
                raw_message = json.loads(raw_message)
                chat_cmd = raw_message["cmd"]

                if chat_cmd == CHZZK_CHAT_CMD["ping"]:
                    self.sock.send(json.dumps({"ver": 2, "cmd": CHZZK_CHAT_CMD["pong"]}))
                    if self.chatChannelId != api.fetch_chatChannelId(
                        self.streamer, self.cookies
                    ):
                        self.connect()  # connect 호출
                    continue
                if chat_cmd not in (CHZZK_CHAT_CMD["chat"], CHZZK_CHAT_CMD["donation"]):
                    continue

                for chat_data in raw_message["bdy"]:
                    if chat_data["uid"] == "anonymous":
                        nickname = "익명의 후원자"
                        uid = "anonymous"
                    else:
                        try:
                            profile_data = json.loads(chat_data["profile"])
                            nickname = profile_data["nickname"]
                            uid = chat_data.get("uid", "unknown")
                        except (json.JSONDecodeError, KeyError) as e:
                            print(f"프로필 파싱 오류: {e}")
                            nickname = "Unknown"
                            uid = "Unknown"
                        if "msg" not in chat_data:
                            continue

                    time_ms = chat_data['msgTime']  # 밀리초
                    chat_time = datetime.fromtimestamp(time_ms / 1000)  # datetime 객체로 변환
                    formatted_time = chat_time.strftime("%H:%M:%S") # 시간:분:초

                    user_color = get_color_for_user(uid)

                    # 후원 메시지 처리 (extras 필드 파싱)
                    if chat_cmd == CHZZK_CHAT_CMD["donation"]:
                        try:
                            extras = json.loads(chat_data["extras"])
                            amount = extras.get("amount", 0)  # 후원 금액 (없으면 0)
                            currency = extras.get("currency", "KRW")  # 통화 (없으면 KRW)

                            # 후원 메시지 형식 변경
                            console_message = (
                                f"{Fore.WHITE}[{formatted_time}]{Style.RESET_ALL}"
                                f"[{Fore.RED}후원{Style.RESET_ALL}] "
                                f"{user_color}{nickname}({uid}){Style.RESET_ALL} : "
                                f"{Fore.WHITE}{chat_data['msg']} "
                                f"({amount} {currency}){Style.RESET_ALL}"
                            )
                            log_message = f"[{formatted_time}][후원] {nickname}({uid}) : {chat_data['msg']} ({amount} {currency})"

                        except (json.JSONDecodeError, KeyError) as e:
                            print(f"후원 extras 파싱 오류: {e}")
                            # extras 파싱에 실패한 경우, 기본 후원 메시지 형식 사용
                            console_message = (
                                f"{Fore.WHITE}[{formatted_time}]{Style.RESET_ALL}"
                                f"[{Fore.RED}후원{Style.RESET_ALL}] "
                                f"{user_color}{nickname}({uid}){Style.RESET_ALL} : "
                                f"{Fore.WHITE}{chat_data['msg']}{Style.RESET_ALL}"
                            )
                            log_message = (
                                f"[{formatted_time}][후원] {nickname}({uid}) : {chat_data['msg']}"
                            )
                    else:
                        # 일반 채팅 메시지 처리 (기존 코드)
                        console_message = (
                            f"{Fore.WHITE}[{formatted_time}]{Style.RESET_ALL}"
                            f"[{Fore.YELLOW}채팅{Style.RESET_ALL}] "
                            f"{user_color}{nickname}({uid}){Style.RESET_ALL} : "
                            f"{Fore.WHITE}{chat_data['msg']}{Style.RESET_ALL}"
                        )
                        log_message = f"[{formatted_time}][채팅] {nickname}({uid}) : {chat_data['msg']}"

                    try:
                        self.logger.info(log_message)
                    except Exception as e:
                        print(f"run.py에서 파일 쓰기 예외 발생: {e}")

                    print(console_message)

            except Exception as e:
                print(f"채팅 처리 오류: {e}")
                print(traceback.format_exc())
                self.connect()

            time.sleep(1)  # 1초 대기

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--streamer_id", type=str, default="9381e7d6816e6d915a44a13c0195b202"
    )
    parser.add_argument("--log_path", type=str, default="chat.log")
    parser.add_argument(
        "--retry_interval", type=int, default=30, help="재시도 간격(초)" # 한국어
    )
    parser.add_argument("--time_shift", type=int, default=0, help="타임머신 시간 (초)") # 타임머신 인자 추가
    args = parser.parse_args()

    try:
        cookies = get_cookies()  # 수정: get_cookies 함수 사용
        if cookies is None:
            print("오류: 쿠키 로드 실패.") # 한국어
            return

        logger = get_logger(args.streamer_id, args.log_path)
        if logger is None:
            print("오류: 로거 초기화 실패.")  # 한국어
            return

        chzzkchat = ChzzkChat(
            args.streamer_id, cookies, args.log_path, logger, args.retry_interval
        )
        chzzkchat.time_shift = args.time_shift  # ChzzkChat 객체에 time_shift 설정

        # chzzkchat 실행 디렉토리(run.py가 있는 디렉토리)에 time_shift.txt 생성.
        try:
            with open(os.path.join(current_directory, "time_shift.txt"), "w") as f:
                f.write(str(chzzkchat.time_shift))
                print(f"time_shift 저장됨: {chzzkchat.time_shift}") # 한국어
        except Exception as e:
            print(f"오류: time_shift 파일 쓰기 실패: {e}") # 한국어
            traceback.print_exc()

        chzzkchat.connect()  # connect 호출 (동기)
        chzzkchat.run()  # run 호출 (동기)

    except Exception as e:
        print(f"run.py 실행 중 오류 발생: {e}") # 한국어
        traceback.print_exc()
    finally:  # 추가
        input("Press Enter to exit...")

    print("채팅 프로그램 종료.") # 한국어

if __name__ == "__main__":
    main()