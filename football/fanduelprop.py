import time
from configparser import ConfigParser
from datetime import datetime
from os import environ

from selenium.common.exceptions import (NoSuchElementException,
                                        StaleElementReferenceException)
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from utilities.logging import get_logger
from utilities.utils import str_to_timedelta, split_string, get_driver, add_data_redis, update_redis_status, actions_on_page, text_filter, read_url_redis
from utilities.driver_proxy import get_driver_proxy


# read config file
config_parser = ConfigParser()
config_parser.read('conf/fanduel.conf')
module_conf = config_parser["MODULE"]

# init logging
logger_name = environ.get('football_fanduelprop_get_logger', 'football_fanduel_prop')
# for local logs storage and stdout use DEBUG_FLAG = 1
DEBUG_FLAG = environ.get('PROP_LOG_DEBUG_FLAG', 0)
log_level = environ.get('football_fanduelprop_log_level', 'WARNING')

logger = get_logger(logger_name, DEBUG_FLAG, log_level)

# other variables
# URL = environ['fanduel_prop_url']
URL = None
file_tail = None

module_work_duration = str_to_timedelta(environ.get('football_fanduelprop_module_work_duration', module_conf.get('module_work_duration')))
update_frequency = str_to_timedelta(environ.get('football_fanduelprop_update_frequency', module_conf.get('update_frequency')))
browser = environ.get('football_fanduelprop_browser', module_conf.get('browser_prop'))

scrap_step = int(environ.get('football_scrap_step', module_conf.get('scrap_step')))
scrap_limit = int(environ.get('football_scrap_limit', module_conf.get('scrap_limit')))

# init web driver
driver = get_driver(browser)
driver.get(URL)
# driver = None

logger.warning(f'Module started working with parameters:\nURL: {URL}\nmodule_work_duration: {module_work_duration}\nupdate_frequency: {update_frequency}\nbrowser: {browser}\nlogger_name: {logger_name}\nlog_level: {log_level}\nDEBUG_FLAG: {DEBUG_FLAG}')


def check_capture():
    global driver
    global URL
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

def click_on_web_element(element: WebElement):
    driver.execute_script("arguments[0].scrollIntoView(true);", element)
    WebDriverWait(driver, 10).until(EC.element_to_be_clickable(element))
    driver.execute_script("arguments[0].click();", element)


def open_bet_list(all_bets_on_page: list):
    logger.info(f'Open all bets on the page')
    for single_bet_table in all_bets_on_page:
        try:
            bet_table_buttons = single_bet_table.find_elements(By.XPATH, './/div[@role="button"]')
        except StaleElementReferenceException:
            logger.warning(f'Bet table element has changed the reference. Unable to open bet')
            continue
               
        if len(bet_table_buttons) == 1:
            click_on_web_element(bet_table_buttons[0])
        

def parse_prop_bets(bet_table, additional_param, title):
    try:
        bet_table_buttons = bet_table.find_elements(By.XPATH, './/div[@role="button"]')
        bet_name = bet_table_buttons[0].text
    except StaleElementReferenceException:
        logger.warning(f'Bet table element has changed the reference. Unable to scrape the bet')
        return []
    except IndexError:
        logger.warning(f'Bet table has no bets')
        return []
    
    if bet_name == 'Gamelines' or len(bet_table_buttons) < 2:
        return []

    if '4th Quarter' in bet_name:
        return []
        
    if title == 'Alternates' and ('Spread' not in bet_name and 'Total Points' not in bet_name):
        return []    

    if 'Quarter' in title and (' '.join((title, 'Spread')) not in bet_name and ' '.join((title, 'Total')) not in bet_name and ' '.join((title, 'Moneyline')) not in bet_name and ' '.join((title, 'Winner')) not in bet_name or '3 Way' in bet_name):
        return []

    logger.info(f'Start scraping bet {bet_name}')
    prop_bet_list = []
    bet_table_main_rows = bet_table.find_elements(By.XPATH, './child::*/child::*/child::*')
    bet_table_second_main_row_text = bet_table_main_rows[1].text

    # check for timeout
    try:
        is_timeout = 0 if ':' in additional_param.get('game_time') else 1
    except:
        is_timeout = 1

    if 'YES' in bet_table_second_main_row_text or 'UNDER' in bet_table_second_main_row_text:
        bet_table_data = bet_table_second_main_row_text.split('\n')
        bet_table_rows = bet_table_main_rows[-1].find_elements(By.XPATH, './div')

        for row_number, bet_table_row in enumerate(bet_table_rows):
            bet_table_first_column_value = bet_table_row.text.split('\n')[0]

            for odds_column_number in range(2):
                bet_button_value, bet_odds = split_string(bet_table_buttons[1 + row_number + odds_column_number].text)
                bet_button_value = bet_button_value.replace('U ', '').replace('O ', '')
                bet_type = bet_table_first_column_value + ' ' + bet_table_data[odds_column_number].capitalize() + ' ' + bet_button_value
                prop_bet_dict = {
                    'SPORT': additional_param.get('sport'),
                    'GAME_TYPE': additional_param.get('game_type'),
                    'IS_PROP': 1,
                    'GAME_NAME': additional_param.get("game_name"),
                    'BET_NAME': bet_name,
                    'BET_TYPE': bet_type.replace('Under', 'U').replace('Over', 'O'),
                    'ODDS': bet_odds,
                    'HOME_TEAM': additional_param.get('home_team'),
                    'AWAY_TEAM': additional_param.get('away_team'),
                    'ALIGNED_BET_NAME': bet_name.replace(additional_param.get('home_team'), 'Home Team').replace(additional_param.get('away_team'), 'Away Team').replace('Under', 'U').replace('Over', 'O'),
                    'ALIGNED_BET_TYPE': text_filter(bet_type),
                    'GAME_TIME': additional_param.get('game_time'),
                    'IS_TIMEOUT': is_timeout,
                    'SPORTS_BOOK': 'Fanduel',
                    'TIMESTAMP': additional_param.get('time_stamp'),
                    'URL': URL
                }
                prop_bet_list.append(prop_bet_dict)
                
    else:
        for bet_table_button in bet_table_buttons[1:]:
            try:
                bet_table_row = bet_table_button.find_element(By.XPATH, './../..')
            except StaleElementReferenceException:
                logger.warning(f'Bet table element has changed the reference. Unable to scrape the bet odd')
                continue
                
            bet_table_row = bet_table_row.text.split('\n')
            bet_type = ' '.join(bet_table_row[:-1])
            bet_type = bet_type.replace('U ', '').replace('O ', '')
            bet_odds = bet_table_row[-1]
            prop_bet_dict = {
                'SPORT': additional_param.get('sport'),
                'GAME_TYPE': additional_param.get('game_type'),
                'IS_PROP': 1,
                'GAME_NAME': additional_param.get("game_name"),
                'BET_NAME': bet_name,
                'BET_TYPE': bet_type,
                'ODDS': bet_odds,
                'HOME_TEAM': additional_param.get('home_team'),
                'AWAY_TEAM': additional_param.get('away_team'),
                'ALIGNED_BET_NAME': bet_name.replace(additional_param.get('home_team'), 'Home Team').replace(additional_param.get('away_team'), 'Away Team').replace('Under', 'U').replace('Over', 'O'),
                'ALIGNED_BET_TYPE': bet_type.replace(additional_param.get('home_team'), 'Home Team').replace(additional_param.get('away_team'), 'Away Team').replace('Under', 'U').replace('Over', 'O'),
                'GAME_TIME': additional_param.get('game_time'),
                'IS_TIMEOUT': is_timeout,
                'SPORTS_BOOK': 'Fanduel',
                'TIMESTAMP': additional_param.get('time_stamp'),
                'URL': URL
            }
            prop_bet_list.append(prop_bet_dict)
    logger.info(f'Bet {bet_name} scraped successfully')
    return prop_bet_list


def main():
    module_operate_until = datetime.now() + module_work_duration
    exception_counter = 0
    count_scraps = 0

    while datetime.now() < module_operate_until:
        urls = read_url_redis('fanduel')
        for redis_url in urls:
            global URL
            URL = redis_url['data']
            check_capture()


            logger.info('Start scraping Fanduel props')
            previous_bet_bur_buttons = driver.find_elements(By.XPATH, '//div[@style="height: 100%;"]//a')

            additional_param = {}

            # get type of sport
            try:
                additional_param['sport'] = URL.split('/')[3].capitalize()
            except:
                additional_param['sport'] = 'Not identified'
                logger.warning('It’s impossible to identify game type')

            # check if the game_type field is active
            try:
                game_online = WebDriverWait(driver, 2).until(EC.visibility_of_element_located((By.ID, 'LiveTag_svg__a')))
                if game_online:
                    additional_param['game_type'] = 'Live'
                if not game_online:
                    additional_param['game_type'] = 'Pre-game'
            except:
                additional_param['game_type'] = 'Unable to Get'
                logger.warning('There are no live game element found')

            # get game_time
            try:
                additional_param['game_time'] = WebDriverWait(driver, 2).until(EC.visibility_of_element_located((By.XPATH, "//span[contains(@class, '') and contains(text(),':') and not(contains(text(),'/'))]"))).text
            except:
                additional_param['game_time'] = ''
                logger.warning('Unable to get element game time')

            try:
                try:
                    additional_param['game_name'] = driver.find_element(By.TAG_NAME, 'h1').text.replace(' v ', ' @ ')
                except NoSuchElementException:
                    logger.info(f'The game is over')
                    res_upd = update_redis_status(URL, 2)
                    logger.info(res_upd)
                    break

                logger.info(f'Start scraping game {additional_param.get("game_name")}')

                parsing_start_time = time.time()
                prop_bets_list = []
                additional_param['away_team'], additional_param['home_team'] = split_string(additional_param.get("game_name"))
                additional_param['time_stamp'] = datetime.now().strftime("%m/%d/%Y %H:%M:%S")

                allowed_bets = {'Alternates'}
                if '4th' not in additional_param.get('game_time') and additional_param.get('game_time'):                
                    period = additional_param.get('game_time').split()[0]
                    allowed_bets.add(' '.join((period,'Quarter')))            
                for bet_button in previous_bet_bur_buttons:
                    try:
                        title = bet_button.get_attribute('title')
                    except:
                        continue
                    if title in allowed_bets:
                        try:
                            driver.execute_script("arguments[0].click();", bet_button.find_element(By.XPATH,'div[@role="button"]'))
                        except:
                            logger.warning(f'Tab {title} not clicked')
                            continue

                        bets_tables = WebDriverWait(driver, 10).until(
                            EC.presence_of_all_elements_located(
                                (By.XPATH, '(//div[contains(@style, "flex-direction: column;")])[2]/div')))[1:]

                        open_bet_list(bets_tables)
                        for bet_table in bets_tables:
                            try:
                                prop_bets_list += parse_prop_bets(bet_table, additional_param, title)
                            except Exception as e:
                                logger.exception(f'Unable to scrape the bet. {e}')

                if not prop_bets_list:
                    continue

                # save data to redis db
                saving_result = add_data_redis(f'football_fanduel_prop_{file_tail}', prop_bets_list)
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
                logger.info(f'Module stopped working')
                res_upd = update_redis_status(URL, 2)
                logger.info(res_upd)
                break

            except Exception as e:
                logger.exception(f"Exception in main scraping cycle. {e}")
                exception_counter += 1
                if exception_counter >= 5:
                    driver.quit()
                    logger.exception(f'Script exited after {exception_counter} unsuccessful attempts to execute the main loop')
                    res_upd = update_redis_status(URL, 3)
                    logger.info(res_upd)
                    break
            
            if count_scraps % scrap_step == 0:
                actions_on_page(driver=driver, class_name="")
                if count_scraps == scrap_limit:
                    driver.refresh()                
                    count_scraps = 0

    driver.quit()
    res_upd = update_redis_status(URL, 2)
    logger.info(res_upd)
    logger.warning(f'Module stopped working')


if __name__ == "__main__":
    main()

