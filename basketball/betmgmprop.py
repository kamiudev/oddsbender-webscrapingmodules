import threading, time, functools
from configparser import ConfigParser
from datetime import datetime
from os import environ

from bs4 import BeautifulSoup
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from utilities.logging import get_logger
from utilities.utils import str_to_timedelta, get_driver, actions_on_page, text_filter
from utilities.queue import QueueClient
from utilities.redis import RedisClient

# read config file
config_parser = ConfigParser()
config_parser.read('conf/betmgm.conf')
module_conf = config_parser["MODULE"]

# init logging
logger_name = environ.get('basketball_betmgmprop_get_logger', 'basketball_betmgm_prop')
# for local logs storage and stdout use DEBUG_FLAG = 1
DEBUG_FLAG = environ.get('PROP_LOG_DEBUG_FLAG', 1)
log_level = environ.get('basketball_betmgmprop_log_level', 'WARNING')

logger = get_logger(logger_name, DEBUG_FLAG, log_level)

module_work_duration = str_to_timedelta(environ.get('basketball_betmgmprop_module_work_duration', module_conf.get('module_work_duration')))
update_frequency = str_to_timedelta(environ.get('basketball_betmgmprop_update_frequency', module_conf.get('update_frequency')))
browser = environ.get('basketball_betmgmprop_browser', module_conf.get('browser_prop'))

scrap_step = int(environ.get('basketball_scrap_step', module_conf.get('scrap_step')))
scrap_limit = int(environ.get('basketball_scrap_limit', module_conf.get('scrap_limit')))

script_version = 'v29122022'
hostname = environ.get("HOSTNAME", "local")
sportsbook = environ.get("sportsbook", "none")
driver = None
URL = None

redisClient = RedisClient()

def parse_gameline_bet(game_data, allowed_bets, period_to_find):
    logger.info(f'Start scraping Gameline')

    soup = BeautifulSoup(game_data, "html.parser")
    all_blocks = soup.find_all("ms-option-panel", {"class": ['option-panel ng-star-inserted']})

    data_list = []
    for ab in all_blocks:
        bet_name = ab.find("div", {"class": ['option-group-name-info-name ng-star-inserted']}).text
        bet_subtype = ab.find_all("span", {"class": ['six-pack-col ng-star-inserted']})
        get_odds = ab.find_all("ms-option", {"class": ['option ng-star-inserted']})
 
        if bet_name.lower() in allowed_bets:
            odds_list = []
            subtype_odds_list = []
            for go in get_odds:
                try:
                    subtype_odds = go.find("div", {"class": ['name ng-star-inserted']}).text
                except:
                    subtype_odds = ''
                try:
                    odds = go.find("div", {"class": ['value option-value ng-star-inserted']}).text
                except:
                    odds = ''                
                subtype_odds_list.append(subtype_odds)
                odds_list.append(odds)
            
            data_list.append([bet_name, [i.text for i in bet_subtype], subtype_odds_list, odds_list])

    list_dict = []

    for dl in data_list:        
        if len(dl[1]) in {2,3}:
            for bt in dl[1]:
                idx = dl[1].index(bt)                 
                list_dict.append([' '.join((dl[0], period_to_find, bt)), '||', ' ', dl[2][idx], '||', dl[3][idx], 'Away Team'])
                list_dict.append([' '.join((dl[0], period_to_find, bt)), '||', ' ', dl[2][idx + len(dl[1])], '||', dl[3][idx + len(dl[1])], 'Home Team'])
        else:
            num = 0
            for sod, od in zip(dl[2], dl[3]):
                sod = sod.upper().replace('UNDER', 'U').replace('OVER', 'O')
                list_dict.append([' '.join(('Alternative', dl[0])), '||', '', sod, '||', od, 'Away Team' if num % 2 == 0 else 'Home Team'])
                num += 1

    return list_dict


def gen_dict(additional_param, data_list):
    logger.info(f'Start generating dict')

    popular_bets_list = []    
    for num, ld in enumerate(data_list):
        BET_TYPE = f"{additional_param.get('away_team') if num % 2 == 0 else additional_param.get('home_team')} {ld[3]}" if 'Total' not in ld[0] else ld[3]
        if 'Total'in ld[0] and not any([x in BET_TYPE for x in ["O", "U"]]):
            continue
            
        prop_one = {'SPORT': additional_param.get('sport'),
                    'GAME_TYPE': f"{additional_param.get('game_type')} {script_version}",
                    'IS_PROP': 1,
                    'GAME_NAME': f"{additional_param.get('away_team')} @ {additional_param.get('home_team')}",
                    'BET_NAME': ld[0],
                    'BET_TYPE': BET_TYPE,
                    'ODDS': (ld[5]).strip(),
                    'HOME_TEAM': additional_param.get('home_team'),
                    'AWAY_TEAM': additional_param.get('away_team'),
                    'ALIGNED_BET_NAME': ld[0],
                    'ALIGNED_BET_TYPE': text_filter(f'{ld[6]} {ld[3]}' if 'Total' not in ld[0] else ld[3], ld[0], additional_param.get('home_team'), additional_param.get('away_team'), num % 2),
                    'GAME_TIME': additional_param.get('game_time_detailed'),
                    'IS_TIMEOUT': additional_param.get('is_timeout'),
                    'SPORTS_BOOK': 'Betmgm',
                    'TIMESTAMP': additional_param.get('time_stamp'),
                    'URL': additional_param.get('url')
                    }
        popular_bets_list.append(prop_one)

    return popular_bets_list


def scraper(URL):
    trail = URL.split('-')[-1]
    URL += '?market=-1'

    # init web driver
    driver = get_driver(browser)
    driver.get(URL)

    logger.warning(f'Module started working with parameters:\nURL: {URL}\nmodule_work_duration: {module_work_duration}\nupdate_frequency: {update_frequency}\nbrowser: {browser}\nlogger_name: {logger_name}\nlog_level: {log_level}\nDEBUG_FLAG: {DEBUG_FLAG}')

    module_operate_until = datetime.now() + module_work_duration
    exception_counter = 0
    count_scraps = 0

    while datetime.now() < module_operate_until:
        additional_param = {}
        allowed_bets = {'totals', 'spread', 'money'}
        try:
            parsing_start_time = time.time()
            logger.info(f'Start scraping...')

            # check if the game is not over
            try:
                game_status = WebDriverWait(driver, 10).until(EC.visibility_of_element_located(
                    (By.XPATH, "//*[@class='scoreboard-message']"))).text
            except:
                try:
                    game_status = WebDriverWait(driver, 1).until(EC.visibility_of_element_located(
                        (By.CSS_SELECTOR, '.scoreboard-timer'))).text
                except:
                    game_status = ''

            if 'Starting in' in game_status:
                time_wait = int(''.join(x for x in game_status if x.isdigit()))
                logger.warning(f'The game {game_status}, waiting...')
                time.sleep(time_wait * 60)

            if game_status:                
                additional_param['sport'] = 'Basketball'
                additional_param['game_type'] = 'Live'
                additional_param['url'] = URL
                try:
                    additional_param['game_time'] = driver.find_element(
                        By.XPATH, "//*[@class='period-name ng-star-inserted']").text
                    
                    additional_param['game_time_detailed'] = driver.find_element(
                        By.XPATH, "//*[@class='sr-lmt-plus-scb__status srt-text-secondary srt-neutral-9']").text
                except:
                    additional_param['game_time'] = 'Starting now'
                    additional_param['game_time_detailed'] = 'Starting now'

                additional_param['game_status'] = game_status
                additional_param['is_timeout'] = 1 if game_status == 'Timeout' else 0
                additional_param['is_timeout'] = 1 if additional_param['game_time'] in {'Halftime', 'Intermission'} else additional_param['is_timeout']
                additional_param['time_stamp'] = datetime.now().strftime("%m/%d/%Y %H:%M:%S")

                get_teams = driver.find_elements(By.XPATH, "//div[@class='participant-name']")
                additional_param['away_team'], additional_param['home_team'] = [i.text for i in get_teams][:2]
                try:
                    get_all_props = driver.find_element(By.XPATH, "//*[@class='option-group-list ng-star-inserted']")
                except:
                    logger.info(f'The game has ended')
                    res_upd = redisClient.update_redis_status(URL.replace('?market=-1', ''), 2)
                    logger.info(res_upd)
                    break
                
                elements = driver.find_elements(By.XPATH, "//div[@class='scroll-adapter__container']//a")
                soup_els = []
                for element in elements:
                    try:
                        el = BeautifulSoup(element.get_attribute('innerHTML'), "html.parser")
                        soup_el = el.find_all('span',{'class':['title title-without-count ng-star-inserted']})[0].text
                        soup_els.append(soup_el)
                    except:
                        soup_els.append('')
                
                els_num = [idx for idx, value in enumerate(soup_els) if 'Full Game' in value][:2]

                if 'H' in additional_param['game_time']:
                    period_to_find = '1st Half'
                elif 'Q' in additional_param['game_time']:
                    if additional_param['game_time'][1] == '1':
                        period_to_find = '1st Quarter'
                    elif additional_param['game_time'][1] == '2':
                        period_to_find = '2nd Quarter'
                    elif additional_param['game_time'][1] == '3':
                        period_to_find = '3rd Quarter'
                    else:
                        period_to_find = ''
                elif 'Halftime' in additional_param['game_time']:
                    period_to_find = ''
                else:
                    period_to_find = ''

                if period_to_find:
                    try:
                        needed = soup_els.index(period_to_find,els_num[0],els_num[1]) 
                        to_click = elements[needed]
                        to_click.click()
                        get_all_props = driver.find_element(By.XPATH, "//*[@class='option-group-list ng-star-inserted']")
                        allowed_bets.add('game lines')
                    except:
                        logger.info(f'Not clicked to current period')
                        pass                

                try:
                    data_list = parse_gameline_bet(get_all_props.get_attribute('innerHTML'), allowed_bets, period_to_find)
                except Exception as data_list_error:
                    logger.warning(f'Maybe game ends or some another error\n{data_list_error}')
                    continue

                popular_bets_list = gen_dict(additional_param, data_list)

                # save data to redis db
                if len(popular_bets_list) != 0:
                    saving_result = redisClient.add_data_redis(f'basketball_betmgm_prop_{trail}', popular_bets_list)
                    logger.info(
                        f'The result of saving data: {saving_result}') if saving_result == 'OK' else logger.exception(
                        f'The result of saving data: {saving_result}')
                count_scraps += 1

                parsing_work_time = time.time() - parsing_start_time
                time.sleep(max(0, update_frequency.total_seconds() - parsing_work_time))

                exception_counter = 0

            if not game_status:
                logger.info(f'The game has ended')
                res_upd = redisClient.update_redis_status(URL.replace('?market=-1', ''), 2)
                logger.info(res_upd)
                break

        except KeyboardInterrupt:
            logger.warning("Keyboard Interrupt. Quit the driver!")
            driver.close()
            logger.info(f'Module stopped working')
            res_upd = redisClient.update_redis_status(URL.replace('?market=-1', ''), 2)
            logger.info(res_upd)
            break

        except Exception as e:
            logger.exception(f"Exception in main scraping cycle. {e}")
            exception_counter += 1
            if exception_counter >= 10:
                driver.close()
                logger.exception(
                    f'Script exited after {exception_counter} unsuccessful attempts to execute the main loop')
                res_upd = redisClient.update_redis_status(URL.replace('?market=-1', ''), 3)
                logger.info(res_upd)
                break

        if count_scraps % scrap_step == 0:
            actions_on_page(driver=driver, class_name="option-group-name-info-name ng-star-inserted")
            if count_scraps == scrap_limit:
                driver.refresh()                
                count_scraps = 0

    res_upd = redisClient.update_redis_status(URL.replace('?market=-1', ''), 2)
    logger.info(res_upd)
    logger.warning(f'Module stopped working')
    driver.close()

def main():
    queue = QueueClient()
   
    def do_work(ch, delivery_tag, body):
        thread_id = threading.get_ident()
        logger.warning('Thread id: %s Deliver Tag: %s Message Body: %s', thread_id, delivery_tag, body)
        url_to_scrape = str(body.decode('UTF-8'))

        cb = None
        try:
            redisClient.update_redis_status(url_to_scrape, 1, {"state": "scraping"})
            scraper(url_to_scrape)
            cb = functools.partial(queue.ack_message, ch, delivery_tag)
        except Exception as ex1:
            logger.exception(ex1)
            # cb = functools.partial(queue.nack_message, ch, delivery_tag)
        
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

