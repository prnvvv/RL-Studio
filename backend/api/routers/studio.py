"""Interactive studio API: catalog, session lifecycle, snapshots, live stream."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, ConfigDict, Field

from backend.studio.catalog import build_catalog
from backend.studio.manager import manager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/studio", tags=["studio"])

STREAM_INTERVAL_S = 0.05


class SessionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    agent: str = Field(max_length=32)
    environment: str = Field(max_length=32)
    name: str | None = Field(default=None, max_length=80)
    agent_params: dict[str, Any] = Field(default_factory=dict)
    env_params: dict[str, Any] = Field(default_factory=dict)
    training: dict[str, Any] = Field(default_factory=dict)


class SpeedRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    speed: float


@router.get("/catalog")
def get_catalog() -> dict[str, Any]:
    return build_catalog()


@router.post("/sessions", status_code=201)
def create_session(request: SessionRequest) -> dict[str, Any]:
    payload = request.model_dump(exclude={"name"})
    session = manager.create(payload, request.name)
    return session.snapshot()


@router.get("/sessions")
def list_sessions() -> dict[str, Any]:
    return {"sessions": manager.list()}


@router.get("/history")
def list_history() -> dict[str, Any]:
    return {"experiments": manager.history()}


@router.get("/history/{run_id}")
def get_history_record(run_id: str) -> dict[str, Any]:
    return manager.history_record(run_id)


@router.get("/sessions/{session_id}")
def get_session(session_id: str) -> dict[str, Any]:
    return manager.get(session_id).snapshot()


@router.post("/sessions/{session_id}/start")
def start_session(session_id: str) -> dict[str, Any]:
    return manager.start(session_id)


@router.post("/sessions/{session_id}/pause")
def pause_session(session_id: str) -> dict[str, Any]:
    return manager.get(session_id).pause()


@router.post("/sessions/{session_id}/resume")
def resume_session(session_id: str) -> dict[str, Any]:
    return manager.get(session_id).resume()


@router.post("/sessions/{session_id}/stop")
def stop_session(session_id: str) -> dict[str, Any]:
    return manager.get(session_id).stop()


@router.post("/sessions/{session_id}/reset")
def reset_session(session_id: str) -> dict[str, Any]:
    return manager.get(session_id).reset()


@router.post("/sessions/{session_id}/speed")
def set_speed(session_id: str, request: SpeedRequest) -> dict[str, Any]:
    return manager.get(session_id).set_speed(request.speed)


@router.get("/sessions/{session_id}/events")
def get_events(session_id: str, after: int = Query(0, ge=0), limit: int = Query(500, ge=1, le=2000)) -> dict[str, Any]:
    """Polling fallback and resync source: events after a sequence number."""
    session = manager.get(session_id)
    events, gap = session.hub.since(after, limit)
    return {"events": events, "gap": gap, "last_seq": session.hub.last_seq()}


@router.websocket("/sessions/{session_id}/stream")
async def stream(websocket: WebSocket, session_id: str, after: int = 0) -> None:
    """Live stream: ``snapshot`` first, then ordered events and coalesced frames.

    A reconnecting client may pass ``after`` (the last sequence it processed);
    it always receives a fresh snapshot so a gap can never leave it stale.
    """
    try:
        session = manager.get(session_id)
    except Exception:  # noqa: BLE001 - unknown session at the socket boundary
        await websocket.close(code=4404)
        return
    await websocket.accept()
    try:
        snapshot = session.snapshot()
        await websocket.send_json({"type": "snapshot", "payload": snapshot})
        last_seq = snapshot["seq"]
        last_frame = (session.hub.latest_frame() or {}).get("frame_seq", 0)
        while True:
            events, _gap = session.hub.since(last_seq)
            for event in events:
                await websocket.send_json(event)
                last_seq = event["seq"]
            frame = session.hub.latest_frame()
            if frame is not None and frame["frame_seq"] != last_frame:
                last_frame = frame["frame_seq"]
                await websocket.send_json(frame)
            await asyncio.sleep(STREAM_INTERVAL_S)
    except WebSocketDisconnect:
        return
    except RuntimeError:
        # Socket already closed by the peer while sending.
        return
