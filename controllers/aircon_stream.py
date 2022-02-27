import logging
from time import sleep

from models.ai_aircon_ctrl import Ai
import settings

logger = logging.getLogger(__name__)

class AirconStream(object):
    def __init__(self) -> None:
        self.ai = Ai()


    def stream_aircon_ctrl(self):
        logger.info(f'stream_aircon_ctrl run')
        
        while True:
            self.ai.ctrl_temp()
            sleep(settings.time_interval_aircon_ai_sec)


aircon_stream = AirconStream()