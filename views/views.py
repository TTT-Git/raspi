import os

import paramiko
import scp

import settings

class Raspi(object):
    def __init__(self, hostname) -> None:
        self.hostname = hostname
    
    def copy_data(self, raspi_data_path='/home/pi/python/raspi/data', file_name='result.csv',
        file_cp_path='data'):
        raspi_file_path = os.path.join(raspi_data_path, file_name)

        with paramiko.SSHClient() as ssh:
            # 初回ログイン時に「Are you sure you want to continue connecting (yes/no)?」と
            # きかれても問題なく接続できるように。
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

            # ssh接続する
            print('[ssh接続]')
            ssh.connect(hostname=settings.host, username=settings.user, key_filename=settings.key_file)

            print('[SCP転送開始]')
            # scp clientオブジェクト生成
            with scp.SCPClient(ssh.get_transport()) as scp_client:
                # SCP受信（サーバ → ローカル）
                scp_client.get(raspi_file_path, os.path.join(file_cp_path, file_name))
