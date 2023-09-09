import datetime
import json
import os
import re
from os import environ
from configparser import ConfigParser
from datetime import timedelta
from user_agent import generate_user_agent

import pandas as pd
import redis
from selenium import webdriver
from selenium.webdriver.chrome.service import Service as ChromeService
from webdriver_manager.chrome import ChromeDriverManager

import random
import time
from selenium.webdriver.common.by import By
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.keys import Keys

# read config file
config_parser = ConfigParser()
# config_parser.read('conf/main.conf')
config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'conf', 'main.conf')

config_parser = ConfigParser()
config_parser.read(config_path)
module_conf = config_parser["MODULE"]

# get redis settings
redis_pass = environ.get('redis_pass', module_conf.get('redis_pass'))
redis_host = environ.get('redis_host', module_conf.get('redis_host'))
redis_port = environ.get('redis_port', module_conf.get('redis_port'))


def get_driver(browser, use_arguments=False):
    arguments_list = [
        '--headless',
        '--no-sandbox',
        '--disable-dev-shm-usage',
        '--incognito',
        '--window-size=1920,1080',
        f"user-agent={generate_user_agent(device_type='desktop')}",
    ]

    if use_arguments:
        arguments_list += [
            '--disable-logging',
            '--disable-extensions',
            '--disable-gpu',
            '--disable-infobars',
            'enable-automation',
            '--disable-dev-shm-usage',
            '--incognito',
        ]

    if browser == 'Chrome':
        options = webdriver.ChromeOptions()
        [options.add_argument(argument) for argument in arguments_list]
        service = ChromeService(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=options)
    elif browser == 'Firefox':
        options = webdriver.FirefoxOptions()
        [options.add_argument(argument) for argument in arguments_list]
        driver = webdriver.Firefox(executable_path="geckodriver", options=options)

    return driver


def str_to_dict(string):
    res_dict = dict((x.strip(), int(y.strip()))
                    for x, y in (element.split(':')
                                 for element in string.split(',')))
    return res_dict


def str_to_timedelta(string):
    return timedelta(**str_to_dict(string))


def save_to_csv(file_name, bets_dict):
    df = pd.DataFrame(bets_dict)
    if os.path.exists(file_name):
        df.to_csv(file_name, index=False, mode='a', header=False)
    else:
        outdir = file_name.split('/')[0]
        if not os.path.exists(outdir):
            os.mkdir(outdir)
        df.to_csv(file_name, index=False)


def split_string(bet: str):
    if '\n' in bet:
        return bet.split('\n')
    elif ' @ ' in bet:
        return bet.split(' @ ')
    elif ' v ' in bet:
        return bet.split(' v ')
    elif ' vs ' in bet:
        return bet.split(' vs ')
    elif bet:
        return '', bet
    else:
        return '', ''


def add_data_redis(stream_name, data_value):
    try:
        pool = redis.ConnectionPool(host=redis_host, port=redis_port, db=1, decode_responses=True, password=redis_pass)
        r = redis.Redis(connection_pool=pool)

        tmp_dict = json.dumps(data_value)
        r.xadd(stream_name, {"data_list": f"{tmp_dict}"})
        return 'OK'
    except Exception as redis_error:
        return redis_error


def add_url_redis(url, rd_game, stream_name):
    pool = redis.ConnectionPool(host=redis_host, port=redis_port, db=0, decode_responses=True, password=redis_pass)
    r = redis.Redis(connection_pool=pool)

    res_lst = []
    tmp_dict = json.dumps({
        "stream_name": stream_name,
        "sportsbook": rd_game,
        "data": url,
        "status": "0",
    })

    cursor_d, get_game_urls = r.scan(match=f'football_url_{rd_game}*', count=10000)

    # if data is present
    if len(get_game_urls) != 0:
        for i in get_game_urls:
            res_dct = json.loads(r.get(i))
            # get all urls
            res_lst.append(res_dct.get('data'))

        # check if new url in list redis db
        if url not in res_lst:
            r.set(f'football_url_{rd_game}_{datetime.datetime.now().timestamp()}', f'{tmp_dict}')
            return 'Added data to DB'

        if url in res_lst:
            return 'The record is present in the database'

    # no data in db, add data
    if len(get_game_urls) == 0:
        r.set(f'football_url_{rd_game}_{datetime.datetime.now().timestamp()}', f'{tmp_dict}')
        return 'Added data to DB'


def read_url_redis(sportbookname):
    pool = redis.ConnectionPool(host=redis_host, port=redis_port, db=0, decode_responses=True, password=redis_pass)
    r = redis.Redis(connection_pool=pool)

    res_list = []
    # get last data id
    if sportbookname == 'ALL':
        cursor, get_rd_counter = r.scan(match=f'football_url_*', count=10000)
        
    if sportbookname != 'ALL':
        cursor, get_rd_counter = r.scan(match=f'football_url_{sportbookname}*', count=10000)

    for grc in get_rd_counter:
        p_data = json.loads(r.get(grc))

        if str(p_data.get('status')) in ('0', '3'):
            url = p_data.get('data')
            sportsbook = p_data.get('sportsbook')
            stream_name = p_data.get('stream_name')
            res_list.append([grc, url, sportsbook, stream_name])

    return res_list


def update_url_redis(data, status):
    try:
        r_data = json.loads(data[1])
        pool = redis.ConnectionPool(host=redis_host, port=redis_port, db=0, decode_responses=True, password=redis_pass)
        r = redis.Redis(connection_pool=pool)

        tmp_dict = json.dumps({
            "stream_name": r_data.get('stream_name'),
            "sportsbook": r_data.get('sportsbook'),
            "data": r_data.get('data'),
            "status": status
        })

        r.set(data[0], f'{tmp_dict}')
        return 'OK'

    except Exception as err_upd:
        return f'{err_upd} on data:\n{data}'


def find_url_redis(url):
    try:
        pool = redis.ConnectionPool(host=redis_host, port=redis_port, db=0, decode_responses=True, password=redis_pass)
        r = redis.Redis(connection_pool=pool)

        cursor, get_rd_counter = r.scan(match=f'football_url_*', count=10000)

        for grc in get_rd_counter:
            p_data = json.loads(r.get(grc))
            if p_data.get('data') == url:
                result = [grc, r.get(grc)]
                return result

    except Exception as error:
        return error


def update_redis_status(url, status):
    find_url_res = find_url_redis(url)
    if find_url_res:
        upd_url_res = update_url_redis(find_url_res, status)
        result = f'Result of updating: {upd_url_res}'
    if not find_url_res:
        result = f"The game for updating hasn't been found in Redis DB"

    return result


def actions_on_page(driver, class_name: str):
    action = ActionChains(driver)
    try:
        element = driver.find_element(By.CLASS_NAME, class_name)
        action.move_to_element(element).perform()
    except:
        pass
    random_scroll_pixel = random.randint(100, 500)
    driver.execute_script(f"window.scrollBy(0, {random_scroll_pixel});")
    body = driver.find_element(By.XPATH, "//body")
    body.send_keys(Keys.CONTROL + 'a')
    body.send_keys(Keys.HOME)
    time.sleep(0.3)


def text_filter(text_in):
    if any(it in text_in.upper() for it in ['HOME TEAM', 'AWAY TEAM']):
        try:
            text_out = re.findall(r'HOME TEAM.+|AWAY TEAM.+', text_in.upper())[0].replace('HOME TEAM', 'Home Team').replace('AWAY TEAM', 'Away Team')
        except:
            text_out = text_in.upper().replace('HOME TEAM', 'Home Team').replace('AWAY TEAM', 'Away Team')
        return text_out.replace('  ', ' ')


    if any(it in text_in.upper() for it in ['OVER', 'UNDER']):
        try:
            text_out = re.findall(r'OVER.+|UNDER.+', text_in.upper())[0].replace('OVER', 'O').replace('UNDER', 'U')
        except:
            text_out = text_in.upper().replace('OVER', 'O').replace('UNDER', 'U')
        return text_out.replace('  ', ' ')

    if len(re.findall(r'O\d+|U\d+', text_in)) == 1:
        text_in = text_in.replace(' ', '')
        text_out = re.sub(r'(O|U)', r'\1 ', text_in)
        return text_out.replace('  ', ' ')

    if not any(it in text_in.upper() for it in ['OVER', 'UNDER', 'HOME TEAM', 'AWAY TEAM']):
        return text_in.replace('  ', ' ')
