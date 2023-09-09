import threading, time, functools
from configparser import ConfigParser
from datetime import datetime
from os import environ

from bs4 import BeautifulSoup
from selenium.common.exceptions import (NoSuchElementException,
                                        StaleElementReferenceException)
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from utilities.logging import get_logger
from utilities.utils import str_to_timedelta, split_string, get_driver, actions_on_page, text_filter
from utilities.queue import QueueClient
from utilities.redis import RedisClient

from utilities.driver_proxy import get_driver_proxy


# read config file
config_parser = ConfigParser()
config_parser.read('conf/fanduel.conf')
module_conf = config_parser["MODULE"]

# init logging
logger_name = environ.get('basketball_fanduelprop_get_logger', 'basketball_fanduel_prop')
# for local logs storage and stdout use DEBUG_FLAG = 1
DEBUG_FLAG = environ.get('PROP_LOG_DEBUG_FLAG', 1)
log_level = environ.get('basketball_fanduelprop_log_level', 'WARNING')

logger = get_logger(logger_name, DEBUG_FLAG, log_level)

# other variables
# URL = environ['fanduel_prop_url']
# file_tail = URL.split('/')[-1]

module_work_duration = str_to_timedelta(environ.get('basketball_fanduelprop_module_work_duration', module_conf.get('module_work_duration')))
update_frequency = str_to_timedelta(environ.get('basketball_fanduelprop_update_frequency', module_conf.get('update_frequency')))
browser = environ.get('basketball_fanduelprop_browser', module_conf.get('browser_prop'))

scrap_step = int(environ.get('basketball_scrap_step', module_conf.get('scrap_step')))
scrap_limit = int(environ.get('basketball_scrap_limit', module_conf.get('scrap_limit')))

script_version = 'v07012023'
hostname = environ.get("HOSTNAME", "local")
sportsbook = environ.get("sportsbook", "none")
driver = None
URL = None

redisClient = RedisClient()


def click_on_web_element(element: WebElement):
    global driver
    driver.execute_script("arguments[0].scrollIntoView(true);", element)
    WebDriverWait(driver, 10).until(EC.element_to_be_clickable(element))
    driver.execute_script("arguments[0].click();", element)
    time.sleep(3)


def open_bet_list(all_bets_on_page: list, mode=None):
    logger.info(f'Open all bets on the page')
    clicks = 0
    for single_bet_table in all_bets_on_page:
        try:
            click_on_web_element(single_bet_table)
            clicks += 1
            if clicks == 1 and mode:
                click_on_web_element(single_bet_table)
        except:
            continue

def parse_prop_bets(bet_table, additional_param, title, URL):
    bet_name = bet_table[0]
    # if bet_name == 'Gamelines':
    #     return []

    # if '2nd Half' in bet_name or '4th Quarter' in bet_name:
    #     return []
    
    # if title == 'Alternates' and ('Spread' not in bet_name and 'Total Points' not in bet_name):
    #     return []

    # if title == 'Popular' and ('Spread' not in bet_name and 'Total Points' not in bet_name):
    #     return []

    # if ('Quarter' in title or 'Half' in title) and (' '.join((title, 'Spread')) not in bet_name and ' '.join((title, 'Total')) not in bet_name and ' '.join((title, 'Moneyline')) not in bet_name and ' '.join((title, 'Winner')) not in bet_name or '3 Way' in bet_name or 'Parlay' in bet_name):
    #     return []


    logger.info(f'Start scraping bet {bet_name}')
    prop_bet_list = []

    # check for timeout
    try:
        is_timeout = 0 if ':' in additional_param.get('game_time') else 1
    except:
        is_timeout = 1

    bet_odds = []

    if 'Spread' in bet_name:
        bet_type = [' '.join((bet_table[1], bet_table[2])), ' '.join((bet_table[4], bet_table[5]))]
    elif 'Alternative' in bet_name:
        bet_type = [bet_table[2], bet_table[5]]
    elif 'Total' in bet_name and title != 'Popular':
        bet_type = [bet_table[4], bet_table[6]]
        try:
            bet_odds = [bet_table[5], bet_table[7]]
        except IndexError:
            return prop_bet_list
    elif 'Total' in bet_name and title == 'Popular':
        bet_type = [' '.join((bet_table[1], bet_table[2])), ' '.join((bet_table[4], bet_table[5]))]
        bet_odds = [bet_table[3], bet_table[6]]
    elif 'Moneyline' in bet_name:
        bet_type = [bet_table[1], bet_table[3]]
        bet_odds = [bet_table[2], bet_table[4]]
    elif 'Winner' in bet_name:
        bet_type = [bet_table[3], bet_table[5]]
        bet_odds = [bet_table[4], bet_table[6]]
    else:
        bet_type = [bet_table[4], bet_table[6]]
    
    if not bet_odds:
        bet_odds = [bet_table[3], bet_table[6]]

    for i in range(2):
        prop_bet_dict = {
            'SPORT': additional_param.get('sport'),
            'GAME_TYPE': f"{additional_param.get('game_type')} {script_version}",
            'IS_PROP': 1,
            'GAME_NAME': additional_param.get("game_name"),
            'BET_NAME': bet_name,
            'BET_TYPE': text_filter(bet_type[i]),
            'ODDS': (bet_odds[i]).strip(),
            'HOME_TEAM': additional_param.get('home_team'),
            'AWAY_TEAM': additional_param.get('away_team'),
            'ALIGNED_BET_NAME': bet_name.replace(additional_param.get('home_team'), 'Home Team').replace(additional_param.get('away_team'), 'Away Team').replace('Under', 'U').replace('Over', 'O'),
            'ALIGNED_BET_TYPE': text_filter(bet_type[i], bet_name, additional_param.get('home_team'), additional_param.get('away_team'), i),
            'GAME_TIME': additional_param.get('game_time'),
            'IS_TIMEOUT': is_timeout,
            'SPORTS_BOOK': 'Fanduel',
            'TIMESTAMP': additional_param.get('time_stamp'),
            'URL': URL
        }

        # if 'Spread' in prop_bet_dict['BET_NAME'] or 'Total Point' in prop_bet_dict['BET_NAME']:
        prop_bet_list.append(prop_bet_dict)

    logger.info(f'Bet {bet_name} scraped successfully')
    return prop_bet_list


def scraper(URL):
    file_tail = URL.split('/')[-1]

    # init web driver
    global driver
    # driver = get_driver(browser)
    # driver.get(URL)

    while True:
        try:
            driver = get_driver_proxy()
            driver.get(URL)
            driver.find_element(By.XPATH, '//h1[contains(text(), "Please verify you are a human")]').text
            time.sleep(3)
            driver.quit()
            continue
        except:
            break

    logger.warning(f'Module started working with parameters:\nURL: {URL}\nmodule_work_duration: {module_work_duration}\nupdate_frequency: {update_frequency}\nbrowser: {browser}\nlogger_name: {logger_name}\nlog_level: {log_level}\nDEBUG_FLAG: {DEBUG_FLAG}')

    module_operate_until = datetime.now() + module_work_duration
    exception_counter = 0
    count_scraps = 0

    while datetime.now() < module_operate_until:

        logger.info('Start scraping Fanduel props')
        previous_bet_bur_buttons = driver.find_elements(By.XPATH, '//div[@style="height: 100%;"]//a')

        additional_param = {}

        # get type of sport
        try:
            additional_param['sport'] = URL.split('/')[3].capitalize()
        except:
            additional_param['sport'] = 'Not identified'
            logger.warning('It’s impossible to identify game type')

        # check if the game_type field is active
        try:
            game_online = WebDriverWait(driver, 2).until(EC.visibility_of_element_located((By.ID, 'LiveTag_svg__a')))
            if game_online:
                additional_param['game_type'] = 'Live'
            if not game_online:
                additional_param['game_type'] = 'Pre-game'
        except Exception as ex:
            additional_param['game_type'] = 'Unable to Get'
            logger.warning('There are no live game element found')
            logger.exception(ex)
        # get game_time
        try:
            additional_param['game_time'] = WebDriverWait(driver, 2).until(EC.visibility_of_element_located((By.XPATH, "//span[contains(@class, '') and contains(text(),':') and not(contains(text(),'/'))]"))).text
        except:
            for ttime in ['HT', '4th', '3rd', '2nd', '1st']:
                try:
                    gm_time = driver.find_element(By.XPATH, f"//span[text()='{ttime}']").text
                    additional_param['game_time'] = gm_time
                    break
                except Exception as e:
                    pass

                additional_param['game_time'] = ''
        
        try:
            a_team_string = driver.find_element(By.XPATH, f'//main[@id="main"]//h1').text
            teams = a_team_string.split(' @ ')
            a_team = teams[0]
            h_team = teams[1]
            additional_param['game_name'] = f'{a_team} @ {h_team}'
            
        except:
            logger.info(f'The game is over')
            res_upd = redisClient.update_redis_status(URL, 2)
            logger.info(res_upd)
            break

        # try:
        #     teams = driver.find_element(By.TAG_NAME, 'h1').text.replace(' v ', ' @ ').split(' @ ')
            
        #     if len(teams[0]) > 20 or len(teams[1]) > 10:
        #         a_team = driver.find_element(By.XPATH, f"//span[contains(text(),'{teams[0]}')]").text
        #         h_team = driver.find_element(By.XPATH, f"//span[contains(text(),'{teams[1]}')]").text
        #     else:
        #         a_team = teams[0]
        #         h_team = teams[1]

        #     additional_param['game_name'] = f'{a_team} @ {h_team}'
        # except NoSuchElementException:
        #     logger.info(f'The game is over')
        #     res_upd = redisClient.update_redis_status(URL, 2)
        #     logger.info(res_upd)
        #     break

        try:
            logger.info(f'Start scraping game {additional_param.get("game_name")}')

            parsing_start_time = time.time()
            prop_bets_list = []
            additional_param['away_team'], additional_param['home_team'] = split_string(additional_param.get("game_name"))
            additional_param['time_stamp'] = datetime.now().strftime("%m/%d/%Y %H:%M:%S") 


            if 'nba' in URL:
                allowed_bets = ['1st Quarter', '2nd Quarter', '3rd Quarter', '4th Quarter']
            elif 'ncaa' in URL:
                allowed_bets = ['Half']
            else:
                break
            

            for bet_button in previous_bet_bur_buttons:
                try:
                    title = bet_button.get_attribute('title')
                except:
                    continue

                mtitile = title.split(":")
                ntitle = str(mtitile[1].lstrip())


                if ntitle.strip() in allowed_bets:
                    
                    allow_bet = False
                    if 'nba' in URL and additional_param['game_time'].split(' ')[0].strip() == ntitle.split(' ')[0].strip():
                        allow_bet = True
                    elif 'ncaa' in URL and additional_param['game_time'].split(' ')[0].strip() in ['4th', '3rd', '2nd', '1st']:
                        allow_bet = True
                    
                    if allow_bet:
                        try:
                            driver.execute_script("arguments[0].click();", bet_button.find_element(By.XPATH, 'div[@role="button"]'))
                        except:
                            logger.warning(f'Tab {title} not clicked')
                            continue

                        bets_tables = WebDriverWait(driver, 10).until(
                            EC.visibility_of_all_elements_located(
                                (By.XPATH, '//*[contains(@style, "flex-direction: column;")]')))

                        try:
                            pages_to_open = bets_tables[-1].find_elements(By.XPATH, './/div[@role="button"]')
                            open_bet_list(pages_to_open, True)
                            try:
                                show_mores = bets_tables[-1].find_elements(By.XPATH, "//span[contains(text(),'Show more')]")
                                open_bet_list(show_mores)
                            except:
                                pass
                            match_rows = bets_tables[-1].get_attribute('innerHTML')

                        except StaleElementReferenceException:
                            continue


                        bs_data = BeautifulSoup(match_rows, "html.parser")
                        match_row = bs_data.find_all("li")
                        data = list(filter(lambda x: len(x) > 0, [in_text.get_text(separator="\n") for in_text in match_row]))

                        for certain_bet in data:
                            certain_bet_split = certain_bet.split('\n')
                            try:
                                prop_bets_list += parse_prop_bets(certain_bet_split, additional_param, title, URL)
                            except Exception as e:
                                logger.exception(f'Unable to scrape the bet. {e}')

            if not prop_bets_list:
                continue

            # save data to redis db
            saving_result = redisClient.add_data_redis(f'basketball_fanduel_prop_{file_tail}', prop_bets_list)
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
            logger.info(f'Module stopped working')
            res_upd = redisClient.update_redis_status(URL, 2)
            logger.info(res_upd)
            break

        except Exception as e:
            logger.exception(f"Exception in main scraping cycle. {e}")
            exception_counter += 1
            if exception_counter >= 5:
                driver.quit()
                logger.exception(f'Script exited after {exception_counter} unsuccessful attempts to execute the main loop')
                res_upd = redisClient.update_redis_status(URL, 3)
                logger.info(res_upd)
                break
                
        if count_scraps % scrap_step == 0:
            actions_on_page(driver=driver, class_name="LiveTag_svg__a")
            if count_scraps == scrap_limit:
                driver.refresh()                
                count_scraps = 0

    driver.quit()
    res_upd = redisClient.update_redis_status(URL, 2)
    logger.info(res_upd)
    logger.warning(f'Module stopped working')

def main():
    queue = QueueClient()
   
    def do_work(ch, delivery_tag, body):
        thread_id = threading.get_ident()
        logger.warning('Thread id: %s Deliver Tag: %s Message Body: %s', thread_id, delivery_tag, body)
        url_to_scrape = str(body.decode('UTF-8'))

        cb = None
        try:
            scraper(url_to_scrape)
            cb = functools.partial(queue.ack_message, ch, delivery_tag)
        except:
            cb = functools.partial(queue.nack_message, ch, delivery_tag)
        
        queue.connection.add_callback_threadsafe(cb)
    
    def on_message(ch, method_frame, _header_frame, body, args):
        threads = args
        delivery_tag = method_frame.delivery_tag
        t = threading.Thread(target=do_work, args=(ch, delivery_tag, body))
        t.start()
        threads.append(t)

    queue.exchange_declare()
    queue.queue_declare(sportsbook, durable=True)
    queue.queue_bind(sportsbook)
    queue.channel.basic_qos(prefetch_count=1)

    threads = []
    on_message_callback = functools.partial(on_message, args=(threads))

    logger.warning("Waiting to receive games...")
    queue.channel.basic_consume(on_message_callback=on_message_callback, queue=sportsbook, consumer_tag=hostname)
    queue.channel.start_consuming()

    for thread in threads:
        thread.join()

    queue.connection.close()

if __name__ == "__main__":
    main()

