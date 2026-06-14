import importlib.util
import sqlite3
import sys
import tempfile
import threading
import time
import types
import unittest
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy import text
from sqlalchemy.orm import scoped_session
from sqlalchemy.orm import sessionmaker


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
BASE_MODULE_PATH = REPOSITORY_ROOT / 'models' / 'base.py'


def load_base_module(database_path):
    fake_settings = types.ModuleType('settings')
    fake_settings.db_name = str(database_path)
    previous_settings = sys.modules.get('settings')
    sys.modules['settings'] = fake_settings

    try:
        spec = importlib.util.spec_from_file_location(
            'db_retry_base_under_test',
            BASE_MODULE_PATH,
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        if previous_settings is None:
            sys.modules.pop('settings', None)
        else:
            sys.modules['settings'] = previous_settings


class DatabaseLockRetryTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temp_dir.name) / 'lock-test.sqlite3'
        self.base = load_base_module(self.database_path)
        self.engine = create_engine(
            f'sqlite:///{self.database_path}',
            connect_args={'timeout': 0.01, 'check_same_thread': False},
        )
        self.session_registry = scoped_session(sessionmaker(bind=self.engine))

        with self.engine.begin() as connection:
            connection.execute(text(
                'CREATE TABLE retry_test (id INTEGER PRIMARY KEY, value TEXT)'
            ))

    def tearDown(self):
        self.session_registry.remove()
        self.engine.dispose()
        self.base.engine.dispose()
        self.temp_dir.cleanup()

    def _insert(self, record_id):
        def operation(session):
            session.execute(
                text('INSERT INTO retry_test (id, value) VALUES (:id, :value)'),
                {'id': record_id, 'value': 'ok'},
            )
            return record_id

        return operation

    def test_application_engine_configures_wal_and_busy_timeout(self):
        self.assertTrue(self.base.init_db())

        with self.base.engine.connect() as connection:
            journal_mode = connection.execute(
                text('PRAGMA journal_mode')
            ).scalar()
            busy_timeout = connection.execute(
                text('PRAGMA busy_timeout')
            ).scalar()

        self.assertEqual(journal_mode.lower(), 'wal')
        self.assertEqual(busy_timeout, self.base.DB_BUSY_TIMEOUT_MS)

    def test_locked_write_retries_then_succeeds(self):
        locking_connection = sqlite3.connect(
            self.database_path,
            timeout=0.01,
            check_same_thread=False,
        )
        locking_connection.execute('BEGIN EXCLUSIVE')

        def release_lock():
            time.sleep(0.04)
            locking_connection.rollback()
            locking_connection.close()

        release_thread = threading.Thread(target=release_lock)
        release_thread.start()
        try:
            result = self.base.execute_db_operation(
                self._insert(1),
                operation_name='temp_humid write test',
                write=True,
                session_registry=self.session_registry,
                retry_delays=(0.01, 0.03, 0.05),
            )
        finally:
            release_thread.join()

        self.assertEqual(result, 1)
        with self.engine.connect() as connection:
            count = connection.execute(
                text('SELECT COUNT(*) FROM retry_test')
            ).scalar()
        self.assertEqual(count, 1)

    def test_locked_write_exhausts_retries_without_terminating_process(self):
        locking_connection = sqlite3.connect(
            self.database_path,
            timeout=0.01,
            check_same_thread=False,
        )
        locking_connection.execute('BEGIN EXCLUSIVE')
        try:
            with self.assertRaises(self.base.DatabaseLockError):
                self.base.execute_db_operation(
                    self._insert(2),
                    operation_name='aircon_state write test',
                    write=True,
                    session_registry=self.session_registry,
                    retry_delays=(0.01, 0.02),
                )
        finally:
            locking_connection.rollback()
            locking_connection.close()

        result = self.base.execute_db_operation(
            self._insert(3),
            operation_name='aircon_state write recovery test',
            write=True,
            session_registry=self.session_registry,
            retry_delays=(),
        )
        self.assertEqual(result, 3)


if __name__ == '__main__':
    unittest.main()
