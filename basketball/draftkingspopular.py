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
from utilities.utils import get_driver, str_to_timedelta, actions_on_page, text_filter
from utilities.redis import RedisClient

# read config file
config_parser = ConfigParser()
config_parser.read('conf/draftkings.conf')
module_conf = config_parser["MODULE"]

# init logging
logger_name = environ.get('basketball_draftkingspopular_get_logger', 'basketball_draftkings_popular')
# for local logs storage and stdout use DEBUG_FLAG = 1
DEBUG_FLAG = environ.get('basketball_draftkingspopular_DEBUG_FLAG', 0)
log_level = environ.get('basketball_draftkingspopular_log_level', 'WARNING')

logger = get_logger(logger_name, DEBUG_FLAG, log_level)

# other variables
URL = environ.get('basketball_draftkings_url', module_conf.get('URL'))
module_work_duration = str_to_timedelta(environ.get('basketball_draftkingspopular_module_work_duration', module_conf.get('module_work_duration')))
update_frequency = str_to_timedelta(environ.get('basketball_draftkingspopular_update_frequency', module_conf.get('update_frequency')))
browser = environ.get('basketball_draftkingspopular_browser', module_conf.get('browser_popular'))

scrap_step = int(environ.get('basketball_scrap_step', module_conf.get('scrap_step')))
scrap_limit = int(environ.get('basketball_scrap_limit', module_conf.get('scrap_limit')))

# init web driver
driver = get_driver(browser)
driver.get(URL)

redisClient = RedisClient()

logger.warning(f'Module started working with parameters:\nURL: {URL}\nmodule_work_duration: {module_work_duration}\nupdate_frequency: {update_frequency}\nbrowser: {browser}\nlogger_name: {logger_name}\nlog_level: {log_level}\nDEBUG_FLAG: {DEBUG_FLAG}')

def pop_game_time(info):
    times = ''
    try:
        if info[1] in {'HALFTIME', ''}:
            return 'HALFTIME'
        else:
            return info[0]
    except:
        return times


def check_timeout(gt):
    if gt in ['HALFTIME', ':', '12:00', '10:00']:
        return 1
    else:
        return 0


def scrape_popular():
    popular_bets = []
    sport = URL.split('=')[-1].capitalize()
    game_type = "Live"
    time_stamp = datetime.now().strftime("%m/%d/%Y %H:%M:%S")
    try:
        match_rows = driver.find_elements(By.XPATH, '//div[@class="sportsbook-header__title"]/a[contains(text(), "College Basketball") or contains(text(), "NBA")]/ancestor::div[contains(@class, "sportsbook-featured-accordion__wrapper sportsbook-accordion")]')
        for matc_row in match_rows:
            bs_data = BeautifulSoup(matc_row.get_attribute('innerHTML'), "html.parser")
            match_row = bs_data.find_all(class_="sportsbook-table__column-row")
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
                h_team = sorted_data[i][0].split('\n')
                h_team = ['']*(4-len(h_team)) + h_team
                period = h_team[1]
                game_time = pop_game_time((h_team[0], h_team[1]))
                is_timeout = check_timeout(game_time)
                h_team = h_team[2]
                a_team = sorted_data[i][4].split('\n')
                a_team = ['']*(4-len(a_team)) + a_team
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
                for j in range(2):
                    kof_t = 1 + j
                    popular_info_dict = {
                        'SPORT': sport,
                        'GAME_TYPE': game_type,
                        'IS_PROP': 0,
                        'GAME': game_name,
                        'TEAM': teams[j],
                        'VS_TEAM': teams[1 - j],
                        'SPREAD': ' '.join((teams[j], sprd[j])),
                        'SPREAD_ODDS': sprd_odds[j],
                        'MONEYLINE_ODDS': moneyline[j],
                        'TOTAL': text_filter(f'{ttl[j + j]}{ttl[kof_t + j]}'),
                        'TOTAL_ODDS': ttl_odds[j],
                        'HOME_TEAM': a_team,
                        'AWAY_TEAM': h_team,
                        'GAME_TIME': ' '.join((period, game_time)),
                        'IS_TIMEOUT': is_timeout,
                        'SPORTS_BOOK': 'Draft Kings',
                        'TIMESTAMP': time_stamp
                    }
                    popular_bets.append(popular_info_dict)
                logger.info(f'Game lines scraped successfully')
    except:
        logger.warning("Couldn't scrape popular. Try again!")
        return []
    return popular_bets


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
                # check if basketball is in live games
                check_game_list = WebDriverWait(driver, 10).until(EC.visibility_of_all_elements_located(
                    (By.XPATH, "//span[@class='sportsbook-tabbed-subheader__tab']")))

                for fg in check_game_list:
                    if fg.text == 'BASKETBALL':
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
                saving_result = redisClient.add_data_redis('basketball_draftkings_popular', popular_bet_list)
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
            logger.info("Keyboard Interrupt. Quit the driver!")
            driver.quit()
            logger.warning(f'Module stopped working')
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
