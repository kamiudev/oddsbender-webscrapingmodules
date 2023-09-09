from os import environ
import time
from configparser import ConfigParser
from datetime import datetime
from random import randrange

from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from utilities.logging import get_logger
from utilities.utils import get_driver, str_to_timedelta, actions_on_page, text_filter
from utilities.redis import RedisClient

# read config file
config_parser = ConfigParser()
config_parser.read('conf/caesars.conf')
module_conf = config_parser["MODULE"]

# init logging
logger_name = environ.get('basketball_caesarspopular_get_logger', 'basketball_caesars_popular')
# for local logs storage and stdout use DEBUG_FLAG = 1
DEBUG_FLAG = environ.get('basketball_caesarspopular_DEBUG_FLAG', 1)
log_level = environ.get('basketball_caesarspopular_log_level', 'WARNING')

logger = get_logger(logger_name, DEBUG_FLAG, log_level)

# other variables
URL = environ.get('basketball_caesars_url', module_conf.get('URL'))
module_work_duration = str_to_timedelta(environ.get('basketball_caesarspopular_module_work_duration', module_conf.get('module_work_duration')))
update_frequency = str_to_timedelta(environ.get('basketball_caesarspopular_update_frequency', module_conf.get('update_frequency')))
browser = environ.get('basketball_caesarspopular_browser', module_conf.get('browser_popular'))

scrap_step = int(environ.get('basketball_scrap_step', module_conf.get('scrap_step')))
scrap_limit = int(environ.get('basketball_scrap_limit', module_conf.get('scrap_limit')))

# init web driver
driver = get_driver(browser)
driver.get(URL)

logger.warning(f'Module started working with parameters:\nURL: {URL}\nmodule_work_duration: {module_work_duration}\nupdate_frequency: {update_frequency}\nbrowser: {browser}\nlogger_name: {logger_name}\nlog_level: {log_level}\nDEBUG_FLAG: {DEBUG_FLAG}')

redisClient = RedisClient()

# Determines the game time
def games_time(page):
    try:
        timing = page.find_elements(By.XPATH, ".//span[@class='liveClock']")
        times = [game_time.text for game_time in timing]
        times = times[0]
    except:
        times = ' '
        pass
    return times


# Checks the timeout
def check_timeout(game_time=str):
    if game_time == 'HALFTIME':
        return 1
    else:
        try:
            gt = games_time.split(' ')
            if gt[1] == '00:00':
                return 1
            else:
                return 0
        except:
            return 0

    
def scrape_all(match_row, bet_title):
    try:
        bet_name = match_row.find_elements(By.XPATH, ".//div[contains(@class, 'header selectionHeader truncate3Rows')]")
        bet_class = [bet.get_attribute("class") for bet in bet_name]
        bet_name = [bet.text for bet in bet_name]        
    except:
        return 'FAILED'
    else:
        if len(bet_name) == 0:
            return 'FAILED'
        try:
            idx = list(map(lambda x: bet_title in x,bet_name)).index(True)
        except ValueError:
            return 'FAILED'  
        col = bet_class[idx].split()[-1]        
        mls = match_row.find_elements(By.XPATH, f".//div[@class='selectionContainer  {col}']")

        if len(mls) == 0:
            return 'FAILED'

        mls = [ml.text.split("\n") for ml in mls]
        if len(mls[0]) == 1 and bet_title != 'MONEY LINE LIVE':
            mls = [['', ''], ['', '']]
        return mls


def scrape_popular(url):
    sport = url.split("/")[-2].capitalize()
    game_type = url.split("/")[-1]
    game_type = "Live" if game_type == 'inplay' else ' '
    match_rows = driver.find_elements(By.XPATH, ".//div[contains(@class, 'EventCard')]")
    time_stamp = datetime.now().strftime("%m/%d/%Y %H:%M:%S")
    popular_bets = []
    for match_row in match_rows:
        game_time = games_time(match_row)
        is_timeout = check_timeout(game_time)
        teams = match_row.find_elements(By.XPATH, ".//span[@class='truncate2Rows']")
        teams = [team.text for team in teams]
        mll = scrape_all(match_row, 'MONEY LINE LIVE')
        logger.info(mll)
        spreads = scrape_all(match_row, 'SPREAD LIVE')
        logger.info(spreads)
        tpl = scrape_all(match_row, 'TOTAL POINTS LIVE')
        logger.info(tpl)

        if spreads == 'FAILED' or mll == 'FAILED' or tpl == 'FAILED':
            continue

        for i in range(2):
            game_name = f'{teams[0] + " @ " + teams[1]}'
            popular_info_dict = {
                'SPORT': sport,
                'GAME_TYPE': game_type,
                'IS_PROP': 0,
                'GAME': game_name,
                'TEAM': teams[i],
                'VS_TEAM': teams[1 - i],
                'SPREAD': ' '.join((teams[i], spreads[i][0])),
                'SPREAD_ODDS': spreads[i][1],
                'MONEYLINE_ODDS': mll[i][0],
                'TOTAL': text_filter(tpl[i][0]),
                'TOTAL_ODDS': tpl[i][1],
                'HOME_TEAM': teams[1],
                'AWAY_TEAM': teams[0],
                'GAME_TIME': game_time,
                'IS_TIMEOUT': is_timeout,
                'SPORTS_BOOK': 'Caesars',
                'TIMESTAMP': time_stamp
            }
            popular_bets.append(popular_info_dict)
    logger.info(f'Game lines scraped successfully')
    return popular_bets


def main():
    module_operate_until = datetime.now() + module_work_duration

    failure_count = 0
    count_scraps = 0

    while datetime.now() < module_operate_until:
        parsing_start_time = time.time()
        try:
            logger.info(f'Start scraping')
            try:
                WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.XPATH, '//div[@class="sportSection"]//span[contains(text(), "NCAA Basketball") or contains(text(), "NBA")]/ancestor::div[contains(@class, "Expander")]//a[@class="competitor firstCompetitor"]')))
                games_on_initial_page = driver.find_elements(By.XPATH, '//div[@class="sportSection"]//span[contains(text(), "NCAA Basketball") or contains(text(), "NBA")]/ancestor::div[contains(@class, "Expander")]//a[@class="competitor firstCompetitor"]')
            except:
                logger.warning('There are no live games, waiting for some time and trying again')
                time.sleep(randrange(4000, 12000, 10) / 1000)
                driver.get(URL)
                driver.refresh()
                continue
            else:
                popular_bet_list = scrape_popular(URL)
                if not popular_bet_list:
                    continue

                # save data to redis db
                saving_result = redisClient.add_data_redis('basketball_caesars_popular', popular_bet_list)
                logger.info(
                    f'The result of saving data: {saving_result}') if saving_result == 'OK' else logger.exception(
                    f'The result of saving data: {saving_result}')
                count_scraps += 1

                parsing_work_time = time.time() - parsing_start_time
                time.sleep(max(0, update_frequency.total_seconds() - parsing_work_time))

                failure_count = 0

        except KeyboardInterrupt:
            logger.warning("Keyboard Interrupt. Quit the driver!")
            driver.quit()
            logger.warning(f'Module stopped working')
            break

        except Exception as e:
            logger.exception(f'Stop script with errors:\n{e}')
            failure_count += 1
            if failure_count >= 5:
                driver.quit()
                logger.warning(f'Script exited after {failure_count} unsuccessful attempts to start the main loop')
                break

        if count_scraps % scrap_step == 0:
            actions_on_page(driver=driver, class_name="competitor firstCompetitor")
            if count_scraps == scrap_limit:
                driver.refresh()                
                count_scraps = 0
            
        parsing_work_time = time.time() - parsing_start_time
        time.sleep(max(0, update_frequency.total_seconds() - parsing_work_time))

    driver.quit()
    logger.warning('Script successfully ended working at the set time')


if __name__ == "__main__":
    main()
