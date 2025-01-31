import time
import pyperclip
import pickle
import json
import os
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver import ActionChains, Keys
from selenium.webdriver.common.by import By
from selenium import webdriver
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from webdriver_manager.chrome import ChromeDriverManager

class NaverLoginService():
    def __init__(self):
        self.driver = None
        self.script_dir = os.path.dirname(os.path.abspath(__file__))
        self.base_dir = os.path.dirname(self.script_dir)
        self.json_dir = os.path.join(self.base_dir, 'json')

    def open_web_mode(self, headless=True):
        chrome_options = Options()
        if headless:
            chrome_options.add_argument("--headless")  # headless 모드 설정
        self.driver = webdriver.Chrome(service=ChromeService(ChromeDriverManager().install()), options=chrome_options)
        self.driver.set_page_load_timeout(15)

    def close_browser(self):
        if self.driver:
            self.driver.quit()
            self.driver = None

    def login(self, Naver_id, Naver_passwd):
        try:
            self.open_web_mode(headless=False)
            self.driver.get("https://nid.naver.com/nidlogin.login")
            time.sleep(2)

            # 아이디 입력
            wait = WebDriverWait(self.driver, 10)
            id_input = wait.until(EC.visibility_of_element_located((By.ID, "id")))
            id_input.click()
            pyperclip.copy(Naver_id)
            actions = ActionChains(self.driver)
            actions.key_down(Keys.CONTROL).send_keys('v').key_up(Keys.CONTROL).perform()
            time.sleep(1)

            # 패스워드 입력
            pw_input = wait.until(EC.visibility_of_element_located((By.ID, "pw")))
            pw_input.click()
            pyperclip.copy(Naver_passwd)
            actions.key_down(Keys.CONTROL).send_keys('v').key_up(Keys.CONTROL).perform()
            time.sleep(1)

            # 로그인 유지 체크
            self.driver.execute_script("document.getElementById('keep').click();")
            time.sleep(1)  # 입력 후 잠시 대기

            # 로그인 버튼 클릭
            self.driver.find_element(By.ID, "log.login").click()

            # 페이지 로딩 대기
            try:
                element = WebDriverWait(self.driver, 10).until(
                    EC.presence_of_element_located((By.ID, "right-content-area"))
                )
                print("로딩완료")
            except Exception as e:
                print(f"페이지 로딩 중 오류 발생: {e}")
                raise e

            # 스크립트 파일이 위치한 디렉토리에 쿠키 저장 naver_cookies.pkl
            cookies = self.driver.get_cookies()
            nid_file_path = os.path.join(self.json_dir, 'naver_cookies.pkl') 
            with open(nid_file_path, 'wb') as f:
                pickle.dump(cookies, f)
                print('PKL 쿠키 저장 완료')

            # NID 정보 저장
            print(f"Driver status before getting cookies: {self.driver}")
            nid_info = {
                'NID_SES': self.driver.get_cookie("NID_SES")['value'] if self.driver.get_cookie("NID_SES") else None,
                'NID_AUT': self.driver.get_cookie("NID_AUT")['value'] if self.driver.get_cookie("NID_AUT") else None
            }

            print(f"NID_SES: {nid_info['NID_SES']}")
            print(f"NID_AUT: {nid_info['NID_AUT']}")

            if not nid_info['NID_SES'] or not nid_info['NID_AUT']:
                raise ValueError("NID_SES 또는 NID_AUT 쿠키를 가져올 수 없습니다.")
            
            self.nid_save(nid_info)

        except Exception as e:
            print(f"로그인 중 오류 발생: {e}")
            raise e
        finally:
            self.close_browser()

    def nid_save(self, nid_info):
        # NID 정보 저장
        try:
            # json 디렉토리에 cookie.json 저장
            cookie_file_path = os.path.join(self.json_dir, 'cookie.json')
            with open(cookie_file_path, 'w') as f:
                json.dump(nid_info, f, indent=4)
                print('NID 쿠키 저장 완료')
        except Exception as e:
            print(f"NID 정보 저장 중 오류 발생: {e}")
            raise e
