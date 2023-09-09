import threading, time, functools
from configparser import ConfigParser
from datetime import datetime
from os import environ

from selenium.common.exceptions import StaleElementReferenceException
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from utilities.driver import DriverClient
from utilities.logging import get_logger
from utilities.utils import get_driver, str_to_timedelta, actions_on_page, text_filter
from utilities.queue import QueueClient
from utilities.redis import RedisClient

# read config file
config_parser = ConfigParser()
config_parser.read('conf/sugarhouse.conf')
module_conf = config_parser["MODULE"]

# init logging
logger_name = environ.get('basketball_sugarhouseprop_get_logger', 'basketball_sugarhouse_prop')
# for local logs storage and stdout use DEBUG_FLAG = 1
DEBUG_FLAG = environ.get('PROP_LOG_DEBUG_FLAG', 1)
log_level = environ.get('basketball_sugarhouseprop_log_level', 'WARNING')

logger = get_logger(logger_name, DEBUG_FLAG, log_level)

module_work_duration = str_to_timedelta(environ.get('basketball_sugarhouseprop_module_work_duration', module_conf.get('module_work_duration')))
update_frequency = str_to_timedelta(environ.get('basketball_sugarhouseprop_update_frequency', module_conf.get('update_frequency')))
browser = environ.get('basketball_sugarhouseprop_browser', module_conf.get('browser_prop'))

scrap_step = int(environ.get('basketball_scrap_step', module_conf.get('scrap_step')))
scrap_limit = int(environ.get('basketball_scrap_limit', module_conf.get('scrap_limit')))

script_version = 'v16012023'
hostname = environ.get("HOSTNAME", "local")
sportsbook = environ.get("sportsbook", "none")
driver = None
URL = None
URL_ALL = environ.get('basketball_sugarhouse_url', module_conf.get('URL'))

redisClient = RedisClient()
driver = DriverClient()

def istimeout(game_time, current_period):
    try:
        if (game_time == "00:00" or game_time == "12:00" or game_time == "24:00" or game_time == "36:00" or game_time == "48:00") and 'Quarter' in current_period:
            timeout = 1
        elif (game_time == "00:00" or game_time == "20:00" or game_time == "40:00") and 'Half' in current_period:
            timeout = 1
        else:
            timeout = 0
        return timeout
    except:
        return ''


def collect_all(sport, game_type, game_name, time_stamp, game_time, is_timeout, bet_list, bet):
    temp_list = []
    teams = game_name.split(" @ ")
    
    # logger.warning(bet_list)

    bet_type = bet_list.pop(0)
    step = 3

    if len(bet_list) < 4:
        return temp_list

    if bet == 'spread':
        to_check = {teams[1], teams[0]}
    elif bet == 'moneyline':
        to_check = {teams[1], teams[0]}
        step = 2
    else:
        to_check = {'Over', 'Under'}
    bet_list_align = []

    i = 0
    while i < len(bet_list):
        chunck = bet_list[i:i + step]
        if len(chunck) == step:
            if chunck[step-1] in to_check:
                chunck = chunck[:step-1] + ['']
                i -= 1
        else:
            chunck = chunck + [''] * (step - len(chunck))

        bet_list_align += chunck
        i += step

    if bet == 'total':
        idx = bet_list_align.index('Under')
    else:
        idx = bet_list_align.index(teams[1])
    
    ovs_list = bet_list_align[:idx]
    und_list = bet_list_align[idx:]

    if len(ovs_list) != len(und_list):
        und_list = und_list[step:]

    for s in range(0, len(ovs_list), step):
        cur_bet_list = list(zip(ovs_list[s:s+step], und_list[s:s+step]))
        try:
            bet_type = f"{bet_type.split('-')[1].strip()} - {bet_type.split('-')[0].strip()}"
            for i in range(2):
                BET_TYPE = text_filter(f'{cur_bet_list[step-3][0]} {cur_bet_list[step-2][0]}' if teams[i] == teams[0] else f'{cur_bet_list[step-3][1]} {cur_bet_list[step-2][1]}') if 'moneyline' not in bet_type.lower() else (cur_bet_list[step-2][0] if teams[i] == teams[0] else cur_bet_list[step-2][1])
                ALIGNED_BET_TYPE = text_filter(f'{cur_bet_list[step-3][0]} {cur_bet_list[step-2][0]}' if teams[i] == teams[0] else f'{cur_bet_list[step-3][1]} {cur_bet_list[step-2][1]}', bet, teams[1], teams[0], i) if bet != 'moneyline' else text_filter(f'{cur_bet_list[step-2][0]}' if teams[i] == teams[0] else f'{cur_bet_list[step-2][1]}', 'spread', teams[1], teams[0], i)
                if 'Total' in bet_type and not 'U' in BET_TYPE and BET_TYPE.split('O')[0] != 'O':
                    BET_TYPE = f"O {BET_TYPE.split('O')[0]}"
                    ALIGNED_BET_TYPE = f"O {ALIGNED_BET_TYPE.split('O')[0]}"
                prop_info = {
                    'SPORT': sport,
                    'GAME_TYPE': f"{game_type} {script_version}",
                    'IS_PROP': 1,
                    'GAME_NAME': game_name,
                    'BET_NAME': bet_type,
                    'BET_TYPE': BET_TYPE,
                    'ODDS': (f'{cur_bet_list[step-1][i]}').strip(),
                    'HOME_TEAM': teams[1],
                    'AWAY_TEAM': teams[0],
                    'ALIGNED_BET_NAME': bet_type,
                    'ALIGNED_BET_TYPE': ALIGNED_BET_TYPE,
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


# def scrape_prop():

#     return prop_bet_list


def get_all():

    browser = environ.get('basketball_sugarhouse_url_browser', module_conf.get('browser_url'))
    driver = get_driver(browser)
    driver.get(URL_ALL)
    try:
        # check if basketball is in live games
        get_check_game = WebDriverWait(driver, 10).until(EC.presence_of_element_located(
            (By.XPATH, "//*[@alt='Basketball']")))
        check_game = 'Basketball' if get_check_game else ""
    except:
        check_game = ''

    if 'Basketball' in check_game:
        # open NBA
        try:
            hidden_tabs = driver.find_elements(By.XPATH, "//*[@aria-expanded='false']")
            for hidden_tab in hidden_tabs:

                if 'NBA' in hidden_tab.get_attribute('id') or 'NCAAB' in hidden_tab.get_attribute('id'):
                    hidden_tab.click()
                    logger.info(f'Opened {hidden_tab.text}')
        except:
            logger.info('All tabs opened')

        # close other tabs
        try:
            unhidden_tabs = driver.find_elements(By.XPATH, "//*[@aria-expanded='true']")
            for unhidden_tab in unhidden_tabs:
                if 'NBA' not in unhidden_tab.get_attribute('id') and 'NCAAB' not in unhidden_tab.get_attribute(
                        'id'):
                    unhidden_tab.click()
                    logger.info(f'Closed {unhidden_tab.text}')
        except:
            logger.info('All tabs closed')

        return driver

       

def scraper(URL):

    '''
    # When the site changed the routing of a single betting link,  hit the site from the base_url and click the single betting like the human being.
    driver = get_all()
    for i in range(10):
        for tmp_game in driver.find_elements(By.XPATH, "//div[contains(@id, 'listview-group-')]"):
            game_name = (tmp_game.get_attribute('data-testid')).split('-')[-1]
            url_e = f'https://pa.playsugarhouse.com/?page=sportsbook#event/live/{game_name}'
            if URL == url_e:
                try:
                    any_title = tmp_game.find_element(By.XPATH, './div/div/div[1]/div[2]')
                    any_title.click()
                    time.sleep(3)
                except Exception as e:
                    pass
                break
    '''

    # browser_prop = Firefox,  it doesn't work for prop.
    browser = environ.get('basketball_sugarhouseprop_browser', 'Chrome')
    driver = get_driver(browser)
    driver.get(URL)


    logger.warning(f'Module started working with parameters:\nURL: {URL}\nmodule_work_duration: {module_work_duration}\nupdate_frequency: {update_frequency}\nbrowser: {browser}\nlogger_name: {logger_name}\nlog_level: {log_level}\nDEBUG_FLAG: {DEBUG_FLAG}')

    module_operate_until = datetime.now() + module_work_duration
    failure_count = 0
    count_scraps = 0

    while datetime.now() < module_operate_until:
        parsing_start_time = time.time()
        try:
            logger.info('Start scraping Sugarhouse props')
            # prop_bet_list = scrape_prop()
            for attempt in range(5):
                try:
                    WebDriverWait(driver, 20).until(EC.presence_of_element_located((By.CLASS_NAME, 'KambiBC-list-view__column')))
                    break
                except Exception as time_wait_error:
                    logger.warning(f'Time wait is passed for \n{URL} \nwith error: {time_wait_error}')

            prop_bet_list = []
            allowed_bets = {'Moneyline', 'Most Popular'}
            sport = "Basketball"
            game_type = "Live"
            time_stamp = datetime.now().strftime("%m/%d/%Y %H:%M:%S")
            
            try:
                scoreboard = driver.find_element(By.CLASS_NAME, "KambiBC-modularized-scoreboard__event-info").get_attribute('innerHTML')
                current_period = scoreboard.split(' | ')[-1].split(':')[0]
            except:
                current_period = ''
                pass

            if current_period:
                if current_period[0] == 'H' and current_period[1] == '1':
                    current_period = '1st Half'
                elif current_period[0] == 'H' and current_period[1] == '2':
                    current_period = '2nd Half'
                elif current_period[0] == 'Q' and current_period[1] == '1':
                    current_period = '1st Quarter'
                elif current_period[0] == 'Q' and current_period[1] == '2':
                    current_period = '2nd Quarter'
                elif current_period[0] == 'Q' and current_period[1] == '3':
                    current_period = '3rd Quarter'
                elif current_period[0] == 'Q' and current_period[1] == '4':
                    current_period = '4th Quarter'
                else:
                    current_period = ''

            if current_period in {'1st Quarter', '2nd Quarter', '3rd Quarter'}:
                allowed_bets.add(current_period)

            elif current_period == '1st Half':
                allowed_bets.add('Half Time')
            
            try:
                clock = driver.find_elements(By.CLASS_NAME, "KambiBC-match-clock__inner")
                game_time = clock[0].text
                is_timeout = istimeout(game_time, current_period)
            except:
                game_time = ''
                is_timeout = ''

            if game_time:
                mins, secs = int(game_time.split(':')[0]), game_time.split(':')[1]
                period_num = int(current_period[0]) - 1 if current_period else 0
                if 'Quarter' in current_period:
                    mins = str(mins - (12*period_num))
                elif 'Half' in current_period:
                    mins = str(mins - (20*period_num))
                else:
                    mins = str(mins)
                game_time = ':'.join((mins, secs))
                    
            game_time = ' '.join((current_period, game_time))

            for attempt in range(5):
                try:
                    teams_drv = WebDriverWait(driver, 5).until(EC.visibility_of_all_elements_located((By.CLASS_NAME, 'KambiBC-modularized-scoreboard__participant-name')))
                    if len(teams_drv) == 2:
                        home_team = teams_drv[0].text
                        away_team = teams_drv[1].text.replace("vs", "").replace("@", "")
                        game_name = f"{home_team} @ {away_team}"
                    if len(teams_drv) == 1:
                        game_name = teams_drv[0].text.replace("vs", "@")
                    break
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
                        title_line = match_row.find_element(By.XPATH, ".//div[contains(@class,'CollapsibleContainer__Title')]").text                
                    except:
                        title_line = ''
                        pass

                    if title_line.strip() not in allowed_bets:
                        continue
                    
                    try:
                        hide_buttons = match_row.find_elements(By.XPATH, ".//button[contains(text(), 'Show list')]")
                        for hide_button in hide_buttons:
                            hide_button.click()
                    except:
                        pass

                    try:
                        first_line = match_row.find_elements(By.XPATH,
                                                            ".//li[@class='KambiBC-bet-offer-subcategory KambiBC-bet-offer-subcategory--onecrosstwo']")
                        first_line = [in_text.text.split('\n') for in_text in first_line]

                        second_line = match_row.find_elements(By.XPATH,
                                                            ".//li[@class='KambiBC-bet-offer-subcategory KambiBC-bet-offer-subcategory--handicap']")
                        second_line = [in_text.text.split('\n') for in_text in second_line]

                        third_line = match_row.find_elements(By.XPATH,
                                                            ".//li[@class='KambiBC-bet-offer-subcategory KambiBC-bet-offer-subcategory--overunder']")
                        third_line = [in_text.text.split('\n') for in_text in third_line]

                    except StaleElementReferenceException as e:
                        logger.warning(f'Bet table element has changed the reference. Unable to scrape the bet odd')
                        continue
                        
                    all_lines = [first_line, second_line, third_line]
                    
                    for line in all_lines:
                        
                        for sub_line in line:
                            if sub_line:
                                try:
                                    sub_line.remove('TEASER +')
                                except:
                                    pass
                                if "moneyline" in sub_line[0].lower():
                                    try:
                                        idx = sub_line.index('Alternate Lines')
                                        sub_line = sub_line[idx:]
                                        sub_line[0] = ' '.join((sub_line[0], 'Moneyline'))
                                    except:
                                        if current_period and current_period not in title_line:
                                            continue
                                        else:
                                            pass
                                    temp_val = collect_all(sport=sport, game_type=game_type, game_name=game_name,
                                                                time_stamp=time_stamp, game_time=game_time, is_timeout=is_timeout,
                                                                bet_list=sub_line, bet='moneyline')
                                    for j in temp_val:
                                        if j['ODDS']:
                                            prop_bet_list.append(j)

                                elif "spread" in sub_line[0].lower():
                                    try:
                                        idx = sub_line.index('Alternate Lines')
                                        sub_line = sub_line[idx:]
                                        sub_line[0] = ' '.join((sub_line[0], 'Spread'))
                                    except:
                                        pass
                                    temp_val = collect_all(sport=sport, game_type=game_type, game_name=game_name,
                                                            time_stamp=time_stamp, game_time=game_time, is_timeout=is_timeout,
                                                            bet_list=sub_line, bet='spread')
                                    for j in temp_val:
                                        if j['ODDS']:
                                            prop_bet_list.append(j)

                                elif "total" in sub_line[0].lower() and 'by' not in sub_line[0].lower():
                                    try:
                                        idx = sub_line.index('Alternate Lines')
                                        sub_line = sub_line[idx:]
                                        sub_line[0] = ' '.join((sub_line[0], 'Total'))
                                    except:
                                        pass
                                    temp_val = collect_all(sport=sport, game_type=game_type, game_name=game_name,
                                                            time_stamp=time_stamp, game_time=game_time, is_timeout=is_timeout,
                                                            bet_list=sub_line, bet='total')
                                    for j in temp_val:
                                        if j['ODDS']:
                                            prop_bet_list.append(j)
            if prop_bet_list == "FINISH":
                logger.info("The game has ended!")
                res_upd = redisClient.update_redis_status(URL, 2)
                logger.info(res_upd)
                break

            else:
                url_part = URL.split('/')
                if not prop_bet_list:
                    continue
                # save data to redis db
                saving_result = redisClient.add_data_redis(f'basketball_sugarhouse_prop_{url_part[-1]}', prop_bet_list)
                logger.info(
                    f'The result of saving data: {saving_result}') if saving_result == 'OK' else logger.exception(
                    f'The result of saving data: {saving_result}')                
                count_scraps += 1

        except KeyboardInterrupt:
            logger.warning("Keyboard Interrupt. Quit the driver!")
            driver.close()
            logger.info(f'Module stopped working')
            res_upd = redisClient.update_redis_status(URL, 2)
            logger.info(res_upd)
            break

        except Exception as e:
            logger.exception(f'Stop script with errors:\n{e}')
            failure_count += 1
            if failure_count >= 5:
                driver.close()
                logger.exception(f'Script exited after {failure_count} unsuccessful attempts to start the main loop')
                res_upd = redisClient.update_redis_status(URL, 3)
                logger.info(res_upd)
                break
                
        if count_scraps % scrap_step == 0:
            actions_on_page(driver=driver, class_name="KambiBC-modularized-scoreboard__participant-name")
            if count_scraps == scrap_limit:
                driver.refresh()
                count_scraps = 0

        parsing_work_time = time.time() - parsing_start_time
        time.sleep(max(0, update_frequency.total_seconds() - parsing_work_time))
        
    driver.close()
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
