import logging
from datetime import datetime
from threading import current_thread
from threading import Event
from threading import Lock
from threading import Thread

from controllers.aircon_control_runner import create_control_runner
from controllers.aircon_control_runner import resolve_control_mode
import settings

logger = logging.getLogger(__name__)


class AirconStream(object):
    STOPPED = 'stopped'
    STARTING = 'starting'
    RUNNING = 'running'
    STOPPING = 'stopping'
    ERROR = 'error'

    def __init__(
        self,
        ai=None,
        control_interval=None,
        control_mode=None,
        runner_factory=None,
    ) -> None:
        self.stop = False
        self.ai = ai
        self.control_mode = resolve_control_mode(
            configured_mode=control_mode
        )
        self.runner_factory = runner_factory or create_control_runner
        self.runner = None
        self.control_interval = (
            settings.time_interval_aircon_ai_sec
            if control_interval is None
            else control_interval
        )
        self.thread = None
        self.is_running = False
        self.state = self.STOPPED
        self.last_error = None
        self.last_started_at = None
        self.last_stopped_at = None
        self._stop_event = Event()
        self._lifecycle_lock = Lock()

    @staticmethod
    def _now():
        return datetime.now().isoformat(timespec='seconds')

    @staticmethod
    def _error_message(error):
        return f'{type(error).__name__}: {error}'

    def stream_aircon_ctrl(self):
        with self._lifecycle_lock:
            self.is_running = True
            self.state = (
                self.STOPPING
                if self._stop_event.is_set()
                else self.RUNNING
            )
        logger.info('stream_aircon_ctrl run')

        ended_with_error = False
        try:
            while not self._stop_event.is_set():
                try:
                    self.runner.run_cycle()
                except Exception as error:
                    with self._lifecycle_lock:
                        self.last_error = self._error_message(error)
                    logger.exception({
                        'action': 'control loop',
                        'status': 'cycle_skipped',
                        'message': 'control cycle failed; continuing with next cycle',
                    })
                if self._stop_event.wait(self.control_interval):
                    break
        except Exception as error:
            ended_with_error = True
            with self._lifecycle_lock:
                self.last_error = self._error_message(error)
                self.state = self.ERROR
            logger.exception({
                'action': 'control loop',
                'status': 'thread_stopped',
                'message': 'aircon control thread terminated unexpectedly',
            })
        finally:
            with self._lifecycle_lock:
                self.is_running = False
                self._stop_event.clear()
                self.stop = False
                if not ended_with_error:
                    self.state = self.STOPPED
                self.last_stopped_at = self._now()
                if self.thread is current_thread():
                    self.thread = None
            logger.info('stream_aircon_ctrl stopped')

    def stop_aircon(self):
        """エアコンをオフにして、制御ループを停止する"""
        with self._lifecycle_lock:
            self._stop_event.set()
            self.stop = True
            thread_alive = self.thread is not None and self.thread.is_alive()
            if thread_alive:
                self.state = self.STOPPING
            else:
                self._stop_event.clear()
                self.stop = False
                self.is_running = False
                self.state = self.STOPPED
                self.thread = None
                self.last_stopped_at = self._now()

        logger.info({
            'action': 'aircon stop',
            'status': 'stop_requested',
            'control_mode': self.control_mode,
        })
        try:
            runner = self.runner
            if runner is None:
                runner = self.runner_factory(
                    mode=self.control_mode,
                    ai=self.ai,
                )
                self.runner = runner
            runner.stop()
        except Exception as error:
            with self._lifecycle_lock:
                self.last_error = self._error_message(error)
            logger.exception({
                'action': 'aircon stop',
                'status': 'ir_send_failed',
                'message': 'stop requested, but air conditioner off command failed',
            })

        return True

    def start_aircon(self):
        """エアコン制御を開始する（新しいスレッドで実行）"""
        with self._lifecycle_lock:
            thread_alive = self.thread is not None and self.thread.is_alive()
            if thread_alive:
                if self._stop_event.is_set():
                    logger.info("Aircon control is stopping; start request ignored")
                else:
                    logger.info("Aircon control is already running")
                return False

            self.thread = None
            self.stop = False
            self.is_running = False
            self._stop_event.clear()
            self.state = self.STARTING
            self.last_error = None
            self.last_started_at = self._now()
            try:
                self.runner = self.runner_factory(
                    mode=self.control_mode,
                    ai=self.ai,
                )
            except Exception as error:
                self.runner = None
                self.state = self.ERROR
                self.last_error = self._error_message(error)
                logger.exception({
                    'action': 'aircon start',
                    'status': 'runner_create_failed',
                    'message': 'failed to create aircon control runner',
                })
                return False
            thread = Thread(
                target=self.stream_aircon_ctrl,
                name='aircon-control',
                daemon=True,
            )
            self.thread = thread
            try:
                thread.start()
            except Exception as error:
                self.thread = None
                self.state = self.ERROR
                self.last_error = self._error_message(error)
                logger.exception({
                    'action': 'aircon start',
                    'status': 'thread_start_failed',
                    'message': 'failed to start aircon control thread',
                })
                return False

        logger.info("Aircon control started")
        return True

    def get_status(self):
        """エアコン制御の状態を返す"""
        with self._lifecycle_lock:
            thread_alive = self.thread is not None and self.thread.is_alive()
            stop_requested = self._stop_event.is_set()
            running = (
                thread_alive
                and self.state == self.RUNNING
                and not stop_requested
            )
            return {
                # Keep the original fields for the existing browser code.
                'is_running': running,
                'stop': stop_requested,
                'running': running,
                'stop_requested': stop_requested,
                'thread_alive': thread_alive,
                'state': self.state,
                'last_error': self.last_error,
                'last_started_at': self.last_started_at,
                'last_stopped_at': self.last_stopped_at,
                'control_mode': self.control_mode,
            }


aircon_stream = AirconStream()

# ユーザーからの入力を待つ関数
def wait_for_stop_command(aircon_stream):
    while True:
        user_input = input("Enter 'stop' to stop the air conditioner: ")
        if user_input.lower() == 'stop':
            aircon_stream.stop_aircon()
            break
