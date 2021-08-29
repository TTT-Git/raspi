import configparser
import os

conf = configparser.ConfigParser()
conf.read('settings.ini')

use_dht22 = int(conf['DEVICE']['dht22'])
use_co2 = int(conf['DEVICE']['co2'])

gpio_dht22 = int(conf['GPIO_NUM']['dht22'])
gpio_irreceiver = int(conf['GPIO_NUM']['irreceiver'])

