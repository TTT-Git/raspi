import configparser
from distutils.util import strtobool
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
codes_aircon_file = conf['FILE']['codes_aircon_file']
remote_aircon_ir_file = conf['FILE']['remote_aircon_ir_file']
main_dir = conf['FILE']['main_dir']
main_dir_host0 = conf['FILE']['main_dir_host0']
main_dir_host1 = conf['FILE']['main_dir_host1']

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

db_name = conf['DB']['name']
db_driver = conf['DB']['driver']

meas_pos_dht = {}
if use_dht22[0]:
    meas_pos_dht[0] = str(conf['MEAS_POSITION']['dht22'])
if use_dht22[1]:
    meas_pos_dht[1] = str(conf['MEAS_POSITION']['dht22_2'])

web_port = int(conf['WEB']['port'])

time_interval_temp_humid_sec = int(conf['DATA_COLLECTION']['time_interval_temp_humid_sec'])

time_interval_aircon_ai_sec = int(conf['AIRCON_AI']['time_interval_aircon_ai_sec'])
target_temp = float(conf['AIRCON_AI']['target_temp'])
temp_range = float(conf['AIRCON_AI']['temp_range'])
remote_ir = bool(strtobool(conf['AIRCON_AI']['remote_ir']))
remote_ir_raspi_ssh_num = int(conf['AIRCON_AI']['remote_ir_raspi_ssh_num'])
heater_setting_lower_limit = int(conf['AIRCON_AI']['heater_setting_lower_limit'])
heater_setting_upper_limit = int(conf['AIRCON_AI']['heater_setting_upper_limit'])
cooler_setting_lower_limit = int(conf['AIRCON_AI']['cooler_setting_lower_limit'])
cooler_setting_upper_limit = int(conf['AIRCON_AI']['cooler_setting_upper_limit'])
heater_mote_initial_setting = bool(strtobool(conf['AIRCON_AI']['heater_mote_initial_setting']))
use_temperature_sensor_hostname = conf['AIRCON_AI']['use_temperature_sensor_hostname']
use_temperature_sensor_device_num = int(conf['AIRCON_AI']['use_temperature_sensor_device_num'])