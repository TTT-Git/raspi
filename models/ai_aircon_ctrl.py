import logging
import math

from pigpios.ir_ctrl import Aircon
from models.base import factory_temp_humid_class
import settings

logger = logging.getLogger(__name__)
h = logging.FileHandler(r'log/aircon_ai.log')
logger.addHandler(h)

class Ai(object):
    def __init__(self, target_temp:int=settings.target_temp) -> None:
        # 設定可能温度の設定
        self.heater_setting_lower_limit = settings.heater_setting_lower_limit
        self.heater_setting_upper_limit = settings.heater_setting_upper_limit
        self.cooler_setting_lower_limit = settings.cooler_setting_lower_limit
        self.cooler_setting_upper_limit = settings.cooler_setting_upper_limit
        # 温度の目標値と許容幅の設定
        self.target_temp = target_temp
        self.temp_upper_limit = self.target_temp + settings.temp_range
        self.temp_lower_limit = self.target_temp - settings.temp_range
        # 赤外線送信の設定
        self.aircon = Aircon(remote_raspi=settings.remote_ir, ssh_num=settings.remote_ir_raspi_ssh_num)
        # 使用する温度センサーの設定
        self.hostname = settings.use_temperature_sensor_hostname
        self.device_num = settings.use_temperature_sensor_device_num
        # 初期値
        self.heater_mode = settings.heater_mote_initial_setting
        self.heater_setting_temp = math.floor(self.target_temp) 
        self.cooler_setting_temp = math.ceil(self.target_temp) 

    def get_temp(self):
        temp_humid_cls = factory_temp_humid_class(self.hostname, self.device_num)
        temp_humid_data = temp_humid_cls.latest_record()
        self.temperature = temp_humid_data.value['temperature']
        self.data_time = temp_humid_data.value['time']

    def ctrl_temp(self):
        self.get_temp()
        gap_temp = abs(self.temperature - self.target_temp)
        if self.temperature > self.temp_upper_limit:
            """
            今の気温が、上限値より高い時、
            heater modeの時
            設定温度を下げる。設定可能温度下限にすでに設定してある場合は、冷房を設定可能温度上限でつける。
            cooler modeの時
            設定温度を下げる。設定可能温度下限にすでに設定してある場合は、そのまま。
            """
            if self.heater_mode:
                if self.heater_setting_temp != self.heater_setting_lower_limit:
                    self.heater_setting_temp = self.heater_setting_temp - math.ceil(gap_temp)
                    if self.heater_setting_temp < self.heater_setting_lower_limit:
                        self.heater_setting_temp = self.heater_setting_lower_limit
                    self.aircon.heater(self.heater_setting_temp)
                else: 
                    self.cooler_setting_temp = self.cooler_setting_upper_limit
                    self.aircon.cooler(self.cooler_setting_temp)
                    self.heater_mode = False
            else:
                if self.cooler_setting_temp != self.cooler_setting_lower_limit:
                    self.cooler_setting_temp = self.cooler_setting_temp - math.ceil(gap_temp)
                    if self.cooler_setting_temp < self.cooler_setting_lower_limit:
                        self.cooler_setting_temp = self.cooler_setting_lower_limit
                    self.aircon.cooler(self.cooler_setting_temp)
  
        elif self.temperature < self.temp_lower_limit:
            """
            今の気温が、下限値より低い時
            heater modeの時
            設定温度をあげる。設定可能温度上限にすでに設定してある場合は、そのまま。
            cooler modeの時
            設定温度をあげる。設定可能温度上限にすでに設定してある場合は、暖房を設定可能温度下限でつける
            """
            if not self.heater_mode:
                if self.cooler_setting_temp != self.cooler_setting_upper_limit:
                    self.cooler_setting_temp = self.cooler_setting_temp + math.ceil(gap_temp)
                    if self.cooler_setting_temp > self.cooler_setting_upper_limit:
                        self.cooler_setting_temp = self.cooler_setting_upper_limit
                    self.aircon.cooler(self.cooler_setting_temp)
                else:
                    self.heater_setting_temp = self.heater_setting_lower_limit
                    self.aircon.heater(self.heater_setting_temp)
                    self.heater_mode = True
            else:
                if self.heater_setting_temp != self.heater_setting_upper_limit:
                    self.heater_setting_temp = self.heater_setting_temp + math.ceil(gap_temp)
                    if self.heater_setting_temp > self.heater_setting_upper_limit:
                        self.heater_setting_temp = self.heater_setting_upper_limit
                    self.aircon.heater(self.heater_setting_temp)
        logger.info({
            'action': 'ctrl_temp',
            'status': 'nomal',
            'message': f'',
            'data': f'data_time: {self.data_time}, temp: {self.temperature}, heater_setting: {self.heater_setting_temp}, \
cooler_setting: {self.cooler_setting_temp} heater_mode: {self.heater_mode}' 
        })

