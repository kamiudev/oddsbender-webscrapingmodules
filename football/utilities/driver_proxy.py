import random
import os
from selenium import webdriver
from selenium.webdriver.support.ui import WebDriverWait
from selenium.common.exceptions import NoSuchElementException, WebDriverException
from selenium.webdriver.common.desired_capabilities import DesiredCapabilities
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

BASE_DIR = (os.path.dirname(os.path.abspath(__file__)))

with open(f'{BASE_DIR}/proxies.txt', 'r') as ff:
    HTTP_PROXIES = list(ff.readlines())

def get_random_proxy(HTTP_PROXIES):
    random_idx = random.randint(1, len(HTTP_PROXIES) - 1)
    proxy_ip = HTTP_PROXIES[random_idx]
    return proxy_ip

enable_docker_selenium = True
global_status_url = 'http://test:test-password@104.225.133.40:4444'

def set_driver(remote=False, use_grid=False):
    i = 0
    global user_agents_list
    while i < 3:
        i += 1
        try:
            proxy_ip = get_random_proxy(HTTP_PROXIES)
            if (enable_docker_selenium == True):
                remote_url = global_status_url + '/wd/hub'

            webdriver.DesiredCapabilities.CHROME['proxy'] = {
                'httpProxy': proxy_ip,
                'ftpProxy': proxy_ip,
                'sslProxy': proxy_ip,
                'proxyType': 'MANUAL',
            }
            user_agents = ['Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/105.0.0.0 Safari/537.36']

            user_agent = user_agents[random.randint(0, len(user_agents) - 1)]

            print(proxy_ip, user_agent)

            chrome_options = webdriver.ChromeOptions()
            chrome_options.add_argument('--headless')
            chrome_options.add_argument('--no-sandbox')
            chrome_options.add_argument('--disable-infobars')
            chrome_options.add_argument('--disable-dev-shm-usage')
            chrome_options.add_argument('--disable-browser-side-navigation')
            chrome_options.add_argument('--disable-features=VizDisplayCompositor')
            chrome_options.add_argument('--blink-settings=imagesEnabled=false')
            chrome_options.add_argument('--disable-gpu')
            chrome_options.add_argument('--force-device-scale-factor=1')
            chrome_options.add_argument('--disable-backgrounding-occluded-windows')
            chrome_options.add_argument('--disable-extensions')
            chrome_options.add_argument('--start-maximized')
            chrome_options.add_argument('--ignore-certificate-errors')
            # chrome_options.add_argument("--incognito")
            chrome_options.add_argument(f'--proxy-server={proxy_ip}')
            chrome_options.add_argument('--allow-running-insecure-content')
            chrome_options.add_experimental_option('prefs', {'intl.accept_languages': 'en,en_US'})
            chrome_options.add_argument("--disable-blink-features")
            chrome_options.add_argument('--disable-blink-features=AutomationControlled')
            chrome_options.add_argument(f'user-agent={user_agent}')
            chrome_options.add_argument('enable-automation')
            experimentalFlags = ['calculate-native-win-occlusion@2']
            chromeLocalStatePrefs = {'browser.enabled_labs_experiments': experimentalFlags}
            chrome_options.add_experimental_option('localState', chromeLocalStatePrefs)
            chrome_options.add_experimental_option('excludeSwitches', ['enable-automation'])
            chrome_options.add_experimental_option('useAutomationExtension', False)

            capabilities = DesiredCapabilities().CHROME
            capabilities['pageLoadStrategy'] = 'normal'
            driver = webdriver.Remote(command_executor=remote_url, desired_capabilities=capabilities,
                                          options=chrome_options)

            if driver is not None:
                driver.set_window_size(1920, 1080)
                driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
                driver.set_page_load_timeout(300)
                print('================driver created================')
                return driver
            else:
                continue
        except Exception as ex:
            print(ex)
            return None
    print('================failed to create driver================')
    return None



def get_driver_proxy():
    driver = set_driver()
    return driver