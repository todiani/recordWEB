import requests
import json
import os
from typing import Optional, Dict, Tuple
from path_config import base_directory, COOKIE_PATH  # COOKIE_PATH 임포트

def load_cookies() -> Optional[Dict[str, str]]:
    """
    cookie.json 파일에서 쿠키를 읽어옵니다.
    파일이 없거나 읽을 수 없으면 None을 반환합니다.
    """
    try:
        with open(COOKIE_PATH, "r", encoding="utf-8") as f:  # COOKIE_PATH 사용
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"Error reading cookies: {e}")
        return None

def get_headers(cookies: Dict[str, str]) -> Dict[str, str]: # cookies를 필수로 받음
    """
    User-Agent와 Cookie를 포함한 헤더를 반환합니다.
    """
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    headers["Cookie"] = f'NID_AUT={cookies.get("NID_AUT", "")}; NID_SES={cookies.get("NID_SES", "")}' # cookies가 None이면 KeyError 발생
    return headers


def fetch_userIdHash(cookies: Dict[str, str]) -> Optional[str]: # cookies를 필수로 받음
    try:
        headers = get_headers(cookies) # cookies가 None이면 KeyError 발생
        response = requests.get(
            "https://comm-api.game.naver.com/nng_main/v1/user/getUserStatus",
            headers=headers,
        )
        response.raise_for_status()
        data = response.json()
        return data["content"]["userIdHash"]
    except (requests.exceptions.RequestException, json.JSONDecodeError, KeyError) as e:
        print(f"Error fetching userIdHash: {e}")
        return None


def fetch_chatChannelId(streamer: str, cookies: Dict[str, str]) -> Optional[str]: # cookies를 필수로 받음
    try:
        headers = get_headers(cookies) # cookies가 None이면 KeyError 발생
        url = f"https://api.chzzk.naver.com/service/v1/channels/{streamer}/live-detail"
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        data = response.json()
        return data["content"]["chatChannelId"]

    except (requests.exceptions.RequestException, json.JSONDecodeError, KeyError) as e:
        print(f"Error fetching chatChannelId: {e}")
        return None


def fetch_accessToken(
    chatChannelId: str, cookies: Dict[str, str]
) -> Tuple[Optional[str], Optional[str]]:  # cookies를 필수로 받음
    try:
        headers = get_headers(cookies) # cookies가 None이면 KeyError 발생
        url = (
            f"https://comm-api.game.naver.com/nng_main/v1/chats/access-token?"
            f"channelId={chatChannelId}&chatType=STREAMING"
        )
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        data = response.json()
        return data["content"]["accessToken"], data["content"]["extraToken"]

    except (requests.exceptions.RequestException, json.JSONDecodeError, KeyError) as e:
        print(f"Error fetching accessToken: {e}")
        return None, None


def fetch_channelName(streamer: str, cookies: Optional[Dict[str, str]] = None) -> Optional[str]:
    try:
        headers = get_headers(cookies)
        url = f"https://api.chzzk.naver.com/service/v1/channels/{streamer}"
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        data = response.json()

        # 'content' 키가 있는지 확인, 'channelName'이 있는지 확인
        if 'content' in data:
            content = data['content']
            if 'channelName' in content:
                return content['channelName']
            elif 'channel' in content and 'channelName' in content['channel']:
                return content['channel']['channelName']
            else:
                print(f"Error fetching channelName: 'channelName' key not found in response")
                return None
        else:
            print("Error fetching channelName: 'content' key not found in response")
            return None  # 필요한 키가 없으면 None 반환

    except (requests.exceptions.RequestException, json.JSONDecodeError, KeyError) as e:
        print(f"Error fetching channelName: {e}")
        return None