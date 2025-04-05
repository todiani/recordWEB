import os
import subprocess
import time
import ctypes

def get_ffmpeg_path():
    current_dir = os.path.dirname(os.path.dirname(__file__))
    ffmpeg_path = os.path.join(current_dir, 'dependent', 'ffmpeg', 'bin', 'ffmpeg.exe')
    return os.path.abspath(ffmpeg_path)

def convert_bitrate(bitrate_str):
    if bitrate_str.endswith('kbps'):
        return bitrate_str.replace('kbps', 'k')
    return bitrate_str

def copy_stream(filename, directory, ffmpeg_path, minimizePostProcessing=False):
    original_path = os.path.join(directory, filename)
    converted_path = os.path.join(directory, f'fixed_{filename}')

    cmd = [
        ffmpeg_path,
        '-i', original_path,
        '-c:v', 'copy',
        '-c:a', 'copy',
        '-y',
        converted_path
    ]

    try:
        print(f"[DEBUG] 명령어 실행: {' '.join(cmd)}")

        startupinfo = None
        if minimizePostProcessing:
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = 6  # SW_MINIMIZE = 6

        process = subprocess.Popen(cmd, startupinfo=startupinfo)
        process.wait()

        if process.returncode != 0:
            raise subprocess.CalledProcessError(process.returncode, cmd)

        print(f"{original_path}를 {converted_path}로 스트림 복사 완료")
    except subprocess.CalledProcessError as e:
        print(f"{original_path} 파일의 스트림 복사가 강제로 종료되었습니다. 오류: {e}")
    except Exception as e:
        print(f"{original_path} 파일의 스트림 복사 중 예상치 못한 오류가 발생했습니다. 오류: {e}")

def copy_specific_file(input_path, output_path, deleteAfterPostProcessing, removeFixedPrefix, minimizePostProcessing=False, config={}):
    ffmpeg_path = get_ffmpeg_path()

    # 인코딩 또는 스트림 복사에 대한 설정 처리
    post_processing_method = config.get('postProcessingMethod')

    input_path = os.path.normpath(input_path)
    output_path = os.path.normpath(output_path)

    print(f"[DEBUG] copy_specific_file 함수 시작")
    print(f"[DEBUG] 입력 파일: {input_path}")
    print(f"[DEBUG] 출력 파일: {output_path}")
    print(f"[DEBUG] 설정: deleteAfterPostProcessing={deleteAfterPostProcessing}, removeFixedPrefix={removeFixedPrefix}, minimizePostProcessing={minimizePostProcessing}, config={config}")

    if post_processing_method == "스트림복사":
        cmd = [
            ffmpeg_path,
            '-i', input_path,
            '-c:v', 'copy',
            '-c:a', 'copy',
            '-y',
            output_path
        ]
    else:  # 인코딩 방식
        codec_map = {
            'x264(CPU)': 'libx264',
            'h264_qsv(인텔 GPU가속)': 'h264_qsv',
            'h264_nvenc(엔비디아 GPU가속)': 'h264_nvenc',
            'h264_amf(AMD GPU가속)': 'h264_amf'
        }

        video_codec = codec_map.get(config.get('videoCodec'), 'libx264')
        video_bitrate = config.get('videoBitrate')
        audio_codec = config.get('audioCodec', 'aac')
        audio_bitrate = convert_bitrate(config.get('audioBitrate', '128k'))
        preset = config.get('preset', 'medium')
        quality_or_bitrate = config.get('qualityOrBitrate')
        video_quality = config.get('videoQuality')

        cmd = [
            ffmpeg_path,
            '-i', input_path,
            '-c:v', video_codec,
            '-preset', preset,
            '-c:a', audio_codec,
            '-b:a', audio_bitrate,
            '-y'
        ]

        # h264_qsv 선택 시 CRF 모드는 global_quality와 look_ahead 옵션으로 대체 적용
        # h264_nvenc 선택 시 CRF 모드는 CQP로 대체 적용
        # h264_amf 선택 시 CRF 모드는 QVBR로 대체 적용

        if video_codec == 'h264_qsv':
            cmd.extend(['-global_quality', str(video_quality if video_quality else '25')])
            cmd.extend(['-look_ahead', '1'])
        elif video_codec == 'h264_nvenc':  
            if quality_or_bitrate == '퀄리티':
                if video_quality is not None:
                    cmd.extend(['-cq', str(video_quality)])
                else:
                    cmd.extend(['-cq', '23'])
        elif video_codec == 'h264_amf':  
            if quality_or_bitrate == '퀄리티':
                cmd.extend(['-rc', 'qvbr'])
                if video_quality is not None:
                    cmd.extend(['-qvbr_quality_level', str(video_quality)])
                else:
                    cmd.extend(['-qvbr_quality_level', '23'])
        elif quality_or_bitrate == '퀄리티':
            if video_quality is not None:
                cmd.extend(['-crf', str(video_quality)])
            else:
                cmd.extend(['-c:v', 'copy'])
        elif quality_or_bitrate == '비트레이트':
            if video_bitrate:
                cmd.extend(['-b:v', f'{video_bitrate}k'])
            else:
                cmd.extend(['-c:v', 'copy'])

        cmd.append(output_path)

    print(f"[DEBUG] 명령어 실행: {' '.join(cmd)}")

    try:
        # 별도의 새 창에서 명령을 실행하고, minimizePostProcessing이 True이면 창을 최소화
        startupinfo = None
        if minimizePostProcessing:
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = 6  # SW_MINIMIZE = 6

        process = subprocess.Popen(cmd, startupinfo=startupinfo, creationflags=subprocess.CREATE_NEW_CONSOLE)
        process.wait()

        if process.returncode != 0:
            raise subprocess.CalledProcessError(process.returncode, cmd)

        print(f"{input_path}를 {output_path}로 스트림 복사 완료")

        if deleteAfterPostProcessing:
            time.sleep(5)
            os.remove(input_path)
            print(f"원본 파일 {input_path} 삭제됨")

        if removeFixedPrefix:
            final_output_path = os.path.join(os.path.dirname(output_path), os.path.basename(output_path).replace('fixed_', ''))
            print(f"[DEBUG] Renaming {output_path} to {final_output_path}")
            os.rename(output_path, final_output_path)
            output_path = final_output_path
            print(f"{output_path}를 {final_output_path}로 이름 변경됨")

    except subprocess.CalledProcessError as e:
        print(f"{input_path} 파일의 스트림 복사가 강제로 종료되었습니다. 오류: {e}")
    except Exception as e:
        print(f"{input_path} 파일의 스트림 복사 중 예상치 못한 오류가 발생했습니다. 오류: {e}")

    return output_path