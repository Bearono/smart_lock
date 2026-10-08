"""Worker-owned device health reporting; never infer lock state from a command."""
import logging
from threading import Event, Thread

logger = logging.getLogger(__name__)


class HeartbeatWorker:
    def __init__(self, transmitter, camera, interval=30, actuator=None):
        if interval <= 0:
            raise ValueError('Heartbeat interval must be positive')
        self.transmitter = transmitter
        self.camera = camera
        self.actuator = actuator
        self.interval = interval
        self.stop_event = Event()
        self.thread = None

    def report_once(self):
        try:
            camera_status = 'ONLINE' if self.camera.capture_frame() is not None else 'OFFLINE'
        except Exception:
            logger.exception('Camera health check failed')
            camera_status = 'ERROR'
        lock_status = 'UNKNOWN'
        if self.actuator is not None:
            try:
                observed = self.actuator.read_state()
                if observed in ('LOCKED', 'UNLOCKED'):
                    lock_status = observed
            except Exception:
                logger.exception('Lock feedback unavailable')
        return self.transmitter.heartbeat(lock_status, camera_status=camera_status)

    def _run(self):
        while not self.stop_event.is_set():
            try:
                self.report_once()
            except Exception:
                logger.exception('Device heartbeat failed; retrying next interval')
            self.stop_event.wait(self.interval)

    def start(self):
        if self.thread and self.thread.is_alive():
            return
        self.stop_event.clear()
        self.thread = Thread(target=self._run, name='device-heartbeat', daemon=True)
        self.thread.start()

    def stop(self):
        self.stop_event.set()
        if self.thread:
            self.thread.join(timeout=2)


class CommandWorker:
    """Polling is independent from potentially slow camera health checks."""
    def __init__(self, executor, interval=1):
        if interval <= 0:
            raise ValueError('Command interval must be positive')
        self.executor = executor
        self.interval = interval
        self.stop_event = Event()
        self.thread = None

    def _run(self):
        while not self.stop_event.is_set():
            try:
                self.executor.run_once()
            except Exception:
                logger.exception('Command polling failed; retrying next interval')
            self.stop_event.wait(self.interval)

    def start(self):
        if self.thread and self.thread.is_alive():
            return
        self.stop_event.clear()
        self.thread = Thread(target=self._run, name='device-commands', daemon=True)
        self.thread.start()

    def stop(self):
        self.stop_event.set()
        if self.thread:
            self.thread.join(timeout=2)
