import json

with open('codes_aircon', 'r') as f:
    aircon_dict = json.load(f)

print(aircon_dict['heater:25'])



# import numpy as np
# light_white_array = np.array(ir_code_dict["aircon:on"])
# light_warm_array = np.array(ir_code_dict["aircon:off"])
# print(light_white_array - light_warm_array)
# print(light_white_array)
# print(light_warm_array)