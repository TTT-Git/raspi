from datetime import datetime
import logging
from time import sleep

from models import data_collector

import models
from models.base import factory_temp_humid_class
from models.base import TempHumid_Raspi0_1_0
from models.base import TempHumid_Raspi0_2_0
from models.base import TempHumid_Raspi0_2_1
from models.base import TempHumid_Raspi4B_1_0

logging.basicConfig(level=logging.INFO, 
    format='%(asctime)s %(threadName)s:%(levelname)s:%(name)s: %(message)s',
    )

logger = logging.getLogger(__name__)

base_list = [TempHumid_Raspi0_1_0, TempHumid_Raspi0_2_0, TempHumid_Raspi0_2_1, TempHumid_Raspi4B_1_0]

raspi0_1 = data_collector.Raspi(ssh_num=0, remote=True)
raspi0_2 = data_collector.Raspi(ssh_num=1, remote=True)
raspi4B = data_collector.Raspi(remote=False)


def write_sql(result_dict):
    for device_num in range(2):
        if result_dict[device_num]:
            time = datetime.fromisoformat(result_dict['datetime'])
            temperature=result_dict[device_num]['temperature_c']
            humidity=result_dict[device_num]['humidity']
            if 'co2' in result_dict[device_num].keys():
                co2_ppm=result_dict[device_num]['co2']
            else:
                co2_ppm=None
            meas_position = result_dict[device_num]['meas_position']
            hostname=result_dict['hostname']
            temp_humid_base = factory_temp_humid_class(hostname, device_num)
            temp_humid_base.create(
                time=time,
                temperature=temperature,
                humidity=humidity,
                co2_ppm=co2_ppm,
                meas_position=meas_position,
                hostname=hostname
                )



while True:
    raspi0_1_result_dict = raspi0_1.get_data()

    raspi0_2_result_dict = raspi0_2.get_data()

    raspi4B_result_dict = raspi4B.get_data()

    

    for result_dict in [raspi0_1_result_dict, raspi0_2_result_dict, raspi4B_result_dict]:
        if result_dict == {}:
            continue
        else:
            try:    
                write_sql(result_dict)
            except KeyError as e:
                logger.error({
                            'action': 'write_sql',
                            'status': 'error',
                            'message': f'error message {e}',
                            'data': f'result_dict: {result_dict}'
                        })

    for TempHumid in base_list:
        temp_humid_data = TempHumid.latest_record()
        print(temp_humid_data.value)


    sleep(10)


