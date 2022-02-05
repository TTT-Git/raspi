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

engine = create_engine(f'sqlite:///{settings.db_name}?check_same_thread=False')
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


class TempHumid(Base):
    __tablename__ = 'temp_humid'
    time = Column(DateTime, primary_key=True, nullable=False)
    temperature = Column(Float)
    humidity = Column(Float)
    co2_ppm = Column(Float)
    meas_position = Column(String)
    hostname = Column(String)

    @classmethod
    def create(cls, time, temperature, humidity, co2_ppm, meas_position, hostname):
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
    def get_all_candles(cls, limit=100):
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
    def get_candles_after_time(cls, time):
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
    


def init_db():
    Base.metadata.create_all(bind=engine)
