from __future__ import annotations

import logging
import threading
from collections.abc import Callable

log = logging.getLogger(__name__)


class NoActiveSessionError(RuntimeError):
    pass


class ActiveSessionState:
    def __init__(self) -> None:
        self._active_session_id: str | None = None
        self._lock = threading.Lock()

    def activate(self, session_id: str) -> None:
        with self._lock:
            self._active_session_id = session_id

    def clear(self) -> None:
        with self._lock:
            self._active_session_id = None

    def require_session_id(self) -> str:
        with self._lock:
            if self._active_session_id is None:
                raise NoActiveSessionError("No active session. Call start_session() or activate_session() first.")
            return self._active_session_id


class HeartbeatManager:
    def __init__(self, heartbeat_fn: Callable[[], None], interval: float = 30) -> None:
        self._heartbeat_fn = heartbeat_fn
        self._interval = interval
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()

    def start(self) -> None:
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                log.debug("Heartbeat thread already running")
                return
            self._stop_event.clear()
            t = threading.Thread(target=self._run, daemon=True)
            self._thread = t
            t.start()
        log.debug("Heartbeat thread started")

    def stop(self) -> None:
        self._stop_event.set()
        with self._lock:
            t = self._thread
            self._thread = None
        if t is not None and t.is_alive():
            t.join(timeout=5)
        log.debug("Heartbeat thread stopped")

    def _run(self) -> None:
        while not self._stop_event.wait(self._interval):
            try:
                self._heartbeat_fn()
            except Exception:
                log.exception("Heartbeat function failed, continuing")
