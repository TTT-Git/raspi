import logging
import math

from pigpios.ir_ctl import Aircon
from models.base import factory_temp_humid_class
import settings

logger = logging.getLogger(__name__)

class Ai(object):
    def __init__(self, target_temp:int=settings.target_temp) -> None:
        self.target_temp = target_temp
        self.heater_setting_temp = self.target_temp
        self.temp_upper_limit = self.target_temp + 0.5
        self.temp_lower_limit = self.target_temp - 0.5
        self.aircon = Aircon()


    def get_temp(self):
        hostname = 'raspi4B'
        device_num = 0
        temp_humid_cls = factory_temp_humid_class(hostname, device_num)
        temp_humid_data = temp_humid_cls.latest_record()
        self.temperature = temp_humid_data.value['temperature']
        self.data_time = temp_humid_data.value['time']


    def ctrl_temp(self):
        self.get_temp()
        gap_temp = self.temperature - self.target_temp
        if self.temperature > self.temp_upper_limit:
            if self.heater_setting_temp != 16:
                self.heater_setting_temp = self.heater_setting_temp - math.ceil(gap_temp)
                self.aircon.heater(self.heater_setting_temp)
        elif self.temperature < self.temp_upper_limit:
            if self.heater_setting_temp != 28:
                self.heater_setting_temp = self.heater_setting_temp - math.ceil(gap_temp)
                self.aircon.heater(self.heater_setting_temp)
        logger.info({
            'action': 'ctrl_temp',
            'status': 'nomal',
            'message': f'',
            'data': f'data_time: {self.data_time}, temp: {self.temperature}, setting: {self.heater_setting_temp}'
        })

