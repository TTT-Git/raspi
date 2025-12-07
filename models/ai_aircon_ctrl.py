from datetime import datetime
from datetime import timedelta
import logging
import math
import numpy as np


import pandas as pd

from pigpios.ir_ctrl import Aircon
from models.base import factory_temp_humid_class, AirconState
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
        # temp_humid_data = temp_humid_cls.latest_record()
        # self.temperature = temp_humid_data.value['temperature']
        # self.data_time = temp_humid_data.value['time']


        # 直近3分のデータを１次フィッティングし、3分後の温度を予測する。
        now = datetime.utcnow() + timedelta(hours=9)

        get_from = now - timedelta(minutes=3)

        temp_humid_datas = temp_humid_cls.get_data_after_time(get_from)
        temp_humid_data_list = [temp_humid_data.value for temp_humid_data in temp_humid_datas]
        df = pd.DataFrame(temp_humid_data_list)

        # 時間と温度のデータ
        time = (df['time'] - df.loc[0,'time']).apply(lambda t:t.seconds).values # ここに時間のデータを入力
        temp = df['temperature'].values # ここに温度のデータを入力

        # フィッティング
        #1次式
        coef_1 = np.polyfit(time,temp,1) #係数
        predict_time = 180 + (now - df.loc[0,'time']).seconds

        # 積分項
        get_from = now - timedelta(minutes=10)

        temp_humid_datas = temp_humid_cls.get_data_after_time(get_from)
        temp_humid_data_list = [temp_humid_data.value for temp_humid_data in temp_humid_datas]
        df2 = pd.DataFrame(temp_humid_data_list)
        corr = df2['temperature'].mean() - settings.target_temp
        corr = 0

        self.temperature = coef_1[0]*predict_time+ coef_1[1] + corr #フィッティング関数
        self.data_time = now
        print(f"time:{self.data_time}, predict_temp:{self.temperature}, corr:{corr} temp_now:{temp[-1]}" )
        print(df)
        print(time, temp)

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
                    self.aircon.heater(self.heater_setting_temp, fan='low')
                else: 
                    self.cooler_setting_temp = self.cooler_setting_upper_limit
                    self.aircon.cooler(temp=self.cooler_setting_temp, fan='low')
                    self.heater_mode = False
            else:
                if self.cooler_setting_temp != self.cooler_setting_lower_limit:
                    self.cooler_setting_temp = self.cooler_setting_temp - math.ceil(gap_temp)
                    if self.cooler_setting_temp < self.cooler_setting_lower_limit:
                        self.cooler_setting_temp = self.cooler_setting_lower_limit
                    if gap_temp > 2:
                        self.aircon.cooler(self.cooler_setting_temp, fan='auto')
                    else:
                        self.aircon.cooler(self.cooler_setting_temp, fan='low')
  
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
                    self.aircon.cooler(self.cooler_setting_temp, fan='low')
                else:
                    self.heater_setting_temp = self.heater_setting_lower_limit
                    self.aircon.heater(self.heater_setting_temp, fan='low')
                    self.heater_mode = True
            else:
                if self.heater_setting_temp != self.heater_setting_upper_limit:
                    self.heater_setting_temp = self.heater_setting_temp + math.ceil(gap_temp)
                    if self.heater_setting_temp > self.heater_setting_upper_limit:
                        self.heater_setting_temp = self.heater_setting_upper_limit
                    if gap_temp > 2:
                        self.aircon.heater(self.heater_setting_temp, fan='auto')
                    else:
                        self.aircon.heater(self.heater_setting_temp, fan='low')
        # エアコンの状態をデータベースに保存
        mode = 'heater' if self.heater_mode else 'cooler'
        setting_temp = self.heater_setting_temp if self.heater_mode else self.cooler_setting_temp
        AirconState.create(
            time=self.data_time,
            mode=mode,
            setting_temp=setting_temp,
            heater_setting_temp=self.heater_setting_temp,
            cooler_setting_temp=self.cooler_setting_temp
        )
        
        logger.info({
            'action': 'ctrl_temp',
            'status': 'nomal',
            'message': f'',
            'data': f'data_time: {self.data_time}, temp: {self.temperature}, heater_setting: {self.heater_setting_temp}, \
cooler_setting: {self.cooler_setting_temp} heater_mode: {self.heater_mode}' 
        })

