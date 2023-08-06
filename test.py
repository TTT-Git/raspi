import logging
from threading import Thread

# from controllers.webserver import start
from controllers.aircon_stream import aircon_stream
from controllers.streamdata import stream_temp_humid
# logging.basicConfig(level=logging.INFO, 
#     format='%(asctime)s %(threadName)s:%(levelname)s:%(name)s: %(message)s',
#     filename='logfile/logger.log')

logging.basicConfig(level=logging.INFO, 
    format='%(asctime)s %(threadName)s:%(levelname)s:%(name)s: %(message)s',
    )

if __name__ == "__main__":

    # serverThread = Thread(target=start)
    airconStrameThread = Thread(target=aircon_stream.stream_aircon_ctrl)
    # streamTempHumidThread = Thread(target=stream_temp_humid.stream_get_data())

    # serverThread.start()
    airconStrameThread.start()
    # streamTempHumidThread.start()

    # serverThread.join()
    airconStrameThread.join()
    # streamTempHumidThread.join()
