from pigpios.irrp_m import IRRP
from pigpios.ir_ctrl import Aircon

import settings
# def test():
#     ir = IRRP(file='codes_aircon', no_confirm=True)
#     id = 'heater:26'
#     print(id)
#     ir.Playback(GPIO=19, ID=id)
#     ir.stop()


# class Aircon(object):
#     def __init__(self, file=r'pigpios/codes_aircon', gpio_num=19):
#         self.ir = IRRP(file=file, no_confirm=True)
#         self.gpio_num = gpio_num
    
#     def on(self):
#         id = 'on'
#         print(id)
#         self.ir.Playback(GPIO=self.gpio_num, ID=id)
#         self.ir.stop()
    
#     def off(self):
#         id = 'off'
#         print(id)
#         self.ir.Playback(GPIO=self.gpio_num, ID=id)
#         self.ir.stop()
    
#     def heater(self, temp:int):
#         id = 'heater:' + str(temp)
#         print(id)
#         self.ir.Playback(GPIO=self.gpio_num, ID=id)
#         self.ir.stop()

#     def cooler(self, temp:int):
#         id = 'cooler:' + str(temp)
#         print(id)
#         self.ir.Playback(GPIO=self.gpio_num, ID=id)
#         self.ir.stop()

if __name__ == '__main__':
    # test()
    aircon = Aircon(remote_raspi=settings.remote_ir, ssh_num=settings.remote_ir_raspi_ssh_num)

    # on_offs = ['on', 'off']
    # modes = ['cooler', 'heater']
    # temps = [temp for temp in range(16,32)]
    # fans = ['auto', 'low', "medium", "high"]
    # sounds = ['pi', 'pipi', 'no']
    
    id = f"onoff:{'on'}_mode:{'cooler'}_temp:{26}_fan:{'low'}_sound:{'no'}"
    aircon.send_id(id)

