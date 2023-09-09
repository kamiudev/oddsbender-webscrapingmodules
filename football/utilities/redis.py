import datetime
import json
import redis
import os
from os import environ
from configparser import ConfigParser
from utilities.logging import get_logger

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

logger = get_logger("redis_logger", "1", "INFO")

class RedisClient(object):
  def __init__(self) -> None:
    self.pool_stream = redis.ConnectionPool(host=redis_host, port=redis_port, db=1, decode_responses=True, password=redis_pass)
    self.pool_url = redis.ConnectionPool(host=redis_host, port=redis_port, db=0, decode_responses=True, password=redis_pass)
    self.pool_compare = redis.ConnectionPool(host=redis_host, port=redis_port, db=2, decode_responses=True, password=redis_pass)
    self.redis_stream = redis.Redis(connection_pool=self.pool_stream)
    self.redis_url = redis.Redis(connection_pool=self.pool_url)
    self.redis_compare = redis.Redis(connection_pool=self.pool_compare)

  def add_data_redis(self, stream_name, data_value):
    try:
      tmp_dict = json.dumps(data_value)
      self.redis_stream.xadd(stream_name, {"data_list": f"{tmp_dict}"})
      return "OK"
    except Exception as error:
      return error
  
  def add_url_redis(self, url, rd_game, stream_name, hostname="none"):
    res_list = []
    tmp_dict = json.dumps({
        "stream_name": stream_name,
        "sportsbook": rd_game,
        "data": url,
        "status": "0",
        "created_timestamp": datetime.datetime.now().strftime("%m/%d/%y-%H:%M:%S"),
    })

    cursor_d, get_game_urls = self.redis_url.scan(match=f'basketball_url_{rd_game}*', count=10000)

    # if data is present
    if len(get_game_urls) != 0:
        for i in get_game_urls:
            res_dct = json.loads(self.redis_url.get(i))
            # get all urls
            res_list.append(res_dct.get('data'))

        # check if new url in list redis db
        if url not in res_list:
            self.redis_url.set(f'basketball_url_{rd_game}_{datetime.datetime.now().timestamp()}', f'{tmp_dict}')
            return f'Added data to DB {url}'

        if url in res_list:
            return 'The record is present in the database'

    # no data in db, add data
    if len(get_game_urls) == 0:
        self.redis_url.set(f'basketball_url_{rd_game}_{datetime.datetime.now().timestamp()}', f'{tmp_dict}')
        return 'Added data to DB'

  def read_url_redis(self, sportsbook_name):
    res_list = []
    #get last data id
    if sportsbook_name == 'ALL':
      cursor, get_rd_counter = self.redis_url.scan(match=f'basketball_url_*', count=10000)
    if sportsbook_name != 'ALL':
      cursor, get_rd_counter = self.redis_url.scan(match=f'basketball_url_{sportsbook_name}*', count=10000)

    for grc in get_rd_counter:
      try:        
        p_data = json.loads(self.redis_url.get(grc))  
        
        if str(p_data.get('status')) in ('0', '3'):
            url = p_data.get('data')
            sportsbook = p_data.get('sportsbook')
            stream_name = p_data.get('stream_name')
            status = p_data.get("status")
            state = p_data.get("state")
            res_list.append([grc, url, sportsbook, stream_name, status, state])
      except TypeError as e:
        logger.error("Error parsing url data" + str(self.redis_url.get(grc)))
        pass
    
    return res_list

  def update_url_redis(self, data, status, extra_key=None):
    try:
      r_data = json.loads(data[1])


      tmp_dict = {
        "stream_name": r_data.get('stream_name'),
        "sportsbook": r_data.get('sportsbook'),
        "data": r_data.get('data'),
        "status": status,
        "created_timestamp" : r_data.get('created_timestamp'),
        "updated_timestamp": datetime.datetime.now().strftime("%m/%d/%y-%H:%M:%S"),
      }

      if extra_key:
        for key in extra_key:
          tmp_dict[key] = extra_key[key]
      
      self.redis_url.set(data[0], json.dumps(tmp_dict))
      return 'OK'

    except Exception as err_upd:
        return f'{err_upd} on data:\n{data}'

  def find_url_redis(self, url):
    try:
      cursor, get_rd_counter = self.redis_url.scan(match=f'basketball_url_*', count=10000)

      for grc in get_rd_counter:
        p_data = json.loads(self.redis_url.get(grc))
        if p_data.get('data') == url:
          result = [grc, self.redis_url.get(grc)]
          return result

    except Exception as error:
        return error
  
  def update_redis_status(self, url, status, extra_key = None):
    find_url_res = self.find_url_redis(url)
    if find_url_res:
        upd_url_res = self.update_url_redis(find_url_res, status, extra_key)
        result = f'Result of updating: {upd_url_res}'
    if not find_url_res:
        result = f"The game for updating hasn't been found in Redis DB"
    return result