from os import environ
import time
from configparser import ConfigParser
from datetime import datetime
from random import randrange

from bs4 import BeautifulSoup
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from utilities.logging import get_logger
from utilities.utils import get_driver, str_to_timedelta, add_url_redis, actions_on_page

# read config file
config_parser = ConfigParser()
config_parser.read('conf/betmgm.conf')
module_conf = config_parser["MODULE"]

# init logging
logger_name = environ.get('football_betmgm_url_get_logger', 'football_betmgm_url_logger')
# for local logs storage and stdout use DEBUG_FLAG = 1
DEBUG_FLAG = environ.get('football_betmgm_url_DEBUG_FLAG', 0)
log_level = environ.get('football_betmgm_url_log_level', 'WARNING')

logger = get_logger(logger_name, DEBUG_FLAG, log_level)

# other variables
URL = environ.get('football_betmgm_url', module_conf.get('URL'))
module_work_duration = str_to_timedelta(environ.get('football_betmgm_url_module_work_duration', module_conf.get('module_work_duration')))
update_frequency = str_to_timedelta(environ.get('football_betmgm_url_update_frequency', module_conf.get('update_frequency')))
browser = environ.get('football_betmgm_url_browser', module_conf.get('browser_url'))

scrap_step = int(environ.get('football_scrap_step', module_conf.get('scrap_step')))
scrap_limit = int(environ.get('football_scrap_limit', module_conf.get('scrap_limit')))

# init web driver
driver = get_driver(browser)
driver.get(URL)

logger.warning(f'Module started working with parameters:\nURL: {URL}\nmodule_work_duration: {module_work_duration}\nupdate_frequency: {update_frequency}\nbrowser: {browser}\nlogger_name: {logger_name}\nlog_level: {log_level}\nDEBUG_FLAG: {DEBUG_FLAG}')


def main():
    module_operate_until = datetime.now() + module_work_duration

    failure_count = 0
    count_scraps = 0

    while datetime.now() < module_operate_until:
        parsing_start_time = time.time()
        try:
            logger.info(f'Start scraping urls')

            try:
                # check if football is in live games
                check_game = WebDriverWait(driver, 10).until(EC.visibility_of_all_elements_located(
                    (By.XPATH, "//*[@class='tab-bar-item active ng-star-inserted']")))
                check_game_res = [i.text for i in check_game if 'Football' in i.text]
            except:
                check_game_res = ''

            if check_game_res:
                # get all live games
                games_on_initial_page = WebDriverWait(driver, 10).until(EC.visibility_of_element_located(
                    (By.XPATH, "//div[@class='grid-wrapper ng-star-inserted']")))
                soup = BeautifulSoup(games_on_initial_page.get_attribute('innerHTML'), "html.parser")

                get_hrefs = soup.find_all("a", {"class": "grid-info-wrapper fixed"})

                urls_list = [f"https://sports.nj.betmgm.com{gf['href']}" for gf in get_hrefs]
                logger.info(f"Found {len(urls_list)} url's")

                # save data to redis db
                for rd_url in urls_list:
                    stream_name = rd_url.split('-')[-1]
                    saving_result = add_url_redis(rd_url, 'betmgm', f'football_betmgm_prop_{stream_name}')
                    logger.info(f'Result: {saving_result}')                
                count_scraps += 1

                # reset unsuccessful attempts in main loop
                failure_count = 0

            if not check_game_res:
                logger.warning('There are no live games, waiting for some time and trying again')
                time.sleep(randrange(4000, 12000, 10) / 1000)
                driver.get(URL)
                driver.refresh()

        except KeyboardInterrupt:
            logger.info("Keyboard Interrupt. Quit the driver!")
            driver.quit()
            logger.warning(f'Module stopped working')
            break

        except Exception as e:
            logger.exception(f'Stop script with errors:\n{e}')
            failure_count += 1
            if failure_count >= 5:
                driver.quit()
                logger.exception(f'Script exited after {failure_count} unsuccessful attempts to start the main loop')
                break
        
        if count_scraps % scrap_step == 0:
            actions_on_page(driver=driver, class_name="grid-wrapper ng-star-inserted")
            if count_scraps == scrap_limit:
                driver.refresh()                
                count_scraps = 0

        parsing_work_time = time.time() - parsing_start_time
        time.sleep(max(0, update_frequency.total_seconds() - parsing_work_time))

    driver.quit()
    logger.warning('Script successfully ended working at the set time')


if __name__ == "__main__":
    main()
