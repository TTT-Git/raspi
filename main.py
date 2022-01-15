import csv
import datetime
import time

import settings
import temp_humid
from co2 import get_co2
from temp_humid import Tempreture_humid


while True:
    if settings.use_dht22:
        t_and_h = Tempreture_humid(device_num=0)
        record_temp_humid = t_and_h.get_temp_humid() 
        if not record_temp_humid:
            record_temp_humid = {}
    else:
        record_temp_humid = {}
    
    if settings.use_dht22_2:
        t_and_h_2 = Tempreture_humid(device_num=1)
        record_temp_humid_2 = t_and_h_2.get_temp_humid() 
        if not record_temp_humid_2:
            record_temp_humid_2 = {}
    else:
        record_temp_humid_2 = {}
    
    if settings.use_co2:
        record_co2 = get_co2.get_co2()
        if not record_co2:
            record_co2 = {}
    else:
        record_co2 = {}
    
    record = dict(**record_temp_humid, **record_temp_humid_2 **record_co2)
    record['datetime'] = datetime.datetime.now()
    print(record)
    

    with open(settings.out_file_name, "a") as f:
        writer = csv.DictWriter(f, list(record.keys()))
        writer.writerow(record)
        time.sleep(10)



