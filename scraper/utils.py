from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.service import Service
from typing import Optional

def configure_driver(prefs:Optional[dict]) -> webdriver.Chrome:
        """Adds the options used in the browser"""
        chrome_options = Options()
        if prefs:
            chrome_options.add_experimental_option("prefs",prefs)
        #chrome_options.add_argument("--headless")
        chrome_options.add_argument("--disbale-gpu")
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        chrome_options.add_argument("--disbale-dev-smh-usage")
        chrome_options.add_argument("--disable-interface")
        chrome_options.page_load_strategy = 'eager'
        driver = webdriver.Chrome(options=chrome_options,service=Service(ChromeDriverManager().install()))
        return driver

def check_for_toggle(driver:webdriver.Chrome):
    def use_wapper(self,func):
        def wrapper(*args,**kwargs):
            func(*args,**kwargs)
            toggle_icon = driver.find_element(By.CSS_SELECTOR,'span.svg-icon.svg-icon-2x.mt-1')
            if toggle_icon:
                toggle_icon.click()  
            else:
                pass
        return wrapper
    return use_wapper