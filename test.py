import logging

from controllers.webserver import start
# logging.basicConfig(level=logging.INFO, 
#     format='%(asctime)s %(threadName)s:%(levelname)s:%(name)s: %(message)s',
#     filename='logfile/logger.log')

logging.basicConfig(level=logging.INFO, 
    format='%(asctime)s %(threadName)s:%(levelname)s:%(name)s: %(message)s',
    )

if __name__ == "__main__":
    logging.getLogger(__name__).info(
        'Web server starting with aircon control stopped; use the browser to start it'
    )
    start()
