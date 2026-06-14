import importlib.util
import sys
import threading
import time
import types
import unittest
from unittest import mock
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
AIRCON_STREAM_MODULE_PATH = (
    REPOSITORY_ROOT / 'controllers' / 'aircon_stream.py'
)
WEBSERVER_MODULE_PATH = REPOSITORY_ROOT / 'controllers' / 'webserver.py'


class DummyAircon:
    def __init__(self):
        self.off_calls = 0

    def off(self):
        self.off_calls += 1


class DummyAi:
    def __init__(self, failures=0):
        self.aircon = DummyAircon()
        self.failures = failures
        self.ctrl_calls = 0
        self.control_called = threading.Event()

    def ctrl_temp(self):
        self.ctrl_calls += 1
        self.control_called.set()
        if self.ctrl_calls <= self.failures:
            raise RuntimeError('simulated control failure')


class BlockingAi(DummyAi):
    def __init__(self):
        super().__init__()
        self.release_control = threading.Event()

    def ctrl_temp(self):
        self.ctrl_calls += 1
        self.control_called.set()
        self.release_control.wait(timeout=1.0)


class DummyLegacyRunner:
    def __init__(self, ai):
        self.ai = ai

    def run_cycle(self):
        return self.ai.ctrl_temp()

    def stop(self):
        return self.ai.aircon.off()


def load_aircon_stream_module():
    fake_ai_module = types.ModuleType('models.ai_aircon_ctrl')
    fake_ai_module.Ai = DummyAi
    fake_runner_module = types.ModuleType(
        'controllers.aircon_control_runner'
    )
    fake_runner_module.resolve_control_mode = (
        lambda configured_mode=None: configured_mode or 'legacy'
    )
    fake_runner_module.create_control_runner = (
        lambda mode=None, ai=None: DummyLegacyRunner(ai or DummyAi())
    )
    fake_settings = types.ModuleType('settings')
    fake_settings.time_interval_aircon_ai_sec = 0.01

    previous_ai_module = sys.modules.get('models.ai_aircon_ctrl')
    previous_runner_module = sys.modules.get(
        'controllers.aircon_control_runner'
    )
    previous_settings = sys.modules.get('settings')
    sys.modules['models.ai_aircon_ctrl'] = fake_ai_module
    sys.modules[
        'controllers.aircon_control_runner'
    ] = fake_runner_module
    sys.modules['settings'] = fake_settings

    try:
        spec = importlib.util.spec_from_file_location(
            'aircon_stream_under_test',
            AIRCON_STREAM_MODULE_PATH,
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        if previous_ai_module is None:
            sys.modules.pop('models.ai_aircon_ctrl', None)
        else:
            sys.modules['models.ai_aircon_ctrl'] = previous_ai_module
        if previous_runner_module is None:
            sys.modules.pop('controllers.aircon_control_runner', None)
        else:
            sys.modules[
                'controllers.aircon_control_runner'
            ] = previous_runner_module
        if previous_settings is None:
            sys.modules.pop('settings', None)
        else:
            sys.modules['settings'] = previous_settings


def wait_until(predicate, timeout=1.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.005)
    return predicate()


class FakeSession:
    @staticmethod
    def remove():
        return None


class FakeAirconState:
    @staticmethod
    def get_data_after_time(_time):
        return []


class FakeDataFrameTempHumid:
    pass


class AirconStreamTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = load_aircon_stream_module()

    def setUp(self):
        self.ai = DummyAi()
        self.stream = self.module.AirconStream(
            ai=self.ai,
            control_interval=0.02,
        )

    def tearDown(self):
        self.stream.stop_aircon()
        thread = self.stream.thread
        if thread is not None:
            thread.join(timeout=1.0)

    def test_start_creates_one_thread_and_duplicate_start_is_idempotent(self):
        self.assertTrue(self.stream.start_aircon())
        self.assertTrue(self.ai.control_called.wait(timeout=1.0))
        first_thread = self.stream.thread

        self.assertFalse(self.stream.start_aircon())
        self.assertIs(self.stream.thread, first_thread)
        self.assertTrue(first_thread.is_alive())

        status = self.stream.get_status()
        self.assertTrue(status['running'])
        self.assertFalse(status['stop_requested'])
        self.assertTrue(status['thread_alive'])
        self.assertEqual(status['state'], 'running')

    def test_concurrent_start_requests_create_only_one_thread(self):
        start_results = []
        start_barrier = threading.Barrier(6)

        def start_control():
            start_barrier.wait()
            start_results.append(self.stream.start_aircon())

        callers = [
            threading.Thread(target=start_control)
            for _ in range(6)
        ]
        for caller in callers:
            caller.start()
        for caller in callers:
            caller.join(timeout=1.0)

        self.assertEqual(start_results.count(True), 1)
        self.assertEqual(start_results.count(False), 5)
        self.assertTrue(self.ai.control_called.wait(timeout=1.0))
        self.assertTrue(self.stream.get_status()['thread_alive'])

    def test_start_creates_one_runner_and_duplicate_start_reuses_it(self):
        runners = []

        def runner_factory(mode=None, ai=None):
            del mode
            runner = DummyLegacyRunner(ai)
            runners.append(runner)
            return runner

        stream = self.module.AirconStream(
            ai=self.ai,
            control_interval=0.02,
            runner_factory=runner_factory,
        )
        try:
            self.assertTrue(stream.start_aircon())
            self.assertTrue(self.ai.control_called.wait(timeout=1.0))
            self.assertFalse(stream.start_aircon())
            self.assertEqual(len(runners), 1)
            self.assertIs(stream.runner, runners[0])
        finally:
            stream.stop_aircon()
            thread = stream.thread
            if thread is not None:
                thread.join(timeout=1.0)

    def test_stop_requests_shutdown_and_thread_exits(self):
        self.assertTrue(self.stream.start_aircon())
        self.assertTrue(self.ai.control_called.wait(timeout=1.0))

        self.assertTrue(self.stream.stop_aircon())
        self.assertTrue(wait_until(
            lambda: not self.stream.get_status()['thread_alive']
        ))

        status = self.stream.get_status()
        self.assertFalse(status['running'])
        self.assertFalse(status['stop_requested'])
        self.assertFalse(status['stop'])
        self.assertEqual(status['state'], 'stopped')
        self.assertIsNotNone(status['last_stopped_at'])
        self.assertEqual(self.ai.aircon.off_calls, 1)

    def test_stop_requested_is_true_only_while_thread_is_stopping(self):
        blocking_ai = BlockingAi()
        stream = self.module.AirconStream(
            ai=blocking_ai,
            control_interval=0.02,
        )
        try:
            self.assertTrue(stream.start_aircon())
            self.assertTrue(blocking_ai.control_called.wait(timeout=1.0))

            self.assertTrue(stream.stop_aircon())
            stopping_status = stream.get_status()
            self.assertEqual(stopping_status['state'], 'stopping')
            self.assertTrue(stopping_status['stop_requested'])
            self.assertTrue(stopping_status['stop'])

            blocking_ai.release_control.set()
            self.assertTrue(wait_until(
                lambda: not stream.get_status()['thread_alive']
            ))
            stopped_status = stream.get_status()
            self.assertEqual(stopped_status['state'], 'stopped')
            self.assertFalse(stopped_status['stop_requested'])
            self.assertFalse(stopped_status['stop'])
        finally:
            blocking_ai.release_control.set()
            stream.stop_aircon()
            thread = stream.thread
            if thread is not None:
                thread.join(timeout=1.0)

    def test_repeated_stop_does_not_leave_stop_requested_set(self):
        self.assertTrue(self.stream.start_aircon())
        self.assertTrue(self.ai.control_called.wait(timeout=1.0))

        self.assertTrue(self.stream.stop_aircon())
        self.assertTrue(self.stream.stop_aircon())
        self.assertTrue(wait_until(
            lambda: not self.stream.get_status()['thread_alive']
        ))

        status = self.stream.get_status()
        self.assertEqual(status['state'], 'stopped')
        self.assertFalse(status['stop_requested'])
        self.assertFalse(status['stop'])

    def test_control_can_restart_after_previous_thread_stops(self):
        self.assertTrue(self.stream.start_aircon())
        self.assertTrue(self.ai.control_called.wait(timeout=1.0))
        first_thread = self.stream.thread
        self.stream.stop_aircon()
        first_thread.join(timeout=1.0)

        self.ai.control_called.clear()
        self.assertTrue(self.stream.start_aircon())
        self.assertTrue(self.ai.control_called.wait(timeout=1.0))
        self.assertIsNot(self.stream.thread, first_thread)
        status = self.stream.get_status()
        self.assertTrue(status['running'])
        self.assertFalse(status['stop_requested'])

    def test_control_exception_is_recorded_and_next_cycle_runs(self):
        self.ai.failures = 1
        self.assertTrue(self.stream.start_aircon())
        self.assertTrue(wait_until(lambda: self.ai.ctrl_calls >= 2))

        status = self.stream.get_status()
        self.assertTrue(status['running'])
        self.assertIn('simulated control failure', status['last_error'])

    def test_stopped_status_matches_thread_state(self):
        status = self.stream.get_status()

        self.assertFalse(status['is_running'])
        self.assertFalse(status['running'])
        self.assertFalse(status['thread_alive'])
        self.assertFalse(status['stop_requested'])
        self.assertEqual(status['state'], 'stopped')
        self.assertEqual(status['control_mode'], 'legacy')
        self.assertIsNone(status['last_error'])

    def test_web_api_start_is_idempotent_and_status_tracks_thread(self):
        web_stream = self.module.AirconStream(
            ai=DummyAi(),
            control_interval=0.02,
        )
        fake_stream_module = types.ModuleType('controllers.aircon_stream')
        fake_stream_module.aircon_stream = web_stream
        fake_df_module = types.ModuleType('models.df_temp_humid')
        fake_df_module.DataFrameTempHumid = FakeDataFrameTempHumid
        fake_base_module = types.ModuleType('models.base')
        fake_base_module.AirconState = FakeAirconState
        fake_base_module.Session = FakeSession
        fake_settings = types.ModuleType('settings')
        fake_settings.web_port = 5000

        fake_modules = {
            'controllers.aircon_stream': fake_stream_module,
            'models.df_temp_humid': fake_df_module,
            'models.base': fake_base_module,
            'settings': fake_settings,
        }
        try:
            with mock.patch.dict(sys.modules, fake_modules):
                spec = importlib.util.spec_from_file_location(
                    'webserver_under_test',
                    WEBSERVER_MODULE_PATH,
                )
                webserver = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(webserver)
                client = webserver.app.test_client()

                first_start = client.post('/api/aircon/start/')
                duplicate_start = client.post('/api/aircon/start/')
                running_status = client.get('/api/aircon/status/')

                self.assertEqual(first_start.status_code, 200)
                self.assertTrue(first_start.get_json()['success'])
                self.assertEqual(duplicate_start.status_code, 200)
                self.assertTrue(
                    duplicate_start.get_json()['already_running']
                )
                self.assertTrue(
                    running_status.get_json()['status']['thread_alive']
                )

                stop_response = client.post('/api/aircon/stop/')
                self.assertEqual(stop_response.status_code, 200)
                self.assertTrue(wait_until(
                    lambda: not web_stream.get_status()['thread_alive']
                ))

                stopped_status = client.get('/api/aircon/status/').get_json()
                self.assertEqual(stopped_status['status']['state'], 'stopped')
                self.assertFalse(stopped_status['status']['thread_alive'])
                self.assertFalse(
                    stopped_status['status']['stop_requested']
                )
        finally:
            web_stream.stop_aircon()
            thread = web_stream.thread
            if thread is not None:
                thread.join(timeout=1.0)


if __name__ == '__main__':
    unittest.main()
