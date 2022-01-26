from time import sleep
from models import data_collector

raspi0_1 = data_collector.Raspi(ssh_num=0, remote=True)
raspi0_2 = data_collector.Raspi(ssh_num=1, remote=True)
raspi4B = data_collector.Raspi(remote=False)
for i in range(10):
    
    print('get value:', raspi0_1.get_data())
    print('get value:', raspi0_2.get_data())
    print('get value:', raspi4B.get_data())
    sleep(2)
 