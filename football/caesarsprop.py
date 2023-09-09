import logging
import time
from configparser import ConfigParser
from datetime import datetime
from os import environ

from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from utilities.logging import get_logger
from utilities.utils import get_driver, str_to_timedelta, add_data_redis, update_redis_status, actions_on_page, text_filter, read_url_redis


# read config file
config_parser = ConfigParser()
config_parser.read('conf/caesars.conf')
module_conf = config_parser["MODULE"]

# init logging
logger_name = environ.get('football_caesarsprop_get_logger', 'football_caesars_prop')
# for local logs storage and stdout use DEBUG_FLAG = 1
DEBUG_FLAG = environ.get('PROP_LOG_DEBUG_FLAG', 0)
log_level = environ.get('football_caesarsprop_log_level', 'WARNING')

logger = get_logger(logger_name, DEBUG_FLAG, log_level)

# other variables
# URL = environ['caesars_prop_url']
# file_tail = URL.split('/')[-1]
URL = None
file_tail = None

module_work_duration = str_to_timedelta(environ.get('football_caesarsprop_module_work_duration', module_conf.get('module_work_duration')))
update_frequency = str_to_timedelta(environ.get('football_caesarsprop_update_frequency', module_conf.get('update_frequency')))
browser = environ.get('football_caesarsprop_browser', module_conf.get('browser_prop'))

scrap_step = int(environ.get('football_scrap_step', module_conf.get('scrap_step')))
scrap_limit = int(environ.get('football_scrap_limit', module_conf.get('scrap_limit')))

# init web driver
# driver.get(URL)

driver = get_driver(browser)

logger.warning(f'Module started working with parameters:\nURL: {URL}\nmodule_work_duration: {module_work_duration}\nupdate_frequency: {update_frequency}\nbrowser: {browser}\nlogger_name: {logger_name}\nlog_level: {log_level}\nDEBUG_FLAG: {DEBUG_FLAG}')


def games_time():
    try:
        timing = driver.find_elements(By.XPATH, ".//div[@class='current-time']")
        times = [game_time.text for game_time in timing]
        times = times[0]
    except:
        times = ' '
        pass
    return times


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


def scrape_spread(match_row, teams, game_time):
    try:
        bet_name = match_row.find_element(By.XPATH, ".//span[@class='title']").text
        outcome = match_row.find_elements(By.XPATH, ".//div[@class='outcome']")
        btn_odds = match_row.find_elements(By.XPATH, ".//button")
        bet_type = [
            outcome[0].find_element(By.XPATH, ".//div[@class='outcomeTitle']").text + ' ' +  btn_odds[0].text.split('\n')[0],
            outcome[-1].find_element(By.XPATH, ".//div[@class='outcomeTitle']").text + ' ' +  btn_odds[-1].text.split('\n')[0],
        ]
        odds = [
            btn_odds[0].text.split('\n')[-1],
            btn_odds[-1].text.split('\n')[-1]
        ]

        home_team = teams[1]
        away_team = teams[0]
        aligned_bet_name = bet_name
        aligned_bet_type = [
            'Away Team' + ' ' +  btn_odds[0].text.split('\n')[0],
            'Home Team' + ' ' +  btn_odds[-1].text.split('\n')[0],
        ]
        period_type = 'Quarter'
        period_value = game_time.split(' ')[0]
        period_time = game_time.split(' ')[1]
        return {
                'bet_name': bet_name,
                'bet_type': bet_type,
                'odds': odds,
                'home_team': home_team,
                'away_team': away_team,
                'aligned_bet_name': aligned_bet_name,
                'aligned_bet_type': aligned_bet_type,
                'period_type': period_type,
                'period_value': period_value,
                'period_time': period_time,
            }
    except:
        pass
    
    return 'FAILED'

def scrape_total_points(match_row, teams, game_time):
    try:
        bet_name = match_row.find_element(By.XPATH, ".//span[@class='title']").text
        outcome = match_row.find_elements(By.XPATH, ".//div[@class='outcome']")
        btn_odds = match_row.find_elements(By.XPATH, ".//button")
        bet_type_1 = outcome[0].find_element(By.XPATH, ".//div[@class='outcomeTitle']").text.replace('Over', 'O').replace('Under', 'U')
        bet_type_2 = outcome[-1].find_element(By.XPATH, ".//div[@class='outcomeTitle']").text.replace('Over', 'O').replace('Under', 'U')
        bet_type = [
            bet_type_1 + ' ' +  btn_odds[0].text.split('\n')[0],
            bet_type_2 + ' ' +  btn_odds[-1].text.split('\n')[0],
        ]
        odds = [
            btn_odds[0].text.split('\n')[-1],
            btn_odds[-1].text.split('\n')[-1]
        ]

        home_team = teams[1]
        away_team = teams[0]
        aligned_bet_name = bet_name
        aligned_bet_type = [
            bet_type_1 + ' ' +  btn_odds[0].text.split('\n')[0],
            bet_type_2 + ' ' +  btn_odds[-1].text.split('\n')[0],
        ]
        period_type = 'Quarter'
        period_value = game_time.split(' ')[0]
        period_time = game_time.split(' ')[1]
        return {
                'bet_name': bet_name,
                'bet_type': bet_type,
                'odds': odds,
                'home_team': home_team,
                'away_team': away_team,
                'aligned_bet_name': aligned_bet_name,
                'aligned_bet_type': aligned_bet_type,
                'period_type': period_type,
                'period_value': period_value,
                'period_time': period_time,
            }
    except:
        pass
    
    return 'FAILED'


def scrape_money_line(match_row, teams, game_time):
    try:
        bet_name = match_row.find_element(By.XPATH, ".//span[@class='title']").text
        outcome = match_row.find_elements(By.XPATH, ".//div[@class='outcome']")
        btn_odds = match_row.find_elements(By.XPATH, ".//button")
        bet_type = [
            outcome[0].find_element(By.XPATH, ".//div[@class='outcomeTitle']").text,
            outcome[-1].find_element(By.XPATH, ".//div[@class='outcomeTitle']").text,
        ]
        odds = [
            btn_odds[0].text.split('\n')[-1],
            btn_odds[-1].text.split('\n')[-1]
        ]
        home_team = teams[1]
        away_team = teams[0]
        aligned_bet_name = bet_name
        aligned_bet_type = [
            'Away Team',
            'Home Team',
        ]
        period_type = 'Quarter'
        period_value = game_time.split(' ')[0]
        period_time = game_time.split(' ')[1]
        return {
                'bet_name': bet_name,
                'bet_type': bet_type,
                'odds': odds,
                'home_team': home_team,
                'away_team': away_team,
                'aligned_bet_name': aligned_bet_name,
                'aligned_bet_type': aligned_bet_type,
                'period_type': period_type,
                'period_value': period_value,
                'period_time': period_time,
            }
    except:
        pass
    
    return 'FAILED'



def scrape_popular():
    prop_bets = []
    teams = driver.find_element(By.XPATH, ".//div[@class='teams']").text
    teams = teams.title().split('\n')
    game_name = f'{teams[0] + " @ " + teams[1]}'

    try:
        quarter_half = False
        try:
            # driver.find_element(By.XPATH, ".//li[@data-qa='pill-filter-quarter-half-bets']").click()
            driver.find_element(By.XPATH, ".//li[@data-qa='pill-filter-quarter']").click()
            WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.CLASS_NAME, 'MarketCardContainer')))
            quarter_half = True
        except Exception as e:
            logger.warning(f'Time wait is passed! {e}')
            pass
        
        time_stamp = datetime.now().strftime("%m/%d/%Y %H:%M:%S")
        sport = 'Football'
        game_time = games_time()
        if not game_time:
            return 'FINISH'
        # if 'Q4' in game_time:
        #     quarter_half = False
        is_timeout = check_timeout(game_time)    
        quarter_half = True    
        
        if quarter_half:                
            match_rows_pop = driver.find_elements(By.XPATH, ".//div[contains(@class, 'MarketCard')]")
            for idx, match_row in enumerate(match_rows_pop):
                if idx == 0:
                    continue
                bet_name = match_row.find_element(By.XPATH, ".//span[@class='title']").text
                if 'Spread' in bet_name:
                    sprd = scrape_spread(match_row, teams, game_time)
                    if sprd == 'FAILED':
                      logger.info('Moneylines bet was stopped')
                    else:
                        for i in range(2):
                            prop_info_dict_pop_ml = {
                                'SPORT': sport,
                                'GAME_TYPE': "Live",
                                'IS_PROP': 1,
                                'GAME_NAME': game_name,
                                'BET_NAME': sprd['bet_name'],
                                'BET_TYPE': sprd['bet_type'][i],
                                'ODDS': sprd['odds'][i],
                                'HOME_TEAM': sprd['home_team'],
                                'AWAY_TEAM': sprd['away_team'],
                                'ALIGNED_BET_NAME': sprd['aligned_bet_name'],
                                'ALIGNED_BET_TYPE':  sprd['aligned_bet_type'][i],
                                'PERIOD_TYPE': sprd['period_type'],
                                'PERIOD_VALUE': sprd['period_value'],
                                'PERIOD_TIME': sprd['period_time'],
                                'IS_TIMEOUT': is_timeout,
                                'SPORTS_BOOK': 'Caesars',
                                'TIMESTAMP': time_stamp,
                                'URL': URL
                            }
                            prop_bets.append(prop_info_dict_pop_ml)
                elif 'Total' in bet_name:
                    tps = scrape_total_points(match_row, teams, game_time)
                    
                    if sprd == 'FAILED':
                      logger.info('Moneylines bet was stopped')
                    else:
                        for i in range(2):
                            prop_info_dict_pop_ml = {
                                'SPORT': sport,
                                'GAME_TYPE': "Live",
                                'IS_PROP': 1,
                                'GAME_NAME': game_name,
                                'BET_NAME': tps['bet_name'],
                                'BET_TYPE': tps['bet_type'][i],
                                'ODDS': tps['odds'][i],
                                'HOME_TEAM': tps['home_team'],
                                'AWAY_TEAM': tps['away_team'],
                                'ALIGNED_BET_NAME': tps['aligned_bet_name'],
                                'ALIGNED_BET_TYPE':  tps['aligned_bet_type'][i],
                                'PERIOD_TYPE': tps['period_type'],
                                'PERIOD_VALUE': tps['period_value'],
                                'PERIOD_TIME': tps['period_time'],
                                'IS_TIMEOUT': is_timeout,
                                'SPORTS_BOOK': 'Caesars',
                                'TIMESTAMP': time_stamp,
                                'URL': URL
                            }
                            prop_bets.append(prop_info_dict_pop_ml)
                else:
                    mll = scrape_money_line(match_row, teams, game_time)
                    if mll == 'FAILED':
                      logger.info('Moneylines bet was stopped')
                    else:
                        for i in range(2):
                            prop_info_dict_pop_ml = {
                                'SPORT': sport,
                                'GAME_TYPE': "Live",
                                'IS_PROP': 1,
                                'GAME_NAME': game_name,
                                'BET_NAME': mll['bet_name'],
                                'BET_TYPE': mll['bet_type'][i],
                                'ODDS': mll['odds'][i],
                                'HOME_TEAM': mll['home_team'],
                                'AWAY_TEAM': mll['away_team'],
                                'ALIGNED_BET_NAME': mll['aligned_bet_name'],
                                'ALIGNED_BET_TYPE':  mll['aligned_bet_type'][i],
                                'PERIOD_TYPE': mll['period_type'],
                                'PERIOD_VALUE': mll['period_value'],
                                'PERIOD_TIME': mll['period_time'],
                                'IS_TIMEOUT': is_timeout,
                                'SPORTS_BOOK': 'Caesars',
                                'TIMESTAMP': time_stamp,
                                'URL': URL
                            }
                            prop_bets.append(prop_info_dict_pop_ml)

    except:
        pass
    else:
        if not prop_bets:
            return 'STOP'
        elif len(prop_bets) > 0:
            logger.info(f'Game is scraped successfully')
            return prop_bets

def main():
    module_operate_until = datetime.now() + module_work_duration

    failure_count = 0
    count_of_stopped = 0
    count_scraps = 0

    while datetime.now() < module_operate_until:
        urls = read_url_redis('caesars')
        for redis_url in urls:
            global URL
            URL = redis_url['data']
            driver.get(URL)
            file_tail = URL.split('/')[-1]

            parsing_start_time = time.time()
            try:
                logger.info(f'Start scraping')
                try:
                    # get all live games
                    games_on_initial_page = driver.find_elements(By.XPATH, "//div[@class='MarketCollection']")
                except:
                    logger.info('The game has ended')
                    res_upd = update_redis_status(URL, 2)
                    logger.info(res_upd)
                    break

                popular_bet_list = scrape_popular()
                if popular_bet_list == 'STOP':
                    logger.warning('Bets were stopped')
                    count_of_stopped += 1
                elif popular_bet_list == 'FINISH':
                    logger.info("The game has ended")
                    res_upd = update_redis_status(URL, 2)
                    logger.info(res_upd)
                    break

                else:
                    if not popular_bet_list:
                        time.sleep(10)
                        continue
                    # save data to redis db
                    saving_result = add_data_redis(f'football_caesars_prop_{file_tail}', popular_bet_list)
                    logger.info(
                        f'The result of saving data: {saving_result}') if saving_result == 'OK' else logger.exception(
                        f'The result of saving data: {saving_result}')                
                    count_scraps += 1

                if count_of_stopped == 10:
                    logger.warning('The game does not accept bets!')
                    res_upd = update_redis_status(URL, 3)
                    logger.info(res_upd)
                    count_of_stopped = 0

                parsing_work_time = time.time() - parsing_start_time
                time.sleep(max(0, update_frequency.total_seconds() - parsing_work_time))

                failure_count = 0

            except KeyboardInterrupt:
                logger.warning("Keyboard Interrupt. Quit the driver!")
                driver.quit()
                logger.warning(f'Module stopped working')
                res_upd = update_redis_status(URL, 2)
                logger.info(res_upd)
                break

            except Exception as e:
                logger.warning(f'Stop loop with errors:\n{e}')
                failure_count += 1
                if failure_count >= 5:
                    driver.quit()
                    logger.warning(f'Script exited after {failure_count} unsuccessful attempts to start the main loop')
                    res_upd = update_redis_status(URL, 3)
                    logger.info(res_upd)
                    break
                    
            if count_scraps % scrap_step == 0:
                actions_on_page(driver=driver, class_name="listIconWrapper")
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
