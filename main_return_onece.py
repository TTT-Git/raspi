import csv
import datetime
import json

import settings
import temp_humid
from co2 import get_co2
from temp_humid import Tempreture_humid

temp_and_humids = {
    0: Tempreture_humid(device_num=0),
    1: Tempreture_humid(device_num=1)
}

def main_func()-> dict:

    record_temp_humid = {}

    for device_num in range(2):
        if temp_and_humids[device_num].use_device:
            record_temp_humid[device_num] = temp_and_humids[device_num].get_temp_humid() 
            if not record_temp_humid[device_num]:
                record_temp_humid[device_num] = {}
            record_temp_humid[device_num]['meas_position'] = settings.meas_pos_dht[device_num]
        else:
            record_temp_humid[device_num] = {}

    if settings.use_co2:
        device_num = 0
        record_co2 = get_co2.get_co2()
        if record_co2:
            record_temp_humid[device_num].update(record_co2)

    record_temp_humid['datetime'] = str(datetime.datetime.now())
    if __name__ == '__main__':
        print(json.dumps(record_temp_humid))

    return record_temp_humid


    

if __name__ == '__main__':
    main_func()



