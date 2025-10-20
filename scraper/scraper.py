import time
import os
from pathlib import Path
from selenium import webdriver
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.common.keys import Keys
from utils import *

BASE_DIR:str = Path(__file__).resolve().parent
UPLOADS_DIR:str = os.path.join(BASE_DIR,"uploads")
FILE_LOCATION:str = lambda file:os.path.join(UPLOADS_DIR,file)


class ReceiptDownloader:
    def __init__(self,download_loc:str):
        self.chrome_options = Options()
        prefs = {
            "download.default_directory":FILE_LOCATION(download_loc),
            "profile.default_content_settings.popups":0,
            "download.prompt_for_download":False,
            "profile.default_content_setting_values.automatic_downloads":1,
            "safebrowsing.enabled":False
            }
        add_options(self.chrome_options,prefs)
        self.driver = webdriver.Chrome(options=self.chrome_options,service=Service(ChromeDriverManager().install()))
        url = "https://ecampus.fuotuoke.edu.ng/ecampus/login.html"
        self.driver.get(url)
        self.driver.implicitly_wait(30)


    @check_for_toggle(self.driver)
    def login(self,name:str,password:str):
        username_box = self.driver.find_element(By.ID,"username")
        username_box.clear()
        username_box.send_keys(name)
        continue_button = self.driver.find_element(By.CSS_SELECTOR,"a[onclick='nextStep()']")
        continue_button.click()
        password_box = self.driver.find_element(By.ID,'password')
        password_box.clear()
        password_box.send_keys(password)
        signin_btn = self.driver.find_element(By.ID,"btn_login")
        signin_btn.click()


class CoursesDownloader:
    pass

class ResultsDownloader:
    pass

async def main():
    pass