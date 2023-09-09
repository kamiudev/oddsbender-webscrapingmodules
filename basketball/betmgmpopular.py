from os import environ
import time
from configparser import ConfigParser
from datetime import datetime
from random import randrange

from bs4 import BeautifulSoup
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from utilities.logging import get_logger
from utilities.utils import str_to_timedelta, get_driver, actions_on_page, text_filter
from utilities.redis import RedisClient

# read config file
config_parser = ConfigParser()
config_parser.read('conf/betmgm.conf')
module_conf = config_parser["MODULE"]

# init logging
logger_name = environ.get('basketball_betmgmpopular_get_logger', 'basketball_betmgm_popular')
# for local logs storage and stdout use DEBUG_FLAG = 1
DEBUG_FLAG = environ.get('basketball_betmgmpopular_DEBUG_FLAG', 1)
log_level = environ.get('basketball_betmgmpopular_log_level', 'WARNING')

logger = get_logger(logger_name, DEBUG_FLAG, log_level)

# other variables
URL = environ.get('basketball_betmgm_url', module_conf.get('URL'))
module_work_duration = str_to_timedelta(environ.get('basketball_betmgmpopular_module_work_duration', module_conf.get('module_work_duration')))
update_frequency = str_to_timedelta(environ.get('basketball_betmgmpopular_update_frequency', module_conf.get('update_frequency')))
browser = environ.get('basketball_betmgmpopular_browser', module_conf.get('browser_popular'))

scrap_step = int(environ.get('basketball_scrap_step', module_conf.get('scrap_step')))
scrap_limit = int(environ.get('basketball_scrap_limit', module_conf.get('scrap_limit')))

script_version = 'v29122022'

# init web driver
driver = get_driver(browser)
driver.get(URL)

logger.warning(f'Module started working with parameters:\nURL: {URL}\nmodule_work_duration: {module_work_duration}\nupdate_frequency: {update_frequency}\nbrowser: {browser}\nlogger_name: {logger_name}\nlog_level: {log_level}\nDEBUG_FLAG: {DEBUG_FLAG}')

redisClient = RedisClient()

def parse_gameline_bet(additional_param, get_data, game_time):
    logger.info(f'Start scraping Gameline')

    game_counter = 1
    tmp_list = []
    main_list = []
    popular_bets_list = []

    for i in get_data:
        if game_counter == 4:
            game_counter = 1

        if 'BasketballSort' and 'Game Lines' not in i.text:
            if game_counter == 1:
                team = i.text
                tmp_list.append(team[1:])

            if game_counter == 2:
                vs_team = i.text
                tmp_list.append(vs_team[1:])

            if game_counter == 3:
                get_spread = i.find_all("div", {"class": ["option-attribute ng-star-inserted"]})
                spread = [i.text.replace(' ', '') for i in get_spread][:2]
                spread = ['', ''] if len(spread) != 2 else spread
                tmp_list.append(spread)

                get_spread_odds = i.find_all("div", {"class": ["option option-value ng-star-inserted"]})
                spread_odds = [i.text for i in get_spread_odds[:2]]
                spread_odds = ['', ''] if len(spread_odds) != 2 else spread_odds
                tmp_list.append(spread_odds)

                get_moneyline_odds = i.find_all("div", {"class": ["option option-value ng-star-inserted"]})
                moneyline_odds = [i.text for i in get_moneyline_odds[4:6]]
                moneyline_odds = ['', ''] if len(moneyline_odds) != 2 else moneyline_odds
                tmp_list.append(moneyline_odds)

                get_total = i.find_all("div", {
                    "class": ["option-attribute small-font option-group-attribute ng-star-inserted"]})
                total = [i.text.replace(' ', '') for i in get_total]
                total = ['', ''] if len(total) != 2 else total
                tmp_list.append(total)

                get_total_odds = i.find_all("div", {"class": ["option option-value ng-star-inserted"]})
                total_odds = [i.text for i in get_total_odds[2:4]]
                total_odds = ['', ''] if len(total_odds) != 2 else total_odds
                tmp_list.append(total_odds)

            game_counter += 1
            if game_counter == 4:
                main_list.append(tmp_list)
                tmp_list = []

    for tl, gt in zip(main_list, game_time):
        is_timeout = 0 if ':' in gt else 1
        for side in range(2):
            popular_bet_dict = {}
            popular_bet_dict['SPORT'] = additional_param.get('sport')
            popular_bet_dict['GAME_TYPE'] = f"{additional_param.get('game_type')} {script_version}"
            popular_bet_dict['IS_PROP'] = 0
            popular_bet_dict['GAME'] = f'{tl[0]} vs {tl[1]}'
            popular_bet_dict['TEAM'] = tl[0 + side]
            popular_bet_dict['VS_TEAM'] = tl[1 - side]
            popular_bet_dict['SPREAD'] = ' '.join((tl[0 + side], tl[2][0 + side])) 
            popular_bet_dict['SPREAD_ODDS'] = tl[3][0 + side]
            popular_bet_dict['MONEYLINE_ODDS'] = tl[4][0 + side]
            popular_bet_dict['TOTAL'] = text_filter(tl[5][0 + side])
            popular_bet_dict['TOTAL_ODDS'] = tl[6][0 + side]
            popular_bet_dict['HOME_TEAM'] = tl[1]
            popular_bet_dict['AWAY_TEAM'] = tl[0]
            popular_bet_dict['GAME_TIME'] = gt
            popular_bet_dict['IS_TIMEOUT'] = is_timeout
            popular_bet_dict['SPORTS_BOOK'] = 'Betmgm'
            popular_bet_dict['TIMESTAMP'] = additional_param.get('time_stamp')
            popular_bets_list.append(popular_bet_dict)

    return popular_bets_list


def main():
    module_operate_until = datetime.now() + module_work_duration
    exception_counter = 0
    count_scraps = 0

    while datetime.now() < module_operate_until:
        additional_param = {}
        try:
            parsing_start_time = time.time()
            logger.info(f'Start scraping...')

            try:
                # check if basketball is in live games
                check_game = WebDriverWait(driver, 10).until(EC.visibility_of_all_elements_located(
                    (By.XPATH, "//*[@class='tab-bar-item active ng-star-inserted']")))
                check_game_res = [i.text for i in check_game if 'Basketball' in i.text]
            except:
                check_game_res = ''

            if check_game_res:
                # if we found the games by the link then it's live games and basketball
                additional_param['sport'] = 'Basketball'
                additional_param['game_type'] = 'Live'

                # get all live games
                games_on_initial_page = driver.find_elements(By.XPATH, './/div[@class="title"]/span[contains(text(), "NBA") or contains(text(), "College")]/ancestor::ms-event-group')
                for game_section in games_on_initial_page:
                    soup = BeautifulSoup(game_section.get_attribute('innerHTML'), "html.parser")
                    get_data = [i for i in soup.find_all("div", {"class": ["participant", "grid-group-container"]})]

                    get_game_time = [i for i in soup.find_all("ms-event-timer", {"class": ["grid-event-timer"]})]
                    game_time = [i.text for i in get_game_time]

                    additional_param['time_stamp'] = datetime.now().strftime("%m/%d/%Y %H:%M:%S")

                    popular_bets_list = parse_gameline_bet(additional_param, get_data, game_time)

                    if not popular_bets_list:
                        continue

                    # save data to redis db
                    saving_result = redisClient.add_data_redis('basketball_betmgm_popular', popular_bets_list)
                    logger.info(
                        f'The result of saving data: {saving_result}') if saving_result == 'OK' else logger.exception(
                        f'The result of saving data: {saving_result}')                
                    count_scraps += 1

                    parsing_work_time = time.time() - parsing_start_time
                    time.sleep(max(0, update_frequency.total_seconds() - parsing_work_time))
                    exception_counter = 0

            if not check_game_res:
                logger.warning('There are no live games, waiting for some time and trying again')
                time.sleep(randrange(4000, 12000, 10) / 1000)
                driver.get(URL)
                driver.refresh()

        except KeyboardInterrupt:
            logger.info("Keyboard Interrupt. Quit the driver!")
            driver.close()
            logger.warning(f'Module stopped working')
            break

        except Exception as e:
            logger.exception(f"Exception in main scraping cycle. {e}")
            exception_counter += 1
            if exception_counter >= 5:
                driver.close()
                logger.exception(
                    f'Script exited after {exception_counter} unsuccessful attempts to execute the main loop')
                break
                
        if count_scraps % scrap_step == 0:
            actions_on_page(driver=driver, class_name="grid-wrapper ng-star-inserted")
            if count_scraps == scrap_limit:
                driver.refresh()                
                count_scraps = 0

    driver.close()
    logger.warning(f'Module stopped working')


if __name__ == "__main__":
    main()
