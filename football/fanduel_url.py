from os import environ
import time
from configparser import ConfigParser
from datetime import datetime
from random import randrange

from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from utilities.logging import get_logger
from utilities.utils import get_driver, str_to_timedelta, add_url_redis, actions_on_page
from utilities.driver_proxy import get_driver_proxy


# read config file
config_parser = ConfigParser()
config_parser.read('conf/fanduel.conf')
module_conf = config_parser["MODULE"]

# init logging
logger_name = environ.get('football_fanduel_url_get_logger', 'football_fanduel_url_logger')
# for local logs storage and stdout use DEBUG_FLAG = 1
DEBUG_FLAG = environ.get('football_fanduel_url_DEBUG_FLAG', 0)
log_level = environ.get('football_fanduel_url_log_level', 'WARNING')

logger = get_logger(logger_name, DEBUG_FLAG, log_level)

# other variables
URL = environ.get('football_fanduel_url', module_conf.get('URL'))
module_work_duration = str_to_timedelta(environ.get('football_fanduel_url_module_work_duration', module_conf.get('module_work_duration')))
update_frequency = str_to_timedelta(environ.get('football_fanduel_url_update_frequency', module_conf.get('update_frequency')))
browser = environ.get('football_fanduel_url_browser', module_conf.get('browser_url'))

scrap_step = int(environ.get('football_scrap_step', module_conf.get('scrap_step')))
scrap_limit = int(environ.get('football_scrap_limit', module_conf.get('scrap_limit')))

# init web driver
# driver = get_driver(browser)
# driver.get(URL)
driver = None

logger.warning(f'Module started working with parameters:\nURL: {URL}\nmodule_work_duration: {module_work_duration}\nupdate_frequency: {update_frequency}\nbrowser: {browser}\nlogger_name: {logger_name}\nlog_level: {log_level}\nDEBUG_FLAG: {DEBUG_FLAG}')

def check_capture():
    global driver
    while True:
        try:
            driver = get_driver_proxy()
            driver.get(URL)
            driver.find_element(By.XPATH, '//h1[contains(text(), "Please verify you are a human")]').text
            logger.error('Please verify you are a human')
            time.sleep(3)
            driver.quit()
            continue
        except:
            break

def main():
    module_operate_until = datetime.now() + module_work_duration
    exception_counter = 0
    count_scraps = 0

    global driver
    check_capture()

    while datetime.now() < module_operate_until:
        additional_param = {}
        try:
            parsing_start_time = time.time()
            logger.info(f'Start scraping urls')

            # click on Football game
            click_game_source = driver.find_elements(By.XPATH, "//a[contains(@href,'/live')]")
            [game.click() for game in click_game_source if 'Football' in game.text]
            logger.info('The game selection button has been clicked')

            # get sport and type_game
            try:
                get_sport = WebDriverWait(driver, 10).until(
                    EC.visibility_of_element_located((By.XPATH, "//h2[contains(text(),'Live ')]"))).text.split(' ')[1]
                additional_param['sport'] = get_sport
            except:
                additional_param['sport'] = 'Not identified'
                logger.error('It’s impossible to identify game type')

            if additional_param.get('sport') == 'Football':
                urls_list = []

                football_games = driver.find_elements(By.XPATH, '//a[contains(@href, "football/")]/parent::div')

                for football_game in football_games:
                    tmp_url = football_game.find_element(By.XPATH, './a').get_attribute('href')

                    if (tmp_url not in urls_list
                        and ('nfl' in tmp_url or 'ncaa' in tmp_url)):
                        urls_list.append(tmp_url)
            
                logger.info(f"Found {len(urls_list)} url's")

                # save data to redis db
                for rd_url in urls_list:
                    stream_name = rd_url.split('/')[-1]
                    saving_result = add_url_redis(rd_url, 'fanduel', f'football_fanduel_prop_{stream_name}')
                    logger.info(f'Result: {saving_result}')                
                count_scraps += 1
                
                parsing_work_time = time.time() - parsing_start_time
                time.sleep(max(0, update_frequency.total_seconds() - parsing_work_time))                

                exception_counter = 0

            if additional_param.get('sport') != 'Football':
                logger.warning('There are no live games, waiting for some time and trying again')
                time.sleep(randrange(4000, 12000, 10) / 1000)
                driver.get(URL)

        except KeyboardInterrupt:
            logger.info("Keyboard Interrupt. Quit the driver!")
            driver.quit()
            logger.warning(f'Module stopped working')
            break

        except Exception as e:
            logger.exception(f"Exception in main scraping cycle. {e}")
            exception_counter += 1
            if exception_counter >= 5:
                driver.quit()
                logger.exception(
                    f'Script exited after {exception_counter} unsuccessful attempts to execute the main loop')
                break
                
        if count_scraps % scrap_step == 0:
            actions_on_page(driver=driver, class_name="")
            if count_scraps == scrap_limit:
                driver.refresh()                
                count_scraps = 0

    driver.quit()
    logger.warning(f'Module stopped working')


if __name__ == "__main__":
    main()
