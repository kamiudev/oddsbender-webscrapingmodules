import logging
import logging.config
import sys
import os

def get_logger(logger_name, DEBUG_FLAG, log_level):
    if str(DEBUG_FLAG) == "0":
        logging_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'conf', 'logging.conf')
        logging.config.fileConfig(logging_path)
        # logging.config.fileConfig('conf/logging.conf')
        logger = logging.getLogger(logger_name)
        logger.propagate = False
        level = logging.getLevelName(log_level)
        logger.setLevel(level)

    if str(DEBUG_FLAG) == "1":
        logging_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'conf', 'logging.conf')
        logging.config.fileConfig(logging_path)
        logger = logging.getLogger(logger_name)
        level = logging.getLevelName(log_level)
        logger.setLevel(level)
        formatter = logging.Formatter('%(asctime)s | %(levelname)s | %(message)s')

        if not os.path.exists('logs/'):
            os.makedirs('logs/')
    
        fh = logging.FileHandler(f'logs/{logger_name}.log')
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(formatter)

        fh_f = logging.StreamHandler(sys.stdout)
        fh_f.setLevel(logging.DEBUG)
        fh_f.setFormatter(formatter)

        logger.addHandler(fh)
        logger.addHandler(fh_f)

    return logger