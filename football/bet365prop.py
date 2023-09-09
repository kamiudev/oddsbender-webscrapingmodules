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
from utilities.utils import get_driver, str_to_timedelta, add_data_redis, update_redis_status, actions_on_page, text_filter


# read config file
config_parser = ConfigParser()
config_parser.read('conf/bet365.conf')
module_conf = config_parser["MODULE"]

# init logging
logger_name = environ.get('football_bet365prop_get_logger', 'football_bet365_prop')
# for local logs storage and stdout use DEBUG_FLAG = 1
DEBUG_FLAG = environ.get('PROP_LOG_DEBUG_FLAG', 0)
log_level = environ.get('football_bet365prop_log_level', 'WARNING')

logger = get_logger(logger_name, DEBUG_FLAG, log_level)

# other variables
URL = environ['bet365_prop_url']
file_tail = URL.split('/')[-1]

module_work_duration = str_to_timedelta(environ.get('football_bet365prop_module_work_duration', module_conf.get('module_work_duration')))
update_frequency = str_to_timedelta(environ.get('football_bet365prop_update_frequency', module_conf.get('update_frequency')))
browser = environ.get('football_bet365prop_browser', module_conf.get('browser_prop'))

scrap_step = int(environ.get('football_scrap_step', module_conf.get('scrap_step')))
scrap_limit = int(environ.get('football_scrap_limit', module_conf.get('scrap_limit')))

# init web driver
driver = get_driver(browser)
driver.get(URL)

logger.warning(f'Module started working with parameters:\nURL: {URL}\nmodule_work_duration: {module_work_duration}\nupdate_frequency: {update_frequency}\nbrowser: {browser}\nlogger_name: {logger_name}\nlog_level: {log_level}\nDEBUG_FLAG: {DEBUG_FLAG}')


def split_string(bet: str):
    if '\n' in bet:
        return bet.split('\n')
    elif ' @ ' in bet:
        return bet.split(' @ ')
    elif ' v ' in bet:
        return bet.split(' v ')   
    elif ' vs ' in bet:
        return bet.split(' vs ')       
    elif bet:
        return bet, ''
    else:
        return '', ''


def click_on_web_element(element: WebElement):
    driver.execute_script("arguments[0].scrollIntoView(true);", element)
    WebDriverWait(driver, 10).until(EC.element_to_be_clickable(element))
    driver.execute_script("arguments[0].click();", element)     


def open_bet_list(all_game_bets: list):
    logger.info(f'Open all bets on the page')
    for one_game_bet in all_game_bets:
        try:
            bet_data = one_game_bet.find_elements(By.XPATH, './div')
        except StaleElementReferenceException:
            logger.error(f'Bet table element has changed the reference')
            continue        

        if len(bet_data) == 1:
            bet_data_element = bet_data[0].find_element(By.XPATH, './div')
            click_on_web_element(bet_data_element)
                
    logger.info(f'Find Show more buttons and click on it')
    show_more_buttons = driver.find_elements(By.XPATH, '//div[text()="Show more"]')
    if show_more_buttons:
        [click_on_web_element(show_more_button) for show_more_button in show_more_buttons]


def parse_bet_table(bet: WebElement, game_name, home_team, away_team, time_stamp, url, additional_param):
    prop_bet_list = []

    try:
        bet_name, bet_table = bet.find_elements(By.XPATH, './div')
    except StaleElementReferenceException:
        bet_name = bet.text.split('\n')[0]
        logger.info(f'Unable to scrape the bet {bet_name}. Bet table element has changed the reference')
        return []      
    
    bet_name = bet_name.text
    logger.warning(f'Scrape bet {bet_name}')
    if '2-Way' in bet_name:
        logger.warning(f'Scraping for bet {bet_name} not implemented yet')
        return []

    bet_odds_cells = bet_table.find_elements(By.XPATH, './/div[@aria-label]')
    bet_odds_cells = list(map(lambda x: x.get_attribute('aria-label'), bet_odds_cells))

    # get game_time again to check for timeout
    try:
        get_curent_game_time = driver.find_element(By.CSS_SELECTOR, '.ipe-EventHeader_ClockAndPeriodContainer')
        curent_game_time = get_curent_game_time.text.replace('\n', ' ')
    except:
        curent_game_time = ''
        logger.warning('Сould not get game_time_now')

    is_timeout = 1 if str(curent_game_time) == str(additional_param.get('game_time')) else 0

    for i in range(len(bet_odds_cells)):
        bet_type, bet_odds = split_string(bet_odds_cells[i])
        bet_type = bet_type.replace('Undernder', 'Under').replace('Overver', 'Over')
        bet_type = " ".join(bet_type.split())
        prop_bet_dict = {
            'SPORT': additional_param.get('sport'),
            'GAME_TYPE': additional_param.get('game_type'),
            'IS_PROP': 1,
            'GAME_NAME': game_name,
            'BET_NAME': bet_name,
            'BET_TYPE': bet_type,
            'ODDS': bet_odds,
            'HOME_TEAM': home_team,
            'AWAY_TEAM': away_team,
            'ALIGNED_BET_NAME': bet_name.replace(home_team, 'Home Team').replace(away_team, 'Away Team').replace('Under', 'U').replace('Over', 'O'),
            'ALIGNED_BET_TYPE': text_filter(bet_type),
            'GAME_TIME': curent_game_time,
            'IS_TIMEOUT': is_timeout,
            'SPORTS_BOOK': "Bet365",
            'TIMESTAMP': time_stamp,
            'URL': url
        }
        prop_bet_list.append(prop_bet_dict)
        
    logger.info(f'Bet {bet_name} scraped successfully')
    return prop_bet_list


def main():
    additional_param = {}
    module_operate_until = datetime.now() + module_work_duration
    failure_count = 0
    count_scraps = 0

    while datetime.now() < module_operate_until:
        parsing_start_time = time.time()
        # get type of sport
        try:
            get_sport = WebDriverWait(driver, 5).until(
                EC.visibility_of_element_located((By.CSS_SELECTOR, '.ipn-Classification.ipn-Classification-open'))).text
            additional_param['sport'] = get_sport.split('\n')[0]
        except:
            additional_param['sport'] = 'Not identified'
            logger.warning('It’s impossible to identify game type')

        # check if the game_type field is active
        try:
            game_online = WebDriverWait(driver, 2).until(EC.visibility_of_element_located(
                (By.CSS_SELECTOR, '.hm-HeaderMenuItem_LinkSelected-underscore div'))).text
            if game_online == 'Live In Game':
                additional_param['game_type'] = 'Live'
        except:
            additional_param['game_type'] = 'Pre-game'
            logger.warning('There are no live game element found')

        # get game_time
        try:
            get_curent_game_time = driver.find_element(By.CSS_SELECTOR, '.ipe-EventHeader_ClockAndPeriodContainer')
            additional_param['game_time'] = get_curent_game_time.text.replace('\n', ' ')
        except:
            additional_param['game_time'] = ''
            logger.warning('Сould not get game_time')

        try:
            if URL != driver.current_url:
                logger.warning(f'There are no live game')
                res_upd = update_redis_status(URL, 2)
                logger.info(res_upd)
                time.sleep(update_frequency.total_seconds())
                continue

            prop_bets_list = []
            try:
                game_top_page_data = WebDriverWait(driver, 8).until(EC.presence_of_element_located(
                    (By.XPATH, '//div[@class="ipe-EventHeader "]/div[2]')))
            except NoSuchElementException:
                logger.warning(f'The game is over {URL}')
                res_upd = update_redis_status(URL, 2)
                logger.info(res_upd)
                continue

            game_name = game_top_page_data.text.split('\n')[0]
            logger.info(f'Start scraping game {game_name}')

            away_team, home_team = split_string(game_name)
            time_stamp = datetime.now().strftime("%m/%d/%Y %H:%M:%S")
            url = driver.current_url

            try:
                all_game_bets = WebDriverWait(driver, 5).until(EC.visibility_of_all_elements_located(
                    (By.XPATH, '//div[@class="sip-MarketGroup "]')))[1:]
                driver.execute_script("arguments[0].scrollIntoView(true);", all_game_bets[-1])
                all_game_bets = WebDriverWait(driver, 2).until(EC.visibility_of_all_elements_located(
                    (By.XPATH, '//div[@class="sip-MarketGroup "]')))[1:]

            except Exception as e:
                logger.exception(f'Not enough prop bets for the game \n{e}')

            open_bet_list(all_game_bets)
            for game_bet in all_game_bets:
                try:
                    prop_bets_list += parse_bet_table(game_bet, game_name, home_team, away_team, time_stamp, url, additional_param)
                except Exception as e:
                    bet_name = game_bet.text.split('\n')[0]
                    logger.exception(f'Unable to scrape the bet {bet_name}. Please, contact support@keplercode.com \n{e}')

            # save data to redis db
            saving_result = add_data_redis(f'bet365_prop_{file_tail}', prop_bets_list)
            logger.info(
                f'The result of saving data: {saving_result}') if saving_result == 'OK' else logger.exception(
                f'The result of saving data: {saving_result}')            
            count_scraps += 1

            # reset unsuccessful attempts in main loop
            failure_count = 0

            parsing_work_time = time.time() - parsing_start_time
            time.sleep(max(0, update_frequency.total_seconds() - parsing_work_time))

        except KeyboardInterrupt:
            logger.warning('Script stopped manually')
            driver.quit()
            res_upd = update_redis_status(URL, 2)
            logger.info(res_upd)
            break

        except Exception as e:
            logger.exception(f'Stop script with errors:\n{e}')
            failure_count += 1
            if failure_count >= 5:
                driver.quit()
                logger.exception(f'Script exited after {failure_count} unsuccessful attempts to start the main loop')
                res_upd = update_redis_status(URL, 3)
                logger.info(res_upd)
                break
        
        if count_scraps % scrap_step == 0:
            actions_on_page(driver=driver, class_name="ipe-EventHeader ")
            if count_scraps == scrap_limit:
                driver.refresh()                
                count_scraps = 0

    driver.quit()
    logger.info(f'Module stopped working')
    res_upd = update_redis_status(URL, 2)
    logger.warning(res_upd)


if __name__ == "__main__":
    main()
