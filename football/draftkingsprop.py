import time
from configparser import ConfigParser
from datetime import datetime
from os import environ

from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from selenium.common.exceptions import StaleElementReferenceException
from utilities.logging import get_logger
from utilities.utils import get_driver, str_to_timedelta, add_data_redis, update_redis_status, actions_on_page, text_filter, read_url_redis


# read config file
config_parser = ConfigParser()
config_parser.read('conf/draftkings.conf')
module_conf = config_parser["MODULE"]

# init logging
logger_name = environ.get('football_draftkingsprop_get_logger', 'football_draftkings_prop')
# for local logs storage and stdout use DEBUG_FLAG = 1
DEBUG_FLAG = environ.get('PROP_LOG_DEBUG_FLAG', 0)
log_level = environ.get('football_draftkingsprop_log_level', 'WARNING')

logger = get_logger(logger_name, DEBUG_FLAG, log_level)

# other variables
# URL = environ['draftkings_prop_url']
URL = None

module_work_duration = str_to_timedelta(environ.get('football_draftkingsprop_module_work_duration', module_conf.get('module_work_duration')))
update_frequency = str_to_timedelta(environ.get('football_draftkingsprop_update_frequency', module_conf.get('update_frequency')))
browser = environ.get('football_draftkingsprop_browser', module_conf.get('browser_prop'))

scrap_step = int(environ.get('football_scrap_step', module_conf.get('scrap_step')))
scrap_limit = int(environ.get('football_scrap_limit', module_conf.get('scrap_limit')))

# init web driver
driver = None
# driver = get_driver(browser)
# driver.get(URL)

logger.warning(f'Module started working with parameters:\nURL: {URL}\nmodule_work_duration: {module_work_duration}\nupdate_frequency: {update_frequency}\nbrowser: {browser}\nlogger_name: {logger_name}\nlog_level: {log_level}\nDEBUG_FLAG: {DEBUG_FLAG}')


def check_timeout(gt):
    if gt == 'HALFTIME':
        return 1
    elif gt == '15:00':
        return 1
    else:
        return 0


def scrape_prop():
    prop_bets = []
    sport = "Football"
    game_type = "Live"
    time_stamp = datetime.now().strftime("%m/%d/%Y %H:%M:%S")
    try:
        clock = driver.find_elements(By.CLASS_NAME, "event-cell__time")
        game_time = clock[0].text
        if game_time == 'FINISH':
            return game_time
        elif game_time == '':
            period = driver.find_elements(By.CLASS_NAME, "event-cell__period")
            is_timeout = check_timeout(period)
        else:
            is_timeout = check_timeout(game_time)
    except:
        game_time = ''
        is_timeout = ''
        pass
    try:
        teams = driver.find_elements(By.CLASS_NAME, "live-score-body__row--team")
        teams = [in_text.text for in_text in teams]
        game_name = f'{teams[0] + " @ " + teams[1]}'
    except:
        logger.info("Url avaliable but the game has ended!")
        return 'FINISH'
    
    period = driver.find_element(By.CLASS_NAME, "sportsbook-live-scoreboard-component-1")
    current_time = period.find_element(By.XPATH, './/*[@class="event-cell__period"]')
   

    categories = ['Quarters']  
    
    for subcat in categories:
        xpath = f".//a[@id='subcategory_{subcat}']"        
        try:            
            element = driver.find_element(By.XPATH, xpath)
            driver.execute_script("arguments[0].click();", element)
        except:
            logger.info(f"{subcat} bets were closed!")
            continue        
        
        # scrape spreads, totals, money lines
        
        match_rows = driver.find_elements(By.XPATH, ".//div[contains(@class, 'parlay-card-10-a')]")

        for match_row in match_rows:
            headers = match_row.find_elements(By.XPATH, ".//div[@class='sportsbook-table-header__title']")
            headers = [in_text.text for in_text in headers]
            if subcat in {'Quarters'} and current_time.text not in headers:
                continue

            data = match_row.find_elements(By.CLASS_NAME, "sportsbook-table__column-row")
            classes = [element.get_attribute('innerHTML') for element in data]
            data = [in_text.text.split('\n') for in_text in data]
            spreads = []
            totals = []
            moneylines = []
                
            spreads.append((data[1], classes[1]))
            spreads.append((data[5], classes[5]))

            if spreads[0][0][0] == "" or 'disabled' in spreads[0][1]:
                logger.info("Spread bets were disabled!")
            else:
                for i in range(2):
                    prop_info_dict_spread = {
                        'SPORT': sport,
                        'GAME_TYPE': game_type,
                        'IS_PROP': 1,
                        'GAME_NAME': game_name,
                        'BET_NAME': headers[1],
                        'BET_TYPE': f'{teams[i]} {spreads[i][0][0]}',
                        'ODDS': spreads[i][0][1],
                        'HOME_TEAM': teams[1],
                        'AWAY_TEAM': teams[0],
                        'ALIGNED_BET_NAME': headers[1],
                        'ALIGNED_BET_TYPE': text_filter(f'Home team {spreads[i][0][0]}' if teams[i] == teams[
                            1] else f'Away team {spreads[i][0][0]}'),
                        'GAME_TIME': game_time,
                        'IS_TIMEOUT': is_timeout,
                        'SPORTS_BOOK': 'Draft Kings',
                        'TIMESTAMP': time_stamp,
                        'URL': URL
                    }
                    prop_bets.append(prop_info_dict_spread)

            totals.append((data[2], classes[2]))
            totals.append((data[6], classes[6]))

            if totals[0][0][0] == "" or 'disabled' in totals[0][1]:
                logger.info("Total bets were disabled!")
            else:
                for i in range(2):
                    prop_info_dict_totals = {
                        'SPORT': sport,
                        'GAME_TYPE': game_type,
                        'IS_PROP': 1,
                        'GAME_NAME': game_name,
                        'BET_NAME': headers[2],
                        'BET_TYPE': f'{totals[i][0][0]} {totals[i][0][1]}',
                        # 'ODDS': totals[i][2],
                        'ODDS': totals[i][0][0],
                        'HOME_TEAM': teams[1],
                        'AWAY_TEAM': teams[0],
                        'ALIGNED_BET_NAME': headers[2],
                        'ALIGNED_BET_TYPE': text_filter(f'{totals[i][0][0]} {totals[i][0][1]}'),
                        'GAME_TIME': game_time,
                        'IS_TIMEOUT': is_timeout,
                        'SPORTS_BOOK': 'Draft Kings',
                        'TIMESTAMP': time_stamp,
                        'URL': URL
                    }
                    prop_bets.append(prop_info_dict_totals)

            moneylines.append((data[3], classes[3]))
            moneylines.append((data[7], classes[7]))

            if moneylines[0][0][0] == "" or 'disabled' in moneylines[0][1]:
                logger.info("Moneylines bets were disabled!")
            else:
                for i in range(2):
                    prop_info_dict_moneylines = {
                        'SPORT': sport,
                        'GAME_TYPE': game_type,
                        'IS_PROP': 1,
                        'GAME_NAME': game_name,
                        'BET_NAME': headers[3],
                        'BET_TYPE': f'{teams[i]}',
                        'ODDS': moneylines[i][0][0],
                        'HOME_TEAM': teams[1],
                        'AWAY_TEAM': teams[0],
                        'ALIGNED_BET_NAME': headers[3],
                        'ALIGNED_BET_TYPE': text_filter(f'Home team' if teams[i] == teams[1] else f'Away team'),
                        'GAME_TIME': game_time,
                        'IS_TIMEOUT': is_timeout,
                        'SPORTS_BOOK': 'Draft Kings',
                        'TIMESTAMP': time_stamp,
                        'URL': URL
                    }
                    prop_bets.append(prop_info_dict_moneylines)

        try:
            match_rows = driver.find_elements(By.XPATH, ".//div[contains(@class, 'sportsbook-event-accordion__wrapper')]")
        except:
            logger.info("Alternate did not find!")
            continue


    return prop_bets


def main():
    module_operate_until = datetime.now() + module_work_duration

    failure_count = 0
    count_scraps = 0

    while datetime.now() < module_operate_until:
        urls = read_url_redis('draftkings')
        for redis_url in urls:
            global URL
            URL = redis_url['data']
            driver.get(URL)
            parsing_start_time = time.time()
            driver.implicitly_wait(10)
            try:
                logger.info(f'Start scraping DraftKings props')

                try:
                    prop_bet_list = scrape_prop()
                except StaleElementReferenceException:
                    prop_bet_list = []
                    pass

                if prop_bet_list == "FINISH":
                    logger.info("The game has ended!")
                    res_upd = update_redis_status(URL, 2)
                    logger.info(res_upd)
                    break

                else:
                    url_part = URL.split('/')

                    if not prop_bet_list:
                        continue
                    # save data to redis db
                    saving_result = add_data_redis(f'football_draftkings_prop_{url_part[-1]}', prop_bet_list)
                    logger.info(
                        f'The result of saving data: {saving_result}') if saving_result == 'OK' else logger.exception(
                        f'The result of saving data: {saving_result}')                
                    count_scraps += 1

            except KeyboardInterrupt:
                logger.warning("Keyboard Interrupt. Quit the driver!")
                driver.quit()
                logger.info(f'Module stopped working')
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
                actions_on_page(driver=driver, class_name="sportsbook-event-accordion__title")
                if count_scraps == scrap_limit:
                    driver.refresh()                
                    count_scraps = 0

            parsing_work_time = time.time() - parsing_start_time
            time.sleep(max(0, update_frequency.total_seconds() - parsing_work_time))

    driver.quit()
    res_upd = update_redis_status(URL, 2)
    logger.info(res_upd)
    logger.warning('Script successfully ended working at the set time')


if __name__ == "__main__":
    main()
