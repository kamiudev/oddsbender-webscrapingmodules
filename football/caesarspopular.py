from os import environ
import time
from configparser import ConfigParser
from datetime import datetime
from random import randrange

from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from utilities.logging import get_logger
from utilities.utils import get_driver, str_to_timedelta, add_data_redis, actions_on_page, text_filter

# read config file
config_parser = ConfigParser()
config_parser.read('conf/caesars.conf')
module_conf = config_parser["MODULE"]

# init logging
logger_name = environ.get('football_caesarspopular_get_logger', 'football_caesars_popular')
# for local logs storage and stdout use DEBUG_FLAG = 1
DEBUG_FLAG = environ.get('football_caesarspopular_DEBUG_FLAG', 0)
log_level = environ.get('football_caesarspopular_log_level', 'WARNING')

logger = get_logger(logger_name, DEBUG_FLAG, log_level)

# other variables
URL = environ.get('football_caesars_url', module_conf.get('URL'))
module_work_duration = str_to_timedelta(environ.get('football_caesarspopular_module_work_duration', module_conf.get('module_work_duration')))
update_frequency = str_to_timedelta(environ.get('football_caesarspopular_update_frequency', module_conf.get('update_frequency')))
browser = environ.get('football_caesarspopular_browser', module_conf.get('browser_popular'))

scrap_step = int(environ.get('football_scrap_step', module_conf.get('scrap_step')))
scrap_limit = int(environ.get('football_scrap_limit', module_conf.get('scrap_limit')))

# init web driver
driver = get_driver(browser)
driver.get(URL)
pre_bet_values = {}

logger.warning(f'Module started working with parameters:\nURL: {URL}\nmodule_work_duration: {module_work_duration}\nupdate_frequency: {update_frequency}\nbrowser: {browser}\nlogger_name: {logger_name}\nlog_level: {log_level}\nDEBUG_FLAG: {DEBUG_FLAG}')


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
    if get_period_type(game_time) and get_period_value(game_time) and ':' in game_time:
        return game_time.split(' ')[1].strip()
    else:
        return None


def scrape_spread(match_row):
    try:
        spread_name = match_row.find_elements(By.XPATH, ".//div[@class='header selectionHeader truncate3Rows col2']")
        spread_name = [spread.text for spread in spread_name]
    except:
        pass
    else:
        if len(spread_name) == 0:
            return 'FAILED'
        # elif spread_name[0] == 'SPREAD LIVE':
        else:
            spreads = match_row.find_elements(By.XPATH, ".//div[@class='selectionContainer  col2']")
            spreads = [spread.text.split("\n") for spread in spreads]

            if len(spreads[0]) == 1:
                spreads = [['', ''], ['', '']]

            return spreads
    return 'FAILED'


def scrape_money_line(match_row):
    try:
        ml_name = match_row.find_elements(By.XPATH, ".//div[@class='header selectionHeader truncate3Rows col3']")
        ml_name = [ml.text for ml in ml_name]
    except:
        pass
    else:
        if len(ml_name) == 0:
            return 'FAILED'
        # elif ml_name[0] == 'MONEY LINE LIVE':
        else:
            mls = match_row.find_elements(By.XPATH, ".//div[@class='selectionContainer  col3']")
            mls = [ml.text.split("\n") for ml in mls]
            return mls
    return 'FAILED'


def scrape_total_points(match_row):
    try:
        tp_name = match_row.find_elements(By.XPATH, ".//div[@class='header selectionHeader truncate3Rows col4']")
        tp_name = [tp.text for tp in tp_name]
    except:
        pass
    else:
        if len(tp_name) == 0:
            return 'FAILED'
        # elif tp_name[0] == 'TOTAL POINTS LIVE':
        else:
            tps = match_row.find_elements(By.XPATH, ".//div[@class='selectionContainer  col4']")
            tps = [tp.text.split("\n") for tp in tps]

            if len(tps[0]) == 1:
                tps = [['', ''], ['', '']]

            return tps
    return 'FAILED'


def scrape_popular(url):
    sport = url.split("/")[-2].capitalize()
    if sport == "Americanfootball":
        sport = "Football"
    game_type = url.split("/")[-1]
    game_type = "Live" if game_type == 'inplay' else ' '
    game_sections = driver.find_elements(By.XPATH, ".//div[@class='Expander has--toggle competitionExpander']")
    for g_sec in game_sections:
        league_section = g_sec.find_element(By.XPATH, ".//span[@class='title']")
        league_txt = league_section.text

        if league_txt == 'NCAAF':
            pass
        elif league_txt == 'NFL Pre-Season':
            league_txt = 'NFL'
        else:
            continue

        match_rows = g_sec.find_elements(By.XPATH, ".//div[contains(@class, 'EventCard')]")
        time_stamp = datetime.now().strftime("%m/%d/%Y %H:%M:%S")
        popular_bets = []
        for match_row in match_rows:
            game_time = games_time(match_row)
            is_timeout = check_timeout(game_time)
            teams = match_row.find_elements(By.XPATH, ".//span[@class='truncate2Rows']")
            teams = [team.text for team in teams]
            spreads = scrape_spread(match_row)
            mll = scrape_money_line(match_row)
            tpl = scrape_total_points(match_row)

            if spreads == 'FAILED' or mll == 'FAILED' or tpl == 'FAILED':
                continue
                
            game_name = f'{teams[0] + " @ " + teams[1]}'
            if not game_name in pre_bet_values:
                pre_bet_values[game_name] = {}

            for i in range(2):
                total_v = ''
                if text_filter(tpl[i][0]) != '':
                    total_v = ' '.join(('U', text_filter(tpl[i][0]))) if i % 2 != 0 else ' '.join(('O', text_filter(tpl[i][0])))
                popular_info_dict = {
                    'SPORT': sport,
                    'GAME_TYPE': game_type,
                    'LEAGUE': league_txt,
                    'IS_PROP': 0,
                    'GAME': game_name,
                    'TEAM': teams[i],
                    'VS_TEAM': teams[1 - i],
                    'SPREAD': ' '.join(('Home Team', spreads[i][0])) if i % 2 != 0 else ' '.join(('Away Team', spreads[i][0])),
                    'SPREAD_ODDS': spreads[i][1],
                    'MONEYLINE_ODDS': mll[i][0],
                    # 'TOTAL': text_filter(tpl[i][0]), 
                    'TOTAL': total_v,
                    'TOTAL_ODDS': tpl[i][1],
                    'HOME_TEAM': teams[1],
                    'AWAY_TEAM': teams[0],
                    'PERIOD_TYPE': get_period_type(game_time),
                    'PERIOD_VALUE': get_period_value(game_time),
                    'PERIOD_TIME': get_period_time(game_time),
                    # 'GAME_TIME': game_time,
                    'IS_TIMEOUT': is_timeout,
                    'SPORTS_BOOK': 'Caesars',
                    'TIMESTAMP': time_stamp
                }
                popular_info_dict['HAS_CHANGED'] = get_changed(pre_bet_values[game_name], popular_info_dict, i)
                popular_bets.append(popular_info_dict)
                pre_bet_values[game_name][i] = popular_info_dict
        logger.info(f'Game lines scraped successfully')
    return popular_bets

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

def main():
    module_operate_until = datetime.now() + module_work_duration

    failure_count = 0
    count_scraps = 0

    while datetime.now() < module_operate_until:
        parsing_start_time = time.time()
        try:
            logger.info(f'Start scraping')
            try:
                games_on_initial_page = WebDriverWait(driver, 10).until(
                    EC.presence_of_all_elements_located((By.XPATH, "//a[@class='competitor firstCompetitor']")))
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
                saving_result = add_data_redis('football_caesars_popular', popular_bet_list)
                logger.info(
                    f'The result of saving data: {saving_result}') if saving_result == 'OK' else logger.exception(
                    f'The result of saving data: {saving_result}')                
                count_scraps += 1

                parsing_work_time = time.time() - parsing_start_time
                # time.sleep(max(0, update_frequency.total_seconds() - parsing_work_time))
                time.sleep(15)
                failure_count = 0

        except KeyboardInterrupt:
            logger.warning("Keyboard Interrupt. Quit the driver!")
            driver.quit()
            logger.info(f'Module stopped working')
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
