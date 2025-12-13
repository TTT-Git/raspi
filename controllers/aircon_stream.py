import logging
from time import sleep
from threading import Thread

from models.ai_aircon_ctrl import Ai
import settings

logger = logging.getLogger(__name__)

class AirconStream(object):
    def __init__(self) -> None:
        self.stop = False
        self.ai = Ai()
        self.thread = None
        self.is_running = False
        
    def stream_aircon_ctrl(self):
        logger.info(f'stream_aircon_ctrl run')
        self.is_running = True
        
        while not self.stop:
            self.ai.ctrl_temp()
            sleep(settings.time_interval_aircon_ai_sec)
        
        self.is_running = False
        logger.info(f'stream_aircon_ctrl stopped')
    
    def stop_aircon(self):
        """エアコンをオフにして、制御ループを停止する"""
        self.stop = True
        self.is_running = False  # 即座に停止状態にする
        logger.info("Sending stop signal to the air conditioner...")
        self.ai.aircon.off()
    
    def start_aircon(self):
        """エアコン制御を開始する（新しいスレッドで実行）"""
        # 既に実行中で、かつ停止フラグが立っていない場合はエラー
        if self.is_running and not self.stop:
            logger.warning("Aircon control is already running")
            return False
        
        # 以前のスレッドが残っている場合は待機
        if self.thread and self.thread.is_alive():
            logger.info("Waiting for previous thread to finish...")
            # スレッドが終了するまで待機（最大5秒）
            self.thread.join(timeout=5.0)
        
        self.stop = False
        self.thread = Thread(target=self.stream_aircon_ctrl)
        self.thread.daemon = True
        self.thread.start()
        logger.info("Aircon control started")
        return True
    
    def get_status(self):
        """エアコン制御の状態を返す"""
        # stopがTrueの場合は、is_runningに関係なく停止中と見なす
        is_running = self.is_running and not self.stop
        return {
            'is_running': is_running,
            'stop': self.stop
        }


aircon_stream = AirconStream()

# ユーザーからの入力を待つ関数
def wait_for_stop_command(aircon_stream):
    while True:
        user_input = input("Enter 'stop' to stop the air conditioner: ")
        if user_input.lower() == 'stop':
            aircon_stream.stop_aircon()
            break