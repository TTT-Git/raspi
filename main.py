import csv
import datetime
import time

import settings
import temp_humid
from co2 import get_co2



while True:
    if settings.use_dht22 == 1:
        record_temp_humid = temp_humid.get_temp_humid() 
        if not record_temp_humid:
            record_temp_humid = {}
    else:
        record_temp_humid = {}
    
    if settings.use_co2 == 1:
        record_co2 = get_co2.get_co2()
        if not record_co2:
            record_co2 = {}
    else:
        record_co2 = {}
    
    record = dict(**record_temp_humid, **record_co2)
    record['datetime'] = datetime.datetime.now()
    print(record)
    

    with open(settings.out_file_name, "a") as f:
        writer = csv.DictWriter(f, list(record.keys()))
        writer.writerow(record)
        time.sleep(10)



