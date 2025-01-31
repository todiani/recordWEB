import os
import json

# JSON 파일 경로 설정
# 현재 스크립트의 위치를 기준으로 json 디렉토리를 설정
base_directory = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
json_directory = os.path.join(base_directory, 'json')
channels_path = os.path.join(json_directory, 'channels.json')
config_path = os.path.join(json_directory, 'config.json')

# json 디렉토리가 존재하지 않으면 생성
if not os.path.exists(json_directory):
    os.makedirs(json_directory)

# 채널 정보 로드
def load_channels():
    try:
        with open(channels_path, "r", encoding="utf-8") as file:
            channels = json.load(file)
            
            for channel in channels:
                if 'output_dir' in channel:
                    if not os.path.isabs(channel['output_dir']):
                        channel['output_dir'] = os.path.abspath(os.path.join(base_directory, channel['output_dir']))

            return channels
    except (FileNotFoundError, json.JSONDecodeError):
        return []

# 채널 정보 저장
def save_channels(channels):
    for channel in channels:
        if 'output_dir' in channel:
            channel['output_dir'] = os.path.abspath(channel['output_dir'])

    with open(channels_path, "w", encoding="utf-8") as file:
        json.dump(channels, file, indent=2, ensure_ascii=False)

# 기본 설정
default_config = {
    "auto_record_mode": False,
    "autoPostProcessing": False,
    "recheckInterval": 60,
    "showMessageBox": True,
    "deleteAfterPostProcessing": False,
    "minimizePostProcessing": False,
    "removeFixedPrefix": False,
    "filenamePattern": "[{recording_time}] {channel_name} {safe_live_title} {record_quality}{frame_rate}{file_extension}",
    "postProcessingMethod": "스트림복사",
    "moveAfterProcessingEnabled": False,
    "moveAfterProcessing": "",
    "postProcessingOutputDir": "", 
    "videoCodec": "x264(CPU)",
    "qualityOrBitrate": "퀄리티",
    "videoQuality": None,
    "videoBitrate": "",
    "preset": "medium",
    "audioCodec": "aac",
    "audioBitrate": "128kbps",
    "plugin": "기본 플러그인", 
    "time_shift": 600,  
    "autoStopInterval": 0
}

def load_config():
    config_path = 'config.json'
    if not os.path.exists(config_path):
        with open(config_path, 'w') as config_file:
            json.dump(default_config, config_file, indent=4)
    with open(config_path, 'r') as config_file:
        return json.load(config_file)

def save_config(config):
    config_path = 'config.json'
    with open(config_path, 'w') as config_file:
        json.dump(config, config_file, indent=4)


# 설정 저장 함수
def save_config(config):
    with open(config_path, 'w') as f:
        json.dump(config, f, indent=4)

# 설정 로드 함수
def load_config():
    if os.path.exists(config_path):
        try:
            with open(config_path, 'r') as f:
                config = json.load(f)
                for key, value in default_config.items():
                    if key not in config:
                        config[key] = value
                save_config(config)
                return config
        except json.JSONDecodeError:
            save_config(default_config)
            return default_config
    else:
        save_config(default_config)
        return default_config