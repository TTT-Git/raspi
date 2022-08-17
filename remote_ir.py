import sys

from pigpios.ir_ctrl import Aircon


if __name__ == '__main__':
    args = sys.argv
    if len(args) == 2:
        print(args)
        id = args[1]
        aircon = Aircon()
        aircon.send_id(id)