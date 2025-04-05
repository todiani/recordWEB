import os
import sys

base_directory = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

CONFIG_PATH = os.path.join(base_directory, 'json', 'config.json')
CHANNELS_PATH = os.path.join(base_directory, 'json', 'channels.json')
COOKIE_PATH = os.path.join(base_directory, 'json', 'cookie.json')
yCOOKIE_PATH = os.path.join(base_directory, 'json', 'ycookie.txt')
LOGIN_PATH = os.path.join(base_directory, 'json', 'login.json')


# ffmpeg 경로를 가져오는 함수
def getFFmpeg():
    ffmpeg_path = os.path.join(base_directory, 'dependent', 'ffmpeg', 'bin', 'ffmpeg.exe')
    ffmpeg_abs_path = os.path.abspath(ffmpeg_path)

    if os.path.exists(ffmpeg_abs_path) and os.path.isfile(ffmpeg_abs_path):
        # print(f"[INFO] FFmpeg가 '{ffmpeg_abs_path}' 경로에 있습니다.")
        return ffmpeg_abs_path
    else:
        print(f"[ERROR] FFmpeg가 '{ffmpeg_abs_path}' 경로에 없습니다. 경로를 확인해 주세요.")
        sys.exit(1)  # FFmpeg 경로가 없으면 프로그램 종료


# ffprobe 경로를 가져오는 함수
def getFFprobe():
    ffprobe_path = os.path.join(base_directory, 'dependent', 'ffmpeg', 'bin', 'ffprobe.exe')
    ffprobe_abs_path = os.path.abspath(ffprobe_path)

    if os.path.exists(ffprobe_abs_path) and os.path.isfile(ffprobe_abs_path):
        # print(f"[INFO] FFprobe가 '{ffprobe_abs_path}' 경로에 있습니다.")
        return ffprobe_abs_path
    else:
        print(f"[ERROR] FFprobe가 '{ffprobe_abs_path}' 경로에 없습니다. 경로를 확인해 주세요.")
        sys.exit(1)  # FFprobe 경로가 없으면 프로그램 종료


# streamlink 경로를 가져오는 함수
def getStreamlink():
    streamlink_path = os.path.join(base_directory, 'dependent', 'streamlink', 'bin', 'streamlink.exe')
    streamlink_abs_path = os.path.abspath(streamlink_path)

    if os.path.exists(streamlink_abs_path) and os.path.isfile(streamlink_abs_path):
        # print(f"[INFO] Streamlink가 '{streamlink_abs_path}' 경로에 있습니다.")
        return streamlink_abs_path
    else:
        print(f"[ERROR] Streamlink가 '{streamlink_abs_path}' 경로에 없습니다. 경로를 확인해 주세요.")
        sys.exit(1)  # Streamlink 경로가 없으면 프로그램 종료


# yt-dlp 경로를 가져오는 함수
def getYtDlp():
    yt_dlp_path = os.path.join(base_directory, 'dependent', 'yt-dlp', 'yt-dlp.exe')
    yt_dlp_abs_path = os.path.abspath(yt_dlp_path)

    if os.path.exists(yt_dlp_abs_path) and os.path.isfile(yt_dlp_abs_path):
        # print(f"[INFO] yt-dlp가 '{yt_dlp_abs_path}' 경로에 있습니다.")
        return yt_dlp_abs_path
    else:
        print(f"[ERROR] yt-dlp가 '{yt_dlp_abs_path}' 경로에 없습니다. 경로를 확인해 주세요.")
        sys.exit(1)  # yt-dlp 경로가 없으면 프로그램 종료


# ytarchive 경로를 가져오는 함수
def getYtArchive():
    yt_archive_path = os.path.join(base_directory, 'dependent', 'ytarchive', 'ytarchive.exe')
    yt_archive_abs_path = os.path.abspath(yt_archive_path)

    if os.path.exists(yt_archive_abs_path) and os.path.isfile(yt_archive_abs_path):
        # print(f"[INFO] ytarchive가 '{yt_archive_abs_path}' 경로에 있습니다.")
        return yt_archive_abs_path
    else:
        print(f"[ERROR] ytarchive가 '{yt_archive_abs_path}' 경로에 없습니다. 경로를 확인해 주세요.")
        sys.exit(1)  # ytarchive 경로가 없으면 프로그램 종료