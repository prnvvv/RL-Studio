"""Live-stream latency probe: the server echoes client pings."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from .test_studio import BASE, _create


def test_ping_is_echoed_as_pong_with_the_same_timestamp(client: TestClient) -> None:
    sid = _create(client)
    with client.websocket_connect(f"{BASE}/sessions/{sid}/stream") as ws:
        assert ws.receive_json()["type"] == "snapshot"
        ws.send_json({"type": "ping", "t": 1234.5})
        for _ in range(40):
            message = ws.receive_json()
            if message["type"] == "pong":
                assert message["t"] == 1234.5
                return
    raise AssertionError("no pong received")


def test_malformed_client_messages_do_not_break_the_stream(client: TestClient) -> None:
    sid = _create(client)
    with client.websocket_connect(f"{BASE}/sessions/{sid}/stream") as ws:
        assert ws.receive_json()["type"] == "snapshot"
        ws.send_text("not json")
        ws.send_json({"type": "ping", "t": "bad"})
        ws.send_json([1, 2, 3])
        ws.send_json({"type": "ping", "t": 7})
        for _ in range(40):
            message = ws.receive_json()
            if message["type"] == "pong":
                assert message["t"] == 7
                return
    raise AssertionError("stream stopped answering after malformed input")


# ------------------------------------------------------------------ wire robustness


def test_encoding_survives_numpy_values_and_non_finite_numbers() -> None:
    import json

    import numpy as np

    from backend.api.routers.studio import encode_message

    wire = encode_message({"a": np.float32(1.5), "b": np.arange(3), "loss": float("nan"), "c": [float("inf"), 2.0]})
    # Strict JSON: what a browser's JSON.parse accepts.
    assert json.loads(wire, parse_constant=lambda name: (_ for _ in ()).throw(ValueError(name))) == {
        "a": 1.5,
        "b": [0, 1, 2],
        "loss": None,
        "c": [None, 2.0],
    }


def test_a_client_that_fell_behind_the_event_ring_is_resynchronised_with_a_snapshot() -> None:
    from backend.api.routers.studio import _next_messages
    from backend.studio.hub import SessionHub

    class FakeSession:
        def __init__(self) -> None:
            self.hub = SessionHub("ses_00000001", max_events=5)

        def snapshot(self) -> dict:
            return {"seq": self.hub.last_seq(), "marker": "fresh"}

    session = FakeSession()
    for i in range(3):
        session.hub.publish("log", {"i": i})
    messages, seq, _ = _next_messages(session, 0, 0)
    assert [m["seq"] for m in messages] == [1, 2, 3] and seq == 3  # in step: plain events

    for i in range(20):  # the client stalls while 20 more events overflow the 5-slot ring
        session.hub.publish("log", {"i": i})
    messages, seq, _ = _next_messages(session, seq, 0)
    assert len(messages) == 1 and messages[0]["type"] == "snapshot"
    assert messages[0]["payload"]["marker"] == "fresh" and seq == 23

    assert _next_messages(session, seq, 0)[0] == []  # and then it is back in step


def test_an_unexpected_server_error_closes_the_socket_with_a_reason(client: TestClient, monkeypatch) -> None:
    import backend.api.routers.studio as router

    sid = _create(client)

    def boom(*_args, **_kwargs):
        raise ValueError("synthetic failure")

    monkeypatch.setattr(router, "_next_messages", boom)
    with client.websocket_connect(f"{BASE}/sessions/{sid}/stream") as ws:
        assert ws.receive_json()["type"] == "snapshot"
        from starlette.websockets import WebSocketDisconnect

        with pytest.raises(WebSocketDisconnect) as info:
            ws.receive_json()
    assert info.value.code == 1011 and "server logs" in info.value.reason


def test_after_stop_a_new_session_can_be_initialised_and_trained(client: TestClient) -> None:
    """The workflow behind the UI's unlocked configuration: Stop, change settings, Initialize, Train."""
    import time

    slow = {"total_timesteps": 200_000, "simulation_speed": 8, "checkpoint_every": 0, "eval_every": 0}
    first = _create(client, training=slow)
    assert client.post(f"{BASE}/sessions/{first}/start").status_code == 200
    assert client.post(f"{BASE}/sessions/{first}/stop").status_code == 200
    for _ in range(100):
        if client.get(f"{BASE}/sessions/{first}").json()["status"] == "stopped":
            break
        time.sleep(0.1)
    else:
        raise AssertionError("first session did not stop")

    second = _create(client, agent="A2C", environment="warehouse", training=slow)
    assert client.post(f"{BASE}/sessions/{second}/start").status_code == 200
    snap = client.get(f"{BASE}/sessions/{second}").json()
    assert snap["config"]["agent"] == "A2C" and snap["config"]["environment"] == "warehouse"
    client.post(f"{BASE}/sessions/{second}/stop")
