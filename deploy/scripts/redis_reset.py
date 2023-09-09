from os import environ
import time
from configparser import ConfigParser
from random import randrange
import redis
import json


# other variables
redis_pass = environ.get('redis_pass', 'redispass')
redis_host = environ.get('redis_host', 'localhost')
redis_port = environ.get('redis_port', '6379')

print("started working")

def main():
    try:
        url_pool = redis.ConnectionPool(host=redis_host, port=redis_port, db=0, decode_responses=True, password=redis_pass)
        redis_url = redis.Redis(connection_pool=url_pool)
        
        streams_pool = redis.ConnectionPool(host=redis_host, port=redis_port, db=1, decode_responses=True, password=redis_pass)
        redis_streams = redis.Redis(connection_pool=streams_pool)

        #get games in progress
        print("Getting list of URLs")
        cursor, get_rd_counter = redis_url.scan(match=f'*_url_sugar*', count=1000)
        print("done getting data")       
        streams_list = []
        for grc in get_rd_counter:
            p_data = json.loads(redis_url.get(grc))
            
            if(p_data.get('status') in [1,2] ):
                stream_name = json.loads(redis_url.get(grc))
                streams_list.append([grc, stream_name.get('stream_name'), redis_url.get(grc)])

        # check if stream is in props
        print("Stream length = " + str(len(streams_list)))
        counter = 0
        for stream in streams_list:
            # try:
            data = redis_streams.xread({stream[1]: '0-0'})
            r_data = json.loads(stream[2])
            tmp_dict = json.dumps({
                "stream_name": r_data.get('stream_name'),
                "sportsbook": r_data.get('sportsbook'),
                "data": r_data.get('data'),
                "status": "0",
                "cleanup": "true",
                "state": "None"
            })
            redis_url.set(stream[0],f'{tmp_dict}')
            counter = counter + 1
    
        print(f"Updated {str(counter)} out of {str(len(streams_list))}")

    except KeyboardInterrupt:
        print("Keyboard Interrupt. Quit the driver!")
        print(f'Module stopped working')

    except Exception as e:
        print(f"Exception in main scraping cycle. {e}")

            
    print(f'Module stopped working')


if __name__ == "__main__":
    main()
