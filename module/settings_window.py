import json
import sys
import os
from PyQt5.QtWidgets import QApplication, QMainWindow, QWidget, QFormLayout, QComboBox, QLineEdit, QPushButton, QMessageBox, QHBoxLayout, QLabel, QScrollArea, QVBoxLayout, QFileDialog, QTabWidget, QSpinBox
from PyQt5.QtCore import Qt, QThread, pyqtSignal

from channel_manager import save_config, load_config
from naver_login import NaverLoginService
from path_config import base_directory  # base_directory를 임포트합니다.


# 각 비디오 코덱에 대한 프리셋 목록
codec_presets = {
    'x264': ['ultrafast', 'superfast', 'veryfast', 'faster', 'fast', 'medium', 'slow', 'slower', 'veryslow', 'placebo'],
    'h264_qsv': ['veryfast', 'faster', 'fast', 'balanced', 'slow'],
    'h264_nvenc': ['fast', 'medium', 'slow', 'hq', 'bd', 'll', 'llhq', 'llhp', 'lossless', 'losslesshp'],
    'h264_amf': ['balanced', 'fast', 'quality']
}

class LoginThread(QThread):
    finished = pyqtSignal(bool, str)

    def __init__(self, naver_id, naver_password, parent=None):
        super(LoginThread, self).__init__(parent)
        self.naver_id = naver_id
        self.naver_password = naver_password

    def run(self):
        try:
            naver_login_service = NaverLoginService()
            naver_login_service.login(self.naver_id, self.naver_password)
            self.finished.emit(True, "네이버 로그인에 성공했습니다.")
        except Exception as e:
            self.finished.emit(False, f"네이버 로그인에 실패했습니다. 오류: {e}")

class SettingsWindow(QMainWindow):
    def __init__(self, parent=None):
        super(SettingsWindow, self).__init__(parent)
        self.setWindowTitle('환경설정')
        self.setFixedWidth(720)  # 창의 폭을 줄입니다
        self.setFixedHeight(720)  # 창의 높이를 줄입니다

        # config.json에서 설정 로드
        self.config = load_config()

        # 현재 스크립트 디렉토리
        self.script_dir = os.path.dirname(os.path.abspath(__file__))

        # config.json 및 cookie.json 파일 경로 설정
        self.cookie_data = {}
        self.config_path = os.path.join(self.script_dir, 'config.json')

        # base_directory를 사용하여 cookie_path를 설정합니다.
        self.cookie_path = os.path.join(base_directory, 'json', 'cookie.json')

        # 설정 로드 및 UI 초기화
        self.config = load_config()  # config.json 로드
        self.initUI()

        # 로그인 정보와 쿠키 정보 로드 및 UI에 적용
        self.load_login_info()

    # UI 초기화 메서드
    def initUI(self):
        self.centralWidget = QWidget()
        self.setCentralWidget(self.centralWidget)

        # Tab Widget 생성
        self.tabWidget = QTabWidget()
        self.tabWidget.setStyleSheet("QTabBar::tab { height: 40px; width: 150px; }")
        mainLayout = QVBoxLayout()
        self.centralWidget.setLayout(mainLayout)
        mainLayout.addWidget(self.tabWidget)

        # 첫 번째 탭: 라이브 녹화설정
        liveRecordingSettings = QWidget()
        liveRecordingLayout = QVBoxLayout(liveRecordingSettings)
        liveRecordingScrollArea = QScrollArea()
        liveRecordingScrollArea.setWidgetResizable(True)
        liveRecordingScrollContent = QWidget()
        liveRecordingScrollArea.setWidget(liveRecordingScrollContent)
        liveRecordingFormLayout = QFormLayout(liveRecordingScrollContent)
        liveRecordingFormLayout.setSpacing(20)  # 간격을 넓힙니다
        liveRecordingFormLayout.setContentsMargins(10, 10, 10, 10)  # 여백을 설정합니다
        liveRecordingLayout.addWidget(liveRecordingScrollArea)
        self.tabWidget.addTab(liveRecordingSettings, "라이브 녹화")

        # 두 번째 탭: 녹화 후처리 설정
        postProcessingSettings = QWidget()
        postProcessingLayout = QVBoxLayout(postProcessingSettings)
        postProcessingScrollArea = QScrollArea()
        postProcessingScrollArea.setWidgetResizable(True)
        postProcessingScrollContent = QWidget()
        postProcessingScrollArea.setWidget(postProcessingScrollContent)
        postProcessingFormLayout = QFormLayout(postProcessingScrollContent)
        postProcessingFormLayout.setSpacing(20)  # 간격을 넓힙니다
        postProcessingFormLayout.setContentsMargins(10, 10, 10, 10)  # 여백을 설정합니다
        postProcessingLayout.addWidget(postProcessingScrollArea)
        self.tabWidget.addTab(postProcessingSettings, "녹화 후처리")

        # 라이브 녹화설정 탭 항목들
        self.pluginComboBox = QComboBox()
        self.pluginComboBox.addItems(['기본 플러그인', '타임머신 플러그인', '타임머신 플러스 플러그인'])
        self.pluginComboBox.setCurrentText(self.config.get('plugin', '기본 플러그인'))
        liveRecordingFormLayout.addRow("플러그인 선택:", self.pluginComboBox)

        self.time_shift_label = QLabel('타임머신 시간 (초):')
        self.time_shift_lineedit = QLineEdit()
        self.time_shift_lineedit.setText(str(self.config.get('time_shift', 600)))
        liveRecordingFormLayout.addRow(self.time_shift_label, self.time_shift_lineedit)

        self.recheckIntervalLineEdit = QLineEdit()
        self.recheckIntervalLineEdit.setText(str(self.config.get('recheckInterval', '60')))
        liveRecordingFormLayout.addRow("방송 재탐색 시간(초):", self.recheckIntervalLineEdit)

        self.autoStopIntervalLineEdit = QLineEdit()
        self.autoStopIntervalLineEdit.setText(str(self.config.get('autoStopInterval', '0')))  
        liveRecordingFormLayout.addRow("분할녹화 시간 간격(초):", self.autoStopIntervalLineEdit)

        self.showMessageBoxComboBox = QComboBox()
        self.showMessageBoxComboBox.addItems(['표시', '숨김'])
        self.showMessageBoxComboBox.setCurrentText('표시' if self.config.get('showMessageBox', True) else '숨김')
        liveRecordingFormLayout.addRow("녹화상태 메시지 팝업 표시:", self.showMessageBoxComboBox)

        self.filenamePatternLineEdit = QLineEdit()
        self.filenamePatternLineEdit.setText(self.config.get('filenamePattern', '[{start_time}] {channel_name} {safe_live_title} {record_quality}{frame_rate}{file_extension}'))
        liveRecordingFormLayout.addRow("파일명 생성 규칙:", self.filenamePatternLineEdit)

        filenamePatternExplanation = QLabel(
            "<p>{recording_time} = 녹화시작시간(240801_185035) // {start_time} = 방송시작일(2024-08-01)</p>"
            "<p>{channel_name} = 채널명  //  {safe_live_title} = 방송제목  //  {file_extension} = 확장자</p>"
            "<p>{record_quality} = 녹화 해상도  //  {frame_rate} = 녹화 프레임</p>"
        )
        filenamePatternExplanation.setAlignment(Qt.AlignLeft)
        liveRecordingFormLayout.addRow(filenamePatternExplanation)

        self.autoPostProcessingComboBox = QComboBox()
        self.autoPostProcessingComboBox.addItems(['사용', '사용 안 함'])
        self.autoPostProcessingComboBox.setCurrentText('사용' if self.config.get('autoPostProcessing', False) else '사용 안 함')
        postProcessingFormLayout.addRow("녹화완료된 파일 자동 후처리:", self.autoPostProcessingComboBox)

        # 녹화 후처리 설정 탭 항목들
        self.postProcessingMethodComboBox = QComboBox()
        self.postProcessingMethodComboBox.addItems(['스트림복사', '인코딩'])
        self.postProcessingMethodComboBox.setCurrentText(self.config.get('postProcessingMethod', '스트림복사'))
        self.postProcessingMethodComboBox.currentTextChanged.connect(self.togglePostProcessingOptions)
        postProcessingFormLayout.addRow("후처리 방법:", self.postProcessingMethodComboBox)

        self.minimizePostProcessingComboBox = QComboBox()
        self.minimizePostProcessingComboBox.addItems(['사용', '사용 안 함'])
        self.minimizePostProcessingComboBox.setCurrentText('사용' if self.config.get('minimizePostProcessing', False) else '사용 안 함')
        postProcessingFormLayout.addRow("후처리 실행 시 명령창 최소화:", self.minimizePostProcessingComboBox)

        self.deleteAfterPostProcessingComboBox = QComboBox()
        self.deleteAfterPostProcessingComboBox.addItems(['사용', '사용 안 함'])
        self.deleteAfterPostProcessingComboBox.setCurrentText('사용' if self.config.get('deleteAfterPostProcessing', False) else '사용 안 함')
        postProcessingFormLayout.addRow("후처리 후 원본파일 삭제:", self.deleteAfterPostProcessingComboBox)

        self.removeFixedPrefixComboBox = QComboBox()
        self.removeFixedPrefixComboBox.addItems(['사용', '사용 안 함'])
        self.removeFixedPrefixComboBox.setCurrentText('사용' if self.config.get('removeFixedPrefix', False) else '사용 안 함')
        postProcessingFormLayout.addRow("후처리 후 fixed_ 접두사 지우기:", self.removeFixedPrefixComboBox)

        self.postProcessingOutputDirLineEdit = QLineEdit()
        self.postProcessingOutputDirLineEdit.setPlaceholderText("후처리 완료 파일 저장 경로를 입력하세요")
        self.postProcessingOutputDirLineEdit.setText(self.config.get('postProcessingOutputDir', ''))
        self.postProcessingOutputDirButton = QPushButton("경로 선택")
        self.postProcessingOutputDirButton.clicked.connect(self.selectPostProcessingOutputDir)
        postProcessingOutputDirLayout = QHBoxLayout()
        postProcessingOutputDirLayout.addWidget(self.postProcessingOutputDirLineEdit)
        postProcessingOutputDirLayout.addWidget(self.postProcessingOutputDirButton)
        postProcessingFormLayout.addRow("후처리 완료 파일 저장 경로:", postProcessingOutputDirLayout)

        self.moveAfterProcessingComboBox = QComboBox()
        self.moveAfterProcessingComboBox.addItems(['사용 안 함', '사용'])
        self.moveAfterProcessingComboBox.setCurrentText('사용' if self.config.get('moveAfterProcessingEnabled', False) else '사용 안 함')
        self.moveAfterProcessingComboBox.currentTextChanged.connect(self.toggleMoveAfterProcessingFields)
        postProcessingFormLayout.addRow("후처리 완료 후 파일 자동이동 :", self.moveAfterProcessingComboBox)

        self.moveAfterProcessingLineEdit = QLineEdit()
        self.moveAfterProcessingLineEdit.setPlaceholderText("후처리 완료 후 이동할 경로를 입력하세요")
        self.moveAfterProcessingLineEdit.setText(self.config.get('moveAfterProcessing', ''))
        self.moveAfterProcessingButton = QPushButton("경로 선택")
        self.moveAfterProcessingButton.clicked.connect(self.selectMoveAfterProcessingPath)
        moveAfterProcessingLayout = QHBoxLayout()
        moveAfterProcessingLayout.addWidget(self.moveAfterProcessingLineEdit)
        moveAfterProcessingLayout.addWidget(self.moveAfterProcessingButton)
        postProcessingFormLayout.addRow("후처리 완료 후 이동 경로:", moveAfterProcessingLayout)

        # 인코딩 옵션
        self.encodingOptionsWidget = QWidget()
        encodingOptionsLayout = QFormLayout(self.encodingOptionsWidget)
        self.videoCodecComboBox = QComboBox()
        self.videoCodecComboBox.addItems(['x264(CPU)', 'h264_qsv(인텔 GPU가속)', 'h264_nvenc(엔비디아 GPU가속)', 'h264_amf(AMD GPU가속)'])
        self.videoCodecComboBox.setCurrentText(self.config.get('videoCodec', 'x264(CPU)'))
        self.videoCodecComboBox.currentTextChanged.connect(self.updatePresetComboBox)
        encodingOptionsLayout.addRow("비디오 코덱:", self.videoCodecComboBox)

        self.presetComboBox = QComboBox()
        encodingOptionsLayout.addRow("프리셋:", self.presetComboBox)
        self.updatePresetComboBox()

        self.qualityOrBitrateComboBox = QComboBox()
        self.qualityOrBitrateComboBox.addItems(['퀄리티', '비트레이트'])
        self.qualityOrBitrateComboBox.setCurrentText(self.config.get('qualityOrBitrate', '퀄리티'))
        self.qualityOrBitrateComboBox.currentTextChanged.connect(self.toggleQualityOrBitrateFields)
        encodingOptionsLayout.addRow("비디오 설정:", self.qualityOrBitrateComboBox)

        self.videoQualityLineEdit = QLineEdit()
        self.videoQualityLineEdit.setPlaceholderText("예시) 빈칸: 원본유지, 23: 균형값 추천, 28: 약간의 용량절약, 34: 낮은 품질, 용량절약")
        self.videoQualityLineEdit.setText(str(self.config.get('videoQuality', '')))
        encodingOptionsLayout.addRow("비디오 퀄리티:", self.videoQualityLineEdit)

        self.videoBitrateLineEdit = QLineEdit()
        self.videoBitrateLineEdit.setPlaceholderText("비트레이트를 kbps 단위로 입력하세요(빈칸으로 두면 원본 비트레이트로 인코딩 됩니다)")
        self.videoBitrateLineEdit.setText(str(self.config.get('videoBitrate', '')))
        encodingOptionsLayout.addRow("비디오 비트레이트:", self.videoBitrateLineEdit)

        self.audioCodecComboBox = QComboBox()
        self.audioCodecComboBox.addItems(['mp3', 'aac'])
        self.audioCodecComboBox.setCurrentText(self.config.get('audioCodec', 'aac'))
        encodingOptionsLayout.addRow("오디오 코덱:", self.audioCodecComboBox)

        self.audioBitrateComboBox = QComboBox()
        self.audioBitrateComboBox.addItems(['64kbps', '96kbps', '128kbps', '160kbps', '192kbps', '224kbps', '256kbps', '320kbps'])
        self.audioBitrateComboBox.setCurrentText(self.config.get('audioBitrate', '128kbps'))
        encodingOptionsLayout.addRow("오디오 비트레이트:", self.audioBitrateComboBox)

        postProcessingFormLayout.addRow(self.encodingOptionsWidget)

        self.togglePostProcessingOptions(self.postProcessingMethodComboBox.currentText())

        # 적용 및 취소 버튼
        self.applyButton = QPushButton("적용")
        self.applyButton.setFixedWidth(180)
        self.applyButton.clicked.connect(self.applySettings)

        self.cancelButton = QPushButton("취소")
        self.cancelButton.setFixedWidth(180)
        self.cancelButton.clicked.connect(self.close)

        buttonsLayout = QHBoxLayout()
        buttonsLayout.addWidget(self.applyButton)
        buttonsLayout.addWidget(self.cancelButton)
        buttonsLayout.setAlignment(Qt.AlignCenter)

        mainLayout.addLayout(buttonsLayout)

        NoticeLabel = QLabel("※ 녹화설정 변경을 적용하려면 프로그램을 재시작해야 적용됩니다")
        NoticeLabel.setAlignment(Qt.AlignCenter)
        mainLayout.addWidget(NoticeLabel)

        # NID_SES 레이블과 입력 필드
        self.nid_ses_edit = QLineEdit()
        self.nid_ses_edit.setPlaceholderText("NID_SES 값을 여기에 입력하세요")
        self.nid_ses_label = QLabel("NID_SES:")
        liveRecordingFormLayout.addRow(self.nid_ses_label, self.nid_ses_edit)

        # NID_AUT 레이블과 입력 필드
        self.nid_aut_edit = QLineEdit()
        self.nid_aut_edit.setPlaceholderText("NID_AUT 값을 여기에 입력하세요")
        self.nid_aut_label = QLabel("NID_AUT:")
        liveRecordingFormLayout.addRow(self.nid_aut_label, self.nid_aut_edit)

        # 저장 및 불러오기 버튼 추가
        self.saveButton = QPushButton("저장")
        self.saveButton.clicked.connect(self.saveCookieData)
        self.loadButton = QPushButton("불러오기")
        self.loadButton.clicked.connect(self.loadCookieData)

        # 버튼 레이아웃
        cookieButtonsLayout = QHBoxLayout()
        cookieButtonsLayout.addWidget(self.loadButton)
        cookieButtonsLayout.addWidget(self.saveButton)
        liveRecordingFormLayout.addRow(cookieButtonsLayout)

        # 네이버 로그인
        self.naverIdEdit = QLineEdit()
        self.naverPasswordEdit = QLineEdit()
        self.naverPasswordEdit.setEchoMode(QLineEdit.Password)  # 비밀번호 마스킹
        self.loginButton = QPushButton("네이버 로그인")
        self.loginButton.clicked.connect(self.performLogin)

        liveRecordingFormLayout.addRow("네이버 ID:", self.naverIdEdit)
        liveRecordingFormLayout.addRow("네이버 비밀번호:", self.naverPasswordEdit)
        liveRecordingFormLayout.addRow(self.loginButton)

        # 쿠키 안내문
        CookieLabel = QLabel("※ 네이버 로그인이 불가할 때만 쿠키값 직접입력 저장을 이용해 주세요.")
        CookieLabel.setAlignment(Qt.AlignCenter)
        liveRecordingFormLayout.addRow(CookieLabel)

    # 네이버 로그인폼 처리
    def performLogin(self):
        naver_id = self.naverIdEdit.text()
        naver_password = self.naverPasswordEdit.text()
        self.login_thread = LoginThread(naver_id, naver_password)
        self.login_thread.finished.connect(self.onLoginFinished)
        self.login_thread.start()

    # 네이버 로그인 결과 처리
    def onLoginFinished(self, success, message):
        if success:
            QMessageBox.information(self, "로그인 성공", message)
        else:
            QMessageBox.warning(self, "로그인 실패", message)

    # 로그인 정보 불러오기
    def load_login_info(self):
        config = load_config()
        naver_id = config.get('naver_id', '')
        naver_password = config.get('naver_password', '')

        try:
            with open(self.cookie_path, 'r') as file:
                cookie_data = json.load(file)
                nid_ses = cookie_data.get('NID_SES', '')
                nid_aut = cookie_data.get('NID_AUT', '')
        except FileNotFoundError:
            nid_ses, nid_aut = '', ''

        self.nid_ses_edit.setText(nid_ses)
        self.nid_aut_edit.setText(nid_aut)

        if not (naver_id and naver_password) and not (nid_ses and nid_aut):
            QMessageBox.warning(self, "로그인 정보 또는 쿠키 정보 없음", "로그인 정보 또는 쿠키 정보가 없습니다. 새로운 로그인 정보를 입력하거나 쿠키 값을 추가해주세요.")

    # 쿠키 값 저장
    def saveCookieData(self):
        nid_ses = self.nid_ses_edit.text()
        nid_aut = self.nid_aut_edit.text()
        cookie_data = {
            "NID_SES": nid_ses,
            "NID_AUT": nid_aut
        }
        with open(self.cookie_path, "w") as file:
            json.dump(cookie_data, file, indent=4)
        QMessageBox.information(self, "저장 완료", "쿠키 정보가 저장되었습니다.")

    # 쿠키 값 불러오기
    def loadCookieData(self):
        try:
            with open(self.cookie_path, 'r') as file:
                cookie_data = json.load(file)
                self.nid_ses_edit.setText(cookie_data.get('NID_SES', ''))
                self.nid_aut_edit.setText(cookie_data.get('NID_AUT', ''))
                QMessageBox.information(self, "불러오기 완료", "쿠키 정보를 불러왔습니다.")
        except FileNotFoundError:
            QMessageBox.warning(self, "파일 없음", "쿠키 정보 파일이 없습니다.")

    # 후처리 파일 저장 경로 선택
    def selectPostProcessingOutputDir(self):
        directory = QFileDialog.getExistingDirectory(self, "후처리 완료 파일 저장 경로 선택")
        if directory:
            self.postProcessingOutputDirLineEdit.setText(directory)

    
    # 후처리 완료 후 이동 설정 활성화/비활성화
    def toggleMoveAfterProcessingFields(self, text):
        enabled = (text == '사용')
        self.moveAfterProcessingLineEdit.setEnabled(enabled)
        self.moveAfterProcessingButton.setEnabled(enabled)

    # 후처리 완료 후 이동 경로 선택
    def selectMoveAfterProcessingPath(self):
        directory = QFileDialog.getExistingDirectory(self, "후처리 완료 후 이동할 폴더 선택")
        if directory:
            self.moveAfterProcessingLineEdit.setText(directory)

    # 설정 적용
    def applySettings(self):
        self.config['plugin'] = self.pluginComboBox.currentText()
        self.config['time_shift'] = int(self.time_shift_lineedit.text())
        self.config['recheckInterval'] = int(self.recheckIntervalLineEdit.text())
        auto_stop_interval = int(self.autoStopIntervalLineEdit.text())

        if auto_stop_interval == 0:
            QMessageBox.information(self, "분할 녹화 비활성화", "분할 녹화가 비활성화됩니다. 연속녹화가 설정되었습니다.")
            print("분할 녹화 비활성화: 분할 녹화가 비활성화됩니다. 연속녹화가 설정되었습니다.")
        else:
            print(f"Auto Stop Interval 설정됨: {auto_stop_interval}초")

        self.config['autoStopInterval'] = auto_stop_interval
        self.config['showMessageBox'] = self.showMessageBoxComboBox.currentText() == '표시'
        self.config['autoPostProcessing'] = self.autoPostProcessingComboBox.currentText() == '사용'
        self.config['deleteAfterPostProcessing'] = self.deleteAfterPostProcessingComboBox.currentText() == '사용'
        self.config['minimizePostProcessing'] = self.minimizePostProcessingComboBox.currentText() == '사용'
        self.config['removeFixedPrefix'] = self.removeFixedPrefixComboBox.currentText() == '사용'
        self.config['moveAfterProcessingEnabled'] = self.moveAfterProcessingComboBox.currentText() == '사용'
        self.config['moveAfterProcessing'] = self.moveAfterProcessingLineEdit.text()
        self.config['filenamePattern'] = self.filenamePatternLineEdit.text()
        self.config['postProcessingMethod'] = self.postProcessingMethodComboBox.currentText()
        post_processing_output_dir = self.postProcessingOutputDirLineEdit.text().strip()
        self.config['postProcessingOutputDir'] = post_processing_output_dir if post_processing_output_dir else None

        self.config['videoCodec'] = self.videoCodecComboBox.currentText()
        self.config['qualityOrBitrate'] = self.qualityOrBitrateComboBox.currentText()

        # h264_qsv 선택 시 videoQuality를 global_quality로 설정
        if self.config['videoCodec'] == 'h264_qsv':
            self.config['videoQuality'] = self.videoQualityLineEdit.text().strip() if self.videoQualityLineEdit.text().strip() else '25'
        # h264_nvenc 선택 시 videoQuality를 cqp로 설정
        elif self.config['videoCodec'] == 'h264_nvenc':
            self.config['videoQuality'] = self.videoQualityLineEdit.text().strip() if self.videoQualityLineEdit.text().strip() else '23'
        # h264_amf 선택 시 videoQuality를 qvbr_quality_level로 설정
        elif self.config['videoCodec'] == 'h264_amf':
            self.config['videoQuality'] = self.videoQualityLineEdit.text().strip() if self.videoQualityLineEdit.text().strip() else '23'
        else:
            self.config['videoQuality'] = self.videoQualityLineEdit.text().strip() if self.videoQualityLineEdit.text().strip() else None

        self.config['videoBitrate'] = self.videoBitrateLineEdit.text().strip() if self.videoBitrateLineEdit.text().strip() else None
        self.config['preset'] = self.presetComboBox.currentText()
        self.config['audioCodec'] = self.audioCodecComboBox.currentText()
        self.config['audioBitrate'] = self.audioBitrateComboBox.currentText()

        save_config(self.config)
        QMessageBox.information(self, "적용 완료", "설정이 저장되었습니다. 프로그램을 재시작해 주세요.")
        self.close()


    # 후처리 방법에 따라 옵션 표시/숨김
    def togglePostProcessingOptions(self, method):
        if method == '스트림복사':
            self.encodingOptionsWidget.hide()
        else:
            self.encodingOptionsWidget.show()

    # 비디오 설정에 따라 퀄리티/비트레이트 필드 표시/숨김
    def toggleQualityOrBitrateFields(self, setting):
        if setting == '퀄리티':
            self.videoQualityLineEdit.show()
            self.videoBitrateLineEdit.hide()
        else:
            self.videoQualityLineEdit.hide()
            self.videoBitrateLineEdit.show()

    # 프리셋 콤보박스 업데이트
    def updatePresetComboBox(self):
        codec_map = {
            'x264(CPU)': 'x264',
            'h264_qsv(인텔 GPU가속)': 'h264_qsv',
            'h264_nvenc(엔비디아 GPU가속)': 'h264_nvenc',
            'h264_amf(AMD GPU가속)': 'h264_amf'
        }

        selected_codec = codec_map.get(self.videoCodecComboBox.currentText())
        self.presetComboBox.clear()
        if selected_codec in codec_presets:
            self.presetComboBox.addItems(codec_presets[selected_codec])
        self.presetComboBox.setCurrentText(self.config.get('preset', 'medium'))


if __name__ == '__main__':
    app = QApplication(sys.argv)
    settingsWindow = SettingsWindow()
    settingsWindow.show()
    sys.exit(app.exec_())