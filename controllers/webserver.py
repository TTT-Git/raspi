from datetime import datetime
from datetime import timedelta
from flask import Flask
from flask import jsonify
from flask import render_template
from flask import request
import logging

from models.df_temp_humid import DataFrameTempHumid
from models.base import AirconState
from controllers.aircon_stream import aircon_stream

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
    
    # エアコンの状態を取得
    aircon_states = AirconState.get_data_after_time(time)
    aircon_data = []
    if aircon_states:
        aircon_data = [state.value for state in aircon_states]
    
    result = df.value
    
    # 異常な温度・湿度値をフィルタリング（既存データベースに異常値が入っている場合に対応）
    filtered_temp_humid = []
    for data in result['temp_humid']:
        # 温度が-50度〜60度の範囲内、湿度が0〜100%の範囲内のデータのみを含める
        temp = data.get('temperature')
        humid = data.get('humidity')
        if temp is not None and (temp < -50 or temp > 60):
            logger.warning({
                'action': 'api_make_handler',
                'status': 'filtered_invalid_data',
                'message': f'異常な温度値をフィルタリングしました',
                'data': f'time: {data.get("time")}, temperature: {temp}, hostname: {hostname}'
            })
            continue
        if humid is not None and (humid < 0 or humid > 100):
            logger.warning({
                'action': 'api_make_handler',
                'status': 'filtered_invalid_data',
                'message': f'異常な湿度値をフィルタリングしました',
                'data': f'time: {data.get("time")}, humidity: {humid}, hostname: {hostname}'
            })
            continue
        filtered_temp_humid.append(data)
    
    result['temp_humid'] = filtered_temp_humid
    result['aircon'] = aircon_data

    return jsonify(result), 200


@app.route('/api/latest/', methods=['GET'])
def api_latest_handler():
    """
    最新データのタイムスタンプを返す
    """
    hostname = request.args.get('hostname')
    if not hostname:
        return jsonify({'error': 'No hostname params'}), 400
    
    device_num_str = request.args.get('device_num')
    if device_num_str:
        device_num = int(device_num_str)
    else:
        device_num = 0
    
    df = DataFrameTempHumid(hostname, device_num)
    latest = df.temp_humid_cls.latest_record()
    
    if latest:
        return jsonify({
            'latest_time': latest.time.isoformat(),
            'hostname': hostname,
            'device_num': device_num
        }), 200
    else:
        return jsonify({
            'latest_time': None,
            'hostname': hostname,
            'device_num': device_num
        }), 200


@app.route('/api/aircon/stop/', methods=['POST'])
def api_aircon_stop():
    """
    エアコンをオフにして、温度制御を停止する
    """
    try:
        aircon_stream.stop_aircon()
        status = aircon_stream.get_status()
        logger.info({
            'action': 'api_aircon_stop',
            'status': 'success',
            'message': 'エアコン制御を停止しました'
        })
        return jsonify({
            'success': True,
            'message': 'エアコン制御を停止しました',
            'status': status
        }), 200
    except Exception as e:
        logger.error({
            'action': 'api_aircon_stop',
            'status': 'error',
            'message': str(e)
        })
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/aircon/start/', methods=['POST'])
def api_aircon_start():
    """
    エアコンの温度制御を開始する
    """
    try:
        result = aircon_stream.start_aircon()
        if result:
            status = aircon_stream.get_status()
            logger.info({
                'action': 'api_aircon_start',
                'status': 'success',
                'message': 'エアコン制御を開始しました'
            })
            return jsonify({
                'success': True,
                'message': 'エアコン制御を開始しました',
                'status': status
            }), 200
        else:
            return jsonify({
                'success': False,
                'error': 'エアコン制御は既に実行中です'
            }), 400
    except Exception as e:
        logger.error({
            'action': 'api_aircon_start',
            'status': 'error',
            'message': str(e)
        })
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/aircon/status/', methods=['GET'])
def api_aircon_status():
    """
    エアコン制御の状態を取得する
    """
    try:
        status = aircon_stream.get_status()
        return jsonify({
            'success': True,
            'status': status
        }), 200
    except Exception as e:
        logger.error({
            'action': 'api_aircon_status',
            'status': 'error',
            'message': str(e)
        })
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


def start():
    app.run(host='0.0.0.0', port=settings.web_port, threaded=True)

