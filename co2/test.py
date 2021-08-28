import subprocess

def get_co2()->int:
    out = subprocess.check_output(['sudo', 'python3', '-m', 'mh_z19'])
    out = str(out)
    out = out.split(':')
    out = out[1].split('}')
    out = int(out[0])

    return {'co2':out}

if __name__ == '__main__':
    print(get_co2())

