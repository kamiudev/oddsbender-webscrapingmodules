import threading, time, functools
from configparser import ConfigParser
from datetime import datetime
from os import environ

from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from utilities.logging import get_logger
from utilities.utils import str_to_timedelta, update_redis_status, text_filter, get_driver, actions_on_page
from utilities.queue import QueueClient
from utilities.redis import RedisClient
from utilities.driver import DriverClient

# read config file
config_parser = ConfigParser()
config_parser.read('conf/caesars.conf')
module_conf = config_parser["MODULE"]

# init logging on start
logger_name = environ.get('basketball_caesarsprop_get_logger', 'basketball_caesars_prop')
# for local logs storage and stdout use DEBUG_FLAG = 1
DEBUG_FLAG = environ.get('PROP_LOG_DEBUG_FLAG', 1)
log_level = environ.get('basketball_caesarsprop_log_level', 'WARNING')

logger = get_logger(logger_name, DEBUG_FLAG, log_level)

module_work_duration = str_to_timedelta(environ.get('basketball_caesarsprop_module_work_duration', module_conf.get('module_work_duration')))
update_frequency = str_to_timedelta(environ.get('basketball_caesarsprop_update_frequency', module_conf.get('update_frequency')))
browser = environ.get('basketball_caesarsprop_browser', module_conf.get('browser_prop'))

scrap_step = int(environ.get('basketball_scrap_step', module_conf.get('scrap_step')))
scrap_limit = int(environ.get('basketball_scrap_limit', module_conf.get('scrap_limit')))


hostname = environ.get("HOSTNAME", "local")
sportsbook = environ.get("sportsbook", "none")
URL = None

redisClient = RedisClient()
driverClient = DriverClient()

def games_time():
    try:
        times = WebDriverWait(driverClient.driver, 5).until(EC.presence_of_element_located((By.XPATH, ".//div[@class='sr-lmt-clock__box srt-base-1-background']"))).text
    except:
        try:
            times = driverClient.driver.find_element(By.XPATH, "//div[@class='liveClock' ]").text
        except:
            times = ''

        pass
    return times


def check_timeout(game_time=str):
    if game_time == '':
        return 1
    else:
        try:
            gt = games_time[3:]
            if gt == '00:00':
                return 1
            else:
                return 0
        except:
            return 0


def scrape_all(match_row, bet_title):
    try:
        bet_name = match_row.find_elements(By.XPATH, ".//div[contains(@class, 'header selectionHeader truncate3Rows')]")
        bet_class = [bet.get_attribute("class") for bet in bet_name]
        bet_name = [bet.text for bet in bet_name]
    except:
        return 'FAILED'
    else:
        if len(bet_name) == 0:
            return 'FAILED'
        try:
            idx = list(map(lambda x: bet_title in x, bet_name)).index(True)
        except ValueError:
            return 'FAILED'
        mls_name = bet_name[idx].split(' ')
        mls_name.remove('LIVE')
        mls_name = ''.join(mls_name)
        col = bet_class[idx].split()[-1]
        mls = match_row.find_elements(By.XPATH, f".//div[@class='selectionContainer  {col}']")
        mls = [ml.text.split("\n") for ml in mls]
        mls.insert(0, mls_name)
        return mls



def get_aligned_bet_type(teams, outcome_title, handicap_value, i):

    for team in teams:
        if outcome_title[i] in team:
            if i == 0:
                return f'Away team {handicap_value[i]}'
            else:
                return f'Home team {handicap_value[i]}'
    
    return handicap_value[i]
    



def scrape_popular(period, game_time, URL):
    prop_bets = []

    # teams = driverClient.driver.find_element(By.XPATH, ".//div[@class='eventHeaderTitle']").text
    # teams = teams.title()

    # if (' At ') in teams:
    #     teams = teams.split(' At ')
    # else:
    #     teams = teams.split(' Vs ')

    teams = [
        driverClient.driver.find_elements(By.XPATH, ".//div[@class='name']")[0].text,
        driverClient.driver.find_elements(By.XPATH, ".//div[@class='name']")[1].text
    ]

    game_name = f'{teams[0] + " @ " + teams[1]}'



    try:
        quarter_half = False
        try:
            driverClient.driver.find_element(By.XPATH, ".//li[@data-qa='pill-filter-quarter-half-bets']").click()
            WebDriverWait(driverClient.driver, 10).until(EC.presence_of_element_located((By.CLASS_NAME, 'MarketCardContainer')))
            quarter_half = True
        except Exception as e:
            logger.info(f'Time wait is passed!')
            pass

        time_stamp = datetime.now().strftime("%m/%d/%Y %H:%M:%S")
        sport = URL.split("/")[-3].capitalize()
        if not game_time:
            return 'FINISH'
        if period == '2nd Half' or period == '4th Quarter':
            quarter_half = False
        is_timeout = check_timeout(game_time)

        if quarter_half:
            # Catch NCAA
            if 'Half' in period:
                match_rows_pop = driverClient.driver.find_elements(By.XPATH, './/div[@class="MarketCardContainer"]/div[@class="MarketCard"]')
                for match_row in match_rows_pop:
                    match_data = {
                        "outcome_title": [],
                        "handicap_value": [],
                        "odd_value": []
                    }
                    bet_name = match_row.find_element(By.XPATH, './/span[@class="title"]').text
                    header_ele = match_row.find_element(By.XPATH, './/div[contains(@class, "expanderHeader")]')
                    header_ele_cls = header_ele.get_attribute('class')
                    if "collapsed" in header_ele_cls:
                        header_ele.click()
                        time.sleep(1)
                    
                    if 'Half Spread' in bet_name or 'Half Total Points' in bet_name:
                        outcomes = match_row.find_elements(By.XPATH, './/div[@class="outcome"]')
                        for outcome in outcomes:
                            outcome_title = outcome.find_element(By.XPATH, './/div[@class="outcomeTitle"]').text
                            handicap_value = outcome.find_element(By.XPATH, './/div[@class="handicap"]').text
                            odd_value = outcome.find_element(By.XPATH, './/div[contains(@class, "odds ")]').text
                            match_data['outcome_title'].append(outcome_title)
                            match_data['handicap_value'].append(handicap_value)
                            match_data['odd_value'].append(odd_value)
                        
                        for i in range(2):
                            data = f"{match_data['outcome_title'][i]} {match_data['handicap_value'][i]}" if not match_data['outcome_title'][i] in match_data['handicap_value'][i] else f"{match_data['handicap_value'][i]}"
                            BET_TYPE = data.replace('Over', 'O').replace('Under', 'U')
                            ALIGNED_BET_TYPE = get_aligned_bet_type(teams, match_data['outcome_title'], match_data['handicap_value'], i).replace('Over', 'O').replace('Under', 'U')
                            prop_info_dict_pop_ml = {
                                'SPORT': sport,
                                'GAME_TYPE': "Live",
                                'IS_PROP': 1,
                                'GAME_NAME': game_name,
                                'BET_NAME': bet_name,
                                'BET_TYPE': BET_TYPE,
                                'ODDS': match_data['odd_value'][i],
                                'HOME_TEAM': teams[1],
                                'AWAY_TEAM': teams[0],
                                'ALIGNED_BET_NAME': bet_name,
                                'ALIGNED_BET_TYPE': ALIGNED_BET_TYPE,
                                'GAME_TIME': game_time,
                                'IS_TIMEOUT': is_timeout,
                                'SPORTS_BOOK': 'Caesars',
                                'TIMESTAMP': time_stamp,
                                'URL': URL
                            }
                            prop_bets.append(prop_info_dict_pop_ml)
            
            else:
                #Catch NBA
                match_rows_pop = driverClient.driver.find_elements(By.XPATH, ".//div[contains(@class, 'MarketCard groupedMarketTemplateMarketCard')]")
                for match_row in match_rows_pop:
                    mll = scrape_all(match_row, 'MONEY LINE LIVE')
                    sprd = scrape_all(match_row, 'SPREAD LIVE')
                    tps = scrape_all(match_row, 'TOTAL POINTS LIVE')

                    if mll == 'FAILED' and sprd == 'FAILED' and tps == 'FAILED':
                        logger.info("Bets in popular were stopped")
                        break

                    if mll[1][0] == '' and sprd[1][0] == '' and tps[1][0] == '':
                        logger.info("Bets in popular were stopped")
                        is_timeout = 1
                        break

                    if (game_time[0] not in sprd[0] and game_time[0].isdigit()) or (game_time[1] not in sprd[0] and game_time[1].isdigit()):
                        continue

                    if mll == 'FAILED':
                        logger.info('Moneylines bet was stopped')
                    else:
                        for i in range(2):
                            BET_TYPE = teams[i].replace('Over', 'O').replace('Under', 'U')
                            ALIGNED_BET_TYPE = text_filter('Home team' if teams[i] == teams[1] else 'Away team', mll[0], teams[1], teams[0], i).replace('Over', 'O').replace('Under', 'U')
                            prop_info_dict_pop_ml = {
                                'SPORT': sport,
                                'GAME_TYPE': "Live",
                                'IS_PROP': 1,
                                'GAME_NAME': game_name,
                                'BET_NAME': ' '.join((mll[0][:3].lower(), mll[0][3:mll[0].index('MONEY')].title(), mll[0][mll[0].index('MONEY'):].title())),
                                'BET_TYPE': teams[i],
                                'ODDS': mll[i + 1][0],
                                'HOME_TEAM': teams[1],
                                'AWAY_TEAM': teams[0],
                                'ALIGNED_BET_NAME': ' '.join((mll[0][:3].lower(), mll[0][3:mll[0].index('MONEY')].title(), mll[0][mll[0].index('MONEY'):].title())),
                                'ALIGNED_BET_TYPE': ALIGNED_BET_TYPE,
                                'GAME_TIME': game_time,
                                'IS_TIMEOUT': is_timeout,
                                'SPORTS_BOOK': 'Caesars',
                                'TIMESTAMP': time_stamp,
                                'URL': URL
                            }
                            prop_bets.append(prop_info_dict_pop_ml)

                    if sprd == 'FAILED':
                        logger.info('Spread bet was stopped')
                    else:
                        for i in range(2):
                            BET_TYPE = (f'{teams[i]} {sprd[i + 1][0]}').replace('Over', 'O').replace('Under', 'U')
                            ALIGNED_BET_TYPE = text_filter(f'Home team {sprd[i + 1][0]}' if teams[i] == teams[1] else f'Away team {sprd[i + 1][0]}', sprd[0], teams[1], teams[0], i).replace('Over', 'O').replace('Under', 'U')
                            prop_info_dict_pop_sprd = {
                                'SPORT': sport,
                                'GAME_TYPE': "Live",
                                'IS_PROP': 1,
                                'GAME_NAME': game_name,
                                'BET_NAME': ' '.join((sprd[0][:3].lower(), sprd[0][3:sprd[0].index('SPREAD')].title(), sprd[0][sprd[0].index('SPREAD'):].title())),
                                'BET_TYPE': BET_TYPE,
                                'ODDS': sprd[i + 1][1],
                                'HOME_TEAM': teams[1],
                                'AWAY_TEAM': teams[0],
                                'ALIGNED_BET_NAME': ' '.join((sprd[0][:3].lower(), sprd[0][3:sprd[0].index('SPREAD')].title(), sprd[0][sprd[0].index('SPREAD'):].title())),
                                'ALIGNED_BET_TYPE': ALIGNED_BET_TYPE,
                                'GAME_TIME': game_time,
                                'IS_TIMEOUT': is_timeout,
                                'SPORTS_BOOK': 'Caesars',
                                'TIMESTAMP': time_stamp,
                                'URL': URL
                            }
                            prop_bets.append(prop_info_dict_pop_sprd)

                    if tps == 'FAILED':
                        logger.info('Total points bet was stopped')
                    else:
                        for i in range(2):
                            BET_TYPE = tps[i + 1][0].replace('Over', 'O').replace('Under', 'U')
                            ALIGNED_BET_TYPE = text_filter(tps[i + 1][0] if teams[i] == teams[1] else tps[i + 1][0]).replace('Over', 'O').replace('Under', 'U')
                            prop_info_dict_pop_tps = {
                                'SPORT': sport,
                                'GAME_TYPE': "Live",
                                'IS_PROP': 1,
                                'GAME_NAME': game_name,
                                'BET_NAME': ' '.join((tps[0][:3].lower(), tps[0][3:tps[0].index('TOTAL')].title(), tps[0][tps[0].index('TOTAL'):tps[0].index('POINTS')].title(), tps[0][tps[0].index('POINTS'):].title())),
                                'BET_TYPE': BET_TYPE,
                                'ODDS': (tps[i + 1][1]).strip(),
                                'HOME_TEAM': teams[1],
                                'AWAY_TEAM': teams[0],
                                'ALIGNED_BET_NAME': ' '.join((tps[0][:3].lower(), tps[0][3:tps[0].index('TOTAL')].title(), tps[0][tps[0].index('TOTAL'):tps[0].index('POINTS')].title(), tps[0][tps[0].index('POINTS'):].title())),
                                'ALIGNED_BET_TYPE': ALIGNED_BET_TYPE,
                                'GAME_TIME': game_time,
                                'IS_TIMEOUT': is_timeout,
                                'SPORTS_BOOK': 'Caesars',
                                'TIMESTAMP': time_stamp,
                                'URL': URL
                            }
                            prop_bets.append(prop_info_dict_pop_tps)
    except:
        pass

    else:
        if not prop_bets:
            return 'STOP'
        logger.info(f'Game is scraped successfully')
        return prop_bets


def scraper(URL):
    file_tail = URL.split('/')[-1]

    driverClient.set_driver(get_driver(browser))
    driverClient.driver.get(URL)

    logger.warning(f'Module started working with parameters:\nURL: {URL}\nmodule_work_duration: {module_work_duration}\nupdate_frequency: {update_frequency}\nbrowser: {browser}\nlogger_name: {logger_name}\nlog_level: {log_level}\nDEBUG_FLAG: {DEBUG_FLAG}')

    module_operate_until = datetime.now() + module_work_duration

    failure_count = 0
    count_of_stopped = 0
    count_scraps = 0

    while datetime.now() < module_operate_until:
        parsing_start_time = time.time()
        try:
            logger.info(f'Start scraping')
            
            # Click the button "Game Tracker"
            try:
                WebDriverWait(driverClient.driver, 10).until(EC.presence_of_element_located((By.XPATH, "//*[@id='tab-live-media-game-tracker']"))).click()
            except:
                logger.info('There is no Game Track Button')
                pass

            try:
                # get all live games
                element = WebDriverWait(driverClient.driver, 10).until(EC.presence_of_element_located((By.XPATH,
                                                                                                       ".//div[@class='sr-tabs__flexcontainer']//*[@type='button' and @data-test-tab='pitchBasketball']"))).click()
                games_on_initial_page = driverClient.driver.find_elements(By.XPATH, "//div[@class='MarketCollection']")
            except:
                logger.info('The game has ended')
                res_upd = update_redis_status(URL, 2)
                logger.info(res_upd)
                break

            # get current period
            game_time = games_time()
            try:
                element = WebDriverWait(driverClient.driver, 20).until(EC.presence_of_element_located((By.XPATH, ".//div[@class='sr-tabs__flexcontainer']//*[@type='button' and @data-test-tab='timeline']"))).click()
                period = WebDriverWait(driverClient.driver, 20).until(EC.presence_of_element_located((By.XPATH, './/div[@class="sr-lmt-plus-pbp-period__expand-name srm-is-compact srm-is-uppercase"]'))).text
            except:
                period = ''
                pass

            popular_bet_list = scrape_popular(period=period, game_time=game_time, URL=URL)
            if popular_bet_list == 'STOP':
                logger.info('Bets were stopped')
                count_of_stopped += 1

            elif popular_bet_list == 'FINISH':
                logger.info("The game has ended")
                res_upd = update_redis_status(URL, 2)
                logger.info(res_upd)
                break

            else:
                if not popular_bet_list:
                    continue
                # save data to redis db
                saving_result = redisClient.add_data_redis(f'basketball_caesars_prop_{file_tail}', popular_bet_list)
                logger.info(
                    f'The result of saving data: {saving_result} {popular_bet_list}') if saving_result == 'OK' else logger.exception(
                    f'The result of saving data: {saving_result}')
                count_scraps += 1

            if count_of_stopped == 10:
                logger.info('The game does not accept bets!')
                # res_upd = update_redis_status(URL, 3)
                # logger.info(res_upd)
                count_of_stopped = 0
                raise

            parsing_work_time = time.time() - parsing_start_time
            time.sleep(max(0, update_frequency.total_seconds() - parsing_work_time))

            failure_count = 0

        except KeyboardInterrupt:
            logger.warning("Keyboard Interrupt. Quit the driver!")
            driverClient.driver.quit()
            logger.warning(f'Module stopped working')
            res_upd = update_redis_status(URL, 2)
            logger.info(res_upd)
            break

        except Exception as e:
            logger.warning(f'Stop loop with errors:\n{e}')
            failure_count += 1
            if failure_count >= 5:
                driverClient.driver.quit()
                logger.warning(f'Script exited after {failure_count} unsuccessful attempts to start the main loop')
                # res_upd = update_redis_status(URL, 3)
                # logger.info(res_upd)
                raise
                break
        
        if count_scraps % scrap_step == 0:
            try:
                actions_on_page(driver=driverClient.driver, class_name="eventHeaderTitle")
            except:
                logger.warning(f'There is no class_name="eventHeaderTitle"')
                pass
            if count_scraps == scrap_limit:
                driverClient.driver.refresh()
                count_scraps = 0

        parsing_work_time = time.time() - parsing_start_time
        time.sleep(max(0, update_frequency.total_seconds() - parsing_work_time))

    driverClient.driver.quit()
    res_upd = update_redis_status(URL, 2)
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
        except Exception as ex:
            logger.exception(ex)
            time.sleep(60)
            logger.warning("sleeping 60")
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

    print("Waiting to receive games...")
    queue.channel.basic_consume(on_message_callback=on_message_callback, queue=sportsbook, consumer_tag=hostname)
    queue.channel.start_consuming()

    for thread in threads:
        thread.join()

    queue.connection.close()

if __name__ == "__main__":
    main()
