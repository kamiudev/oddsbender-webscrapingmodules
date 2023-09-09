import pika, ssl, threading, time, functools
from os import environ
from configparser import ConfigParser
from utilities.logging import get_logger

# read config file
config_parser = ConfigParser()
config_parser.read('conf/main.conf')
module_conf = config_parser["MODULE"]

# get redis settings
amqp_host = environ.get('amqp_host', module_conf.get('amqp_host'))
amqp_password = environ.get('amqp_password', module_conf.get('amqp_password'))

#logger
logger = get_logger("queue_logger", "1", "INFO")

class QueueClient(object):
  def __init__(self, sportsbook=None) -> None:
    self.sportsbook = sportsbook
    parameters = pika.URLParameters(amqp_host)
    parameters.credentials = pika.PlainCredentials("user", amqp_password)
    self.connection = pika.BlockingConnection(parameters)
    self.channel = self.connection.channel()
    self.exchange_name = "game_urls"
  
  def exchange_declare(self, type="topic", passive=False, durable=True, auto_delete=False):
    return self.channel.exchange_declare(
      exchange = self.exchange_name,
      exchange_type = type,
      passive = passive,
      durable = durable,
      auto_delete = auto_delete

  )

  def queue_declare(self, name, durable=True):
    return self.channel.queue_declare(name, durable=durable, arguments={
      'x-message-ttl': 10800000
    })

  def queue_bind(self, sportsbook_name):
    return self.channel.queue_bind(
      exchange=self.exchange_name,
      queue=sportsbook_name,
      routing_key="*.%s.#" % sportsbook_name
    )
  
  def basic_publish(self, routing_key, body):
    return self.channel.basic_publish(
      exchange=self.exchange_name,
      routing_key=routing_key,
      body=body,
      properties=pika.BasicProperties(
        delivery_mode=pika.spec.PERSISTENT_DELIVERY_MODE
      )
    )
  
  def ack_message(self, ch, delivery_tag):
    if ch.is_open:
      logger.warning("Message ack'd")
      ch.basic_ack(delivery_tag)
    else:
      logger.warning("channel is closed when attempting to ack message")
      pass
  
  def nack_message(self, ch, deliver_tag):
    if ch.is_open:
      logger.error("Message nack'd %s", deliver_tag)
      ch.basic_nack(deliver_tag, False, True)
    else:
      logger.warning("channel is closed when attempting to nack message")
      pass

