
from models.base import factory_temp_humid_class


class DataFrameTempHumid(object):
    """
    グラフのためのデータリストを管理するクラス
    """

    def __init__(self, hostname, device_num):
        self.hostname = hostname
        self.device_num = device_num
        self.temp_humid_cls = factory_temp_humid_class(self.hostname, self.device_num)
        self.temp_humid_data =[]

    def set_all_data(self, limit=1000):
        self.temp_humid_data = self.temp_humid_cls.get_all_data(limit)
        return self.temp_humid_data
    
    def set_data_after_time(self, time):
        self.temp_humid_data = self.temp_humid_cls.get_data_after_time(time)
        return self.temp_humid_data
    
    @property
    def value(self):
        """
        空のリストのパラメータの値はNone
        """
        return {
            'hostname': self.hostname,
            'device_num': self.device_num,
            'temp_humid': [data.value for data in self.temp_humid_data ],
        }

