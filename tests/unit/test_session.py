from quackit.session import ActiveSessionState, HeartbeatManager, NoActiveSessionError


def test_require_active_session_raises_when_missing() -> None:
    state = ActiveSessionState()
    try:
        state.require_session_id()
    except NoActiveSessionError as exc:
        assert "No active session" in str(exc)
    else:
        raise AssertionError("NoActiveSessionError not raised")


def test_activate_and_clear_session() -> None:
    state = ActiveSessionState()
    state.activate("session-123")
    assert state.require_session_id() == "session-123"
    state.clear()
    try:
        state.require_session_id()
    except NoActiveSessionError:
        pass
    else:
        raise AssertionError("NoActiveSessionError not raised")


def test_heartbeat_manager_calls_fn_on_interval() -> None:
    calls: list[str] = []
    manager = HeartbeatManager(heartbeat_fn=lambda: calls.append("beat"), interval=0.05)
    manager.start()
    import time

    time.sleep(0.12)
    manager.stop()
    assert len(calls) >= 2


def test_heartbeat_manager_stop_prevents_further_calls() -> None:
    calls: list[str] = []
    manager = HeartbeatManager(heartbeat_fn=lambda: calls.append("beat"), interval=0.05)
    manager.start()
    manager.stop()
    count_after_stop = len(calls)
    import time

    time.sleep(0.1)
    assert len(calls) == count_after_stop
