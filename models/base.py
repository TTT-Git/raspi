from contextlib import contextmanager
import logging
import threading
from time import sleep

from sqlalchemy import create_engine
from sqlalchemy import event
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
from sqlalchemy.exc import OperationalError

import settings

logger = logging.getLogger(__name__)

DB_CONNECTION_TIMEOUT_SECONDS = 5
DB_BUSY_TIMEOUT_MS = 5000
DB_RETRY_DELAYS_SECONDS = (0.5, 1.0, 2.0, 4.0, 5.0)


class DatabaseLockError(RuntimeError):
    """Raised after a locked SQLite operation exhausts its retries."""

    def __init__(self, operation_name, attempts):
        super().__init__(
            f'{operation_name} skipped after {attempts} attempts because the database remained locked'
        )
        self.operation_name = operation_name
        self.attempts = attempts


def is_database_locked(error):
    message = str(getattr(error, 'orig', error)).lower()
    return 'locked' in message or 'busy' in message


engine = create_engine(
    f'sqlite:///{settings.db_name}',
    connect_args={
        'timeout': DB_CONNECTION_TIMEOUT_SECONDS,
        'check_same_thread': False,
    },
)
# engine = create_engine(f'sqlite:///:memory:')
Base = declarative_base()
Session = scoped_session(sessionmaker(bind=engine, expire_on_commit=False))
lock = threading.Lock()


@event.listens_for(engine, 'connect')
def set_sqlite_busy_timeout(dbapi_connection, connection_record):
    del connection_record
    cursor = None
    try:
        cursor = dbapi_connection.cursor()
        cursor.execute(f'PRAGMA busy_timeout={DB_BUSY_TIMEOUT_MS}')
    except Exception:
        logger.warning({
            'action': 'sqlite connection setup',
            'status': 'busy_timeout_failed',
            'message': 'failed to set PRAGMA busy_timeout; continuing with connection timeout',
        }, exc_info=True)
    finally:
        if cursor is not None:
            try:
                cursor.close()
            except Exception:
                logger.warning({
                    'action': 'sqlite connection setup',
                    'status': 'cursor_close_failed',
                    'message': 'failed to close SQLite setup cursor',
                }, exc_info=True)


@event.listens_for(engine, 'first_connect')
def enable_sqlite_wal(dbapi_connection, connection_record):
    del connection_record
    cursor = None
    try:
        cursor = dbapi_connection.cursor()
        cursor.execute('PRAGMA journal_mode=WAL')
        result = cursor.fetchone()
        journal_mode = result[0].lower() if result else None
        if journal_mode != 'wal':
            logger.warning({
                'action': 'sqlite connection setup',
                'status': 'wal_not_enabled',
                'message': f'PRAGMA journal_mode returned {journal_mode!r}; continuing without WAL',
            })
    except Exception:
        logger.warning({
            'action': 'sqlite connection setup',
            'status': 'wal_enable_failed',
            'message': 'failed to enable WAL mode; continuing without WAL',
        }, exc_info=True)
    finally:
        if cursor is not None:
            try:
                cursor.close()
            except Exception:
                logger.warning({
                    'action': 'sqlite connection setup',
                    'status': 'cursor_close_failed',
                    'message': 'failed to close SQLite setup cursor',
                }, exc_info=True)


def _rollback_session(session, operation_name):
    try:
        session.rollback()
    except Exception:
        logger.exception({
            'action': operation_name,
            'status': 'rollback_failed',
            'message': 'database rollback failed',
        })


def _close_session(session, session_registry, operation_name):
    try:
        session.close()
    except Exception:
        logger.exception({
            'action': operation_name,
            'status': 'session_close_failed',
            'message': 'database session close failed',
        })
    finally:
        remove = getattr(session_registry, 'remove', None)
        if remove is not None:
            try:
                remove()
            except Exception:
                logger.exception({
                    'action': operation_name,
                    'status': 'session_remove_failed',
                    'message': 'failed to remove scoped database session',
                })


def execute_db_operation(
        operation,
        operation_name,
        write=False,
        session_registry=None,
        retry_delays=None):
    """Execute one replayable DB operation with lock-specific retries."""
    if session_registry is None:
        session_registry = Session
    retry_delays = (
        DB_RETRY_DELAYS_SECONDS
        if retry_delays is None
        else tuple(retry_delays)
    )
    max_attempts = len(retry_delays) + 1

    for attempt in range(1, max_attempts + 1):
        session = session_registry()
        try:
            with lock:
                try:
                    result = operation(session)
                    if write:
                        session.commit()
                except Exception:
                    _rollback_session(session, operation_name)
                    raise
            return result
        except OperationalError as error:
            if not is_database_locked(error):
                logger.exception({
                    'action': operation_name,
                    'status': 'database_error',
                    'message': 'non-lock OperationalError occurred',
                })
                raise

            if attempt < max_attempts:
                delay = retry_delays[attempt - 1]
                logger.warning({
                    'action': operation_name,
                    'status': 'database_locked_retry',
                    'message': 'database is locked or busy; retrying operation',
                    'attempt': attempt,
                    'max_retries': len(retry_delays),
                    'retry_in_seconds': delay,
                })
            else:
                logger.error({
                    'action': operation_name,
                    'status': 'database_locked_skipped',
                    'message': 'database remained locked; skipping operation',
                    'attempts': attempt,
                })
                raise DatabaseLockError(operation_name, attempt) from error
        except Exception:
            logger.exception({
                'action': operation_name,
                'status': 'database_error',
                'message': 'database operation failed',
            })
            raise
        finally:
            _close_session(session, session_registry, operation_name)

        sleep(delay)


@contextmanager
def session_scope(operation_name='database operation'):
    """Provide a single transaction with guaranteed rollback and cleanup."""
    session = Session()
    try:
        with lock:
            try:
                yield session
                session.commit()
            except Exception:
                _rollback_session(session, operation_name)
                raise
    finally:
        _close_session(session, Session, operation_name)


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
        
        operation_name = f'temp_humid write {cls.__tablename__}'

        def create_record(session):
            temp_humid_data = cls(
                time=time,
                temperature=temperature,
                humidity=humidity,
                co2_ppm=co2_ppm,
                meas_position=meas_position,
                hostname=hostname,
            )
            session.add(temp_humid_data)
            return temp_humid_data

        try:
            return execute_db_operation(
                create_record,
                operation_name=operation_name,
                write=True,
            )
        except IntegrityError:
            return False
        except DatabaseLockError:
            return False
    
    @classmethod
    def get(cls,time):
        def get_record(session):
            return session.query(cls).filter(cls.time == time).first()

        return execute_db_operation(
            get_record,
            operation_name=f'temp_humid read by time {cls.__tablename__}',
        )
    
    def save(self):
        return execute_db_operation(
            lambda session: session.merge(self),
            operation_name=f'temp_humid save {self.__tablename__}',
            write=True,
        )
    
    @classmethod
    def get_all_data(cls, limit=100):
        """
        データベースからデータを取得して,返す。
        データは、最新のものから、limitで指定した数、
        順番は古いものから順番になっている。
        """
        def get_records(session):
            return session.query(cls).order_by(
                desc(cls.time)).limit(limit).all()

        temp_humid_data = execute_db_operation(
            get_records,
            operation_name=f'temp_humid read recent {cls.__tablename__}',
        )

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
        return execute_db_operation(
            lambda session: session.query(cls).order_by(
                desc(cls.time)).first(),
            operation_name=f'temp_humid read latest {cls.__tablename__}',
        )
    
    @classmethod
    def oldest_record(cls):
        """
        データベースにある最初のデータを取得する。
        """
        return execute_db_operation(
            lambda session: session.query(cls).order_by(cls.time).first(),
            operation_name=f'temp_humid read oldest {cls.__tablename__}',
        )
    
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
        temp_humid_data = execute_db_operation(
            lambda session: session.query(cls).filter(
                cls.time >= time).order_by(cls.time).all(),
            operation_name=f'temp_humid read range {cls.__tablename__}',
        )

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
        def create_record(session):
            aircon_state = cls(
                time=time,
                mode=mode,
                setting_temp=setting_temp,
                heater_setting_temp=heater_setting_temp,
                cooler_setting_temp=cooler_setting_temp,
            )
            session.add(aircon_state)
            return aircon_state

        try:
            return execute_db_operation(
                create_record,
                operation_name='aircon_state write',
                write=True,
            )
        except IntegrityError:
            return False
        except DatabaseLockError:
            return False
    
    @classmethod
    def get_data_after_time(cls, time):
        aircon_states = execute_db_operation(
            lambda session: session.query(cls).filter(
                cls.time >= time).order_by(cls.time).all(),
            operation_name='aircon_state read range',
        )
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
    max_attempts = len(DB_RETRY_DELAYS_SECONDS) + 1

    for attempt in range(1, max_attempts + 1):
        try:
            Base.metadata.create_all(bind=engine)
            return True
        except OperationalError as error:
            if not is_database_locked(error):
                logger.exception({
                    'action': 'database initialization',
                    'status': 'database_error',
                    'message': 'database initialization failed',
                })
                raise

            if attempt < max_attempts:
                delay = DB_RETRY_DELAYS_SECONDS[attempt - 1]
                logger.warning({
                    'action': 'database initialization',
                    'status': 'database_locked_retry',
                    'message': 'database is locked or busy; retrying initialization',
                    'attempt': attempt,
                    'max_retries': len(DB_RETRY_DELAYS_SECONDS),
                    'retry_in_seconds': delay,
                })
                sleep(delay)
                continue

            logger.error({
                'action': 'database initialization',
                'status': 'database_locked_skipped',
                'message': 'database remained locked; continuing without schema initialization',
                'attempts': attempt,
            })
            return False
