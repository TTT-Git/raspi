import json

def generate_ac_remote_signal(on_off:str, mode:str, temp:int, fan:str, sound:str):
    on_offs = {'on':'1', 'off':'0'}
    on_off_bin = on_offs[on_off]
    temp_bin = format(temp - 16, '04b')[::-1]  # 16度を基準として4bitで表現
    modes = {'cooler': '1', 'heater': '0'}
    mode_bin = modes[mode]
    fin_modes = {"cooler": "01101100", "heater": "01100000"}
    fin_bin = fin_modes[mode]
    fans = {'auto':'00', "low": "01", "medium": "10", "high": "11"}
    fan_bin = fans[fan][::-1]
    sounds = {'pi':'01', 'pipi':'10', 'no':'00'}
    sound_bin = sounds[sound][::-1]

    signals_by_bite_dict = {
        0: '11000100',
        1: '11010011',
        2: '01100100',
        3: '10000000',
        4: '00000000',
        5: '00000' + on_off_bin + '00',
        6: '0001' + mode_bin + '000',
        7: temp_bin + '0000',
        8: fin_bin,
        9: fan_bin + '0000' + sound_bin,
        10: '00000000',
        11: '00000000',
        12: '00000000',
        13: '00000000',
        14: '00100000',
        15: '00000000',
        16: '00000000',
    }
    
    return to_ms_signal(add_check_bite(signals_by_bite_dict))

def add_check_bite(signals_by_bite_dict):
    sum = 0
    for bite_str in signals_by_bite_dict.values():
        sum += int(bite_str[::-1], 2)
    signals_by_bite_dict[17] = bin(sum)[-8:][::-1]
    return signals_by_bite_dict


def to_ms_signal(signals_by_bite_dict):

    ms_signal = [3487, 1653]
    for bite_str in signals_by_bite_dict.values():

        for bit in bite_str:
            if bit == '1':
                ms_signal += [481, 1228]
            else:
                ms_signal += [481, 380]

    ms_signal = ms_signal + [481, 13226] + ms_signal + [481]

    return ms_signal


def write_gene_signal(ms_signal, FILE):
        f = open(FILE, "w")
        f.write(json.dumps({'generated':ms_signal}, sort_keys=True).replace("],", "],\n") + "\n")
        f.close()

if __name__ == '__main__':

    print(generate_ac_remote_signal(on_off='on', mode='cooler', temp=27, fan='low', sound='no'))


