import configparser
import os

conf = configparser.ConfigParser()
conf.read('settings.ini')

def use_or_not(int_value):
    if int_value == 1:
        return True
    elif int_value == 0:
        return False
    else:
        raise ValueError

use_dht22 = {
    0: use_or_not(int(conf['DEVICE']['dht22'])),
    1: use_or_not(int(conf['DEVICE']['dht22_2']))
}
use_co2 = use_or_not(int(conf['DEVICE']['co2']))

gpio_dht22 = {
    0: int(conf['GPIO_NUM']['dht22']),
    1: int(conf['GPIO_NUM']['dht22_2'])
}

gpio_irreceiver = int(conf['GPIO_NUM']['ir_receiver'])
gpio_irled = int(conf['GPIO_NUM']['ir_led'])

out_file_name = conf['FILE']['out_file_name']

ssh = {
    0:{
        'host' : str(conf['SSH']['host_0']),
        'user' : str(conf['SSH']['user_0']),
        'key_file' : str(conf['SSH']['key_file_0'])
    },
    1:{
        'host' : str(conf['SSH']['host_1']),
        'user' : str(conf['SSH']['user_1']),
        'key_file' : str(conf['SSH']['key_file_1'])
    }
}

system_name = str(conf['SYSTEM_INFO']['name'])