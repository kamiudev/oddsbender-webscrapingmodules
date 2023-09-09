import time
from configparser import ConfigParser
from datetime import datetime, timezone
from random import randrange
from os import environ

from bs4 import BeautifulSoup
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from utilities.logging import get_logger
from utilities.utils import str_to_timedelta, get_driver, add_data_redis, actions_on_page, text_filter
import traceback

# read config file
config_parser = ConfigParser()
config_parser.read('conf/betmgm.conf')
module_conf = config_parser["MODULE"]

# init logging
logger_name = environ.get('football_betmgmpopular_get_logger', 'football_betmgm_popular')
# for local logs storage and stdout use DEBUG_FLAG = 1
DEBUG_FLAG = environ.get('football_betmgmpopular_DEBUG_FLAG', 0)
log_level = environ.get('football_betmgmpopular_log_level', 'WARNING')

logger = get_logger(logger_name, DEBUG_FLAG, log_level)

# other variables
URL = environ.get('football_betmgm_url', module_conf.get('URL'))
module_work_duration = str_to_timedelta(environ.get('football_betmgmpopular_module_work_duration', module_conf.get('module_work_duration')))
update_frequency = str_to_timedelta(environ.get('football_betmgmpopular_update_frequency', module_conf.get('update_frequency')))
browser = environ.get('football_betmgmpopular_browser', module_conf.get('browser_popular'))

scrap_step = int(environ.get('football_scrap_step', module_conf.get('scrap_step')))
scrap_limit = int(environ.get('football_scrap_limit', module_conf.get('scrap_limit')))

# init web driver
driver = get_driver(browser)
driver.get(URL)
pre_bet_values = {}

logger.warning(f'Module started working with parameters:\nURL: {URL}\nmodule_work_duration: {module_work_duration}\nupdate_frequency: {update_frequency}\nbrowser: {browser}\nlogger_name: {logger_name}\nlog_level: {log_level}\nDEBUG_FLAG: {DEBUG_FLAG}')


def parse_gameline_bet(additional_param, get_data, game_time, league):
    logger.info(f'Start scraping Gameline')

    game_counter = 1
    tmp_list = []
    main_list = []
    popular_bets_list = []

    for i in get_data:
        if game_counter == 4:
            game_counter = 1

        if 'FootballSort' and 'Game Lines' not in i.text:
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
                    "class": ["option-attribute option-group-attribute ng-star-inserted"]})
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
        is_timeout = 0 if '<' in gt else 1
        game_name =  (f'{tl[0]} @ {tl[1]}').strip()

        if not game_name in pre_bet_values:
            pre_bet_values[game_name] = {}

        for side in range(2):
            popular_bet_dict = {}
            popular_bet_dict['SPORT'] = additional_param.get('sport')
            popular_bet_dict['LEAGUE'] = league
            popular_bet_dict['GAME_TYPE'] = additional_param.get('game_type')
            popular_bet_dict['IS_PROP'] = 0
            popular_bet_dict['GAME'] = game_name
            popular_bet_dict['TEAM'] = (tl[0 + side]).strip()
            popular_bet_dict['VS_TEAM'] = (tl[1 - side]).strip()
            popular_bet_dict['SPREAD'] = tl[2][0 + side]
            popular_bet_dict['SPREAD_ODDS'] = tl[3][0 + side]
            popular_bet_dict['MONEYLINE_ODDS'] = tl[4][0 + side]
            popular_bet_dict['TOTAL'] = text_filter(tl[5][0 + side])
            popular_bet_dict['TOTAL_ODDS'] = tl[6][0 + side]
            popular_bet_dict['HOME_TEAM'] = (tl[1]).strip()
            popular_bet_dict['AWAY_TEAM'] = (tl[0]).strip()
            popular_bet_dict['PERIOD_TYPE'] = get_period_type(gt)
            popular_bet_dict['PERIOD_VALUE'] = get_period_value(gt)
            popular_bet_dict['PERIOD_TIME'] = get_period_time(gt)
            popular_bet_dict['IS_TIMEOUT'] = is_timeout
            popular_bet_dict['SPORTS_BOOK'] = 'Betmgm'
            popular_bet_dict['TIMESTAMP'] = additional_param.get('time_stamp')

            popular_bet_dict['HAS_CHANGED'] = get_changed(pre_bet_values[game_name], popular_bet_dict, side)
            popular_bets_list.append(popular_bet_dict)

            pre_bet_values[game_name][side] = popular_bet_dict

    return popular_bets_list

def get_changed(pre_values, bet_dict, side):
    if not side in pre_values:
        return 1
    if (pre_values[side]['SPREAD'] == bet_dict['SPREAD']
        and pre_values[side]['SPREAD_ODDS'] == bet_dict['SPREAD_ODDS']
        and pre_values[side]['MONEYLINE_ODDS'] == bet_dict['MONEYLINE_ODDS']
        and pre_values[side]['TOTAL'] == bet_dict['TOTAL']
        and pre_values[side]['TOTAL_ODDS'] == bet_dict['TOTAL_ODDS']):
        return 0
    else:
        return 1

def get_period_type(game_time):
    game_time = game_time.lower()

    if game_time in ('intermission', 'brk'):
        return 'Intermission'
    elif 'halftime' in game_time or 'half time' in game_time or game_time.startswith('ht'):
        return 'Halftime'
    elif 'start' in game_time or 'pm' in game_time or 'am' in game_time or '12:00' in game_time or '20:00' in game_time:
        return 'Starting Now'
    elif 'qtr' in game_time or 'quarter' in game_time or game_time.startswith('q1') or game_time.startswith('q2') or game_time.startswith('q3') or game_time.startswith('q4'):
        return 'Quarter'
    elif ('half' in game_time and ('1st' in game_time or '2nd' in game_time)) or game_time.startswith('1h') or game_time.startswith('2h') or game_time.startswith('h1') or game_time.startswith('h2'):
        return 'Half'
    elif 'period' in game_time or 'prd' in game_time:
        return 'Period'
    elif 'end regulation' in game_time or 'reg. time over' in game_time or 'ended' in game_time:
        return 'End of Regulation'
    elif 'ot' in game_time or 'overtime' in game_time:
        return 'Overtime'
    elif any(game_time.startswith(period) for period in ('1st', '2nd', '3rd', '4th')):
        return 'Invalid: Period Missing Q/H/P'
    elif not game_time.strip():
        return 'Invalid: Blank'
    elif any(game_time.startswith(time) for time in ('1', '2', '3', '4', '5', '6', '7', '8', '9', '10', '11', '12')):
        return 'Invalid: Only Contains Time'
    else:
        return 'Invalid: No Period No Time'

def get_period_value(game_time):
    game_time = game_time.lower()

    if '1st qtr' in game_time:
        return '1st'
    elif '2nd qtr' in game_time:
        return '2nd'
    elif '3rd qtr' in game_time:
        return '3rd'
    elif '4th qtr' in game_time:
        return '4th'
    elif '1st quarter' in game_time:
        return '1st'
    elif '2nd quarter' in game_time:
        return '2nd'
    elif '3rd quarter' in game_time:
        return '3rd'
    elif '4th quarter' in game_time:
        return '4th'
    elif game_time.startswith('q1'):
        return '1st'
    elif game_time.startswith('q2'):
        return '2nd'
    elif game_time.startswith('q3'):
        return '3rd'
    elif game_time.startswith('q4'):
        return '4th'
    elif 'half' in game_time and '1st' in game_time:
        return '1st'
    elif 'half' in game_time and '2nd' in game_time:
        return '2nd'
    elif game_time.startswith('1h'):
        return '1st'
    elif game_time.startswith('2h'):
        return '2nd'
    elif game_time.startswith('h1'):
        return '1st'
    elif game_time.startswith('h2'):
        return '2nd'
    elif '1st period' in game_time:
        return '1st'
    elif '2nd period' in game_time:
        return '2nd'
    elif '3rd period' in game_time:
        return '3rd'
    elif game_time.startswith('1st prd'):
        return '1st'
    elif game_time.startswith('2nd prd'):
        return '2nd'
    elif game_time.startswith('3rd prd'):
        return '3rd'
    elif 'ot' in game_time or 'overtime' in game_time:
        return 'Overtime'
    else:
        return None

def get_period_time(game_time):
    if ">" in game_time:
        period_time = (game_time.split(">")[-1].split('min'))[0].strip()
    elif "<" in game_time:
        period_time = (game_time.split("<")[-1].split('min'))[0].strip()
    else:
        period_time = None
    
    return period_time
    

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
                # check if football is in live games
                check_game = WebDriverWait(driver, 10).until(EC.visibility_of_all_elements_located(
                    (By.XPATH, "//*[@class='tab-bar-item active ng-star-inserted']")))
                check_game_res = [i.text for i in check_game if 'Football' in i.text]
            except:
                check_game_res = ''

            if check_game_res:
                # if we found the games by the link then it's live games and football
                additional_param['sport'] = 'Football'
                additional_param['game_type'] = 'Live'

                # get all live games
                games_on_initial_page = driver.find_elements(By.XPATH, ".//ms-grid")

                games_group = games_on_initial_page[0].find_elements(By.XPATH, ".//ms-event-group")
                for games_on in games_group:
                    league = ''
                    try:
                        title_element = games_on.find_element(By.XPATH, ".//div[@class='title']")
                        # check if the current live game is NFL PRESEASON or NCAFF
                        if ((title_element.text).strip()).lower() == 'nfl preseason':
                            league = 'NFL'
                        elif ((title_element.text).strip()).lower() == 'college football':
                            league = 'NCAAF'
                        else:
                            continue
                    except:
                        logger.warning('There are no NFL or NCAAF')
                        continue

                    soup = BeautifulSoup(games_on.get_attribute('innerHTML'), "html.parser")
                    get_data = [i for i in soup.find_all("div", {"class": ["participant", "grid-group-container"]})]

                    get_game_time = [i for i in soup.find_all("ms-event-timer", {"class": ["grid-event-timer"]})]
                    game_time = [i.text for i in get_game_time]

                    additional_param['time_stamp'] = datetime.now(timezone.utc).strftime("%m/%d/%Y %H:%M:%S")

                    popular_bets_list = parse_gameline_bet(additional_param, get_data, game_time, league)

                    if not popular_bets_list:
                        continue

                    # save data to redis db
                    saving_result = add_data_redis('football_betmgm_popular', popular_bets_list)

                    logger.info(
                        f'The result of saving data: {saving_result}') if saving_result == 'OK' else logger.exception(
                        f'The result of saving data: {saving_result}')                
                    count_scraps += 1

                    parsing_work_time = time.time() - parsing_start_time
                    time.sleep(20)
                    # time.sleep(max(0, update_frequency.total_seconds() - parsing_work_time))
                    exception_counter = 0

            if not check_game_res:
                logger.warning('There are no live games, waiting for some time and trying again')
                driver.get(URL)
                driver.refresh()
                time.sleep(randrange(4000, 12000, 10) / 1000)

        except KeyboardInterrupt:
            logger.warning("Keyboard Interrupt. Quit the driver!")
            driver.quit()
            logger.info(f'Module stopped working')
            break

        except Exception as e:
            logger.exception(f"Exception in main scraping cycle. {e}")
            exception_counter += 1
            if exception_counter >= 5:
                driver.quit()
                logger.exception(
                    f'Script exited after {exception_counter} unsuccessful attempts to execute the main loop')
                break
        
        if count_scraps % scrap_step == 0:
            actions_on_page(driver=driver, class_name="grid-wrapper ng-star-inserted")
            if count_scraps == scrap_limit:
                driver.refresh()                
                count_scraps = 0

    driver.quit()
    logger.warning(f'Module stopped working')


if __name__ == "__main__":
    main()
