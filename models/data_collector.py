import json
import logging

import paramiko
import socket

import main_return_onece
import settings

logger = logging.getLogger(__name__)

class Raspi(object):
    def __init__(self, ssh_num=0, remote=True) -> None:
        self.ssh_num = ssh_num
        self.remote = remote
    
    def get_data(self, py_file_path='/home/pi/python/raspi', py_file_name='main_return_onece.py'):
        
        if self.remote:
            with paramiko.SSHClient() as ssh:
                # 初回ログイン時に「Are you sure you want to continue connecting (yes/no)?」と
                # きかれても問題なく接続できるように。
                ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

                # ssh接続する
                try:
                    ssh.connect(hostname=settings.ssh[self.ssh_num]['host'], 
                        username=settings.ssh[self.ssh_num]['user'],
                        key_filename=settings.ssh[self.ssh_num]['key_file'])
                except socket.gaierror as e:
                    logger.error({
                            'action': 'ssh connect',
                            'status': 'socket.gaierror',
                            'message': f'error message: {e}',
                            'data': f"hostname={settings.ssh[self.ssh_num]['host']}, username={settings.ssh[self.ssh_num]['user']}, key_filename={settings.ssh[self.ssh_num]['key_file']}"
                        })
                    return {}
                except ValueError as e:
                    logger.error({
                            'action': 'ssh connect',
                            'status': 'ValueError',
                            'message': f'error message: {e}',
                            'data': f"hostname={settings.ssh[self.ssh_num]['host']}, username={settings.ssh[self.ssh_num]['user']}, key_filename={settings.ssh[self.ssh_num]['key_file']}"
                        })
                    return {}


                # サーバー上で実行するコマンドを設定
                CMD = 'cd ' + py_file_path + ' ; python3 ' + py_file_name
                # コマンドの実行
                stdin, stdout, stderr = ssh.exec_command(CMD)
                # コマンド実行結果を変数に格納
                self.result_dict = {}
                for line in stdout:
                    try:
                        self.result_dict = json.loads(line)
                        for device_num in range(2):
                            self.result_dict[device_num] = self.result_dict.pop(str(device_num))
                        self.result_dict['hostname'] = settings.ssh[self.ssh_num]['host']
                    except json.JSONDecodeError as e:
                        logger.error({
                            'action': 'json decode',
                            'status': 'json.JSONDecodeError',
                            'message': f'error message {e}',
                            'data': f'line={line}'
                        })
        
        else:
            self.result_dict = main_return_onece.main_func()
            self.result_dict['hostname'] = settings.system_name


        
        return self.result_dict
