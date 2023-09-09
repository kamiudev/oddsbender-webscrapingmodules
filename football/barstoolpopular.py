import time
from configparser import ConfigParser
from datetime import datetime
from random import randrange
from os import environ

from lxml import html
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from utilities.logging import get_logger
from utilities.utils import get_driver, str_to_timedelta, add_data_redis, actions_on_page, text_filter


# read config file
config_parser = ConfigParser()
config_parser.read('conf/barstool.conf')
module_conf = config_parser["MODULE"]

# init logging
logger_name = environ.get('football_barstoolpopular_get_logger', 'football_barstool_popular_logger')
# for local logs storage and stdout use DEBUG_FLAG = 1
DEBUG_FLAG = environ.get('football_barstoolpopular_DEBUG_FLAG', 0)
log_level = environ.get('football_barstoolpopular_log_level', 'WARNING')

logger = get_logger(logger_name, DEBUG_FLAG, log_level)

# other variables
URL = environ.get('football_barstool_url', module_conf.get('URL'))
module_work_duration = str_to_timedelta(environ.get('football_barstoolpopular_module_work_duration', module_conf.get('module_work_duration')))
update_frequency = str_to_timedelta(environ.get('football_barstoolpopular_update_frequency', module_conf.get('update_frequency')))
browser = environ.get('football_barstoolpopular_browser', module_conf.get('browser_popular'))

scrap_step = int(environ.get('football_scrap_step', module_conf.get('scrap_step')))
scrap_limit = int(environ.get('football_scrap_limit', module_conf.get('scrap_limit')))

# init web driver
driver = get_driver(browser)
driver.get(URL)

logger.warning(f'Module started working with parameters:\nURL: {URL}\nmodule_work_duration: {module_work_duration}\nupdate_frequency: {update_frequency}\nbrowser: {browser}\nlogger_name: {logger_name}\nlog_level: {log_level}\nDEBUG_FLAG: {DEBUG_FLAG}')
pre_bet_values = {}


def click_on_web_element(element: WebElement):
    driver.execute_script("arguments[0].scrollIntoView(true);", element)
    WebDriverWait(driver, 10).until(EC.element_to_be_clickable(element))
    driver.execute_script("arguments[0].click();", element)   
    

def parse_bet(away_team, home_team, bets):
    t1 = [away_team, home_team]
    # spread
    if bets[0] == '--':
        a = ''
    else:
        a = bets[0].split('\n')[0]
    if bets[3] == '--':
        b = ''
    else:
        b = bets[3].split('\n')[0]
    t1.append([a, b])

    # spread odd
    if bets[0] == '--':
        a = ''
    else:
        a = bets[0].split('\n')[1]
    if bets[3] == '--':
        b = ''
    else:
        b = bets[3].split('\n')[1]
    t1.append([a, b])

    # money
    if bets[2] == '--':
        a = ''
    else:
        a = bets[2]
    if bets[5] == '--':
        b = ''
    else:
        b = bets[5]
    
    t1.append([a, b])

    # total
    if bets[1] == '--':
        a = ''
    else:
        a = bets[1].split('\n')[0]

    if bets[4] == '--':
        b = ''
    else:
        b = bets[4].split('\n')[0]            
    t1.append([a, b])

    # total odd            
    if bets[1] == '--':
        a = ''
    else:
        a = bets[1].split('\n')[1]
    if bets[4] == '--':
        b = ''
    else:
        b = bets[4].split('\n')[1]
    
    t1.append([a, b])

    return t1


def get_period_type(game_time):
    game_time = game_time.lower()
    if '1st' in game_time or '2nd' in game_time:
        return 'Halftime'
    elif '3rd' in game_time or '4th' in game_time:
        return 'Quarter'
    else:
        return 'Invalid: No Period No Time'

def get_period_value(game_time):
    game_time = game_time.lower()
    if ':' in game_time:
        return game_time.split(' ')[1].strip()
    else:
        return None

def get_period_time(game_time):
    game_time = game_time.lower()
    if ':' in game_time:
        return game_time.split(' ')[0].strip()
    else:
        return None


def expand_bets(active_page):
    closed_bets_panels = active_page.find_elements(By.XPATH, ".//button[@class='v-expansion-panel-header header-wrapper']")
    list(map(click_on_web_element, closed_bets_panels))
    

def scrape_popular_bets(active_page, league):
    match_rows = active_page.find_elements(By.XPATH, ".//div[contains(@class, 'bg-card-primary rounded p-4')]")

    if match_rows == []:
        logger.warning('There is no live football games')
        time.sleep(5)
        return []

    logger.info(f'Start scraping Gameline')
    time_stamp = datetime.now().strftime("%m/%d/%Y %H:%M:%S")
    popular_bets = []

    
    for match_row in match_rows:
        participants_card = match_row.find_element(By.XPATH, ".//button[@data-testid='navigate-to-matchup-btn']")
        participants_card_data = participants_card.text.split("\n")[0]
        if 'LIVE' in participants_card_data:
            game_time = participants_card_data.split(' ')[1]
            is_timeout = 1 if "10:00" in game_time or "12:00" in game_time else 0
            teams_card =  match_row.find_elements(By.XPATH, ".//div[@class='text-primary text-description text-primary']")
            away_team = teams_card[0].text
            home_team = teams_card[1].text
            game_name = f'{away_team} @ {home_team}'
            bets = match_row.find_elements(By.XPATH, ".//button[contains(@class, 'relative flex ')]")
            bets = [bet.text for bet in bets]
            tl = parse_bet(away_team, home_team, bets)
            
            if not game_name in pre_bet_values:
                pre_bet_values[game_name] = {}

            for side in range(2):
                popular_bet_dict = {}
                popular_bet_dict['SPORT'] = 'Football'
                popular_bet_dict['LEAGUE'] = league
                popular_bet_dict['GAME_TYPE'] = game_type
                popular_bet_dict['IS_PROP'] = 0
                popular_bet_dict['GAME'] = (f'{game_name}').strip()
                popular_bet_dict['TEAM'] = (tl[0 + side]).strip()
                popular_bet_dict['VS_TEAM'] = (tl[1 - side]).strip()
                popular_bet_dict['SPREAD'] = ' '.join(('Home Team', tl[2][0 + side])) if side % 2 == 0 else ' '.join(('Away Team', tl[2][0 + side])) 
                popular_bet_dict['SPREAD_ODDS'] = '100' if tl[3][0 + side] == 'Even' else tl[3][0 + side]
                popular_bet_dict['MONEYLINE_ODDS'] = '100' if tl[4][0 + side] == 'Even' else tl[4][0 + side]
                popular_bet_dict['TOTAL'] = text_filter(tl[5][0 + side])
                popular_bet_dict['TOTAL_ODDS'] = '100' if tl[6][0 + side] == 'Even' else tl[6][0 + side]
                popular_bet_dict['HOME_TEAM'] = (tl[1]).strip()
                popular_bet_dict['AWAY_TEAM'] = (tl[0]).strip()
                popular_bet_dict['PERIOD_TYPE'] = get_period_type(participants_card_data.split(' ')[-1])

                if popular_bet_dict['PERIOD_TYPE'] == 'Halftime':
                    popular_bet_dict['PERIOD_VALUE'] = ''
                    popular_bet_dict['PERIOD_TIME'] = ''
                elif popular_bet_dict['PERIOD_TYPE'] == 'Invalid: No Period No Time':
                    popular_bet_dict['PERIOD_VALUE'] = ''
                    popular_bet_dict['PERIOD_TIME'] = ''
                else:
                    popular_bet_dict['PERIOD_VALUE'] = participants_card_data.split(' ')[-1]
                    popular_bet_dict['PERIOD_TIME'] = game_time

                popular_bet_dict['IS_TIMEOUT'] = is_timeout
                popular_bet_dict['SPORTS_BOOK'] = 'Barstool'
                popular_bet_dict['TIMESTAMP'] = time_stamp
                popular_bet_dict['HAS_CHANGED'] = get_changed(pre_bet_values[game_name], popular_bet_dict, side)
                popular_bets.append(popular_bet_dict)

                pre_bet_values[game_name][side] = popular_bet_dict

            
    logger.info(f'Gameline scraped successfully')        
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
    

def is_right_tab(active_page):
    football_d_value = "M14.843"
    sport_pictogram = active_page.find_elements(By.XPATH, '//span[@class="header-left"]')[0]
    sport_pictogram_html = sport_pictogram.get_attribute('innerHTML')
    tree = html.fromstring(sport_pictogram_html)
    d_value = tree.xpath('//path[1]/@d')[0]
    return True if football_d_value in d_value else False
    

def find_corresponding_page():
    tab_list = driver.find_elements(By.XPATH, "//div[@role='tab']")
    for tab in tab_list:
        click_on_web_element(tab)
        active_page = driver.find_element(By.XPATH, "//div[@class='v-window-item active-tab']")
        if is_right_tab(active_page):
            logger.info(f'Go back to football page')
            return True
    return False
    

def main():
    module_operate_until = datetime.now() + module_work_duration
    exception_counter = 0
    count_scraps = 0

    while datetime.now() < module_operate_until:
        parsing_start_time = time.time()
        logger.warning(f'Start scraping games')
        global game_type, sport

        try:
            WebDriverWait(driver, 20).until(EC.element_to_be_clickable((By.XPATH, "//div[contains(text(), 'Football')]"))).click()
        except:
            logger.warning("No football games")

        for ft_game in driver.find_elements(By.XPATH, "//div[@class='flex w-full justify-between']"):
            if ('LIVE' in ft_game.text 
                and ('NFL' in ft_game.text or 'NCAAF' in ft_game.text)):

                league = ''
                if 'NFL' in ft_game.text:
                    league = 'NFL'
                elif 'NCAAF' in ft_game.text:
                    league = 'NCAAF'


                ft_game.click()
                time.sleep(5)
                game_type = 'Live'
                if "sports/" in driver.current_url:
                    sport = driver.current_url.split("/")[4]
                else:
                    sport = driver.current_url.split("=")[-1]

                if sport == "united-states":
                    sport = "Football"

                try:
                    active_page = driver.find_element(By.XPATH, "//div[@data-testid='marketplace-shelf-']")

                    popular_bet_list = scrape_popular_bets(active_page, league)

                    if not popular_bet_list:
                        continue

                    # save data to redis db
                    saving_result = add_data_redis('football_barstool_popular', popular_bet_list)
                    logger.info(
                        f'The result of saving data: {saving_result}') if saving_result == 'OK' else logger.exception(
                        f'The result of saving data: {saving_result}')            
                    count_scraps += 1

                    parsing_work_time = time.time() - parsing_start_time
                    time.sleep(max(0, update_frequency.total_seconds() - parsing_work_time))
                    exception_counter = 0

                except KeyboardInterrupt:
                    logger.warning("Keyboard Interrupt. Quit the driver!")
                    driver.quit()
                    break

                except Exception as e:
                    logger.exception(f"Exception in main scraping cycle. {e}")
                    exception_counter += 1
                    if exception_counter >= 5:
                        driver.quit()
                        logger.exception(f'Script is stopped after {exception_counter} unsuccessful attempts to execute the main loop')
                        break
                
                # if count_scraps % scrap_step == 0:
                #     actions_on_page(driver=driver, class_name="v-window-item active-tab")
                #     if count_scraps == scrap_limit:
                #         driver.refresh()                
                #         count_scraps = 0
            
    driver.quit()
    logger.warning(f'Module stopped working')


if __name__ == "__main__":
    main()
