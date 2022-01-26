import csv
import datetime
import time

import settings
import temp_humid
from co2 import get_co2
from temp_humid import Tempreture_humid

temp_and_humids = {
    0: Tempreture_humid(device_num=0),
    1: Tempreture_humid(device_num=1)
}
record_temp_humid = {}
while True:
    for device_num in range(2):
        if temp_and_humids[device_num].use_device:
            record_temp_humid[device_num] = temp_and_humids[device_num].get_temp_humid() 
            if not record_temp_humid[device_num]:
                record_temp_humid[device_num] = {}
        else:
            record_temp_humid[device_num] = {}
    
    if settings.use_co2:
        record_co2 = get_co2.get_co2()
        if not record_co2:
            record_co2 = {}
    else:
        record_co2 = {}
    
    record = dict(**record_temp_humid[0], **record_temp_humid[1], **record_co2)
    record['datetime'] = datetime.datetime.now()
    print(record)
    

    with open(settings.out_file_name, "a") as f:
        writer = csv.DictWriter(f, list(record.keys()))
        writer.writerow(record)
        time.sleep(10)



