from user_agent import generate_user_agent

import pandas as pd
import redis
from selenium import webdriver
from selenium.webdriver.chrome.service import Service as ChromeService
from webdriver_manager.chrome import ChromeDriverManager
from utilities.logging import get_logger

import random
import time
from selenium.webdriver.common.by import By
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.keys import Keys

logger = get_logger("redis_logger", "1", "INFO")

class DriverClient(object):
    def __init__(self, driver=None) -> None:
        # self.browser = browser
        if driver:
            self.driver = driver

    def get_driver(self, browser, use_arguments=False):
        arguments_list = [
            '--headless',
            '--no-sandbox',
            '--disable-dev-shm-usage',
            '--incognito',
            '--window-size=1920,1080',
            '--disable-blink-features=AutomationControlled',
            f"user-agent={generate_user_agent(device_type='desktop')}",
        ]

        if use_arguments:
            arguments_list += [
                '--disable-logging',
                '--disable-extensions',
                '--disable-gpu',
                '--disable-infobars',
                'enable-automation',
                '--disable-dev-shm-usage',
                '--incognito',
            ]
        if browser == 'Chrome':
            options = webdriver.ChromeOptions()
            [options.add_argument(argument) for argument in arguments_list]
            service = ChromeService(ChromeDriverManager().install())
            driver = webdriver.Chrome(service=service, options=options)
        elif browser == 'Firefox':
            options = webdriver.FirefoxOptions()
            [options.add_argument(argument) for argument in arguments_list]
            driver = webdriver.Firefox(executable_path="geckodriver", options=options)

        return driver

    def actions_on_page(self, class_name: str):
        action = ActionChains(self.driver)
        try:
            element = self.driver.find_element(By.CLASS_NAME, class_name)
            action.move_to_element(element).perform()
        except:
            pass
        random_scroll_pixel = random.randint(100, 500)
        self.driver.execute_script(f"window.scrollBy(0, {random_scroll_pixel});")
        body = self.driver.find_element(By.XPATH, "//body")
        body.send_keys(Keys.CONTROL + 'a')
        body.send_keys(Keys.HOME)
        time.sleep(0.3)

    def set_driver(self, driver):
        self.driver = driver
    def quit(self):
        return self.driver.quit()