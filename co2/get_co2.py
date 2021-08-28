import subprocess
import sys

def get_co2(limit=15)->int:
    """
    get co2 concentration from mh_z19
    input
        limit: how many times retry to get value from mh_z19 if error happens.
    return
         {'co2':out}: out is co2 concentration in integer. if error, return False
    """
    for _ in range(limit):
        try:
            out = subprocess.check_output(['sudo', 'python3', '-m', 'mh_z19'])
            out = str(out)
            out = out.split(':')
            out = out[1].split('}')
            out = int(out[0])
            return {'co2':out}
        except Exception as error:
            print(sys._getframe().f_code.co_name, error)
            continue

    return False

if __name__ == '__main__':
    print(get_co2())

