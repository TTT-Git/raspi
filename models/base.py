from contextlib import contextmanager
import threading

from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy.orm import scoped_session

from sqlalchemy import Column
from sqlalchemy import desc
from sqlalchemy import DateTime
from sqlalchemy import Float
from sqlalchemy import Integer
from sqlalchemy import String
from sqlalchemy.exc import IntegrityError

import settings

engine = create_engine(f'sqlite:///{settings.db_name}?check_same_thread=False', connect_args={'timeout': 10})
# engine = create_engine(f'sqlite:///:memory:')
Base = declarative_base()
Session = scoped_session(sessionmaker(bind=engine))
lock = threading.Lock()

@contextmanager
def session_scope():
    session = Session()
    session.expire_on_commit = False
    try:
        # 関数が呼び出されたらロックする。
        lock.acquire()
        yield session
        session.commit()
    except Exception as e:
        # logger.error(f'action=session_scope error={e}')
        session.rollback()
        raise
    finally:
        session.expire_on_commit = True
        # 関数が実行し終わったら、ロックを解除する。
        lock.release()


class BaseTempHumidMixin(object):
    time = Column(DateTime, primary_key=True, nullable=False)
    temperature = Column(Float)
    humidity = Column(Float)
    co2_ppm = Column(Float)
    meas_position = Column(String)
    hostname = Column(String)

    @classmethod
    def create(cls, time, temperature, humidity, co2_ppm, meas_position, hostname):
        # 温度のバリデーション: -50度〜60度の範囲外は異常値として保存しない
        if temperature is not None and (temperature < -50 or temperature > 60):
            import logging
            logger = logging.getLogger(__name__)
            logger.warning({
                'action': 'create',
                'status': 'validation_error',
                'message': f'異常な温度値が検出されました。保存をスキップします。',
                'data': f'time: {time}, temperature: {temperature}, hostname: {hostname}, meas_position: {meas_position}'
            })
            return False
        
        # 湿度のバリデーション: 0〜100%の範囲外は異常値として保存しない
        if humidity is not None and (humidity < 0 or humidity > 100):
            import logging
            logger = logging.getLogger(__name__)
            logger.warning({
                'action': 'create',
                'status': 'validation_error',
                'message': f'異常な湿度値が検出されました。保存をスキップします。',
                'data': f'time: {time}, humidity: {humidity}, hostname: {hostname}, meas_position: {meas_position}'
            })
            return False
        
        temp_humid_data = cls(time=time,
                     temperature=temperature,
                     humidity=humidity,
                     co2_ppm=co2_ppm,
                     meas_position=meas_position,
                     hostname=hostname
                     )
        try:
            with session_scope() as session:
                session.add(temp_humid_data)
                return temp_humid_data
        except IntegrityError:
            return False
    
    @classmethod
    def get(cls,time):
        with session_scope() as session:
            temp_humid_data = session.query(cls).filter(
                cls.time == time).first()
            if temp_humid_data is None:
                return None
            return temp_humid_data
    
    def save(self):
        with session_scope() as session:
            session.add(self)
    
    @classmethod
    def get_all_data(cls, limit=100):
        """
        データベースからデータを取得して,返す。
        データは、最新のものから、limitで指定した数、
        順番は古いものから順番になっている。
        """
        with session_scope() as session:
            #order_by 値を使ってソートする
            #limit で読み込むレコード数を制限する。
            temp_humid_data = session.query(cls).order_by(
                desc(cls.time)).limit(limit).all()

        if temp_humid_data is None:
            return None
        #reverseでデータベースの順番を逆にする。
        temp_humid_data.reverse()
        return temp_humid_data

    
    @property
    def value(self):
        return {
            'time': self.time,
            'temperature': self.temperature,
            'humidity': self.humidity,
            'co2_ppm': self.co2_ppm,
            'meas_position': self.meas_position,
            'hostname': self.hostname
        }
    
    @classmethod
    def latest_record(cls):
        """
        データベースにある最後のデータを取得する。
        """
        with session_scope() as session:
            #order_by 値を使ってソートする
            #limit で読み込むレコード数を制限する。
            temp_humid_data = session.query(cls).order_by(
                desc(cls.time)).first()
        return temp_humid_data
    
    @classmethod
    def oldest_record(cls):
        """
        データベースにある最初のデータを取得する。
        """
        with session_scope() as session:
            #order_by 値を使ってソートする
            #limit で読み込むレコード数を制限する。
            temp_humid_data = session.query(cls).order_by(
                cls.time).first()
        return temp_humid_data
    
    @classmethod
    def get_data_after_time(cls, time):
        """
        ある日時以降のcandleを抽出

        使い方
        now = datetime.datetime.utcnow()
        now = now - datetime.timedelta(minutes=10)
        candles = cls.get_candles_after_time(now)
        for candle in candles:
            print(candle.value)
        """
        with session_scope() as session:
            temp_humid_data = session.query(cls).filter(cls.time >= time).order_by(
                cls.time).all()

        if temp_humid_data is None:
            return None

        return temp_humid_data


class TempHumid_Raspi0_1_0(BaseTempHumidMixin,Base):
    __tablename__ = 'TempHumid_Raspi0_1_0'

class TempHumid_Raspi0_2_0(BaseTempHumidMixin,Base):
    __tablename__ = 'TempHumid_Raspi0_2_0'

class TempHumid_Raspi0_2_1(BaseTempHumidMixin,Base):
    __tablename__ = 'TempHumid_Raspi0_2_1'

class TempHumid_Raspi4B_1_0(BaseTempHumidMixin,Base):
    __tablename__ = 'TempHumid_Raspi4B_1_0'


class AirconState(Base):
    __tablename__ = 'aircon_state'
    
    time = Column(DateTime, primary_key=True, nullable=False)
    mode = Column(String)  # 'heater' or 'cooler' or 'off'
    setting_temp = Column(Float)  # 設定温度
    heater_setting_temp = Column(Float)  # 暖房設定温度
    cooler_setting_temp = Column(Float)  # 冷房設定温度
    
    @classmethod
    def create(cls, time, mode, setting_temp, heater_setting_temp, cooler_setting_temp):
        aircon_state = cls(
            time=time,
            mode=mode,
            setting_temp=setting_temp,
            heater_setting_temp=heater_setting_temp,
            cooler_setting_temp=cooler_setting_temp
        )
        try:
            with session_scope() as session:
                session.add(aircon_state)
                return aircon_state
        except IntegrityError:
            return False
    
    @classmethod
    def get_data_after_time(cls, time):
        with session_scope() as session:
            aircon_states = session.query(cls).filter(cls.time >= time).order_by(
                cls.time).all()
        if aircon_states is None:
            return None
        return aircon_states
    
    @property
    def value(self):
        return {
            'time': self.time,
            'mode': self.mode,
            'setting_temp': self.setting_temp,
            'heater_setting_temp': self.heater_setting_temp,
            'cooler_setting_temp': self.cooler_setting_temp
        }


def factory_temp_humid_class(hostname, device_num):
    
    if hostname == settings.ssh[0]['host']:
        if device_num == 0:
            return TempHumid_Raspi0_1_0
    if hostname == settings.ssh[1]['host']:
        if device_num == 0:
            return TempHumid_Raspi0_2_0
        if device_num == 1:
            return TempHumid_Raspi0_2_1
    if hostname == settings.system_name:
        if device_num == 0:
            return TempHumid_Raspi4B_1_0

def init_db():
    Base.metadata.create_all(bind=engine)
