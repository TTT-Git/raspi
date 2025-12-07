import logging
from time import sleep

from models.ai_aircon_ctrl import Ai
import settings

logger = logging.getLogger(__name__)

class AirconStream(object):
    def __init__(self) -> None:
        self.stop = False
        self.ai = Ai()
        
    def stream_aircon_ctrl(self):
        logger.info(f'stream_aircon_ctrl run')
        
        while not self.stop:
            self.ai.ctrl_temp()
            sleep(settings.time_interval_aircon_ai_sec)
    
    def stop_aircon(self):
        self.stop = True
        print("Sending stop signal to the air conditioner...")
        self.ai.aircon.off()


aircon_stream = AirconStream()

# ユーザーからの入力を待つ関数
def wait_for_stop_command(aircon_stream):
    while True:
        user_input = input("Enter 'stop' to stop the air conditioner: ")
        if user_input.lower() == 'stop':
            aircon_stream.stop_aircon()
            break