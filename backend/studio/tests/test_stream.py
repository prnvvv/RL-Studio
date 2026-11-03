"""Live-stream latency probe: the server echoes client pings."""

from __future__ import annotations

from fastapi.testclient import TestClient

from .test_studio import BASE, _create, client  # noqa: F401  (client is a fixture)


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
