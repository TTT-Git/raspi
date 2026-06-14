from datetime import datetime
import logging
from time import sleep

from models import ssh_ctrl_remote_raspi

import models
from models.base import factory_temp_humid_class
from models.base import TempHumid_Raspi0_1_0
from models.base import TempHumid_Raspi0_2_0
from models.base import TempHumid_Raspi0_2_1
from models.base import TempHumid_Raspi4B_1_0
import settings

logging.basicConfig(level=logging.INFO, 
    format='%(asctime)s %(threadName)s:%(levelname)s:%(name)s: %(message)s',
    )

logger = logging.getLogger(__name__)

base_list = [TempHumid_Raspi0_1_0, TempHumid_Raspi0_2_0, TempHumid_Raspi0_2_1, TempHumid_Raspi4B_1_0]
base_list = [TempHumid_Raspi0_1_0, TempHumid_Raspi4B_1_0]

raspi0_1 = ssh_ctrl_remote_raspi.Raspi(ssh_num=0, remote=True)
raspi0_2 = ssh_ctrl_remote_raspi.Raspi(ssh_num=1, remote=True)
raspi4B = ssh_ctrl_remote_raspi.Raspi(remote=False)


def write_sql(result_dict):
    """
    ラズパイで取得した温度、湿度、CO2濃度をデータベースに書き込む
    """
    for device_num in range(2):
        if result_dict[device_num]:
            time = datetime.fromisoformat(result_dict['datetime'])
            temperature=result_dict[device_num]['temperature_c']
            humidity=result_dict[device_num]['humidity']
            if 'co2' in result_dict[device_num].keys():
                co2_ppm=result_dict[device_num]['co2']
            else:
                co2_ppm=None
            meas_position = result_dict[device_num]['meas_position']
            hostname=result_dict['hostname']
            temp_humid_base = factory_temp_humid_class(hostname, device_num)
            result = temp_humid_base.create(
                time=time,
                temperature=temperature,
                humidity=humidity,
                co2_ppm=co2_ppm,
                meas_position=meas_position,
                hostname=hostname
                )
            if not result:
                logger.error({
                    'action': 'temp_humid write',
                    'status': 'write_skipped',
                    'message': 'temperature and humidity record was not written',
                    'data': f'hostname: {hostname}, device_num: {device_num}, time: {time}',
                })



while True:
    try:
        results = []
        data_sources = [
            (
                'raspi0_1',
                lambda: raspi0_1.get_data(py_file_path=settings.main_dir_host0),
            ),
            (
                'raspi0_2',
                lambda: raspi0_2.get_data(py_file_path=settings.main_dir_host1),
            ),
            ('raspi4B', raspi4B.get_data),
        ]

        for source_name, get_data in data_sources:
            try:
                results.append(get_data())
            except Exception:
                logger.exception({
                    'action': 'sensor read',
                    'status': 'cycle_skipped',
                    'message': 'sensor data acquisition failed',
                    'data': f'source: {source_name}',
                })

        for result_dict in results:
            if not result_dict:
                continue
            try:
                write_sql(result_dict)
            except KeyError as error:
                logger.exception({
                    'action': 'temp_humid write',
                    'status': 'cycle_skipped',
                    'message': f'required sensor field is missing: {error}',
                    'data': f'result_dict: {result_dict}',
                })
            except Exception:
                logger.exception({
                    'action': 'temp_humid write',
                    'status': 'cycle_skipped',
                    'message': 'database write failed; continuing with next source',
                    'data': f'result_dict: {result_dict}',
                })

        for TempHumid in base_list:
            try:
                temp_humid_data = TempHumid.latest_record()
                if temp_humid_data:
                    logger.info({
                        'action': 'latest temperature read',
                        'status': 'success',
                        'data': temp_humid_data.value,
                    })
            except Exception:
                logger.exception({
                    'action': 'latest temperature read',
                    'status': 'cycle_skipped',
                    'message': 'failed to read latest temperature record',
                    'data': f'table: {TempHumid.__tablename__}',
                })
    except Exception:
        logger.exception({
            'action': 'sensor collection loop',
            'status': 'cycle_skipped',
            'message': 'unexpected collection cycle error; continuing',
        })
    finally:
        sleep(10)

