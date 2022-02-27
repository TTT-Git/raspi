from pigpios.irrp_m import IRRP

def test():
    ir = IRRP(file='codes_aircon', no_confirm=True)
    id = 'heater:26'
    print(id)
    ir.Playback(GPIO=19, ID=id)
    ir.stop()


class Aircon(object):
    def __init__(self, file=r'pigpios/codes_aircon', gpio_num=19):
        self.ir = IRRP(file=file, no_confirm=True)
        self.gpio_num = gpio_num
    
    def on(self):
        id = 'on'
        print(id)
        self.ir.Playback(GPIO=self.gpio_num, ID=id)
        self.ir.stop()
    
    def off(self):
        id = 'off'
        print(id)
        self.ir.Playback(GPIO=self.gpio_num, ID=id)
        self.ir.stop()
    
    def heater(self, temp:int):
        id = 'heater:' + str(temp)
        print(id)
        self.ir.Playback(GPIO=self.gpio_num, ID=id)
        self.ir.stop()


if __name__ == '__main__':
    # test()
    aircon = Aircon()
    aircon.heater(28)

