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
from bs4 import BeautifulSoup

# read config file
config_parser = ConfigParser()
config_parser.read('conf/draftkings.conf')
module_conf = config_parser["MODULE"]

# init logging
logger_name = environ.get('football_draftkingspopular_get_logger', 'football_draftkings_popular')
# for local logs storage and stdout use DEBUG_FLAG = 1
DEBUG_FLAG = environ.get('football_draftkingspopular_DEBUG_FLAG', 0)
log_level = environ.get('football_draftkingspopular_log_level', 'WARNING')

logger = get_logger(logger_name, DEBUG_FLAG, log_level)

# other variables
URL = environ.get('football_draftkings_url', module_conf.get('URL'))
module_work_duration = str_to_timedelta(environ.get('football_draftkingspopular_module_work_duration', module_conf.get('module_work_duration')))
update_frequency = str_to_timedelta(environ.get('football_draftkingspopular_update_frequency', module_conf.get('update_frequency')))
browser = environ.get('football_draftkingspopular_browser', module_conf.get('browser_popular'))

scrap_step = int(environ.get('football_scrap_step', module_conf.get('scrap_step')))
scrap_limit = int(environ.get('football_scrap_limit', module_conf.get('scrap_limit')))

# init web driver
driver = get_driver(browser)
driver.get(URL)

pre_bet_values = {}

logger.warning(f'Module started working with parameters:\nURL: {URL}\nmodule_work_duration: {module_work_duration}\nupdate_frequency: {update_frequency}\nbrowser: {browser}\nlogger_name: {logger_name}\nlog_level: {log_level}\nDEBUG_FLAG: {DEBUG_FLAG}')


def pop_game_time(info):
    times = ''
    try:
        if info == 'HALFTIME':
            return info
        else:
            temp = info.split(' ')
            if temp[-1] == "12:00":
                return "12:00"
            else:
                times = info.replace("1ST QUARTER", "").replace("2ND QUARTER", "").replace("3RD QUARTER", "") \
                    .replace("4TH QUARTER", "")
                return times
    except:
        return times


def check_timeout(gt):
    if gt in ['HALFTIME', ':', '15:00']:
        return 1
    else:
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
        return game_time.split(':')[1].strip()
    else:
        return None


def scrape_popular():
    popular_bets = []
    sport = URL.split('=')[-1].capitalize()
    game_type = "Live"
    time_stamp = datetime.now().strftime("%m/%d/%Y %H:%M:%S")
    try:
        game_sections = driver.find_elements(By.XPATH, ".//div[contains(@class, 'sportsbook-featured-accordion__wrapper sportsbook-accordion__wrapper')]")

        # click game sections
        for i, g_s in enumerate(game_sections):
            if i > 0:
                g_s.click()
                time.sleep(5)

        for g_s in game_sections:
            league_section = g_s.find_element(By.XPATH, ".//div[@class='sportsbook-header__title']")
            league_txt = league_section.text


            if 'college football' in league_txt.lower().strip():
                league_txt = 'NCAAF'
            elif 'nfl' in league_txt.lower().strip():
                league_txt = 'NFL'
            else:
                continue

            match_rows = g_s.get_attribute('innerHTML')
            bs_data = BeautifulSoup(match_rows, "html.parser")
            try:
                match_row = bs_data.find_all(class_="sportsbook-table__column-row")
            except:
                continue
            data = [in_text.get_text(separator="\n") for in_text in match_row]

            size = 8
            sorted_data = []
            while len(data) > size:
                pice = data[:size]
                sorted_data.append(pice)
                data = data[size:]
            sorted_data.append(data)

            for i in range(len(sorted_data)):
                spread = []
                total = []
                moneyline = []
                teams = []
                sprd = []
                sprd_odds = []
                ttl = []
                ttl_odds = []
                sorted_data[i][0] = f':\n{sorted_data[i][0]}' if ':' not in sorted_data[i][0].split('\n')[0] else sorted_data[i][0]
                h_team = sorted_data[i][0].split('\n')
                period = h_team[1]
                game_time = pop_game_time(h_team[0])
                is_timeout = check_timeout(game_time)
                h_team = h_team[2]
                sorted_data[i][4] = f':\n{sorted_data[i][4]}' if ':' not in sorted_data[i][4] else sorted_data[i][4]
                a_team = sorted_data[i][4].split('\n')
                a_team = a_team[2]
                spread.append(sorted_data[i][1].split('\n'))
                spread.append(sorted_data[i][5].split('\n'))
                total.append(sorted_data[i][2].split('\n'))
                total.append(sorted_data[i][6].split('\n'))
                moneyline.append(sorted_data[i][3])
                moneyline.append(sorted_data[i][7])
                if spread[0][0] == '':
                    sprd = ['', '']
                    sprd_odds = ['', '']
                else:
                    for k in range(2):
                        sprd.append(spread[k][0])
                        sprd_odds.append(spread[k][1])

                if total[0][0] == '':
                    ttl = ['', '', '', '']
                    ttl_odds = ['', '']
                else:
                    for k in range(2):
                        ttl.append(total[k][0])
                        ttl.append(total[k][2])
                        ttl_odds.append(total[k][3])
                game_name = f'{h_team + " @ " + a_team}'
                teams.append(h_team)
                teams.append(a_team)

                if not game_name in pre_bet_values:
                    pre_bet_values[game_name] = {}

                for j in range(2):
                    kof_t = 1 + j
                    popular_info_dict = {
                        'SPORT': sport,
                        'LEAGUE': league_txt,
                        'GAME_TYPE': game_type,
                        'IS_PROP': 0,
                        'GAME': game_name,
                        'TEAM': teams[j],
                        'VS_TEAM': teams[1 - j],
                        'SPREAD': ' '.join(('Home Team', sprd[j].replace('\u2212', '-'))) if j % 2 != 0 else ' '.join(('Away Team', sprd[j].replace('\u2212', '-'))),
                        'SPREAD_ODDS': sprd_odds[j].replace('\u2212', '-'),
                        'MONEYLINE_ODDS': moneyline[j].replace('\u2212', '-'),
                        'TOTAL': text_filter(f'{ttl[j + j]}{ttl[kof_t + j]}'),
                        'TOTAL_ODDS': ttl_odds[j].replace('\u2212', '-'),
                        'HOME_TEAM': a_team,
                        'AWAY_TEAM': h_team,
                        'PERIOD_TYPE': get_period_type(period),
                        'PERIOD_VALUE': get_period_value(period),
                        'PERIOD_TIME': '' if game_time == ':' else game_time,
                        # 'GAME_TIME': ' '.join((period, game_time)),
                        'IS_TIMEOUT': is_timeout,
                        'SPORTS_BOOK': 'Draft Kings',
                        'TIMESTAMP': time_stamp
                    }

                    popular_info_dict['HAS_CHANGED'] = get_changed(pre_bet_values[game_name], popular_info_dict, j)

                    if popular_info_dict['PERIOD_TYPE'] == 'Halftime':
                        popular_info_dict['PERIOD_VALUE'] = ''
                        popular_info_dict['PERIOD_TIME'] = ''

                    popular_bets.append(popular_info_dict)
                    pre_bet_values[game_name][j] = popular_info_dict
                logger.info(f'Game lines scraped successfully')
    except:
        logger.info("Couldn't scrape popular. Try again!")
        return []
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
            logger.info(f'Start scraping DraftKings popular')
            check_game = False

            try:
                # check if football is in live games
                check_game_list = WebDriverWait(driver, 10).until(EC.visibility_of_all_elements_located(
                    (By.XPATH, "//span[@class='sportsbook-tabbed-subheader__tab']")))
                for fg in check_game_list:
                    if fg.text == 'FOOTBALL':
                        check_game = True
                        break
            except Exception as error:
                logger.exception(f"Problem with extracting the name of the game\n{error}")

            if check_game:
                hidden_games = True
                while hidden_games:
                    try:
                        get_hidden_games = WebDriverWait(driver, 3).until(EC.visibility_of_all_elements_located(
                            (By.XPATH, "//div[@class='sportsbook-featured-accordion__wrapper sportsbook-accordion__wrapper collapsed']")))
                        if len(get_hidden_games) > 0:
                            [i.click() for i in get_hidden_games]
                    except:
                        hidden_games = False

                popular_bet_list = scrape_popular()

                if not popular_bet_list:
                    continue

                # save data to redis db
                saving_result = add_data_redis('football_draftkings_popular', popular_bet_list)
                logger.info(
                    f'The result of saving data: {saving_result}') if saving_result == 'OK' else logger.exception(
                    f'The result of saving data: {saving_result}')                
                count_scraps += 1

                # reset unsuccessful attempts in main loop
                failure_count = 0

            if not check_game:
                logger.warning('There are no live games, waiting for some time and trying again')
                time.sleep(randrange(4000, 12000, 10) / 1000)
                driver.get(URL)
                driver.refresh()

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
                logger.exception(f'Script exited after {failure_count} unsuccessful attempts to start the main loop')
                break
         
        if count_scraps % scrap_step == 0:
            actions_on_page(driver=driver, class_name="sportsbook-tabbed-subheader__tab selected")
            if count_scraps == scrap_limit:
                driver.refresh()                
                count_scraps = 0

        parsing_work_time = time.time() - parsing_start_time
        time.sleep(max(0, update_frequency.total_seconds() - parsing_work_time))

    driver.quit()
    logger.warning('Script successfully ended working at the set time')


if __name__ == "__main__":
    main()
