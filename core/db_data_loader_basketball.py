import datetime
import json
from configparser import ConfigParser
from os import environ
from time import sleep

import psycopg2
import redis
import snowflake.connector

from utilities.logging import get_logger
from utilities.utils import str_to_timedelta
from utilities.redis import RedisClient

### NEW ###
from multiprocessing import Pool
import warnings
warnings.simplefilter(action='ignore', category=FutureWarning)

import pandas as pd
import re
from pandas.io.json import json_normalize
import numpy as np
import datetime as dt
from sqlalchemy import create_engine, URL
from functools import partial


# read config file
config_parser = ConfigParser()
config_parser.read('conf/main.conf')
module_conf = config_parser["MODULE"]

# init logging
logger_name = environ.get('basketball_db_data_loader_get_logger', 'basketball_db_data_loader')
# for local logs storage and stdout use DEBUG_FLAG = 1
DEBUG_FLAG = environ.get('basketball_db_data_loader_DEBUG_FLAG', 1)
log_level = environ.get('basketball_db_data_loader_log_level', 'WARNING')

logger = get_logger(logger_name, DEBUG_FLAG, log_level)

# other variables
update_frequency = str_to_timedelta(environ.get('basketball_db_data_loader_update_frequency', module_conf.get('update_frequency')))
history_data_time_indicator = int(environ.get('basketball_db_data_loader_history_data_time_indicator', module_conf.get('history_data_time_indicator')))
main_database = environ.get('main_database', module_conf.get('main_database'))
existence_url_time = int(environ.get('existence_url_time', module_conf.get('existence_url_time')))

# get redis settings
redis_pass = environ.get('redis_pass', module_conf.get('redis_pass'))
redis_host = environ.get('redis_host', module_conf.get('redis_host'))
redis_port = environ.get('redis_port', module_conf.get('redis_port'))

# get postgres settings
postgres_user = environ.get('postgres_user', module_conf.get('postgres_user'))
postgres_password = environ.get('postgres_password', module_conf.get('postgres_password'))
postgres_host = environ.get('postgres_host', module_conf.get('postgres_host'))
postgres_port = environ.get('postgres_port', module_conf.get('postgres_port'))
postgres_db_name = environ.get('postgres_dbname', module_conf.get('postgres_dbname'))

engine = create_engine(URL.create(
    "postgresql",
    username = postgres_user,
    password = postgres_password,
    host = postgres_host,
    database = postgres_db_name
))

# init redis
pool = redis.ConnectionPool(host=redis_host, port=redis_port, db=0, decode_responses=True, password=redis_pass)
r = redis.Redis(connection_pool=pool)

pool_d = redis.ConnectionPool(host=redis_host, port=redis_port, db=1, decode_responses=True, password=redis_pass)
r_d = redis.Redis(connection_pool=pool_d)

redisClient = RedisClient()


def init_db_connection():
    if main_database == 'postgres':
        connection = psycopg2.connect(
            user=postgres_user,
            password=postgres_password,
            host=postgres_host,
            port=postgres_port,
            dbname=postgres_db_name
        )

    return connection


def move_finished_games(connection):
    logger.info('Starting function to move finished games')

    cursor, get_rd_counter = r.scan(match=f'basketball_url_*', count=1000)

    # get finished games
    streams_list = []
    for grc in get_rd_counter:
        p_data = json.loads(r.get(grc))

        if p_data.get('status') in (2, 4):
            stream_name = json.loads(r.get(grc))
            streams_list.append([grc, stream_name.get('stream_name')])

    # get all data for finished games
    for str_n in streams_list:
        data_to_save = r_d.xread({str_n[1]: '0-0'})

        if len(data_to_save) != 0:
            data_to_save = data_to_save[0]

            logger.info(f'Parsing stream {str_n[1]}')

            combined = pd.DataFrame([])
            combined_clean_df = pd.DataFrame([])
            data_ts = []

            cursor = connection.cursor()
            data_counter = 0

            # convert json data into dataframe format
            for dts in data_to_save[1]:
                
                j_dump = dts[1].get('data_list')[1:-1]

                # logger.info(j_dump)

                df = pd.DataFrame(
                    {'stream_name': data_to_save[0],
                     'timestamp': dts[0],
                     'json': j_dump}
                    , index=[0]
                )
                combined = combined.append(df)
                data_ts = dts[0]

            combined = combined.reset_index(drop=True)

            if len(combined.index) > 0:

                try:
                    # split games into multiple rows
                    clean_df =(combined.set_index(['stream_name', 'timestamp'])
                    .apply(lambda x: x.str.split('}, ').explode())
                    .reset_index())  

                    clean_df['json'] = clean_df['json'].apply(json_cleanup)
                    # logger.info(j_dump)
                    clean_df2 = clean_df.reset_index(drop=True)
                        
                    data_length = range(len(clean_df2.index))

                    logger.info(f'Parallel Processing for {data_length}')

                    with Pool(20) as p:
                        combined_clean_df = pd.concat(p.map(partial(parse_json, clean_df2), data_length))

                    combined_clean_df = combined_clean_df.reset_index(drop=True)
                    combined_clean_df = combined_clean_df.drop_duplicates()

                    if len(combined_clean_df.index) > 0:
                        combined_clean_df['IS_TIMEOUT'] = 0

                        if combined_clean_df['IS_PROP'][0] == 1:
                            logger.info('Loading to props')
                            # upload to prop table        
                            combined_clean_df.to_sql('props_db_loader_historical_tbl', engine, schema='public', if_exists='append', index=False)

                        else:
                            logger.info('Loading to popular')
                            # upload to popular table
                            combined_clean_df.to_sql('popular_db_loader_historical_tbl', engine, schema='public', if_exists='append', index=False)

                        logger.info(f'Successfully loaded {str_n}')

                    # delete data after saving to db
                    r_d.delete(str_n[1])
                    logger.info(f'Data {str_n[1]} deleted')
                    r.delete(str_n[0])
                    logger.info(f'Url {str_n[0]} deleted')

                except Exception as e: 
                    logger.warning(e)
                    pass
                    logger.warning(f'Error parsing stream {stream_name}')

                    # upload to error table
                    cursor = connection.cursor()
                    cursor.execute('insert into parse_error_tbl(stream_name, time_stamp, json_data) VALUES (%s, %s, %s);', (data_to_save[0], data_ts, j_dump))
                    connection.commit()

                    cursor.close()
                    logger.info('Upload to error table successful')

        if len(data_to_save) == 0:
            r_d.delete(str_n[1])
            logger.info(f'Empty stream {str_n[1]} deleted')
            r.delete(str_n[0])
            logger.info(f'Empty url {str_n[0]} deleted')


def move_games_by_time(connection):
    logger.info('Starting function to move games by time')
    resp = r_d.scan(0, count=1000)

    time_cut = str(datetime.datetime.now().timestamp() - history_data_time_indicator).replace('.', '')[:13]

    for str_name in resp[1]:
        # if 'basketball_' in str_name:
        resp = r_d.xrange(str_name, min='-', max=time_cut, count=None)
        # resp = r_d.xrange(str_name, min='-', max='+', count=None)
        data_to_save = [str_name, resp]

        logger.info(str_name)
        logger.info(f'Parsing stream {str_name}')

        combined = pd.DataFrame([])
        combined_clean_df = pd.DataFrame([])
        data_ts = []

        cursor = connection.cursor()
        data_counter = 0

        # convert json data into dataframe format
        for dts in data_to_save[1]:
            
            j_dump = dts[1].get('data_list')[1:-1]

            df = pd.DataFrame(
                {'stream_name': data_to_save[0],
                 'timestamp': dts[0],
                 'json': j_dump}
                , index=[0]
            )
            combined = combined.append(df)
            data_ts = dts[0]

        combined = combined.reset_index(drop=True)

        if len(combined.index) > 0:

            try:
                # split games into multiple rows
                clean_df =(combined.set_index(['stream_name', 'timestamp'])
                .apply(lambda x: x.str.split('}, ').explode())
                .reset_index())  

                clean_df['json'] = clean_df['json'].apply(json_cleanup)
                clean_df2 = clean_df.reset_index(drop=True)

                clean_df2['json'] = clean_df2['json'].replace("'", "")
                clean_df2['json'] = clean_df2['json'].replace("\'", "")
                    
                data_length = range(len(clean_df2.index))
                logger.info(f'Parallel Processing for {data_length}')

                with Pool(20) as p:
                    combined_clean_df = pd.concat(p.map(partial(parse_json, clean_df2), data_length))

                combined_clean_df = combined_clean_df.reset_index(drop=True)
                combined_clean_df = combined_clean_df.drop_duplicates()

                if len(combined_clean_df.index) > 0:
                    combined_clean_df['IS_TIMEOUT'] = 0
                    # combined_clean_df['IS_TIMEOUT'] = combined_clean_df['IS_TIMEOUT'].replace("''", 0)

                    if combined_clean_df['IS_PROP'][0] == 1:
                        logger.info('Loading to props')
                        # upload to prop table        
                        combined_clean_df.to_sql('props_db_loader_historical_tbl', engine, if_exists='append', index=False)

                    else:
                        logger.info('Loading to populars')
                        # upload to popular table
                        combined_clean_df.to_sql('popular_db_loader_historical_tbl', engine, if_exists='append', index=False)

                    logger.info(f'Successfully loaded {str_name}')
                else:
                    logger.info(f'Empty dataframe for {str_name}')

                # delete data after saving to db
                for d_del in resp:
                    r_d.xdel(str_name, d_del[0])
                    logger.info(f'Deleted from DB {d_del[0]} from stream {str_name}')

            except Exception as e: 
                logger.warning(e)
                pass
                logger.warning(f'Error parsing stream {str_name}')
                
                # upload to error table
                cursor = connection.cursor()
                cursor.execute('insert into parse_error_tbl(stream_name, time_stamp, json_data) VALUES (%s, %s, %s);', (data_to_save[0], data_ts, j_dump))
                connection.commit()

                cursor.close()
                logger.info('Upload to error table successful')


def clean_unused_streams():
    logger.info('Starting function to clean unused streams')

    resp = r_d.scan(0, count=1000)
    for str_name in resp[1]:
        if 'basketball_' in str_name:
            resp = r_d.xrange(str_name, min='-', max='+', count=None)
            if len(resp) == 0:
                r_d.delete(str_name)
                logger.info(f'Empty stream {str_name} deleted')

    cursor, get_rd_counter = r.scan(match=f'basketball_url_*', count=1000)
    for grc in get_rd_counter:
        game_insert_time = datetime.datetime.fromtimestamp(float(grc.split('_')[-1]))
        time_now = datetime.datetime.now()
        time_difference = int((time_now - game_insert_time).total_seconds())
        if time_difference > 7200:
            p_data = json.loads(r.get(grc))
            if p_data.get('status') == 1:
                r.delete(grc)
                logger.info(f"Url removed from redis: {p_data.get('data')}")


def json_cleanup(json_data):
    
    if json_data[-1:] == "}" or len(json_data)<1:
        return json_data.replace("'", '"')
    else:
        return str(json_data.replace("'", '"')) + "}"


def parse_json(clean_df2, data_length):
    try:
    # logger.info(i)
        stream_name = clean_df2['stream_name'][data_length]
        stream_time_stamp = clean_df2['timestamp'][data_length]
        stream_json = clean_df2['json'][data_length]
        
        temp_df = json.loads(clean_df2['json'][data_length])
        temp_df = pd.json_normalize(temp_df)

        temp_df['stream_name'] = stream_name
        temp_df['stream_time_stamp'] = stream_time_stamp
        temp_df['parsed_time_stamp'] = dt.datetime.now().strftime("%m/%d/%Y %H:%M:%S")

    except:
        pass
        logger.warning(f'Error parsing {stream_name}')
        temp_df = pd.DataFrame([])
            
    return temp_df


def main():
    while True:
        logger.info('Start loop')

        connection = init_db_connection()

        move_finished_games(connection)
        move_games_by_time(connection)
        clean_unused_streams()

        connection.close()
        logger.info(f'Loop ends, waiting {update_frequency.total_seconds()}')
        sleep(update_frequency.total_seconds())
    logger.warning("Stop Loading Data")


if __name__ == "__main__":
    main()