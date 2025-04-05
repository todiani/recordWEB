import os
import json

def load_channels():
    channels_path = os.path.join(os.path.dirname(os.path.dirname(os.path.realpath(__file__))), 'json', 'channels.json')
    try:
        with open(channels_path, 'r', encoding='utf-8') as f:
            channels = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        channels = []
    return channels

def save_channels(channels):
    channels_path = os.path.join(os.path.dirname(os.path.dirname(os.path.realpath(__file__))), 'json', 'channels.json')
    try:
        with open(channels_path, 'w', encoding='utf-8') as f:
            json.dump(channels, f, indent=4, ensure_ascii=False) # indent=4 추가, ensure_ascii=False 추가
    except Exception as e:
        print(f"Error saving channels: {e}")


def load_config():
    config_path = os.path.join(os.path.dirname(os.path.dirname(os.path.realpath(__file__))), 'json', 'config.json')
    default_config = {  # 기본 설정 값
        "auto_record_mode": False,
        "chat_auto_start": False,
        "recheckInterval": 60,
        "autoStopInterval": 0,
        "showMessageBox": True,
        "autoPostProcessing": False,
        "filenamePattern": "[{recording_time}] {channel_name} {safe_live_title}{file_extension}",
        "deleteAfterPostProcessing": False,
        "postProcessingOutputDir": "",
        "plugin": "기본",
        "time_shift": "00:01:00",
        "moveAfterProcessingEnabled": False,
        "moveAfterProcessing": "",
        "postProcessingMethod": "스트림복사",
        "videoCodec": "x264(CPU)",
        "videoBitrate": "8000",
        "audioCodec": "aac",
        "audioBitrate": "192k",
        "preset": "veryfast",
        "qualityOrBitrate":"퀄리티",
        "videoQuality": "25",
        "removeFixedPrefix": False,
        "minimizePostProcessing": False
    }
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
    except FileNotFoundError:
        config = default_config.copy()  # 기본 설정 복사
        save_config(config)  # 기본 설정으로 파일 생성
    except json.JSONDecodeError as e:
        print(f"Error decoding JSON from config.json: {e}")
        config = default_config.copy()  # JSON 파싱 오류 시 기본값 사용
    
    # 기본 설정에 없는 키가 있으면 추가 (업데이트 시 누락된 설정 방지)
    for key, value in default_config.items():
        if key not in config:
            config[key] = value

    return config

def save_config(config):
    config_path = os.path.join(os.path.dirname(os.path.dirname(os.path.realpath(__file__))), 'json', 'config.json')
    try:
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=4, ensure_ascii=False)  # 들여쓰기, 유니코드 설정
    except Exception as e:
         print(f"Error saving config: {e}")