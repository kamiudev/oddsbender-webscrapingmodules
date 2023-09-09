from configparser import ConfigParser
from os import environ
import asyncio
import websockets
import sys
import pika
import time
from utilities.logging import get_logger
from utilities.queue import QueueClient
from utilities.redis import RedisClient

# read config file
config_parser = ConfigParser()
config_parser.read('conf/main.conf')
module_conf = config_parser["MODULE"]

# init logging
logger_name = environ.get('basketball_master_get_logger', 'basketball_master')

# for local logs storage and stdout use DEBUG_FLAG = 1
DEBUG_FLAG = environ.get('PROP_LOG_DEBUG_FLAG', 1)
log_level = environ.get('basketball_master_log_level', 'INFO')

logger = get_logger(logger_name, DEBUG_FLAG, log_level)

logger.warning(f'Module started working with parameters:\n{logger_name=}\n{log_level=}\n{DEBUG_FLAG=}')

redisClient = RedisClient()

def main():
    logger.warning("start main loop")
    scheduled_games = []
    while True:
        found_games = redisClient.read_url_redis('ALL')

        if found_games:
            queue = QueueClient()
            for game in found_games:
                logger.warning(game)
                url = game[1]
                sport = game[0].split('_')[0]
                sport_book = game [2]
                redis_key = game[0]
                state = game[5]
                routing_key = "%s.%s.%s" % (sport, sport_book, redis_key)
                if state not in ["scraping", "scheduled"]:
                  queue.exchange_declare()
                  queue.queue_declare(sport_book)
                  queue.queue_bind(sport_book)
                  queue.basic_publish(routing_key, url)
                  logger.warning("Added to queue: %r:%r" % (routing_key, url))
                  redisClient.update_redis_status(url, 1, {"state": "scheduled"})
                else:
                  logger.warning("Pass %s", url)

            queue.connection.close()
            time.sleep(10)

if __name__ == '__main__':
    try:
      main()
    except KeyboardInterrupt:
      sys.exit(0)