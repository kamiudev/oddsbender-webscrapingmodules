import time
from configparser import ConfigParser
from datetime import datetime
from random import randrange
from os import environ

from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from utilities.logging import get_logger
from utilities.utils import str_to_timedelta, split_string, get_driver, add_data_redis, actions_on_page, text_filter
from utilities.redis import RedisClient
from utilities.driver_proxy import get_driver_proxy

# read config file
config_parser = ConfigParser()
config_parser.read('conf/fanduel.conf')
module_conf = config_parser["MODULE"]

# init logging
logger_name = environ.get('basketball_fanduelpopular_get_logger', 'basketball_fanduel_popular')
# for local logs storage and stdout use DEBUG_FLAG = 1
DEBUG_FLAG = environ.get('basketball_fanduelpopular_DEBUG_FLAG', 1)
log_level = environ.get('basketball_fanduelpopular_log_level', 'WARNING')

logger = get_logger(logger_name, DEBUG_FLAG, log_level)

# other variables
URL = environ.get('basketball_fanduel_url', module_conf.get('URL'))
module_work_duration = str_to_timedelta(environ.get('basketball_fanduelpopular_module_work_duration', module_conf.get('module_work_duration')))
update_frequency = str_to_timedelta(environ.get('basketball_fanduelpopular_update_frequency', module_conf.get('update_frequency')))
browser = environ.get('basketball_fanduelpopular_browser', module_conf.get('browser_popular'))

scrap_step = int(environ.get('basketball_scrap_step', module_conf.get('scrap_step')))
scrap_limit = int(environ.get('basketball_scrap_limit', module_conf.get('scrap_limit')))

# init web driver
# driver = get_driver(browser)
# driver.get(URL)
driver = None

redisClient = RedisClient()

logger.warning(f'Module started working with parameters:\nURL: {URL}\nmodule_work_duration: {module_work_duration}\nupdate_frequency: {update_frequency}\nbrowser: {browser}\nlogger_name: {logger_name}\nlog_level: {log_level}\nDEBUG_FLAG: {DEBUG_FLAG}')


def parse_gameline_bet(bet_table, additional_param, iter):
    logger.info(f'Start scraping Gameline')
    game_name = bet_table.find_element(By.XPATH, './a').get_attribute('title')
    away_home_team_list = split_string(game_name)
    bet_table_buttons = bet_table.find_elements(By.XPATH, './/div[@role="button"]')
    bet_table_buttons_text = [single_bet_data.text for single_bet_data in bet_table_buttons]

    if bet_table_buttons_text == ['', '', '', '', '', '']:
        logger.warning(f'Empty gameline')

    # check for timeout
    try:
        is_timeout = 0 if ':' in additional_param.get('times_list')[iter] else 1
    except:
        is_timeout = 1

    popular_bets = []
    for i in range(2):
        spread, spread_odds = split_string(bet_table_buttons_text[i*3])
        total, total_odds = split_string(bet_table_buttons_text[2+i*3])
        popular_bet_dict = {
            'SPORT': additional_param.get('sport'),
            'GAME_TYPE': additional_param.get('game_type'),
            'IS_PROP': 0,
            'GAME': game_name,
            'TEAM': away_home_team_list[i],
            'VS_TEAM': away_home_team_list[1-i],
            'SPREAD': ' '.join((away_home_team_list[i], spread)),
            'SPREAD_ODDS': spread_odds,
            'MONEYLINE_ODDS': bet_table_buttons_text[1+i*3],
            'TOTAL': text_filter(total),
            'TOTAL_ODDS': total_odds,
            'HOME_TEAM': away_home_team_list[1],
            'AWAY_TEAM': away_home_team_list[0],
            'GAME_TIME': additional_param.get('times_list')[iter],
            'IS_TIMEOUT': is_timeout,
            'SPORTS_BOOK': 'Fanduel',
            'TIMESTAMP': additional_param.get('time_stamp')
        } 
        popular_bets.append(popular_bet_dict)
    logger.info(f'Gameline scraped successfully')
    return popular_bets

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

        # check bot capture
        try:
            driver.find_element(By.XPATH, '//h1[contains(text(), "Please verify you are a human")]').text
            logger.error('Please verify you are a human')
            check_capture()
        except:
            pass

        try:
            driver.implicitly_wait(10)

            parsing_start_time = time.time()
            logger.info(f'Start scraping...')

            # click on Basketball game
            try:
                click_game_source = driver.find_elements(By.XPATH, "//a[contains(@href,'/live')]")
                clicks = [game.click() for game in click_game_source if 'Basketball' in game.text]
                if len(clicks) == 0:
                    logger.error('The basketball tab is absent')
                    # time.sleep(randrange(4000, 12000, 10) / 1000)
                    time.sleep(1)
                    logger.info('Page refresh')
                    driver.refresh()
                    continue

                logger.info('The game selection button has been clicked')
            except:
                logger.error("Not found click_game_source html elements - //a[contains(@href,'/live')]")
                # time.sleep(randrange(4000, 12000, 10) / 1000)
                time.sleep(1)
                logger.info('Page refresh')
                driver.refresh()
                continue

            try:
                basketball_games = WebDriverWait(driver, 10).until(
                    EC.visibility_of_all_elements_located((By.XPATH, '//a[contains(@href, "basketball/")]/parent::div')))
            except:
                logger.error('Not found basketball_games html elements - //a[contains(@href, "basketball/")]/parent::div')
                # time.sleep(randrange(4000, 12000, 10) / 1000)
                time.sleep(1)
                logger.info('Page refresh')
                driver.refresh()
                continue

            # get sport and type_game
            try:
                get_sport = driver.find_element(By.XPATH, "//h2[contains(text(),'Live ')]").text.split(' ')[1]
                additional_param['sport'] = get_sport
                additional_param['game_type'] = 'Live'
            except:
                additional_param['game_type'] = 'Pre-game'
                additional_param['sport'] = 'Not identified'
                logger.error('It’s impossible to identify game type')

            if additional_param.get('sport') == 'Basketball':
                # get game time
                try:
                    cur_time = driver.find_elements(By.XPATH, "//span [contains(text(),'QUARTER') or contains(text(),'HALF') or contains(text(),'OVERTIME')]")
                    times_list = []
                    for ct in cur_time:
                        if ct.text != '':
                            times_list += [ct.text]*2
                    additional_param['times_list'] = times_list
                except:
                    additional_param['times_list'] = ['' for i in range(len(basketball_games))]

                popular_bets_list = []
                additional_param['time_stamp'] = datetime.now().strftime("%m/%d/%Y %H:%M:%S")
                logger.info(f'Start scraping backetball games')

                if len(basketball_games) >= 1:
                    iter = 0
                    while iter < len(additional_param['times_list']):
                        try:
                            basketball_game = basketball_games[iter]
                            logger.info(f'{iter}: {basketball_game.text}')
                        except Exception as e:
                            logger.error(f"stale element reference: element is not attached to the page document - {e}")
                            break

                        if 'More wagers' in basketball_game.text:
                            if 'LiveTag_svg__a' not in basketball_game.get_attribute('innerHTML'):
                                del basketball_games[iter-1:iter+1]
                                iter-=1
                                continue
                            else:
                                game_url = basketball_game.find_element(By.XPATH, './a').get_attribute('href')
                                if 'nba' in game_url or 'ncaa-basketball-men' in game_url:
                                    popular_bets_list += parse_gameline_bet(basketball_game, additional_param, iter)
                        iter += 1

                    if not popular_bets_list:
                        continue

                    # save data to redis db
                    saving_result = redisClient.add_data_redis('basketball_fanduel_popular', popular_bets_list)
                    logger.info(
                        f'The result of saving data: {saving_result}') if saving_result == 'OK' else logger.exception(
                        f'The result of saving data: {saving_result}')                    
                    count_scraps += 1

                    parsing_work_time = time.time() - parsing_start_time
                    # time.sleep(max(0, update_frequency.total_seconds() - parsing_work_time))                    
                    time.sleep(1)                    

                    exception_counter = 0

                if len(basketball_games) == 0:
                    logger.warning('The game tab is present, but no live games are detected')
                    logger.info(f'Try to reopen after system time out')
                    # time.sleep(randrange(4000, 12000, 10) / 1000)
                    time.sleep(1)
                    driver.refresh()

            if additional_param.get('sport') != 'Basketball':
                logger.warning('There are no live games or there was a redirection')
                logger.info(f'Trying to reopen after system time out')
                time.sleep(randrange(4000, 12000, 10)/1000)
                driver.refresh()

        except KeyboardInterrupt:
            logger.warning("Keyboard Interrupt. Quit the driver!")
            driver.quit()
            logger.warning(f'Module stopped working')
            break

        except Exception as e:
            logger.exception(f"Exception in main scraping cycle. {e}")
            exception_counter += 1
            if exception_counter >= 5:
                driver.quit()
                logger.exception(f'Script exited after {exception_counter} unsuccessful attempts to execute the main loop')
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
