
import sys
import time

import adafruit_dht
import board

from gpio import gpio
import settings

class Tempreture_humid(object):
    def __init__(self,device_num=0) -> None:
        self.device_num = device_num
        self.use_device = settings.use_dht22[self.device_num]
        if self.use_device:    
            try:
                self.dhtDevice = adafruit_dht.DHT22(gpio[settings.gpio_dht22[self.device_num]], use_pulseio=True)
            except NameError as e:
                print(e, 'change use_pulseio True -> False')
                self.dhtDevice = adafruit_dht.DHT22(gpio[settings.gpio_dht22[self.device_num]], use_pulseio=False)


    def get_temp_humid(self, limit=15, wait_time_sec=1.0):
        for _ in range(limit):
            try:
                # Print the values to the serial port
                temperature_c = self.dhtDevice.temperature
                humidity = self.dhtDevice.humidity
                if type(temperature_c) == float and type(humidity) == float: 
                    record = {
                        "temperature_c": round(temperature_c,2),
                        'humidity': round(humidity, 1)
                    }
                    return record

            except RuntimeError as error:
                # Errors happen fairly often, DHT's are hard to read, just keep going
                print(sys._getframe().f_code.co_name, error.args[0])
                time.sleep(1.0)
                continue
            except Exception as error:
                self.dhtDevice.exit()
                raise error

            time.sleep(wait_time_sec)
        return False
    

if __name__ == '__main__':
    t_and_h = Tempreture_humid(0)
    print(t_and_h.get_temp_humid())