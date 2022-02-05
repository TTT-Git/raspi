from datetime import datetime
from this import d
from turtle import position
import pandas as pd
from time import sleep
from models import data_collector

import models
from models.base import TempHumid

raspi0_1 = data_collector.Raspi(ssh_num=0, remote=True)
raspi0_2 = data_collector.Raspi(ssh_num=1, remote=True)
raspi4B = data_collector.Raspi(remote=False)
# for i in range(10):


def write_sql(result_dict):
    for device_num in range(2):

        if retsult_dict[device_num]:
            time = datetime.fromisoformat(retsult_dict['datetime'])
            temperature=retsult_dict[device_num]['temperature_c']
            humidity=retsult_dict[device_num]['humidity']
            if 'co2' in retsult_dict[device_num].keys():
                co2_ppm=retsult_dict[device_num]['co2']
            meas_position = result_dict[device_num]['meas_position']
            hostname=retsult_dict['hostname']
            TempHumid.create(
                time=time,
                temperature=temperature,
                humidity=humidity,
                co2_ppm=co2_ppm,
                meas_position=meas_position,
                hostname=hostname
                )



while True:
    # raspi0_1_result_dict = raspi0_1.get_data()
    # raspi0_2_result_dict = raspi0_2.get_data()
    raspi4B_result_dict = raspi4B.get_data()

    # print(raspi0_1_result_dict.keys())
    # print(raspi0_2_result_dict.keys())
    # print(raspi4B_result_dict)
    #     df = pd.DataFrame([raspi0_1_result_dict, raspi0_2_result_dict, raspi4B_result_dict])
    #     print(df)
    #     sleep(2)
    

    for retsult_dict in [raspi4B_result_dict]:
        write_sql(retsult_dict)
        # time = datetime.fromisoformat(retsult_dict['datetime'])
        # temperature=retsult_dict['temperature_c_0']
        # humidity=retsult_dict['humidity_0']
        # try:
        #     co2_ppm=retsult_dict['co2']
        # except KeyError:
        #     co2_ppm=None
        # hostname=retsult_dict['hostname']
        # TempHumid.create(
        #     time=time,
        #     temperature=temperature,
        #     humidity=humidity,
        #     co2_ppm=co2_ppm,
        #     hostname=hostname
        #     )
    temp_humid_datas = TempHumid.get_all_candles()
    for temp_humid_data in temp_humid_datas:
        print(temp_humid_data.value)

    sleep(10)


