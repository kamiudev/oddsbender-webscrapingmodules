## make this script work for all sports, and change location to utils?

import datetime
import json
import os
from configparser import ConfigParser
from os import environ
from time import sleep
from multiprocessing import Pool
from functools import partial
from sqlalchemy import create_engine, URL
import warnings
import pandas as pd

import psycopg2
import redis

from utilities.logging import get_logger
from utilities.utils import str_to_timedelta
from utilities.redis import RedisClient

warnings.simplefilter(action='ignore', category=FutureWarning)

# Configuration setup
# config_parser.read('conf/main.conf')
config_parser = ConfigParser()
current_dir = os.path.dirname(os.path.abspath(__file__))
config_file_path = os.path.join(current_dir, 'conf', 'main.conf')
config_parser.read(config_file_path)
module_conf = config_parser["MODULE"]

# Initialize logging
DEBUG_FLAG = int(environ.get('football_db_data_loader_DEBUG_FLAG', 1))
log_level = environ.get('football_db_data_loader_log_level', 'WARNING')
logger = get_logger(environ.get('football_db_data_loader_get_logger', 'football_db_data_loader'), DEBUG_FLAG, log_level)

# Other variables
update_frequency = str_to_timedelta(environ.get('football_db_data_loader_update_frequency', module_conf.get('update_frequency')))
history_data_time_indicator = int(environ.get('football_db_data_loader_history_data_time_indicator', module_conf.get('history_data_time_indicator')))
existence_url_time = int(environ.get('existence_url_time', module_conf.get('existence_url_time')))

# Database configurations
main_database = environ.get('main_database', module_conf.get('main_database'))
db_config = {key: environ.get(key, module_conf.get(key)) for key in ['redis_pass', 'redis_host', 'redis_port', 'postgres_user', 'postgres_password', 'postgres_host', 'postgres_port', 'postgres_dbname']}
db_data_loader_props_table = environ.get('db_data_loader_props_table', module_conf.get('db_data_loader_props_table')) 
db_data_loader_popular_table = environ.get('db_data_loader_popular_table', module_conf.get('db_data_loader_popular_table')) 
db_data_loader_error_table = environ.get('db_data_loader_error_table', module_conf.get('db_data_loader_error_table')) 

#Database Initialization
engine = create_engine(URL.create("postgresql", username=db_config['postgres_user'], password=db_config['postgres_password'], host=db_config['postgres_host'], database=db_config['postgres_dbname']))

# Initialize Redis
# r = redis.Redis(host=db_config['redis_host'], port=db_config['redis_port'], db=0, decode_responses=True, password=None)
# r_d = redis.Redis(host=db_config['redis_host'], port=db_config['redis_port'], db=1, decode_responses=True, password=None)
r = redis.Redis(host=db_config['redis_host'], port=db_config['redis_port'], db=0, decode_responses=True, password=db_config['redis_pass'])
r_d = redis.Redis(host=db_config['redis_host'], port=db_config['redis_port'], db=1, decode_responses=True, password=db_config['redis_pass'])
redisClient = RedisClient()

# Helper functions
def get_db_connection():
    if main_database == 'postgres':
        return psycopg2.connect(user=db_config['postgres_user'], password=db_config['postgres_password'], host=db_config['postgres_host'], port=db_config['postgres_port'], dbname=db_config['postgres_dbname'])

def json_cleanup(json_data):
    json_data = json_data.replace("'", '"')
    return json_data + "}" if json_data[-1] != "}" and len(json_data) > 1 else json_data

# Main functionalities
def move_finished_games(connection):
    logger.info('Starting function to move finished games')

    cursor, get_rd_counter = r.scan(match=f'football_url_*', count=1000)

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
                            combined_clean_df.to_sql(db_data_loader_props_table, engine, schema='public', if_exists='append', index=False)

                        else:
                            logger.info('Loading to popular')
                            # upload to popular table
                            combined_clean_df.to_sql('popular_db_loader_tbl', engine, schema='public', if_exists='append', index=False)

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
                    cursor.execute(f'insert into {db_data_loader_error_table}(stream_name, time_stamp, json_data) VALUES (%s, %s, %s);', (data_to_save[0], data_ts, j_dump))
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
        # if 'football_' in str_name:
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
                        combined_clean_df.to_sql(db_data_loader_props_table, engine, if_exists='append', index=False)

                    else:
                        logger.info('Loading to populars')
                        # upload to popular table
                        combined_clean_df.to_sql(db_data_loader_popular_table, engine, if_exists='append', index=False)

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
                cursor.execute(f'insert into {db_data_loader_error_table}(stream_name, time_stamp, json_data) VALUES (%s, %s, %s);', (data_to_save[0], data_ts, j_dump))
                connection.commit()

                cursor.close()
                logger.info('Upload to error table successful')


def clean_unused_streams():
    logger.info('Starting function to clean unused streams')

    resp = r_d.scan(0, count=1000)
    for str_name in resp[1]:
        # if 'football_' in str_name:
        resp = r_d.xrange(str_name, min='-', max='+', count=None)
        if len(resp) == 0:
            r_d.delete(str_name)
            logger.info(f'Empty stream {str_name} deleted')

    cursor, get_rd_counter = r.scan(match=f'football_url_*', count=1000)
    for grc in get_rd_counter:
        game_insert_time = datetime.datetime.fromtimestamp(float(grc.split('_')[-1]))
        time_now = datetime.datetime.now()
        time_difference = int((time_now - game_insert_time).total_seconds())
        if time_difference > 7200:
            p_data = json.loads(r.get(grc))
            if p_data.get('status') == 1:
                r.delete(grc)
                logger.info(f"Url removed from redis: {p_data.get('data')}")


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
        temp_df['parsed_time_stamp'] = datetime.datetime.now().strftime("%m/%d/%Y %H:%M:%S")

    except:
        pass
        logger.warning(f'Error parsing {stream_name}')
        temp_df = pd.DataFrame([])
            
    return temp_df


def main():
    while True:
        logger.info('Start loop')

        with get_db_connection() as connection:
            move_finished_games(connection)
            move_games_by_time(connection)
            clean_unused_streams()

        logger.info(f'Loop ends, waiting {update_frequency.total_seconds()}')
        sleep(update_frequency.total_seconds())

    logger.warning("Stop Loading Data")

if __name__ == "__main__":
    main()
