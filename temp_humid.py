
import sys
import time

import adafruit_dht
import board

from gpio import gpio
import settings

try:
    dhtDevice = adafruit_dht.DHT22(gpio[settings.gpio_dht22], use_pulseio=True)
except NameError as e:
    print(e, 'change use_pulseio True -> False')
    dhtDevice = adafruit_dht.DHT22(gpio[settings.gpio_dht22], use_pulseio=False)
def get_temp_humid(limit=15):


    for _ in range(limit):
        try:
            # Print the values to the serial port
            temperature_c = dhtDevice.temperature
            humidity = dhtDevice.humidity
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
            dhtDevice.exit()
            raise error

        time.sleep(1.0)
    return False
    

if __name__ == '__main__':
    print(get_temp_humid())