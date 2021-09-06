import configparser

conf = configparser.ConfigParser()
conf.read('settings.ini')

use_dht22 = int(conf['DEVICE']['dht22'])
use_co2 = int(conf['DEVICE']['co2'])
use_pulseio_dht22 = conf.getboolean('DEVICE', 'use_pulseio_dht22')

gpio_dht22 = int(conf['GPIO_NUM']['dht22'])

out_file_name = conf['FILE']['out_file_name']