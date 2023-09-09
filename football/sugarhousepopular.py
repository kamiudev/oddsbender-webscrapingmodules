import time
import re
from configparser import ConfigParser
from datetime import datetime
from random import randrange
from os import environ

from bs4 import BeautifulSoup
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.common.keys import Keys
from utilities.logging import get_logger
from utilities.utils import str_to_timedelta, get_driver, add_data_redis, actions_on_page, text_filter

# read config file
config_parser = ConfigParser()
config_parser.read('conf/sugarhouse.conf')
module_conf = config_parser["MODULE"]

# init logging
logger_name = environ.get('football_sugarhousepopular_get_logger', 'football_sugarhouse_popular')
# for local logs storage and stdout use DEBUG_FLAG = 1
DEBUG_FLAG = environ.get('football_sugarhousepopular_DEBUG_FLAG', 0)
log_level = environ.get('football_sugarhousepopular_log_level', 'WARNING')

logger = get_logger(logger_name, DEBUG_FLAG, log_level)

# other variables
URL = environ.get('football_sugarhouse_url', module_conf.get('URL'))
module_work_duration = str_to_timedelta(environ.get('football_sugarhousepopular_module_work_duration', module_conf.get('module_work_duration')))
update_frequency = str_to_timedelta(environ.get('football_sugarhousepopular_update_frequency', module_conf.get('update_frequency')))
browser = environ.get('football_sugarhousepopular_browser', module_conf.get('browser_popular'))

scrap_step = int(environ.get('football_scrap_step', module_conf.get('scrap_step')))
scrap_limit = int(environ.get('football_scrap_limit', module_conf.get('scrap_limit')))

# init web driver
driver = get_driver(browser)
driver.get(URL)
pre_bet_values = {}

logger.warning(f'Module started working with parameters:\nURL: {URL}\nmodule_work_duration: {module_work_duration}\nupdate_frequency: {update_frequency}\nbrowser: {browser}\nlogger_name: {logger_name}\nlog_level: {log_level}\nDEBUG_FLAG: {DEBUG_FLAG}')


def parse_bet(away_team, home_team, bets):
    t1 = [away_team, home_team]
    # spread
    if bets[0] == 'Closed':
        a = ''
    else:
        a = bets[0].split('\n')[0]
    if bets[1] == 'Closed':
        b = ''
    else:
        b = bets[1].split('\n')[0]
    t1.append([a, b])

    # spread odd
    if bets[0] == 'Closed':
        a = ''
    else:
        a = bets[0].split('\n')[1]
    if bets[1] == 'Closed':
        b = ''
    else:
        b = bets[1].split('\n')[1]
    t1.append([a, b])

    # money
    if bets[2] == 'Closed':
        a = ''
    else:
        a = bets[2]
    if bets[3] == 'Closed':
        b = ''
    else:
        b = bets[3]
    
    t1.append([a, b])

    # total
    if bets[4] == 'Closed':
        a = ''
    else:
        a = bets[4].split('\n')[0]

    if bets[5] == 'Closed':
        b = ''
    else:
        b = bets[5].split('\n')[0]            
    t1.append([a, b])

    # total odd            
    if bets[4] == 'Closed':
        a = ''
    else:
        a = bets[4].split('\n')[1]
    if bets[5] == 'Closed':
        b = ''
    else:
        b = bets[5].split('\n')[1]
    
    t1.append([a, b])

    return t1

def parse_gameline_bet(football_game, additional_param, league):
    logger.info(f'Start scraping Gameline')
    popular_bets_list = []

    for match_row in football_game:
        try:
            gt_data = match_row.find_element(By.XPATH, ".//span[@class='sc-efUWQm sc-kdAnDb hmDMkt jopoNF']")
            game_time = gt_data.text
            period_data = match_row.find_element(By.XPATH, ".//span[@class='sc-efUWQm sc-dBAzgk hmDMkt llQmEp']")
            is_timeout = 1 if "10:00" in game_time or "12:00" in game_time else 0
            teams_card =  match_row.find_elements(By.XPATH, ".//div[@class='sc-bYtSoG iulbpG']")
            away_team = teams_card[0].text
            home_team = teams_card[1].text
            game_name = f'{away_team} @ {home_team}'
            bets = match_row.find_elements(By.XPATH, ".//div[contains(@class, 'sc-hqMhxz bugfLi')]")
            bets = [bet.text for bet in bets]
            tl = parse_bet(away_team, home_team, bets)
        except:
            continue
        
        if not game_name in pre_bet_values:
            pre_bet_values[game_name] = {}

        for side in range(2):
            popular_bet_dict = {}
            popular_bet_dict['SPORT'] = 'Football'
            popular_bet_dict['LEAGUE'] = league
            popular_bet_dict['GAME_TYPE'] = 'Live'
            popular_bet_dict['IS_PROP'] = 0
            popular_bet_dict['GAME'] = (f'{game_name}').strip()
            popular_bet_dict['TEAM'] = (tl[0 + side]).strip()
            popular_bet_dict['VS_TEAM'] = (tl[1 - side]).strip()
            popular_bet_dict['SPREAD'] = ' '.join(('Home Team', tl[2][0 + side])) if side % 2 == 0 else ' '.join(('Away Team', tl[2][0 + side])) 
            popular_bet_dict['SPREAD_ODDS'] = tl[3][0 + side]
            popular_bet_dict['MONEYLINE_ODDS'] = tl[4][0 + side]
            popular_bet_dict['TOTAL'] = text_filter(tl[5][0 + side])
            popular_bet_dict['TOTAL_ODDS'] = tl[6][0 + side]
            popular_bet_dict['HOME_TEAM'] = (tl[1]).strip()
            popular_bet_dict['AWAY_TEAM'] = (tl[0]).strip()
            popular_bet_dict['PERIOD_TYPE'] = (period_data.text.split(' ')[1]).capitalize()
            popular_bet_dict['PERIOD_VALUE'] = (period_data.text.split(' ')[0]).lower()
            popular_bet_dict['PERIOD_TIME'] = game_time
            popular_bet_dict['IS_TIMEOUT'] = is_timeout
            popular_bet_dict['SPORTS_BOOK'] = 'Sugarhouse'
            popular_bet_dict['TIMESTAMP'] = additional_param['time_stamp']
            popular_bet_dict['HAS_CHANGED'] = get_changed(pre_bet_values[game_name], popular_bet_dict, side)
            popular_bets_list.append(popular_bet_dict)

            pre_bet_values[game_name][side] = popular_bet_dict


    logger.info(f'Gameline scraped successfully')
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

def section_expanded(bt_id, driver_):
    try:
        hidden_tab = driver_.find_element(By.XPATH, f"//button[@id='{bt_id}']")
        hidden_tab.click()
        time.sleep(5)
        logger.info(f'Opened {hidden_tab.text}')
        return True
    except:
        return False

def main():
    module_operate_until = datetime.now() + module_work_duration

    failure_count = 0
    count_scraps = 0

    while datetime.now() < module_operate_until:
        additional_param = {}
        parsing_start_time = time.time()
        # logger.info(f'Start scraping populars')
        print(f'Start scraping populars')
        try:

            try:
                check_game = WebDriverWait(driver, 10).until(EC.visibility_of_element_located(
                    (By.XPATH, "//div[@data-testid='listview-header-title']"))).text
                check_live = driver.find_element(By.XPATH, "//button[@class='sc-ihSraS cgGTYn imtab']").text
            except:
                check_game = ''
                check_live = ''
            
            # if 'AMERICAN_FOOTBALL' in check_game:
            additional_param['sport'] = check_game
            additional_param['game_type'] = check_live
            additional_param['time_stamp'] = datetime.now().strftime("%m/%d/%Y %H:%M:%S")

            popular_bets_list = []

            # open NFL
            btn_ids = [
                'accordion-NFL Preseason',
                'accordion-NCAAF',
                'accordion-NCAAF FCS'
            ]
            
            for b_id in btn_ids:
                all_games = driver.find_elements(By.XPATH, f"//div[@aria-labelledby='{b_id}']")
                # click the game section if the tab was hidden
                if len(all_games) == 0:
                    if section_expanded(b_id, driver):
                        all_games = driver.find_elements(By.XPATH, f"//div[@aria-labelledby='{b_id}']") 
                    else:
                        continue
              
                if b_id == 'accordion-NFL Preseason':
                    league = 'NFL'
                elif b_id == 'accordion-NCAAF':
                    league = 'NCAAF'
                else:
                    league = 'NCAAF FCS'


                popular_bets_list = parse_gameline_bet(all_games, additional_param, league)

                if len(popular_bets_list) > 0:
                    # save data to redis db
                    saving_result = add_data_redis('football_sugarhouse_popular', popular_bets_list)
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

        except KeyboardInterrupt:
            logger.warning("Keyboard Interrupt. Quit the driver!")
            driver.quit()
            logger.info(f'Module stopped working')
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
