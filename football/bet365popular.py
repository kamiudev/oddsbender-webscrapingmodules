import time
from configparser import ConfigParser
from datetime import datetime
from random import randrange
from os import environ

from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from utilities.logging import get_logger
from utilities.utils import get_driver, str_to_timedelta, add_data_redis, actions_on_page, text_filter


# read config file
config_parser = ConfigParser()
config_parser.read('conf/bet365.conf')
module_conf = config_parser["MODULE"]

# init logging
logger_name = environ.get('football_bet365popular_get_logger', 'football_bet365_popular')
# for local logs storage and stdout use DEBUG_FLAG = 1
DEBUG_FLAG = environ.get('football_bet365popular_DEBUG_FLAG', 0)
log_level = environ.get('football_bet365popular_log_level', 'WARNING')

logger = get_logger(logger_name, DEBUG_FLAG, log_level)

# other variables
URL = environ.get('football_bet365_url', module_conf.get('URL'))
module_work_duration = str_to_timedelta(environ.get('football_bet365popular_module_work_duration', module_conf.get('module_work_duration')))
update_frequency = str_to_timedelta(environ.get('football_bet365popular_update_frequency', module_conf.get('update_frequency')))
browser = environ.get('football_bet365popular_browser', module_conf.get('browser_popular'))

scrap_step = int(environ.get('football_scrap_step', module_conf.get('scrap_step')))
scrap_limit = int(environ.get('football_scrap_limit', module_conf.get('scrap_limit')))

# init web driver
driver = get_driver(browser)
driver.get(URL)

logger.warning(f'Module started working with parameters:\nURL: {URL}\nmodule_work_duration: {module_work_duration}\nupdate_frequency: {update_frequency}\nbrowser: {browser}\nlogger_name: {logger_name}\nlog_level: {log_level}\nDEBUG_FLAG: {DEBUG_FLAG}')


def get_max_str(lst):
    max_str = lst[0]   # list is not empty
    for x in lst:
        if len(x) > len(max_str):
            max_str = x
    return max_str


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


def parse_gameline(game_on_initial_page, time_stamp, additional_param, iter):
    logger.info(f'Scrape Gameline')
    game_time_dict = {}
    game_name = game_on_initial_page.find_element(By.XPATH, './div/div/div/div').text.replace('\n', ' @ ')
    previous_game_time = game_on_initial_page.find_element(By.XPATH,
                                                           '//div[@class="ovm-FixtureDetailsTwoWay_Timer ovm-InPlayTimer "]').text
    away_home_team_list = split_string(game_name)
    if len(additional_param['times_list']) == 0:
        curent_game_time = game_on_initial_page.find_element(By.XPATH, './/div[contains(@class, "ovm-InPlayTimer")]').text
    if len(additional_param['times_list']) != 0:
        curent_game_time = additional_param.get('times_list')[iter]
    # previous_game_time = game_time_dict.get(game_name, '')
    is_timeout = 1 if curent_game_time == previous_game_time else 0
    game_time_dict[game_name] = curent_game_time

    gameline_bet_table = game_on_initial_page.find_element(By.XPATH, './div[2]')
    gameline_bet_table_data = gameline_bet_table.find_elements(By.XPATH, './/div[@aria-label]')
    gameline_bet_table_data_array = [bet.text for bet in gameline_bet_table_data]

    if gameline_bet_table_data_array == ['', '', '', '', '', '']:
        logger.warning(f'Empty gameline')
        
    if len(gameline_bet_table_data_array) == 2:
        gameline_bet_table_data_array = ['', '', '', '', gameline_bet_table_data_array[0], gameline_bet_table_data_array[1]]
        
    elif len(gameline_bet_table_data_array) == 4:
        gameline_bet_table_data_array = [gameline_bet_table_data_array[0], gameline_bet_table_data_array[1],
        gameline_bet_table_data_array[2], gameline_bet_table_data_array[3], '', '']

    popular_bets_array = []
    for i in range(2):
        spread, spread_odds = split_string(gameline_bet_table_data_array[i])
        total, total_odds = split_string(gameline_bet_table_data_array[i + 2])
        moneyline_odds = gameline_bet_table_data_array[i + 4]
        popular_bet_dict = {
            'SPORT': additional_param.get('sport'),
            'GAME_TYPE': additional_param.get('game_type'),
            'IS_PROP': 0,
            'GAME': game_name,
            'TEAM': away_home_team_list[i],
            'VS_TEAM': away_home_team_list[1 - i],
            'SPREAD': spread,
            'SPREAD_ODDS': spread_odds,
            'MONEYLINE_ODDS': moneyline_odds,
            'TOTAL': text_filter(total),
            'TOTAL_ODDS': total_odds,
            'HOME_TEAM': away_home_team_list[1],
            'AWAY_TEAM': away_home_team_list[0],
            'GAME_TIME': curent_game_time,
            'IS_TIMEOUT': is_timeout,
            'SPORTS_BOOK': 'Bet365',
            'TIMESTAMP': time_stamp
                            }
        popular_bets_array.append(popular_bet_dict)
    logger.info(f'Gameline scraped successfully')
    return popular_bets_array


def main():
    module_operate_until = datetime.now() + module_work_duration
    failure_count = 0
    count_scraps = 0

    while datetime.now() < module_operate_until:
        parsing_start_time = time.time()
        logger.warning(f'Start scraping games')
        # close notification window
        try:
            popup_close_button = WebDriverWait(driver, 3).until(EC.element_to_be_clickable(
                (By.CSS_SELECTOR, "body > div.iip-IntroductoryPopup > div > div.iip-IntroductoryPopup_Cross > span")))
            driver.execute_script("arguments[0].click();", popup_close_button)
            logger.info(f'Notification window closed on 1st try')
        except:
            logger.info(f'Notification window not found, try to use another XPATH ')
            try:
                popup_close_button = WebDriverWait(driver, 2).until(EC.element_to_be_clickable(
                    (By.XPATH, "/html/body/div[6]/div/div[1]")))
                driver.execute_script("arguments[0].click();", popup_close_button)
                logger.info(f'Notification window closed on 2nd try')
            except:
                logger.info(f'Notification window not found, continue working')

        additional_param = {}

        try:

            try:
                games_on_initial_page = WebDriverWait(driver, 10).until(EC.visibility_of_all_elements_located((By.XPATH, '//div[contains(@class, "ovm-Fixture_Container")]')))
                time.sleep(0.5)
            except KeyboardInterrupt:
                logger.warning('Script stopped manually')
                driver.quit()
                break

            if URL == driver.current_url:
                popular_bets_list = []

                # iterate web page for correct scrap all game time
                try:
                    if len(games_on_initial_page) >= 3:
                        tmp_times_list = []
                        times_list = []
                        for read_more in games_on_initial_page:
                            cur_time = driver.find_elements(By.XPATH, '//div[contains(@class, "ovm-Fixture_Container")]')
                            tmp_times_list.append([i.find_element(By.CSS_SELECTOR, '.ovm-InPlayTimer').text for i in cur_time])
                            driver.execute_script("arguments[0].scrollIntoView();", read_more)
                            time.sleep(0.1)

                        for it in range(len(tmp_times_list)):
                            times_list.append(get_max_str([i[it] for i in tmp_times_list]))
                        additional_param['times_list'] = times_list
                    else:
                        additional_param['times_list'] = ''

                except:
                    break

                # get sport
                try:
                    additional_param['sport'] = WebDriverWait(driver, 3).until(
                        EC.visibility_of_element_located((By.CSS_SELECTOR, '.ovm-ClassificationHeader_Text'))).text
                except:
                    additional_param['sport'] = 'Not identified'
                    logger.warning('It’s impossible to identify game type')

                # check if the game_type field is active
                try:
                    game_online = WebDriverWait(driver, 2).until(EC.visibility_of_element_located(
                        (By.CSS_SELECTOR, '.hm-HeaderMenuItem_LinkSelected-underscore div'))).text
                    if game_online == 'Live In Game':
                        additional_param['game_type'] = 'Live'
                    if game_online == 'Sports':
                        additional_param['game_type'] = 'Pre-game'
                except:
                    additional_param['game_type'] = 'Unable to Get'
                    logger.warning('There are no live game element found')

                time_stamp = datetime.now().strftime("%m/%d/%Y %H:%M:%S")

                for iter, game_on_initial_page in enumerate(games_on_initial_page):
                    logger.info(f'Start scraping {additional_param.get("sport")} gamelines')
                    popular_bets_list += parse_gameline(game_on_initial_page, time_stamp, additional_param, iter)

                # save data to redis db
                saving_result = add_data_redis('football_bet365_popular', popular_bets_list)
                logger.info(
                    f'The result of saving data: {saving_result}') if saving_result == 'OK' else logger.exception(
                    f'The result of saving data: {saving_result}')                
                count_scraps += 1

                # reset unsuccessful attempts in main loop
                failure_count = 0

                parsing_work_time = time.time() - parsing_start_time
                time.sleep(max(0, update_frequency.total_seconds() - parsing_work_time))

            if URL != driver.current_url or not games_on_initial_page:
                logger.warning(f'There are no live games')
                logger.info(f'Try to reopen {URL}')
                driver.get(URL)
                driver.refresh()
                time.sleep(randrange(4000, 12000, 10)/1000)

        except Exception as e:
            logger.exception(f'Stop script with errors:\n{e}')
            failure_count += 1
            if failure_count >= 5:
                driver.quit()
                logger.exception(f'Script exited after {failure_count} unsuccessful attempts to start the main loop')
                break
        
        if count_scraps % scrap_step == 0:
            actions_on_page(driver=driver, class_name="ovm-Fixture_Container")
            if count_scraps == scrap_limit:
                driver.refresh()                
                count_scraps = 0

    driver.quit()
    logger.warning(f'Module stopped working')


if __name__ == "__main__":
    main()
