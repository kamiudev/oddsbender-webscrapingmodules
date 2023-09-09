import threading, time, functools
from configparser import ConfigParser
from datetime import datetime
from os import environ

from selenium.webdriver.common.by import By
from selenium.common.exceptions import StaleElementReferenceException
from utilities.logging import get_logger
from utilities.utils import get_driver, str_to_timedelta, actions_on_page, text_filter
from utilities.queue import QueueClient
from utilities.redis import RedisClient

# read config file
config_parser = ConfigParser()
config_parser.read('conf/draftkings.conf')
module_conf = config_parser["MODULE"]

# init logging
logger_name = environ.get('basketball_draftkingsprop_get_logger', 'basketball_draftkings_prop')
# for local logs storage and stdout use DEBUG_FLAG = 1
DEBUG_FLAG = environ.get('PROP_LOG_DEBUG_FLAG', 0)
log_level = environ.get('basketball_draftkingsprop_log_level', 'WARNING')

logger = get_logger(logger_name, DEBUG_FLAG, log_level)

# other variables
module_work_duration = str_to_timedelta(environ.get('basketball_draftkingsprop_module_work_duration', module_conf.get('module_work_duration')))
update_frequency = str_to_timedelta(environ.get('basketball_draftkingsprop_update_frequency', module_conf.get('update_frequency')))
browser = environ.get('basketball_draftkingsprop_browser', module_conf.get('browser_prop'))

scrap_step = int(environ.get('basketball_scrap_step', module_conf.get('scrap_step')))
scrap_limit = int(environ.get('basketball_scrap_limit', module_conf.get('scrap_limit')))

script_version = 'v29122022'
hostname = environ.get("HOSTNAME", "local")
sportsbook = environ.get("sportsbook", "none")
driver = None
URL = None

redisClient = RedisClient()


def check_timeout(gt):
    if gt == 'HALFTIME':
        return 1
    elif gt == '12:00' or gt == '10:00':
        return 1
    else:
        return 0


# def scrape_prop():

#     return prop_bets_list


def scraper(URL):

    # init web driver
    driver = get_driver(browser)
    driver.get(URL)

    logger.warning(f'Module started working with parameters:\nURL: {URL}\nmodule_work_duration: {module_work_duration}\nupdate_frequency: {update_frequency}\nbrowser: {browser}\nlogger_name: {logger_name}\nlog_level: {log_level}\nDEBUG_FLAG: {DEBUG_FLAG}')

    module_operate_until = datetime.now() + module_work_duration
    failure_count = 0
    count_scraps = 0

    while datetime.now() < module_operate_until:
        parsing_start_time = time.time()
        driver.implicitly_wait(10)                          
        try:
            logger.info(f'Start scraping DraftKings props')

            try:
                # prop_bet_list = scrape_prop()
                prop_bet_list = []
                sport = "Basketball"
                game_type = "Live"
                time_stamp = datetime.now().strftime("%m/%d/%Y %H:%M:%S")

                try:
                    clock = driver.find_elements(By.CLASS_NAME, "event-cell__time")
                    game_time = clock[0].text        
                    if game_time == 'FINISH':
                        return game_time
                    elif game_time == '':
                        period = driver.find_elements(By.CLASS_NAME, "event-cell__period")
                        is_timeout = check_timeout(period)
                    else:
                        is_timeout = check_timeout(game_time)
                except:
                    game_time = ''
                    is_timeout = ''
                    pass

                try:
                    teams = driver.find_elements(By.CLASS_NAME, "live-score-body__row--team")
                    teams = [in_text.text for in_text in teams]
                    game_name = f'{teams[0] + " @ " + teams[1]}'
                except:
                    logger.info("Url avaliable but the game has ended!")
                    return 'FINISH'

                # league = driver.find_element(By.CLASS_NAME, "sportsbook-league-page__header").text
                league = driver.find_element(By.CLASS_NAME, "sportsbook-tabbed-subheader__tabs").text
                period = driver.find_element(By.CLASS_NAME, "sportsbook-live-scoreboard-component-1")
                current_time = period.find_element(By.XPATH, './/*[@class="event-cell__period"]')

                # game_part = ''
                # if 'College' in league and current_time.text != '2ND HALF':
                #     game_part = 'Halves'
                # elif 'College' not in league and current_time.text != '4TH QUARTER':
                #     game_part = 'Quarters'
                # if game_part != '':
                #     categories = ['Game Lines', game_part]
                # else:
                #     categories = ['Game Lines']
                #     # scrape spreads, totals, money lines

                page_header = driver.find_element(By.CLASS_NAME, "sportsbook-event-page__header").text
                
                categories = ['Game Lines']
                if 'NBA' in page_header:
                    categories.append('Quarters')
                elif 'College' in page_header:
                    categories.append('Halves')

                for subcat in categories:
                    xpath = f"//a[@id='subcategory_{subcat}']"
                    try:
                        element = driver.find_element(By.XPATH, xpath)
                        driver.execute_script("arguments[0].click();", element)
                    except:
                        logger.info(f"{subcat} bets were closed!")
                        continue

                    try:
                        match_rows = driver.find_elements(By.XPATH, ".//div[contains(@class, 'parlay-card-10-a')]")
                    except:
                        logger.info("Bets did not found!")
                        continue

                    for match_row in match_rows:
                        headers = match_row.find_elements(By.XPATH, ".//div[@class='sportsbook-table-header__title']")
                        headers = [in_text.text for in_text in headers]
                        if subcat in {'Halves', 'Quarters'} and current_time.text not in headers:
                            continue

                        data = match_row.find_elements(By.CLASS_NAME, "sportsbook-table__column-row")
                        classes = [element.get_attribute('innerHTML') for element in data]
                        data = [in_text.text.split('\n') for in_text in data]
                        spreads = []
                        totals = []
                        moneylines = []

                        spreads.append((data[1], classes[1]))
                        spreads.append((data[5], classes[5]))

                        if spreads[0][0][0] == "" or 'disabled' in spreads[0][1]:
                            logger.info("Spread bets were disabled!")
                        else:
                            for i in range(2):
                                prop_info_dict_spread = {
                                    'SPORT': sport,
                                    'GAME_TYPE': f"{game_type} {script_version}",
                                    'IS_PROP': 1,
                                    'GAME_NAME': game_name,
                                    'BET_NAME': headers[1],
                                    'BET_TYPE': f'{teams[i]} {spreads[i][0][0]}',
                                    'ODDS': str(spreads[i][0][1]).replace('\u2212', '-'),
                                    'HOME_TEAM': teams[1],
                                    'AWAY_TEAM': teams[0],
                                    'ALIGNED_BET_NAME': headers[1],
                                    'ALIGNED_BET_TYPE': text_filter(spreads[i][0][0], headers[1], teams[1], teams[0], i),
                                    'GAME_TIME': f'{current_time.text} {game_time}',
                                    'IS_TIMEOUT': is_timeout,
                                    'SPORTS_BOOK': 'Draft Kings',
                                    'TIMESTAMP': time_stamp,
                                    'URL': URL
                                }
                                if prop_info_dict_spread['BET_NAME'] == 'SPREAD':
                                    prop_bet_list.append(prop_info_dict_spread)

                        totals.append((data[2], classes[2]))
                        totals.append((data[6], classes[6]))

                        if totals[0][0][0] == "" or 'disabled' in totals[0][1]:
                            logger.info("Total bets were disabled!")
                        else:
                            for i in range(2):
                                prop_info_dict_totals = {
                                    'SPORT': sport,
                                    'GAME_TYPE': f"{game_type} {script_version}",
                                    'IS_PROP': 1,
                                    'GAME_NAME': game_name,
                                    'BET_NAME': headers[2],
                                    'BET_TYPE': f'{totals[i][0][0]} {totals[i][0][1]}',
                                    'ODDS': str(totals[i][0][2]).replace('\u2212', '-'),
                                    'HOME_TEAM': teams[1],
                                    'AWAY_TEAM': teams[0],
                                    'ALIGNED_BET_NAME': headers[2],
                                    'ALIGNED_BET_TYPE': text_filter(f'{totals[i][0][0]} {totals[i][0][1]}'),
                                    'GAME_TIME': f'{current_time.text} {game_time}',
                                    'IS_TIMEOUT': is_timeout,
                                    'SPORTS_BOOK': 'Draft Kings',
                                    'TIMESTAMP': time_stamp,
                                    'URL': URL
                                }
                                if prop_info_dict_totals['BET_NAME'] == 'TOTAL':
                                    prop_bet_list.append(prop_info_dict_totals)

                        moneylines.append((data[3], classes[3]))
                        moneylines.append((data[7], classes[7]))

                        if moneylines[0][0][0] == "" or 'disabled' in moneylines[0][1]:
                            logger.info("Moneylines bets were disabled!")
                        else:
                            for i in range(2):
                                prop_info_dict_moneylines = {
                                    'SPORT': sport,
                                    'GAME_TYPE': f"{game_type} {script_version}",
                                    'IS_PROP': 1,
                                    'GAME_NAME': game_name,
                                    'BET_NAME': headers[3],
                                    'BET_TYPE': f'{teams[i]}',
                                    'ODDS': str(moneylines[i][0][0]).replace('\u2212', '-'),
                                    'HOME_TEAM': teams[1],
                                    'AWAY_TEAM': teams[0],
                                    'ALIGNED_BET_NAME': headers[3],
                                    'ALIGNED_BET_TYPE': text_filter('', headers[3], teams[1], teams[0], i),
                                    'GAME_TIME': f'{current_time.text} {game_time}',
                                    'IS_TIMEOUT': is_timeout,
                                    'SPORTS_BOOK': 'Draft Kings',
                                    'TIMESTAMP': time_stamp,
                                    'URL': URL
                                }

                                if prop_info_dict_moneylines['BET_NAME'] == 'MONEYLINE':
                                    prop_bet_list.append(prop_info_dict_moneylines)

                    try:
                        match_rows = driver.find_elements(By.XPATH, ".//div[contains(@class, 'sportsbook-event-accordion__wrapper')]")
                    except:
                        logger.info("Alternate did not find!")
                        continue

                    for match_row in match_rows:
                        title = match_row.find_elements(By.CLASS_NAME, "sportsbook-event-accordion__title")
                        title = [in_text.text for in_text in title]
                        bet_name = title[0]
                        a_bet_name = title[0]

                        info = match_row.find_elements(By.XPATH, ".//div[@class='sportsbook-outcome-body-wrapper']")
                        classes = [element.get_attribute('innerHTML') for element in info]
                        info = [in_text.text.split("\n") for in_text in info]
                        try:
                            for k in info:
                                if k[0] == "" or 'disabled' in classes[0]:
                                    continue
                                if teams[0] in k[0]:
                                    bet_type = k[0] + " " + k[1]
                                    a_bet_type = k[0].replace(teams[0], "Away team")
                                    a_bet_type = a_bet_type + " " + k[1]
                                elif teams[1] in k[0]:
                                    bet_type = k[0] + " " + k[1]
                                    a_bet_type = k[0].replace(teams[1], "Home team")
                                    a_bet_type = a_bet_type + " " + k[1]
                                else:
                                    bet_type = k[0].replace('Over', 'O').replace('Under', 'U') + " " + k[1]
                                    a_bet_type = k[0].replace('Over', 'O').replace('Under', 'U') + " " + k[1]
                                prop_info_dict = {
                                    'SPORT': sport,
                                    'GAME_TYPE': f"{game_type} {script_version}",
                                    'IS_PROP': 1,
                                    'GAME_NAME': game_name,
                                    'BET_NAME': bet_name,
                                    'BET_TYPE': bet_type,
                                    'ODDS': str(k[2]).replace('\u2212', '-'),
                                    'HOME_TEAM': teams[1],
                                    'AWAY_TEAM': teams[0],
                                    'ALIGNED_BET_NAME': a_bet_name,
                                    'ALIGNED_BET_TYPE': text_filter(a_bet_type),
                                    'GAME_TIME': f'{current_time.text} {game_time}',
                                    'IS_TIMEOUT': is_timeout,
                                    'SPORTS_BOOK': 'Draft Kings',
                                    'TIMESTAMP': time_stamp,
                                    'URL': URL
                                }
                                prop_bet_list.append(prop_info_dict)
                        except:
                            continue
            # done
            except StaleElementReferenceException:
                prop_bet_list = []
                pass

            if prop_bet_list == "FINISH":
                logger.warning("The game has ended!")
                res_upd = redisClient.update_redis_status(URL, 2)
                logger.info(res_upd)
                break

            else:
                url_part = URL.split('/')
                if not prop_bet_list:
                    continue

                # save data to redis db
                saving_result = redisClient.add_data_redis(f'basketball_draftkings_prop_{url_part[-1]}', prop_bet_list)
                count_scraps += 1
                logger.info(
                    f'The result of saving data: {saving_result}') if saving_result == 'OK' else logger.exception(
                    f'The result of saving data: {saving_result}')

        except KeyboardInterrupt:
            logger.info("Keyboard Interrupt. Quit the driver!")
            driver.quit()
            logger.warning(f'Module stopped working')
            res_upd = redisClient.update_redis_status(URL, 2)
            logger.info(res_upd)
            break

        except Exception as e:
            logger.exception(f'Stop script with errors:\n{e}')
            failure_count += 1
            if failure_count >= 5:
                driver.quit()
                logger.exception(f'Script exited after {failure_count} unsuccessful attempts to start the main loop')
                res_upd = redisClient.update_redis_status(URL, 3)
                logger.info(res_upd)
                break
        if count_scraps % scrap_step == 0:
            actions_on_page(driver=driver, class_name="sportsbook-event-accordion__title")
            if count_scraps == scrap_limit:
                driver.refresh()
                count_scraps = 0

        parsing_work_time = time.time() - parsing_start_time
        time.sleep(max(0, update_frequency.total_seconds() - parsing_work_time))

    driver.quit()
    res_upd = redisClient.update_redis_status(URL, 2)
    logger.info(res_upd)
    logger.warning('Script successfully ended working at the set time')


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
