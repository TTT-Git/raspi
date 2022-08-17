from datetime import datetime
from datetime import timedelta
from flask import Flask
from flask import jsonify
from flask import render_template
from flask import request
import logging

from models.df_temp_humid import DataFrameTempHumid

import settings

logger = logging.getLogger(__name__)

app = Flask(__name__, template_folder='../views')


@app.teardown_appcontext
def remove_session(ex=None):
    from models.base import  Session
    Session.remove()


@app.route('/')
def index():
    # hostname = settings.system_name
    # device_num = 0
    # df = DataFrameTempHumid(hostname, device_num)
    # term_hour = 24
    # now = datetime.utcnow()
    # time = now - timedelta(hours=term_hour)
    # df.set_data_after_time(time)
    
    # temp_humid_data = df.value['temp_humid']
    # print(temp_humid_data)
    # return render_template('./test.html', temp_humid_data=temp_humid_data)
    return render_template('./jquery.html')

@app.route('/api/candle/', methods=['GET'])
def api_make_handler():
    hostname = request.args.get('hostname')
    if not hostname:
        logger.error({
            'action': 'api_make_handler check hostname',
            'status': 'error',
            'message': f'no hostname',
            'data': f'hostname: {hostname}'
        })
        return jsonify({'error': 'No hostname params'}) ,400
    
    term_hour_str = request.args.get('term_hour')
    term_hour = 24
    if term_hour_str:
        term_hour = int(term_hour_str)

    if term_hour < 0 or term_hour > 720:
        term_hour = 720

    device_num_str = request.args.get('device_num')
    if device_num_str:
        device_num = int(device_num_str)
    else:
        device_num = 0
    
    df = DataFrameTempHumid(hostname, device_num)

    now = datetime.now()
    time = now - timedelta(hours=term_hour)
    df.set_data_after_time(time)

    return jsonify(df.value), 200




def start():
    app.run(host='0.0.0.0', port=settings.web_port, threaded=True)

