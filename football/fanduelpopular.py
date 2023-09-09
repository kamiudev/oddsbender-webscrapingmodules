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
from utilities.driver_proxy import get_driver_proxy

# read config file
config_parser = ConfigParser()
config_parser.read('conf/fanduel.conf')
module_conf = config_parser["MODULE"]

# init logging
logger_name = environ.get('football_fanduelpopular_get_logger', 'football_fanduel_popular')
# for local logs storage and stdout use DEBUG_FLAG = 1
DEBUG_FLAG = environ.get('football_fanduelpopular_DEBUG_FLAG', 0)
log_level = environ.get('football_fanduelpopular_log_level', 'WARNING')

logger = get_logger(logger_name, DEBUG_FLAG, log_level)

# other variables
URL = environ.get('football_fanduel_url', module_conf.get('URL'))
module_work_duration = str_to_timedelta(environ.get('football_fanduelpopular_module_work_duration', module_conf.get('module_work_duration')))
update_frequency = str_to_timedelta(environ.get('football_fanduelpopular_update_frequency', module_conf.get('update_frequency')))
browser = environ.get('football_fanduelpopular_browser', module_conf.get('browser_popular'))

scrap_step = int(environ.get('football_scrap_step', module_conf.get('scrap_step')))
scrap_limit = int(environ.get('football_scrap_limit', module_conf.get('scrap_limit')))

# init web driver
# driver = get_driver(browser)
# driver.get(URL)
driver = None

pre_bet_values = {}

nfl_teams = [
    'Arizona Cardinals',
    'Atlanta Falcons',
    'Baltimore Ravens',
    'Buffalo Bills',
    'Carolina Panthers',
    'Chicago Bears',
    'Cincinnati Bengals',
    'Cleveland Browns',
    'Dallas Cowboys',
    'Denver Broncos',
    'Detroit Lions',
    'Green Bay Packers',
    'Houston Texans',
    'Indianapolis Colts',
    'Jacksonville Jaguars',
    'Kansas City Chiefs',
    'Las Vegas Raiders',
    'Los Angeles Chargers',
    'Los Angeles Rams',
    'Miami Dolphins',
    'Minnesota Vikings',
    'New England Patriots',
    'New Orleans Saints',
    'New York Giants',
    'New York Jets',
    'Philadelphia Eagles',
    'Pittsburgh Steelers',
    'San Francisco 49ers',
    'Seattle Seahawks',
    'Tampa Bay Buccaneers',
    'Tennessee Titans',
    'Washington Commanders'
]

logger.warning(f'Module started working with parameters:\nURL: {URL}\nmodule_work_duration: {module_work_duration}\nupdate_frequency: {update_frequency}\nbrowser: {browser}\nlogger_name: {logger_name}\nlog_level: {log_level}\nDEBUG_FLAG: {DEBUG_FLAG}')

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

def parse_gameline_bet(bet_table, additional_param, iter):
    try:
        logger.info(f'Start scraping Gameline')
        game_name = bet_table.find_element(By.XPATH, './a').get_attribute('title')
        away_home_team_list = split_string(game_name)
        popular_bets = []

        league = ''
        
        test_le = bet_table.find_elements(By.XPATH, './/ancestor::li/preceding-sibling::li')
        for l_l in test_le[::-1]:
            try:
                aa_t = l_l.find_element(By.XPATH, './/h3[@role="heading"]')
                if 'NFL' in aa_t.text:
                    league = 'NFL'
                    break
                elif 'NCAA' in aa_t.text:
                    league = 'NCAA'
                    break
            except:
                pass

        if league == 'NCAA' or league == 'NFL':

            bet_table_buttons = bet_table.find_elements(By.XPATH, './/div[@role="button"]')
            bet_table_buttons_text = [single_bet_data.text for single_bet_data in bet_table_buttons]

            if bet_table_buttons_text == ['', '', '', '', '', '']:
                logger.warning(f'Empty gameline')

            # check for timeout
            try:
                is_timeout = 0 if ':' in additional_param.get('times_list')[iter] else 1
            except:
                is_timeout = 1
            
            game_name = f'{away_home_team_list[0]} @ {away_home_team_list[1]}'
            
            if not game_name in pre_bet_values:
                pre_bet_values[game_name] = {}

            for i in range(2):
                spread, spread_odds = split_string(bet_table_buttons_text[i * 3])
                total, total_odds = split_string(bet_table_buttons_text[2 + i * 3])
                popular_bet_dict = {
                    'SPORT': additional_param.get('sport'),
                    'GAME_TYPE': additional_param.get('game_type'),
                    'LEAGUE': league,
                    'IS_PROP': 0,
                    'GAME': game_name,
                    'TEAM': away_home_team_list[i],
                    'VS_TEAM': away_home_team_list[1 - i],
                    'SPREAD': ' '.join(('Home Team', spread)) if i % 2 != 0 else ' '.join(('Away Team', spread)),
                    'SPREAD_ODDS': spread_odds,
                    'MONEYLINE_ODDS': bet_table_buttons_text[1 + i * 3],
                    'TOTAL': text_filter(total),
                    'TOTAL_ODDS': total_odds,
                    'HOME_TEAM': away_home_team_list[1],
                    'AWAY_TEAM': away_home_team_list[0],
                    'PERIOD_TYPE': get_period_type(additional_param.get('times_list')[iter]),
                    'PERIOD_VALUE': get_period_value(additional_param.get('times_list')[iter]),
                    'PERIOD_TIME': get_period_time(additional_param.get('times_list')[iter]),
                    # 'GAME_TIME': additional_param.get('times_list')[iter],
                    'IS_TIMEOUT': is_timeout,
                    'SPORTS_BOOK': 'Fanduel',
                    'TIMESTAMP': additional_param.get('time_stamp')
                }

                popular_bet_dict['HAS_CHANGED'] = get_changed(pre_bet_values[game_name], popular_bet_dict, i)

                pre_bet_values[game_name][i] = popular_bet_dict

                popular_bets.append(popular_bet_dict)
            logger.info(f'Gameline scraped successfully')
    except:
        return []
    else:
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
    exception_counter = 0
    count_scraps = 0

    global driver
    check_capture()

    while datetime.now() < module_operate_until:
        additional_param = {}
        try:
            driver.implicitly_wait(10)

            parsing_start_time = time.time()
            logger.info(f'Start scraping')
            # click on football game
            click_game_source = driver.find_elements(By.XPATH, "//a[contains(@href,'/live')]")
            [game.click() for game in click_game_source if 'Football' in game.text]
            logger.info('The game selection button has been clicked')

            football_games = WebDriverWait(driver, 20).until(
                EC.visibility_of_all_elements_located((By.XPATH, '//a[contains(@href, "football/")]/parent::div')))

            # get sport and type_game
            try:
                get_sport = driver.find_element(By.XPATH, "//h2[contains(text(),'Live ')]").text.split(' ')[1]
                additional_param['sport'] = get_sport
                additional_param['game_type'] = 'Live'
            except:
                additional_param['game_type'] = 'Pre-game'
                additional_param['sport'] = 'Not identified'
                logger.error('It’s impossible to identify game type')

            if additional_param.get('sport') == 'Football':
                # get game time
                try:
                    cur_time = driver.find_elements(By.XPATH, "//span [contains(text(),'Q') or contains(text(),'HALF TIME') or contains(text(),'OVERTIME')]")
                    times_list = []
                    for ct in cur_time:
                        # Added the exception code to pass the issue when we pulled the unexpected item.
                        if ct.text == 'FAQs':
                            continue
                        if ct.text != '':
                            times_list += [ct.text]*2
                    additional_param['times_list'] = times_list
                except:
                    additional_param['times_list'] = ['' for i in range(len(football_games))]

                popular_bets_list = []
                additional_param['time_stamp'] = datetime.now().strftime("%m/%d/%Y %H:%M:%S")
                logger.info(f'Start scraping football games')

                if len(football_games) >= 1:
                    iter = 0
                    while iter < len(additional_param['times_list']):
                        if 'More wagers' in football_games[iter].text:
                            if 'LiveTag_svg__a' not in football_games[iter].get_attribute('innerHTML'):                                
                                del football_games[iter-1:iter+1]
                                iter-=1
                                continue
                            else:
                                popular_bets_list += parse_gameline_bet(football_games[iter], additional_param, iter)
                        iter+=1

                    if not popular_bets_list:
                        continue

                    # save data to redis db
                    saving_result = add_data_redis('football_fanduel_popular', popular_bets_list)
                    logger.info(
                        f'The result of saving data: {saving_result}') if saving_result == 'OK' else logger.exception(
                        f'The result of saving data: {saving_result}')                    
                    count_scraps += 1

                    parsing_work_time = time.time() - parsing_start_time
                    time.sleep(max(0, update_frequency.total_seconds() - parsing_work_time))

                    exception_counter = 0

                if len(football_games) == 0:
                    logger.warning('The game tab is present, but no live games are detected')
                    logger.info(f'Try to reopen after system time out')
                    time.sleep(randrange(4000, 12000, 10) / 1000)
                    driver.get(URL)

            if additional_param.get('sport') != 'Football':
                logger.warning('There are no live games or there was a redirection')
                logger.info(f'Trying to reopen after system time out')
                time.sleep(randrange(4000, 12000, 10)/1000)
                driver.get(URL)

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
                logger.exception(f'Script exited after {exception_counter} unsuccessful attempts to execute the main loop')
                break
                
        if count_scraps % scrap_step == 0:
            actions_on_page(driver=driver, class_name="")
            if count_scraps == scrap_limit:
                driver.refresh()                
                count_scraps = 0

    try:
        driver.quit()
        logger.warning(f'Module stopped working')
    except:
        pass


if __name__ == "__main__":
    main()
