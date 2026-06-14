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
        # モード切り替え待機状態の管理
        self.mode_switch_pending = False  # モード切り替え待機中かどうか
        self.prev_mode = 'heater' if self.heater_mode else 'cooler'  # 前回のモード
        self.current_temp = None  # 現在の実測温度（予測温度と比較用） 

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

        # データが無い場合は処理を中断（しばらく待って再実行する上位ループに任せる）
        if df.empty:
            logger.warning({'action':'get_temp','status':'no_data','message':'no temp data available, skipping control'})
            self.temperature = None
            self.current_temp = None
            self.data_time = now
            return

        # 時間と温度のデータ
        time = (df['time'] - df.loc[0,'time']).apply(lambda t:t.seconds).values # ここに時間のデータを入力
        temp = df['temperature'].values # ここに温度のデータを入力

        # フィッティング
        #1次式
        if len(temp) == 1:
            # データが1点しかない場合は定数近似を使う
            coef_1 = np.array([0.0, float(temp[0])])
        else:
            coef_1 = np.polyfit(time,temp,1) #係数
        predict_time = 180 + (now - df.loc[0,'time']).seconds

        # 積分項
        get_from = now - timedelta(minutes=10)

        temp_humid_datas = temp_humid_cls.get_data_after_time(get_from)
        temp_humid_data_list = [temp_humid_data.value for temp_humid_data in temp_humid_datas]
        df2 = pd.DataFrame(temp_humid_data_list)
        corr = df2['temperature'].mean() - settings.target_temp
        corr = 0

        self.temperature = coef_1[0]*predict_time+ coef_1[1] + corr #フィッティング関数（3分後の予測温度）
        self.current_temp = temp[-1]  # 現在の実測温度（最新のデータ）
        self.data_time = now
        print(f"time:{self.data_time}, predict_temp:{self.temperature}, corr:{corr} temp_now:{self.current_temp}" )
        print(df)
        print(time, temp)

    def ctrl_temp(self):
        self.get_temp()
        # get_tempがデータ不足で終了した場合は処理を行わず待機する
        if self.temperature is None:
            logger.warning({'action': 'ctrl_temp', 'status': 'no_data', 'message': 'No temperature data available - skipping control'})
            return
        gap_temp = abs(self.temperature - self.target_temp)
        current_mode = 'heater' if self.heater_mode else 'cooler'
        
        # モード切り替え待機中の処理（改善点6: モード切り替え時の制御）
        if self.mode_switch_pending:
            # 既存の予測システム（self.temperatureは3分後の予測温度）を使って判断
            
            if self.prev_mode == 'heater':
                # 暖房→冷房の切り替え待機中
                if self.temperature > self.temp_upper_limit:
                    # 予測温度が上限を超えそう → 冷房に切り替え
                    logger.info({
                        'action': 'ctrl_temp',
                        'status': 'mode_switch',
                        'message': f'暖房→冷房: 予測温度が上限を超えそう（予測: {self.temperature:.2f}度）のため冷房に切り替え',
                        'data': f'predict_temp: {self.temperature}, current_temp: {self.current_temp}'
                    })
                    self.cooler_setting_temp = self.cooler_setting_upper_limit
                    self.aircon.cooler(temp=self.cooler_setting_temp, fan='low')
                    self.heater_mode = False
                    self.mode_switch_pending = False
                    self.prev_mode = 'cooler'
                elif self.temperature < self.temp_lower_limit:
                    # 予測温度が下限を下回りそう → 暖房に切り替え
                    logger.info({
                        'action': 'ctrl_temp',
                        'status': 'mode_switch',
                        'message': f'暖房→暖房: 予測温度が下限を下回りそう（予測: {self.temperature:.2f}度）のため暖房を継続',
                        'data': f'predict_temp: {self.temperature}, current_temp: {self.current_temp}'
                    })
                    self.heater_setting_temp = self.heater_setting_lower_limit
                    self.aircon.heater(self.heater_setting_temp, fan='low')
                    self.heater_mode = True
                    self.mode_switch_pending = False
                    self.prev_mode = 'heater'
                else:
                    # 予測温度が範囲内でキープされそう → OFFを継続
                    logger.info({
                        'action': 'ctrl_temp',
                        'status': 'mode_switch',
                        'message': f'暖房→OFF継続: 予測温度が安定（予測: {self.temperature:.2f}度）',
                        'data': f'predict_temp: {self.temperature}, current_temp: {self.current_temp}'
                    })
                    self.aircon.heater_off()
                    # オフ状態をデータベースに保存
                    AirconState.create(
                        time=self.data_time,
                        mode='off',
                        setting_temp=None,
                        heater_setting_temp=self.heater_setting_temp,
                        cooler_setting_temp=self.cooler_setting_temp
                    )
                    return
            
            elif self.prev_mode == 'cooler':
                # 冷房→暖房の切り替え待機中
                if self.temperature < self.temp_lower_limit:
                    # 予測温度が下限を下回りそう → 暖房に切り替え
                    logger.info({
                        'action': 'ctrl_temp',
                        'status': 'mode_switch',
                        'message': f'冷房→暖房: 予測温度が下限を下回りそう（予測: {self.temperature:.2f}度）のため暖房に切り替え',
                        'data': f'predict_temp: {self.temperature}, current_temp: {self.current_temp}'
                    })
                    self.heater_setting_temp = self.heater_setting_lower_limit
                    self.aircon.heater(self.heater_setting_temp, fan='low')
                    self.heater_mode = True
                    self.mode_switch_pending = False
                    self.prev_mode = 'heater'
                elif self.temperature > self.temp_upper_limit:
                    # 予測温度が上限を超えそう → 冷房に切り替え
                    logger.info({
                        'action': 'ctrl_temp',
                        'status': 'mode_switch',
                        'message': f'冷房→冷房: 予測温度が上限を超えそう（予測: {self.temperature:.2f}度）のため冷房を継続',
                        'data': f'predict_temp: {self.temperature}, current_temp: {self.current_temp}'
                    })
                    self.cooler_setting_temp = self.cooler_setting_upper_limit
                    self.aircon.cooler(temp=self.cooler_setting_temp, fan='low')
                    self.heater_mode = False
                    self.mode_switch_pending = False
                    self.prev_mode = 'cooler'
                else:
                    # 予測温度が範囲内でキープされそう → OFFを継続
                    logger.info({
                        'action': 'ctrl_temp',
                        'status': 'mode_switch',
                        'message': f'冷房→OFF継続: 予測温度が安定（予測: {self.temperature:.2f}度）',
                        'data': f'predict_temp: {self.temperature}, current_temp: {self.current_temp}'
                    })
                    self.aircon.cooler_off()
                    # オフ状態をデータベースに保存
                    AirconState.create(
                        time=self.data_time,
                        mode='off',
                        setting_temp=None,
                        heater_setting_temp=self.heater_setting_temp,
                        cooler_setting_temp=self.cooler_setting_temp
                    )
                    return
        
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
                    self.prev_mode = 'heater'
                else: 
                    # 暖房→冷房の切り替えが必要な場合、一度オフにして待機状態にする
                    logger.info({
                        'action': 'ctrl_temp',
                        'status': 'mode_switch_init',
                        'message': '暖房→冷房切り替え: 一度オフにして温度変化を観察',
                        'data': f'temp: {self.temperature}, heater_setting: {self.heater_setting_temp}'
                    })
                    self.aircon.off()
                    self.mode_switch_pending = True
                    self.prev_mode = 'heater'
                    # オフ状態をデータベースに保存
                    AirconState.create(
                        time=self.data_time,
                        mode='off',
                        setting_temp=None,
                        heater_setting_temp=self.heater_setting_temp,
                        cooler_setting_temp=self.cooler_setting_temp
                    )
                    return
            else:
                if self.cooler_setting_temp != self.cooler_setting_lower_limit:
                    self.cooler_setting_temp = self.cooler_setting_temp - math.ceil(gap_temp)
                    if self.cooler_setting_temp < self.cooler_setting_lower_limit:
                        self.cooler_setting_temp = self.cooler_setting_lower_limit
                    if gap_temp > 2:
                        self.aircon.cooler(self.cooler_setting_temp, fan='auto')
                    else:
                        self.aircon.cooler(self.cooler_setting_temp, fan='low')
                    self.prev_mode = 'cooler'
  
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
                    self.prev_mode = 'cooler'
                else:
                    # 冷房→暖房の切り替えが必要な場合、一度オフにして待機状態にする
                    logger.info({
                        'action': 'ctrl_temp',
                        'status': 'mode_switch_init',
                        'message': '冷房→暖房切り替え: 一度オフにして温度変化を観察',
                        'data': f'temp: {self.temperature}, cooler_setting: {self.cooler_setting_temp}'
                    })
                    self.aircon.off()
                    self.mode_switch_pending = True
                    self.prev_mode = 'cooler'
                    # オフ状態をデータベースに保存
                    AirconState.create(
                        time=self.data_time,
                        mode='off',
                        setting_temp=None,
                        heater_setting_temp=self.heater_setting_temp,
                        cooler_setting_temp=self.cooler_setting_temp
                    )
                    return
            else:
                if self.heater_setting_temp != self.heater_setting_upper_limit:
                    self.heater_setting_temp = self.heater_setting_temp + math.ceil(gap_temp)
                    if self.heater_setting_temp > self.heater_setting_upper_limit:
                        self.heater_setting_temp = self.heater_setting_upper_limit
                    if gap_temp > 2:
                        self.aircon.heater(self.heater_setting_temp, fan='auto')
                    else:
                        self.aircon.heater(self.heater_setting_temp, fan='low')
                    self.prev_mode = 'heater'
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

