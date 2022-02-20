import logging
from threading import Thread

from controllers.webserver import start

# logging.basicConfig(level=logging.INFO, 
#     format='%(asctime)s %(threadName)s:%(levelname)s:%(name)s: %(message)s',
#     filename='logfile/logger.log')

logging.basicConfig(level=logging.INFO, 
    format='%(asctime)s %(threadName)s:%(levelname)s:%(name)s: %(message)s',
    )

if __name__ == "__main__":

    serverThread = Thread(target=start)

    serverThread.start()

    serverThread.join()
