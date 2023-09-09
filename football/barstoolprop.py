import time
from configparser import ConfigParser
from datetime import datetime
from os import environ

from selenium.common.exceptions import NoSuchElementException, TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from utilities.logging import get_logger
from utilities.utils import get_driver, split_string, str_to_timedelta, add_data_redis, update_redis_status, actions_on_page, text_filter


# read config file
config_parser = ConfigParser()
config_parser.read('conf/barstool.conf')
module_conf = config_parser["MODULE"]

# init logging
logger_name = environ.get('football_barstoolprop_get_logger', 'football_barstool_prop')
# for local logs storage and stdout use DEBUG_FLAG = 1
DEBUG_FLAG = environ.get('PROP_LOG_DEBUG_FLAG', 0)
log_level = environ.get('football_barstoolprop_log_level', 'WARNING')

logger = get_logger(logger_name, DEBUG_FLAG, log_level)

# other variables
URL = environ['barstool_prop_url']
file_tail = URL.split('/')[-1].split('?')[0]

allowed_bets = ['quarter', 'half', 'total', 'spread', 'moneyline']

module_work_duration = str_to_timedelta(environ.get('football_barstoolprop_module_work_duration', module_conf.get('module_work_duration')))
update_frequency = str_to_timedelta(environ.get('football_barstoolprop_update_frequency', module_conf.get('update_frequency')))
browser = environ.get('football_barstoolprop_browser', module_conf.get('browser_prop'))

scrap_step = int(environ.get('football_scrap_step', module_conf.get('scrap_step')))
scrap_limit = int(environ.get('football_scrap_limit', module_conf.get('scrap_limit')))

# init web driver
driver = get_driver(browser)
driver.get(URL)

logger.warning(f'Module started working with parameters:\nURL: {URL}\nmodule_work_duration: {module_work_duration}\nupdate_frequency: {update_frequency}\nbrowser: {browser}\nlogger_name: {logger_name}\nlog_level: {log_level}\nDEBUG_FLAG: {DEBUG_FLAG}')


def is_odds(string):
    try:
        numb = int(string)
        if abs(numb) >= 100:
            return True
        return False
    except:
        return False


def split_bet(string):
    if "\n" in string:
        res = string.split("\n")
        if is_odds(res[-1]):
            return " ".join(res[:-1]), res[-1]
        return " ".join(res), ""
    elif string:
        return string, ""
    else:
        return "", ""

def click_on_web_element(element: WebElement):
    driver.execute_script("arguments[0].scrollIntoView(true);", element)
    WebDriverWait(driver, 10).until(EC.element_to_be_clickable(element))
    driver.execute_script("arguments[0].click();", element)


def expand_bets(active_page):
    closed_bets_panels = active_page.find_elements(By.XPATH, ".//div[@aria-expanded='false']/button")
    list(map(click_on_web_element, closed_bets_panels))
    view_all_button = active_page.find_elements(By.XPATH, ".//button[@aria-label='view all hidden outcomes']")
    list(map(click_on_web_element, view_all_button))


def scrape_prop_bets(active_page):
    game_time = driver.find_elements(By.XPATH, "//div[@class='match-clock h-24']")
    game_time = game_time[0].text if game_time else ''
    is_timeout = 1 if "10:00" in game_time or "12:00" in game_time else 0
    
    bets_panels = active_page.find_elements(By.XPATH, ".//div[@class='v-expansion-panel v-expansion-panel--active  expansion-panel-active expansion-panel-wrapper']")
    if bets_panels == []:
        logger.warning('There is no bets')
        time.sleep(5)
        return []

    logger.warning(f'Start scraping bets')
    prop_bet_list = []
    for bets_panel in bets_panels:
        driver.execute_script("arguments[0].scrollIntoView(true);", bets_panel)
        bet_button = bets_panel.find_element(By.XPATH, ".//button")
        bet_name = bet_button.text.split("\n")[0]

        if any(ab in bet_name.lower() for ab in allowed_bets):
            aligned_bet_name = bet_name.replace(home_team, 'Home Team').replace(away_team, 'Away Team')

            bet_contents = bets_panel.find_elements(By.XPATH, ".//label")
            bet_contents = [bet_content.text for bet_content in bet_contents]
            for bet_content in bet_contents:
                bet_type, odds = split_bet(bet_content)
                prop_bet_dict = {
                    'SPORT': sport,
                    'GAME_TYPE': game_type,
                    'IS_PROP': 1,
                    'GAME_NAME': game_name,
                    'BET_NAME': bet_name,
                    'BET_TYPE': bet_type,
                    'ODDS': odds,
                    'HOME_TEAM': home_team,
                    'AWAY_TEAM': away_team,
                    'ALIGNED_BET_NAME': aligned_bet_name,
                    'ALIGNED_BET_TYPE': text_filter(bet_type),
                    'GAME_TIME': game_time,
                    'IS_TIMEOUT': is_timeout,
                    'SPORTS_BOOK': 'Barstool',
                    'TIMESTAMP': time_stamp,
                    'URL': URL
                }
                prop_bet_list.append(prop_bet_dict)

    logger.info(f'Bets scraped successfully')
    return prop_bet_list


def main():
    global away_team, home_team, game_type, sport, time_stamp, game_name

    try:
        top_page_data = WebDriverWait(driver, 30).until(EC.visibility_of_element_located(
            (By.XPATH, "//div[contains(@class, 'event-header-main')]")))
        time_info, game_name = top_page_data.find_elements(By.XPATH, "./div")
        game_name = game_name.text.replace("\n", " ")
        time_info = time_info.text
    except TimeoutException:
        logger.warning("The game has ended")
        res_upd = update_redis_status(URL, 2)
        logger.info(res_upd)
        return

    module_operate_until = datetime.now() + module_work_duration
    exception_counter = 0
    count_scraps = 0

    away_team, home_team = split_string(game_name)
    game_type = 'Live' if time_info == 'Live' else 'Pre-game'

    hidden_element = driver.find_element(
        By.XPATH, "//a[contains(@href, '/sports/') and contains(@aria-label, 'Go to')]")
    sport = hidden_element.get_attribute("href").split("/")[4].capitalize()

    if sport == "American_football":
        sport = "Football"

    while datetime.now() < module_operate_until:
        try:
            parsing_start_time = time.time()
            time_stamp = datetime.now().strftime("%m/%d/%Y %H:%M:%S")

            try:
                active_page = WebDriverWait(driver, 10).until(EC.visibility_of_element_located(
            (By.XPATH, "//div[@class='v-window-item active-tab']")))
            except NoSuchElementException:
                logger.info(f'The game has ended')
                res_upd = update_redis_status(URL, 2)
                logger.info(res_upd)
                break

            expand_bets(active_page)

            prop_bet_list = scrape_prop_bets(active_page)
            if not prop_bet_list:
                continue

            # save data to redis db
            saving_result = add_data_redis(f'football_barstool_prop_{file_tail}', prop_bet_list)
            logger.info(
                f'The result of saving data: {saving_result}') if saving_result == 'OK' else logger.exception(
                f'The result of saving data: {saving_result}')            
            count_scraps += 1

            parsing_work_time = time.time() - parsing_start_time
            time.sleep(max(0, update_frequency.total_seconds() - parsing_work_time))
            exception_counter = 0

        except KeyboardInterrupt:
            logger.warning("Keyboard Interrupt. Quit the driver!")
            driver.quit()
            res_upd = update_redis_status(URL, 2)
            logger.info(res_upd)
            break

        except Exception as e:
            logger.exception(f"Exception in main scraping cycle. {e}")
            exception_counter += 1
            if exception_counter >= 5:
                driver.quit()
                logger.exception(f'Script is stopped after {exception_counter} unsuccessful attempts to execute the main loop')
                res_upd = update_redis_status(URL, 3)
                logger.info(res_upd)
                break      
        
        if count_scraps % scrap_step == 0:
            actions_on_page(driver=driver, class_name="match-clock h-24")
            if count_scraps == scrap_limit:
                driver.refresh()                
                count_scraps = 0
            
    driver.quit()
    logger.warning(f'Module stopped working')
    res_upd = update_redis_status(URL, 2)
    logger.info(res_upd)
    

if __name__ == "__main__":
    main()


