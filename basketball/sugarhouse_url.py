from os import environ
import time
from configparser import ConfigParser
from datetime import datetime
from random import randrange

from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.common.keys import Keys
from utilities.logging import get_logger
from utilities.utils import get_driver, str_to_timedelta, actions_on_page
from utilities.redis import RedisClient

# read config file
config_parser = ConfigParser()
config_parser.read('conf/sugarhouse.conf')
module_conf = config_parser["MODULE"]

# init logging
logger_name = environ.get('basketball_sugarhouse_url_get_logger', 'basketball_sugarhouse_url_logger')
# for local logs storage and stdout use DEBUG_FLAG = 1
DEBUG_FLAG = environ.get('URL_LOG_DEBUG_FLAG', 1)
log_level = environ.get('basketball_sugarhouse_url_log_level', 'WARNING')

logger = get_logger(logger_name, DEBUG_FLAG, log_level)

# other variables
URL = environ.get('basketball_sugarhouse_url', module_conf.get('URL'))
module_work_duration = str_to_timedelta(environ.get('basketball_sugarhouse_url_module_work_duration', module_conf.get('module_work_duration')))
update_frequency = str_to_timedelta(environ.get('basketball_sugarhouse_url_update_frequency', module_conf.get('update_frequency')))
browser = environ.get('basketball_sugarhouse_url_browser', module_conf.get('browser_url'))

scrap_step = int(environ.get('basketball_scrap_step', module_conf.get('scrap_step')))
scrap_limit = int(environ.get('basketball_scrap_limit', module_conf.get('scrap_limit')))

# init web driver
driver = get_driver(browser)
driver.get(URL)

redisClient = RedisClient()

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
                # check if basketball is in live games
                get_check_game = WebDriverWait(driver, 10).until(EC.presence_of_element_located(
                    (By.XPATH, "//*[@alt='Basketball']")))
                check_game = 'Basketball' if get_check_game else ""
            except:
                check_game = ''

            if 'Basketball' in check_game:
                # open NBA
                try:
                    hidden_tabs = driver.find_elements(By.XPATH, "//*[@aria-expanded='false']")
                    for hidden_tab in hidden_tabs:

                        if 'NBA' in hidden_tab.get_attribute('id') or 'NCAAB' in hidden_tab.get_attribute('id'):
                            hidden_tab.click()
                            logger.info(f'Opened {hidden_tab.text}')
                except:
                    logger.info('All tabs opened')

                # close other tabs
                try:
                    unhidden_tabs = driver.find_elements(By.XPATH, "//*[@aria-expanded='true']")
                    for unhidden_tab in unhidden_tabs:
                        if 'NBA' not in unhidden_tab.get_attribute('id') and 'NCAAB' not in unhidden_tab.get_attribute(
                                'id'):
                            unhidden_tab.click()
                            logger.info(f'Closed {unhidden_tab.text}')
                except:
                    logger.info('All tabs closed')

                body = driver.find_element(By.CSS_SELECTOR, 'body')
                all_games = []

                for i in range(10):
                    for tmp_game in driver.find_elements(By.XPATH, "//div[contains(@id, 'listview-group-')]"):
                        all_games.append(tmp_game.get_attribute('data-testid'))

                    body.send_keys(Keys.PAGE_DOWN)
                    time.sleep(0.1)

                    try:
                        show_more = driver.find_element(By.XPATH, "//*[contains(text(),'Show more')]")
                        driver.execute_script("arguments[0].click();", show_more)
                        logger.info('Clicked button - Show more games')
                    except:
                        pass

                logger.info(f'Found {len(all_games)} unfiltered rows')

                urls_list = []
                for basketball_game in all_games:
                    game_name = basketball_game.split('-')[-1]
                    url = f'https://pa.playsugarhouse.com/?page=sportsbook#event/live/{game_name}'
                    urls_list.append(url) if url not in urls_list else None

                logger.info(f"Found {len(urls_list)} url's")

                # save data to redis db
                for rd_url in urls_list:
                    stream_name = rd_url.split('/')[-1]
                    saving_result = redisClient.add_url_redis(rd_url, 'sugarhouse', f'basketball_sugarhouse_prop_{stream_name}')
                    logger.info(f'Result: {saving_result}')                
                count_scraps += 1

                # reset unsuccessful attempts in main loop
                failure_count = 0

                if len(urls_list) == 0:
                    logger.warning('There are no live games, waiting for some time and trying again')
                    time.sleep(randrange(4000, 12000, 10) / 1000)
                    driver.refresh()
                    continue

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
            actions_on_page(driver=driver, class_name="sc-fzXfNO gPURds")
            if count_scraps == scrap_limit:
                driver.refresh()                
                count_scraps = 0

        parsing_work_time = time.time() - parsing_start_time
        time.sleep(max(0, update_frequency.total_seconds() - parsing_work_time))

    driver.quit()
    logger.warning('Script successfully ended working at the set time')


if __name__ == "__main__":
    main()
