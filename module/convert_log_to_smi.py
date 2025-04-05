import re
import argparse
import os
import sys
from datetime import datetime, timedelta, time

def convert_log_to_smi(log_filepath, smi_filepath):
    """Converts a Chzzk chat log file to an SMI subtitle file."""

    try:
        with open(log_filepath, 'r', encoding='utf-8') as log_file, \
             open(smi_filepath, 'w', encoding='utf-8') as smi_file:

            # Write SMI header
            smi_file.write("<SAMI>\n")
            smi_file.write("<HEAD>\n")
            smi_file.write("<TITLE>Chzzk Chat Log</TITLE>\n")
            smi_file.write("<STYLE TYPE=\"text/css\">\n")
            smi_file.write("<!--\n")
            smi_file.write("P { margin-left:8pt; margin-right:8pt; margin-bottom:2pt;\n")
            smi_file.write("    margin-top:2pt; font-size:14pt; text-align:left;\n")
            smi_file.write("    font-family:sans-serif; font-weight:normal; color:white;\n")
            smi_file.write("    background-color:black; }\n")
            smi_file.write(".DONATION { color: red; }\n")
            smi_file.write("-->\n")
            smi_file.write("</STYLE>\n")
            smi_file.write("</HEAD>\n")
            smi_file.write("<BODY>\n")

            # Regular expressions
            log_pattern = re.compile(r"^\[(.*?)\]\[(.*?)\] (.*?)\s*:\s*(.*)$")
            emoji_pattern = re.compile(r'{:\w+:}')
            id_pattern = re.compile(r'\([0-9a-f]+\)')

            # 파일 이름에서 녹화 시작 시간 파싱
            filename = os.path.basename(log_filepath)
            match = re.match(r"\[(\d{6}_\d{6})\]", filename)
            if match:
                try:
                    recording_start_time = datetime.strptime(match.group(1), '%y%m%d_%H%M%S')

                    # 타임머신 시간 가져오기
                    time_shift = 0
                    try:
                        time_shift_file = os.path.join(os.path.dirname(log_filepath), "time_shift.txt")
                        with open(time_shift_file, "r") as f:
                            time_shift_str = f.read().strip()
                            time_shift = int(time_shift_str)
                    except FileNotFoundError:
                        print("time_shift.txt not found, using time_shift = 0")
                    except ValueError:
                        print("Invalid time_shift value, using time_shift = 0")

                    recording_start_time -= timedelta(seconds=time_shift)

                except ValueError:
                    print("Error: Invalid recording start time format in filename.")
                    return 1
            else:
                print("Error: Could not extract recording start time from filename.")
                return 1

            for line_num, line in enumerate(log_file):
                match = log_pattern.match(line)
                if match:
                    timestamp_str, chat_type, nickname, message = match.groups()
                    nickname = id_pattern.sub('', nickname).strip()
                    try:
                        chat_time = datetime.strptime(timestamp_str, '%H:%M:%S')
                        current_chat_time = chat_time.replace(year=recording_start_time.year, month=recording_start_time.month, day=recording_start_time.day)
                        start_time = int((current_chat_time - recording_start_time).total_seconds() * 1000)

                    except ValueError as e:
                        print(f"Error parsing time on line {line_num}: {e}")
                        continue

                    message = emoji_pattern.sub(lambda m: f"({m.group(0)[1:-1]})", message)

                    if chat_type == "후원":
                        smi_file.write(f'<SYNC Start={start_time}><P Class=DONATION><font color="red">[후원]</font> {nickname}: {message}\n')
                    else:
                        smi_file.write(f'<SYNC Start={start_time}><P>{nickname}: {message}\n')
                else:
                    print(f"Line does not match regex: {line.strip()}")


            # Write SMI footer
            smi_file.write("</BODY>\n")
            smi_file.write("</SAMI>\n")

        print(f"Successfully converted '{log_filepath}' to '{smi_filepath}'")

    except FileNotFoundError:
        print(f"Error: Log file not found at '{log_filepath}'")
        return 1
    except ValueError as e:
        print(f"Error: Invalid time format: {e}")
        return 1
    except TypeError as e:
        print(f"Error: Type error: {e}")
        return 1
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        import traceback
        traceback.print_exc()
        return 1
    sys.exit(1)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Convert Chzzk chat log to SMI.")
    parser.add_argument("log_filepath", help="Path to the Chzzk chat log file.")
    parser.add_argument("smi_filepath", help="Path to the output SMI file.")
    args = parser.parse_args()

    if convert_log_to_smi(args.log_filepath, args.smi_filepath) == 1:
        sys.exit(1)
    input("Press Enter to exit...")