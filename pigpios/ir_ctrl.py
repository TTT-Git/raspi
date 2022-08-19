from pigpios.irrp_m import IRRP

import settings


class Aircon(object):
    def __init__(self, file=settings.codes_aircon_file, gpio_num=settings.gpio_irled, 
                remote_raspi=False, ssh_num=1):
        self.ir = IRRP(file=file, no_confirm=True)
        self.gpio_num = gpio_num
        self.remote_raspi = remote_raspi
        self.ssh_num = ssh_num
    
    def on(self):
        id = 'on'
        print(id)
        if self.remote_raspi:
            self.remote_raspi_ir_ctl(id)
            return
        self.ir.Playback(GPIO=self.gpio_num, ID=id)
        self.ir.stop()
    
    def off(self):
        id = 'off'
        print(id)
        if self.remote_raspi:
            self.remote_raspi_ir_ctl(id)
            return
        self.ir.Playback(GPIO=self.gpio_num, ID=id)
        self.ir.stop()
    
    def heater(self, temp:int):
        id = 'heater:' + str(int(temp))
        print(id)
        if self.remote_raspi:
            self.remote_raspi_ir_ctl(id)
            return
        self.ir.Playback(GPIO=self.gpio_num, ID=id)
        self.ir.stop()

    def cooler(self, temp:int):
        id = 'cooler:' + str(int(temp))
        print(id)
        if self.remote_raspi:
            self.remote_raspi_ir_ctl(id)
            return
        self.ir.Playback(GPIO=self.gpio_num, ID=id)
        self.ir.stop()
    
    def send_id(self, id:str):
        print(id)
        if self.remote_raspi:
            self.remote_raspi_ir_ctl(id)
            return
        self.ir.Playback(GPIO=self.gpio_num, ID=id)
        self.ir.stop()
    
    def remote_raspi_ir_ctl(self, id):
        from models.ssh_ctrl_remote_raspi import Raspi
        raspi = Raspi(self.ssh_num)
        # サーバー上で実行するコマンドを設定
        CMD = 'cd ' + settings.main_dir + ' ; python3 ' + settings.remote_aircon_ir_file + ' ' + id
        # コマンドの実行
        raspi.send_cmd(CMD)



