from os import environ
import time
from configparser import ConfigParser
from datetime import datetime
from random import randrange

from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from utilities.logging import get_logger
from utilities.utils import get_driver, str_to_timedelta, actions_on_page
from utilities.redis import RedisClient

# read config file
config_parser = ConfigParser()
config_parser.read('conf/draftkings.conf')
module_conf = config_parser["MODULE"]

# init logging
logger_name = environ.get('basketball_draftkings_url_get_logger', 'basketball_draftkings_url_logger')
# for local logs storage and stdout use DEBUG_FLAG = 1
DEBUG_FLAG = environ.get('URL_LOG_DEBUG_FLAG', 1)
log_level = environ.get('basketball_draftkings_url_log_level', 'INFO')

logger = get_logger(logger_name, DEBUG_FLAG, log_level)

# other variables
URL = environ.get('basketball_draftkings_url', module_conf.get('URL'))
module_work_duration = str_to_timedelta(environ.get('basketball_draftkings_url_module_work_duration', module_conf.get('module_work_duration')))
update_frequency = str_to_timedelta(environ.get('basketball_draftkings_url_update_frequency', module_conf.get('update_frequency')))
browser = environ.get('basketball_draftkings_url_browser', module_conf.get('browser_url'))

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
            check_game = False
            
            try:
                # check if football is in live games
                check_game_list = WebDriverWait(driver, 10).until(EC.visibility_of_all_elements_located(
                    (By.XPATH, "//span[@class='sportsbook-tabbed-subheader__tab']")))
                for fg in check_game_list:
                    if fg.text == 'BASKETBALL':
                        check_game = True
                        break
            except Exception as error:
                logger.exception(f"Problem with extracting the name of the game\n{error}")
                

            if check_game:
                hidden_games = True
                while hidden_games:
                    try:
                        get_hidden_games = WebDriverWait(driver, 3).until(EC.visibility_of_all_elements_located(
                            (By.XPATH, "//div[@class='sportsbook-featured-accordion__wrapper sportsbook-accordion__wrapper collapsed']")))
                        if len(get_hidden_games) > 0:
                            [i.click() for i in get_hidden_games]
                    except:
                        hidden_games = False

                # get all live games
                match_rows = driver.find_elements(By.XPATH, '//div[@class="sportsbook-header__title"]/a[contains(text(), "College Basketball") or contains(text(), "NBA")]/ancestor::div[contains(@class, "sportsbook-featured-accordion__wrapper sportsbook-accordion")]')
                for match_row in match_rows:
                    games_on_initial_page = WebDriverWait(match_row, 10).until(EC.visibility_of_all_elements_located(
                            (By.XPATH, "//a[@class='event-cell-link']")))
                    urls_list = []
                    for game in games_on_initial_page:
                        if game.get_attribute('href') not in urls_list:
                            urls_list.append(game.get_attribute('href'))
                    logger.info(f"Found {len(urls_list)} url's")

                    # save data to redis db
                    for rd_url in urls_list:
                        stream_name = rd_url.split('/')
                        saving_result = redisClient.add_url_redis(rd_url, 'draftkings', f'basketball_draftkings_prop_{stream_name[-1]}')
                        logger.info(f'Result: {saving_result}')                
                    count_scraps += 1
                # reset unsuccessful attempts in main loop
                failure_count = 0
            
            else:
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
            actions_on_page(driver=driver, class_name="sportsbook-tabbed-subheader__tab selected")
            if count_scraps == scrap_limit:
                driver.refresh()                
                count_scraps = 0

        parsing_work_time = time.time() - parsing_start_time
        time.sleep(max(0, update_frequency.total_seconds() - parsing_work_time))

    driver.quit()
    logger.warning('Script successfully ended working at the set time')


if __name__ == "__main__":
    main()
