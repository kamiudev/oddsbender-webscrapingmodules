import time
from configparser import ConfigParser
from datetime import datetime
from os import environ

from selenium.common.exceptions import StaleElementReferenceException
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from utilities.logging import get_logger
from utilities.utils import get_driver, str_to_timedelta, add_data_redis, update_redis_status, actions_on_page, text_filter


# read config file
config_parser = ConfigParser()
config_parser.read('conf/sugarhouse.conf')
module_conf = config_parser["MODULE"]

# init logging
logger_name = environ.get('football_sugarhouseprop_get_logger', 'football_sugarhouse_prop')
# for local logs storage and stdout use DEBUG_FLAG = 1
DEBUG_FLAG = environ.get('PROP_LOG_DEBUG_FLAG', 0)
log_level = environ.get('football_sugarhouseprop_log_level', 'WARNING')

logger = get_logger(logger_name, DEBUG_FLAG, log_level)

# other variables
URL = environ['sugarhouse_prop_url']

module_work_duration = str_to_timedelta(environ.get('football_sugarhouseprop_module_work_duration', module_conf.get('module_work_duration')))
update_frequency = str_to_timedelta(environ.get('football_sugarhouseprop_update_frequency', module_conf.get('update_frequency')))
browser = environ.get('football_sugarhouseprop_browser', module_conf.get('browser_prop'))

scrap_step = int(environ.get('football_scrap_step', module_conf.get('scrap_step')))
scrap_limit = int(environ.get('football_scrap_limit', module_conf.get('scrap_limit')))

# init web driver
driver = get_driver(browser)
driver.get(URL)

logger.warning(f'Module started working with parameters:\nURL: {URL}\nmodule_work_duration: {module_work_duration}\nupdate_frequency: {update_frequency}\nbrowser: {browser}\nlogger_name: {logger_name}\nlog_level: {log_level}\nDEBUG_FLAG: {DEBUG_FLAG}')


def istimeout(game_time):
    temp_lst = game_time.split(" ")
    try:
        if temp_lst[1] == "00:00" or temp_lst[1] == "12:00":
            timeout = 1
        else:
            timeout = 0
        return timeout
    except:
        return ''


def collect_moneyline(sport, game_type, game_name, time_stamp, game_time, is_timeout, bet_list):
    temp_list = []
    teams = game_name.split(" @ ")
    try:
        for i in range(2):
            prop_info = {
                'SPORT': sport,
                'GAME_TYPE': game_type,
                'IS_PROP': 1,
                'GAME_NAME': game_name,
                'BET_NAME': bet_list[0],
                'BET_TYPE': f'{bet_list[(i * 2) + 1]}',
                'ODDS': f'{bet_list[(i * 2) + 2]}',
                'HOME_TEAM': teams[1],
                'AWAY_TEAM': teams[0],
                'ALIGNED_BET_NAME': bet_list[0],
                'ALIGNED_BET_TYPE': text_filter(f'Home team' if teams[i] == teams[0] else f'Away team'),
                'GAME_TIME': game_time,
                'IS_TIMEOUT': is_timeout,
                'SPORTS_BOOK': 'Sugarhouse',
                'TIMESTAMP': time_stamp,
                'URL': URL
            }
            temp_list.append(prop_info)
    except:
        return temp_list
    return temp_list


def collect_spreads(sport, game_type, game_name, time_stamp, game_time, is_timeout, bet_list):
    temp_list = []
    teams = game_name.split(" @ ")
    try:
        for i in range(2):
            prop_info = {
                'SPORT': sport,
                'GAME_TYPE': game_type,
                'IS_PROP': 1,
                'GAME_NAME': game_name,
                'BET_NAME': bet_list[0],
                'BET_TYPE': f'{bet_list[(i * 3) + 1]} {bet_list[(i * 3) + 2]}',
                'ODDS': f'{bet_list[(i * 3) + 3]}',
                'HOME_TEAM': teams[1],
                'AWAY_TEAM': teams[0],
                'ALIGNED_BET_NAME': bet_list[0],
                'ALIGNED_BET_TYPE': text_filter(f'Home team {bet_list[2]}' if teams[i] == teams[0] else f'Away team {bet_list[5]}'),
                'GAME_TIME': game_time,
                'IS_TIMEOUT': is_timeout,
                'SPORTS_BOOK': 'Sugarhouse',
                'TIMESTAMP': time_stamp,
                'URL': URL
            }
            temp_list.append(prop_info)
    except:
        return temp_list
    return temp_list


def collect_totals(sport, game_type, game_name, time_stamp, game_time, is_timeout, bet_list):
    temp_list = []
    teams = game_name.split(" @ ")
    try:
        for i in range(2):
            prop_info = {
                'SPORT': sport,
                'GAME_TYPE': game_type,
                'IS_PROP': 1,
                'GAME_NAME': game_name,
                'BET_NAME': bet_list[0],
                'BET_TYPE': f'O {bet_list[2]}' if teams[i] == teams[0] else f'U {bet_list[5]}',
                'ODDS': f'{bet_list[(i * 3) + 3]}',
                'HOME_TEAM': teams[1],
                'AWAY_TEAM': teams[0],
                'ALIGNED_BET_NAME': bet_list[0],
                'ALIGNED_BET_TYPE': text_filter(f'O {bet_list[2]}' if teams[i] == teams[0] else f'U {bet_list[5]}'),
                'GAME_TIME': game_time,
                'IS_TIMEOUT': is_timeout,
                'SPORTS_BOOK': 'Sugarhouse',
                'TIMESTAMP': time_stamp,
                'URL': URL
            }
            temp_list.append(prop_info)
    except:
        return temp_list
    return temp_list


def scrape_prop():
    for attempt in range(5):
        try:
            WebDriverWait(driver, 20).until(EC.presence_of_element_located((By.CLASS_NAME, 'KambiBC-list-view__column')))
            break
        except Exception as time_wait_error:
            logger.warning(f'Time wait is passed for \n{URL} \nwith error: {time_wait_error}')

    prop_bets = []
    sport = "Football"
    game_type = "Live"
    time_stamp = datetime.now().strftime("%m/%d/%Y %H:%M:%S")

    try:
        clock = driver.find_elements(By.CLASS_NAME, "KambiBC-match-clock__inner")
        game_time = clock[0].text
        is_timeout = istimeout(game_time)
    except:
        game_time = ''
        is_timeout = ''

    try:
        teams_drv = WebDriverWait(driver, 1).until(EC.visibility_of_all_elements_located(
            (By.CLASS_NAME, 'KambiBC-scoreboard-american-football__participants')))
    except:
        teams_drv = WebDriverWait(driver, 1).until(EC.visibility_of_all_elements_located(
            (By.CLASS_NAME, 'KambiBC-modularized-scoreboard__participant-name')))

    try:
        if len(teams_drv) == 2:
            home_team = teams_drv[0].text
            away_team = teams_drv[1].text.replace("vs", "")
            game_name = f"{home_team} @ {away_team}"
        if len(teams_drv) == 1:
            game_name = teams_drv[0].text.replace("\n", " @ ")
    except Exception as ex:
        logger.warning(f"Couldn't scrape teams! Error:\n{ex}")
        return []

    try:
        elem = driver.find_elements(By.XPATH, ".//ul[contains(@class, 'KambiBC-list-view__column')]")
    except:
        return "FINISH"

    for elem_row in elem:
        try:
            clicks = elem_row.find_elements(By.XPATH, ".//li[@class='KambiBC-bet-offer-category']")
            for click in clicks:
                click.click()
        except StaleElementReferenceException as e:
            logger.warning(f'Bet table element has changed the reference. Unable to scrape the bet odd')
            continue
        except:
            pass

        try:
            match_rows = elem_row.find_elements(By.XPATH, ".//li[@class='KambiBC-bet-offer-category KambiBC-expanded']")
        except StaleElementReferenceException as e:
            logger.warning(f'Bet table element has changed the reference. Unable to scrape the bet odd')
            continue
        except:
            return "FINISH"

        for match_row in match_rows:
            try:
                first_line = match_row.find_elements(By.XPATH, ".//li[@class='KambiBC-bet-offer-subcategory KambiBC-bet-offer-subcategory--onecrosstwo']")
                first_line = [in_text.text.split('\n') for in_text in first_line]

                second_line = match_row.find_elements(By.XPATH, ".//li[@class='KambiBC-bet-offer-subcategory KambiBC-bet-offer-subcategory--handicap']")
                second_line = [in_text.text.split('\n') for in_text in second_line]

                third_line = match_row.find_elements(By.XPATH, ".//li[@class='KambiBC-bet-offer-subcategory KambiBC-bet-offer-subcategory--overunder']")
                third_line = [in_text.text.split('\n') for in_text in third_line]
            except StaleElementReferenceException as e:
                logger.warning(f'Bet table element has changed the reference. Unable to scrape the bet odd')
                continue

            for i in first_line:
                if "moneyline" in i[0].lower():
                    temp_val = collect_moneyline(sport=sport, game_type=game_type, game_name=game_name, time_stamp=time_stamp, game_time=game_time, is_timeout=is_timeout, bet_list=i)
                    for j in temp_val:
                        prop_bets.append(j)
                elif "spread" in i[0].lower():
                    temp_val = collect_spreads(sport=sport, game_type=game_type, game_name=game_name, time_stamp=time_stamp, game_time=game_time, is_timeout=is_timeout, bet_list=i)
                    for j in temp_val:
                        prop_bets.append(j)
                elif "total" in i[0].lower():
                    temp_val = collect_totals(sport=sport, game_type=game_type, game_name=game_name, time_stamp=time_stamp, game_time=game_time, is_timeout=is_timeout, bet_list=i)
                    for j in temp_val:
                        prop_bets.append(j)

            for i in second_line:
                if "moneyline" in i[0].lower():
                    temp_val = collect_moneyline(sport=sport, game_type=game_type, game_name=game_name, time_stamp=time_stamp, game_time=game_time, is_timeout=is_timeout, bet_list=i)
                    for j in temp_val:
                        prop_bets.append(j)
                elif "spread" in i[0].lower():
                    temp_val = collect_spreads(sport=sport, game_type=game_type, game_name=game_name, time_stamp=time_stamp, game_time=game_time, is_timeout=is_timeout, bet_list=i)
                    for j in temp_val:
                        prop_bets.append(j)
                elif "total" in i[0].lower():
                    temp_val = collect_totals(sport=sport, game_type=game_type, game_name=game_name, time_stamp=time_stamp, game_time=game_time, is_timeout=is_timeout, bet_list=i)
                    for j in temp_val:
                        prop_bets.append(j)

            for i in third_line:
                if "moneyline" in i[0].lower():
                    temp_val = collect_moneyline(sport=sport, game_type=game_type, game_name=game_name, time_stamp=time_stamp, game_time=game_time, is_timeout=is_timeout, bet_list=i)
                    for j in temp_val:
                        prop_bets.append(j)
                elif "spread" in i[0].lower():
                    temp_val = collect_spreads(sport=sport, game_type=game_type, game_name=game_name, time_stamp=time_stamp, game_time=game_time, is_timeout=is_timeout, bet_list=i)
                    for j in temp_val:
                        prop_bets.append(j)
                elif "total" in i[0].lower():
                    temp_val = collect_totals(sport=sport, game_type=game_type, game_name=game_name, time_stamp=time_stamp, game_time=game_time, is_timeout=is_timeout, bet_list=i)
                    for j in temp_val:
                        prop_bets.append(j)

    return prop_bets


def main():
    module_operate_until = datetime.now() + module_work_duration

    failure_count = 0
    count_scraps = 0

    while datetime.now() < module_operate_until:
        parsing_start_time = time.time()
        try:
            logger.info('Start scraping Sugarhouse props')
            prop_bet_list = scrape_prop()

            if prop_bet_list == "FINISH":
                logger.info("The game has ended!")
                res_upd = update_redis_status(URL, 2)
                logger.info(res_upd)
                break

            else:
                url_part = URL.split('/')
                if not prop_bet_list:
                    continue
                # save data to redis db
                saving_result = add_data_redis(f'football_sugarhouse_prop_{url_part[-1]}', prop_bet_list)
                logger.info(
                    f'The result of saving data: {saving_result}') if saving_result == 'OK' else logger.exception(
                    f'The result of saving data: {saving_result}')                
                count_scraps += 1

        except KeyboardInterrupt:
            logger.warning("Keyboard Interrupt. Quit the driver!")
            driver.close()
            logger.info(f'Module stopped working')
            res_upd = update_redis_status(URL, 2)
            logger.info(res_upd)
            break

        except Exception as e:
            logger.exception(f'Stop script with errors:\n{e}')
            failure_count += 1
            if failure_count >= 5:
                driver.close()
                logger.exception(f'Script exited after {failure_count} unsuccessful attempts to start the main loop')
                res_upd = update_redis_status(URL, 3)
                logger.info(res_upd)
                break
         
        if count_scraps % scrap_step == 0:
            actions_on_page(driver=driver, class_name="sc-fzXfNO gPURds")
            if count_scraps == scrap_limit:
                driver.refresh()                
                count_scraps = 0

        parsing_work_time = time.time() - parsing_start_time
        time.sleep(max(0, update_frequency.total_seconds() - parsing_work_time))
        
    driver.close()
    res_upd = update_redis_status(URL, 2)
    logger.info(res_upd)
    logger.warning('Script successfully ended working at the set time')


if __name__ == "__main__":
    main()
