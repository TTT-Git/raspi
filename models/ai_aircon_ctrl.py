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
        self.heater_setting_lower_limit = 20
        self.heater_setting_upper_limit = 28
        self.cooler_setting_lower_limit = 23
        self.cooler_setting_upper_limit = 31
        self.target_temp = target_temp
        self.heater_setting_temp = math.floor(self.target_temp) 
        self.cooler_setting_temp = math.ceil(self.target_temp) 
        self.temp_upper_limit = self.target_temp + 0.5
        self.temp_lower_limit = self.target_temp - 0.5
        self.aircon = Aircon()
        self.heater_mode = False
        
        # self.aircon.on()
        # self.setting_aircon_on = True
        

    def get_temp(self):
        hostname = 'raspi4B'
        device_num = 0
        temp_humid_cls = factory_temp_humid_class(hostname, device_num)
        temp_humid_data = temp_humid_cls.latest_record()
        self.temperature = temp_humid_data.value['temperature']
        self.data_time = temp_humid_data.value['time']


    def ctrl_temp(self):
        self.get_temp()
        gap_temp = abs(self.temperature - self.target_temp)
        if self.temperature > self.temp_upper_limit:
            """
            今の気温が、上限値より高い時、
            設定温度を下げる。１６度にすでに設定してある場合は、エアコンをOFFにする。
            エアコンOFFでも温度が上がったら、冷房をつけて下げていく。
            """
            if self.heater_mode:
                if self.heater_setting_temp != self.heater_setting_lower_limit:
                    self.heater_setting_temp = self.heater_setting_temp - math.ceil(gap_temp)
                    if self.heater_setting_temp < self.heater_setting_lower_limit:
                        self.heater_setting_temp = self.heater_setting_lower_limit
                    self.aircon.heater(self.heater_setting_temp)
                else: 
                    # if self.setting_aircon_on:
                    #     self.aircon.off()
                    #     self.setting_aircon_on = False
                    # else:
                    self.cooler_setting_temp = self.cooler_setting_upper_limit
                    # self.aircon.on()
                    # self.setting_aircon_on = True
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
            エアコンがオフの場合はONにする
            設定温度をあげる。28度にすでに設定してある場合は、設定不要
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


            # if not self.setting_aircon_on:
            #     self.aircon.on()
            #     self.setting_aircon_on = True
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

