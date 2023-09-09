import time
from configparser import ConfigParser
from datetime import datetime
from random import randrange
from os import environ

from bs4 import BeautifulSoup
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.common.keys import Keys
from selenium.common.exceptions import StaleElementReferenceException
from utilities.logging import get_logger
from utilities.utils import str_to_timedelta, get_driver, actions_on_page, text_filter
from utilities.redis import RedisClient

# read config file
config_parser = ConfigParser()
config_parser.read('conf/sugarhouse.conf')
module_conf = config_parser["MODULE"]

# init logging
logger_name = environ.get('basketball_sugarhousepopular_get_logger', 'basketball_sugarhouse_popular')
# for local logs storage and stdout use DEBUG_FLAG = 1
DEBUG_FLAG = environ.get('POPULAR_LOG_DEBUG_FLAG', 1 )
log_level = environ.get('basketball_sugarhouse_popular_log_level', 'WARNING')
logger = get_logger(logger_name, DEBUG_FLAG, log_level)

# other variables
URL = environ.get('basketball_sugarhouse_url', module_conf.get('URL'))
module_work_duration = str_to_timedelta(environ.get('basketball_sugarhousepopular_module_work_duration', module_conf.get('module_work_duration')))
update_frequency = str_to_timedelta(environ.get('basketball_sugarhousepopular_update_frequency', module_conf.get('update_frequency')))
browser = environ.get('basketball_sugarhousepopular_browser', module_conf.get('browser_popular'))

scrap_step = int(environ.get('basketball_scrap_step', module_conf.get('scrap_step')))
scrap_limit = int(environ.get('basketball_scrap_limit', module_conf.get('scrap_limit')))

# init web driver
driver = get_driver(browser)
driver.get(URL)

redisClient = RedisClient()

logger.warning(f'Module started working with parameters:\nURL: {URL}\nmodule_work_duration: {module_work_duration}\nupdate_frequency: {update_frequency}\nbrowser: {browser}\nlogger_name: {logger_name}\nlog_level: {log_level}\nDEBUG_FLAG: {DEBUG_FLAG}')

def parse_gameline_bet(basketball_game, additional_param):
    logger.info(f'Start scraping Gameline')
    try:
        popular_bets_list = []

        tmp_game = []
        soup = BeautifulSoup(basketball_game, "html.parser")

        for k in soup.prettify().split('\n'):
            if '<' not in k:
                tmp_game.append(k.replace('\xa0', '').lstrip())

        if [i for i in tmp_game if i in ['Spread', 'Win', 'TOTAL POINTS']] and len(tmp_game) < 25:
            moneyline = ['', '']
            spread = ['', '']
            spread_odds = ['', '']
            total = ['', '']
            total_odds = ['', '']
            game_time = ''

            if 'Live' not in tmp_game:
                return None

            tmp_game = tmp_game[3:] if 'events' == tmp_game[2] else tmp_game
            if 'Live' in tmp_game:
                game_type = tmp_game[tmp_game.index('Live')]
                if ':' in tmp_game[tmp_game.index('Live') + 1]:
                    teams = [tmp_game[tmp_game.index('Live') + 3], tmp_game[tmp_game.index('Live') + 5]]
                    game_time = f"{tmp_game[tmp_game.index('Live') + 2]} {tmp_game[tmp_game.index('Live') + 1]}"
                    is_timeout = 1 if tmp_game[tmp_game.index('Live') + 1] in ['00:00', '20:00'] else 0
                if ':' not in tmp_game[tmp_game.index('Live') + 1]:
                    teams = [tmp_game[tmp_game.index('Live') + 1], tmp_game[tmp_game.index('Live') + 2]]
                    game_time = ''
                    is_timeout = 1

            if 'Spread' in tmp_game:
                if '+' in tmp_game[tmp_game.index('Spread') + 1] or '-' in tmp_game[tmp_game.index('Spread') + 1] and \
                        tmp_game[
                            tmp_game.index('Spread') + 1] != 'Closed':
                    spread = [tmp_game[tmp_game.index('Spread') + 1], tmp_game[tmp_game.index('Spread') + 3]]
                    spread_odds = [tmp_game[tmp_game.index('Spread') + 2], tmp_game[tmp_game.index('Spread') + 4]]

                elif '+' in tmp_game[tmp_game.index('Spread') + 2] or '-' in tmp_game[tmp_game.index('Spread') + 2] and \
                        tmp_game[tmp_game.index('Spread') + 2] != 'Closed':
                    spread = [tmp_game[tmp_game.index('Spread') + 2], tmp_game[tmp_game.index('Spread') + 4]]
                    spread_odds = [tmp_game[tmp_game.index('Spread') + 3], tmp_game[tmp_game.index('Spread') + 5]]

                elif '+' in tmp_game[tmp_game.index('Spread') + 3] or '-' in tmp_game[tmp_game.index('Spread') + 3] and \
                        tmp_game[tmp_game.index('Spread') + 3] != 'Closed':
                    spread = [tmp_game[tmp_game.index('Spread') + 3], tmp_game[tmp_game.index('Spread') + 5]]
                    spread_odds = [tmp_game[tmp_game.index('Spread') + 4], tmp_game[tmp_game.index('Spread') + 6]]

            if 'Win' in tmp_game and 'TOTAL POINTS' in tmp_game and 'Spread' in tmp_game:
                if tmp_game[tmp_game.index('Spread') + 4] != 'Closed':
                    moneyline = [tmp_game[tmp_game.index('Win') + 6].replace('Closed', ''),
                                 tmp_game[tmp_game.index('Win') + 7].replace('Closed', '')]

                if tmp_game[tmp_game.index('Spread') + 4] == 'Closed':
                    moneyline = [tmp_game[tmp_game.index('Win') + 4].replace('Closed', ''),
                                 tmp_game[tmp_game.index('Win') + 5].replace('Closed', '')]

            if 'Win' in tmp_game and 'TOTAL POINTS' not in tmp_game and 'Spread' in tmp_game:
                for i in tmp_game:
                    if ' Bets' in i and tmp_game[tmp_game.index(i) - 1] != 'Closed':
                        moneyline = [tmp_game[tmp_game.index(i) - 2], tmp_game[tmp_game.index(i) - 1]]

            if 'Win' in tmp_game and 'TOTAL POINTS' in tmp_game and 'Spread' not in tmp_game:
                moneyline = [tmp_game[tmp_game.index('Win') + 2], tmp_game[tmp_game.index('Win') + 3]]

            if 'Win' in tmp_game and 'TOTAL POINTS' not in tmp_game and 'Spread' not in tmp_game:
                moneyline = [tmp_game[tmp_game.index('Win') + 1], tmp_game[tmp_game.index('Win') + 2]]

            if 'TOTAL POINTS' in tmp_game:
                for i in tmp_game:
                    if ' Bets' in i:
                        if tmp_game[tmp_game.index(i) - 1] != 'Closed':
                            if 'U' in tmp_game[tmp_game.index(i) - 2]:
                                total = [tmp_game[tmp_game.index(i) - 4], tmp_game[tmp_game.index(i) - 2]]
                                total_odds = [tmp_game[tmp_game.index(i) - 3], tmp_game[tmp_game.index(i) - 1]]
                                break
                            if 'U' in tmp_game[tmp_game.index(i) - 3]:
                                total = [tmp_game[tmp_game.index(i) - 6], tmp_game[tmp_game.index(i) - 3]]
                                total_odds = [tmp_game[tmp_game.index(i) - 4], tmp_game[tmp_game.index(i) - 1]]
                                break

            for side in range(2):
                popular_bet_dict = {}

                popular_bet_dict['SPORT'] = additional_param.get('sport')
                popular_bet_dict['GAME_TYPE'] = game_type
                popular_bet_dict['IS_PROP'] = 0
                popular_bet_dict['GAME'] = f'{teams[0]} @ {teams[1]}'
                popular_bet_dict['TEAM'] = teams[0 + side]
                popular_bet_dict['VS_TEAM'] = teams[1 - side]
                popular_bet_dict['SPREAD'] = f'{teams[0 + side]} {spread[0 + side]}'
                popular_bet_dict['SPREAD_ODDS'] = spread_odds[0 + side]
                popular_bet_dict['MONEYLINE_ODDS'] = moneyline[0 + side]
                popular_bet_dict['TOTAL'] = text_filter(total[0 + side])
                popular_bet_dict['TOTAL_ODDS'] = total_odds[0 + side]
                popular_bet_dict['HOME_TEAM'] = teams[1]
                popular_bet_dict['AWAY_TEAM'] = teams[0]
                popular_bet_dict['GAME_TIME'] = game_time
                popular_bet_dict['IS_TIMEOUT'] = is_timeout
                popular_bet_dict['SPORTS_BOOK'] = 'Sugarhouse'
                popular_bet_dict['TIMESTAMP'] = additional_param.get('time_stamp')
                popular_bets_list.append(popular_bet_dict)

            logger.info(f'Gameline scraped successfully')
            return popular_bets_list

    except Exception as parcing_error:
        logger.exception(f'{parcing_error}\n{tmp_game}')
        return None

def main():
    module_operate_until = datetime.now() + module_work_duration

    failure_count = 0
    count_scraps = 0

    while datetime.now() < module_operate_until:
        additional_param = {}
        parsing_start_time = time.time()
        try:
            logger.info(f'Start scraping populars')

            try:
                # check if basketball is in live games
                get_check_game = WebDriverWait(driver, 10).until(EC.presence_of_element_located(
                    (By.XPATH, "//*[@alt='Basketball']")))
                check_game = 'Basketball' if get_check_game else ""
            except:
                check_game = ''
            
            if 'Basketball' in check_game:
                additional_param['sport'] = check_game
                additional_param['time_stamp'] = datetime.now().strftime("%m/%d/%Y %H:%M:%S")

                popular_bets_list = []

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
                        if 'NBA' not in unhidden_tab.get_attribute('id') and 'NCAAB' not in unhidden_tab.get_attribute('id'):
                            unhidden_tab.click()
                            logger.info(f'Closed {unhidden_tab.text}')
                except:
                    logger.info('All tabs closed')

                body = driver.find_element(By.CSS_SELECTOR, 'body')
                all_games = []

                for i in range(10):
                    for tmp_game in driver.find_elements(By.XPATH, "//div[contains(@data-testid, 'listview-group')]"):
                        try:
                            all_games.append(tmp_game.get_attribute('innerHTML'))
                        except StaleElementReferenceException:
                            pass

                    body.send_keys(Keys.PAGE_DOWN)
                    time.sleep(0.1)

                    try:
                        show_more = driver.find_element(By.XPATH, "//*[contains(text(),'Show more')]")
                        driver.execute_script("arguments[0].click();", show_more)
                        logger.info('Clicked button - Show more games')
                    except:
                        pass
                logger.info(f'Found {int(len(all_games)/2)} unfiltered games')
                for basketball_game in all_games:
                    if basketball_game != None:
                        dct_result = parse_gameline_bet(basketball_game, additional_param)
                        if dct_result != None:
                            if str(dct_result[0].get('GAME')) not in str(popular_bets_list):
                                popular_bets_list += dct_result

                # save data to redis db
                logger.info(f'Found {len(popular_bets_list)} filtered rows')
                if len(popular_bets_list) != 0:
                    saving_result = redisClient.add_data_redis('basketball_sugarhouse_popular', popular_bets_list)
                    logger.info(
                        f'The result of saving data: {saving_result}') if saving_result == 'OK' else logger.exception(
                        f'The result of saving data: {saving_result}')

                count_scraps += 1

                # reset unsuccessful attempts in main loop
                failure_count = 0

                if len(all_games) == 0:
                    logger.warning('There are no live games, waiting for some time and trying again')
                    time.sleep(randrange(4000, 12000, 10) / 1000)
                    driver.refresh()
                    continue

                parsing_work_time = time.time() - parsing_start_time
                time.sleep(max(0, update_frequency.total_seconds() - parsing_work_time))

                failure_count = 0

            if 'Basketball' not in check_game:
                logger.info('No games or VPN disable')

        except KeyboardInterrupt:
            logger.info("Keyboard Interrupt. Quit the driver!")
            driver.quit()
            logger.warning(f'Module stopped working')
            break

        except Exception as e:
            logger.exception(f"Exception in main scraping cycle. {e}")
            failure_count += 1
            if failure_count >= 5:
                driver.quit()
                logger.exception(
                    f'Script exited after {failure_count} unsuccessful attempts to execute the main loop')
                break
                
        if count_scraps % scrap_step == 0:
            actions_on_page(driver=driver, class_name="sc-fzXfNO gPURds")
            if count_scraps == scrap_limit:
                driver.refresh()                
                count_scraps = 0

    driver.quit()
    logger.warning(f'Module stopped working')


if __name__ == "__main__":
    main()
