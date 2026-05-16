from __future__ import annotations

import threading

from quackit.session import ActiveSessionState, HeartbeatManager


def test_active_session_state_concurrent_activate() -> None:
    state = ActiveSessionState()
    results: list[str] = []
    lock = threading.Lock()

    def worker(i: int) -> None:
        state.activate(f"session-{i}")
        sid = state.require_session_id()
        with lock:
            results.append(sid)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(results) == 10
    assert state.require_session_id() is not None


def test_active_session_state_concurrent_clear_activate() -> None:
    state = ActiveSessionState()
    state.activate("session-init")

    def toggle() -> None:
        for _ in range(50):
            state.clear()
            state.activate("session-toggled")

    threads = [threading.Thread(target=toggle) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert state.require_session_id() == "session-toggled"


def test_active_session_state_no_deadlock_on_require() -> None:
    state = ActiveSessionState()
    state.activate("session-lock")
    errors: list[Exception] = []
    lock = threading.Lock()

    def reader() -> None:
        try:
            for _ in range(100):
                sid = state.require_session_id()
                assert sid is not None
        except Exception as e:
            with lock:
                errors.append(e)

    def writer() -> None:
        try:
            for i in range(100):
                state.activate(f"session-{i}")
        except Exception as e:
            with lock:
                errors.append(e)

    threads = [threading.Thread(target=reader) for _ in range(4)]
    threads += [threading.Thread(target=writer) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(errors) == 0


def test_active_session_state_concurrent_clear_causes_no_error() -> None:
    state = ActiveSessionState()
    state.activate("session-clear-test")
    errors: list[Exception] = []
    lock = threading.Lock()

    def clearer() -> None:
        for _ in range(50):
            try:
                state.clear()
            except Exception as e:
                with lock:
                    errors.append(e)

    threads = [threading.Thread(target=clearer) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(errors) == 0


def test_heartbeat_concurrent_start_stop() -> None:
    calls: list[str] = []
    manager = HeartbeatManager(heartbeat_fn=lambda: calls.append("beat"), interval=0.005)

    def hammer() -> None:
        for _ in range(20):
            manager.start()
            manager.stop()

    threads = [threading.Thread(target=hammer) for _ in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()


def test_heartbeat_concurrent_start_stop_with_active_beats() -> None:
    calls: list[str] = []
    threading.Lock()
    manager = HeartbeatManager(heartbeat_fn=lambda: calls.append("beat"), interval=0.01)
    manager.start()

    def concurrent_stops() -> None:
        for _ in range(10):
            manager.stop()
            manager.start()

    threads = [threading.Thread(target=concurrent_stops) for _ in range(3)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    manager.stop()


def test_heartbeat_fn_exception_does_not_propagate() -> None:
    call_count = 0

    def failing_fn() -> None:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise RuntimeError("heartbeat failure")

    manager = HeartbeatManager(heartbeat_fn=failing_fn, interval=0.01)
    manager.start()
    import time

    time.sleep(0.03)
    manager.stop()

    assert call_count >= 2
