"""Interactive studio API: catalog, session lifecycle, snapshots, live stream."""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import re
from collections.abc import Iterator
from typing import Any

from fastapi import APIRouter, Query, Request, Response, WebSocket, WebSocketDisconnect
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field, StrictBool

from backend.database.exceptions import ConflictError, NotFoundError, StudioError
from backend.studio import custom
from backend.studio.catalog import build_catalog
from backend.studio.manager import manager
from backend.studio.session import store_path
from backend.studio.store import MAX_PAGE, TrajectoryReader

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


class ControlRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    active: StrictBool


class BrainRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: StrictBool


class ChaosRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: StrictBool | None = None
    intensity: float | None = Field(default=None, ge=0.0, le=1.0)
    kinds: list[str] | None = Field(default=None, max_length=8)


class ChaosTriggerRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: str = Field(max_length=32)


class ActionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    #: An int for discrete spaces or a list of floats for box spaces; validated against the real space.
    action: Any


class BattleSide(BaseModel):
    model_config = ConfigDict(extra="forbid")

    agent: str = Field(max_length=64)
    agent_params: dict[str, Any] = Field(default_factory=dict)


class BattleRequest(BaseModel):
    """Two agents on one environment, one seed and one training budget."""

    model_config = ConfigDict(extra="forbid")

    environment: str = Field(max_length=64)
    name: str | None = Field(default=None, max_length=60)
    env_params: dict[str, Any] = Field(default_factory=dict)
    training: dict[str, Any] = Field(default_factory=dict)
    a: BattleSide
    b: BattleSide


class SpeedRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    speed: float


@router.get("/catalog")
def get_catalog() -> dict[str, Any]:
    return build_catalog()


MAX_LAYOUT_BYTES = 64 * 1024


@router.get("/models")
def list_models() -> dict[str, Any]:
    return {"models": [{k: v for k, v in m.items() if k != "stored_as"} for m in custom.list_models()]}


@router.post("/models/upload", status_code=201)
async def upload_model(
    request: Request,
    response: Response,
    filename: str = Query(..., min_length=1, max_length=200),
    name: str | None = Query(None, max_length=60),
) -> dict[str, Any]:
    """Upload a model as the raw request body (``?filename=policy.zip``).

    The file is streamed to a quarantine path with a hard size cap, validated
    without executing anything inside it, and only then moved into the library.
    """
    custom.require_supported_extension(filename)
    declared = request.headers.get("content-length", "")
    if declared.isdigit() and int(declared) > custom.MAX_MODEL_BYTES:
        raise custom.PayloadTooLarge("The file is too large", details={"max_bytes": custom.MAX_MODEL_BYTES})
    temp = custom.new_incoming_path()
    try:
        size = 0
        with temp.open("wb") as handle:
            async for chunk in request.stream():
                size += len(chunk)
                if size > custom.MAX_MODEL_BYTES:
                    raise custom.PayloadTooLarge("The file is too large", details={"max_bytes": custom.MAX_MODEL_BYTES})
                handle.write(chunk)
        record, duplicate = await run_in_threadpool(custom.store_model, temp, filename, name)
    finally:
        temp.unlink(missing_ok=True)
    if duplicate:
        response.status_code = 200
    return {"model": record, "duplicate": duplicate}


@router.delete("/models/{model_id}")
def delete_model(model_id: str) -> dict[str, Any]:
    record = custom.get_model(model_id)
    if record["key"] in manager.active_references():
        raise ConflictError("This model is in use by a running session", details={"model_id": record["model_id"]})
    custom.delete_model(model_id)
    return {"deleted": record["model_id"]}


@router.post("/environments/upload", status_code=201)
async def upload_environment(request: Request, response: Response) -> dict[str, Any]:
    """Register a declarative warehouse grid layout (JSON). No code is executed."""
    body = await request.body()
    if len(body) > MAX_LAYOUT_BYTES:
        raise custom.PayloadTooLarge("The layout is too large", details={"max_bytes": MAX_LAYOUT_BYTES})
    try:
        raw = json.loads(body)
    except ValueError:
        raise custom.ValidationError("The layout is not valid JSON", details={"errors": [{"field": "layout", "message": "not valid JSON"}]}) from None
    record, duplicate = await run_in_threadpool(custom.store_environment, raw)
    if duplicate:
        response.status_code = 200
    return {"environment": record, "duplicate": duplicate}


@router.delete("/environments/{env_id}")
def delete_environment(env_id: str) -> dict[str, Any]:
    record = custom.get_environment_record(env_id)
    if record["key"] in manager.active_references():
        raise ConflictError("This environment is in use by a running session", details={"env_id": record["env_id"]})
    custom.delete_environment(env_id)
    return {"deleted": record["env_id"]}


@router.post("/sessions", status_code=201)
def create_session(request: SessionRequest) -> dict[str, Any]:
    payload = request.model_dump(exclude={"name"})
    session = manager.create(payload, request.name)
    return session.snapshot()


@router.post("/battles", status_code=201)
def create_battle(request: BattleRequest) -> dict[str, Any]:
    payload = request.model_dump(exclude={"name"})
    return manager.create_battle(payload, request.name)


@router.get("/battles/{battle_id}")
def get_battle(battle_id: str) -> dict[str, Any]:
    return manager.battle_snapshot(battle_id)


@router.post("/battles/{battle_id}/start")
def start_battle(battle_id: str) -> dict[str, Any]:
    return manager.battle_start(battle_id)


@router.post("/battles/{battle_id}/pause")
def pause_battle(battle_id: str) -> dict[str, Any]:
    return manager.battle_command(battle_id, "pause")


@router.post("/battles/{battle_id}/resume")
def resume_battle(battle_id: str) -> dict[str, Any]:
    return manager.battle_command(battle_id, "resume")


@router.post("/battles/{battle_id}/stop")
def stop_battle(battle_id: str) -> dict[str, Any]:
    return manager.battle_command(battle_id, "stop")


@router.post("/battles/{battle_id}/reset")
def reset_battle(battle_id: str) -> dict[str, Any]:
    return manager.battle_command(battle_id, "reset")


@router.post("/battles/{battle_id}/speed")
def set_battle_speed(battle_id: str, request: SpeedRequest) -> dict[str, Any]:
    return manager.battle_command(battle_id, "set_speed", speed=request.speed)


@router.get("/sessions")
def list_sessions() -> dict[str, Any]:
    return {"sessions": manager.list()}


@router.get("/history")
def list_history() -> dict[str, Any]:
    return {"experiments": manager.history()}


@router.get("/history/{run_id}")
def get_history_record(run_id: str) -> dict[str, Any]:
    return manager.history_record(run_id)


_NL = chr(10)
_SESSION_ID = re.compile(r"^ses_[0-9a-f]{8}$")
_RUN_ID = re.compile(r"^ses_[0-9a-f]{8}_r[0-9]{1,4}$")


def _reader() -> TrajectoryReader:
    return TrajectoryReader(store_path())


def _require_run(run_id: str) -> dict[str, Any]:
    run = _reader().get_run(run_id) if _RUN_ID.match(run_id) else None
    if run is None:
        raise NotFoundError("Run not found", details={"run_id": run_id[:40]})
    return run


@router.get("/sessions/{session_id}/runs")
def list_session_runs(session_id: str) -> dict[str, Any]:
    """Every persisted run of a session (survives server restarts)."""
    if not _SESSION_ID.match(session_id):
        raise NotFoundError("Session not found", details={"session_id": session_id[:40]})
    return {"session_id": session_id, "runs": _reader().list_runs(session_id)}


@router.get("/runs/{run_id}")
def get_run(run_id: str) -> dict[str, Any]:
    return _require_run(run_id)


@router.get("/runs/{run_id}/episodes")
def get_run_episodes(run_id: str, offset: int = Query(0, ge=0), limit: int = Query(500, ge=1, le=MAX_PAGE)) -> dict[str, Any]:
    run = _require_run(run_id)
    return {"run_id": run_id, "total": run["episode_count"], "offset": offset, "episodes": _reader().episodes(run_id, offset, limit)}


@router.get("/runs/{run_id}/steps")
def get_run_steps(
    run_id: str,
    episode: int | None = Query(None, ge=1),
    source: str | None = Query(None, pattern="^(agent|human)$"),
    offset: int = Query(0, ge=0),
    limit: int = Query(500, ge=1, le=MAX_PAGE),
) -> dict[str, Any]:
    """Step-level trajectory: observation, action, source, reward, termination, next observation."""
    run = _require_run(run_id)
    return {"run_id": run_id, "obs_shape": run["obs_shape"], "offset": offset, "steps": _reader().steps(run_id, episode=episode, source=source, offset=offset, limit=limit)}


@router.get("/runs/{run_id}/updates")
def get_run_updates(run_id: str, offset: int = Query(0, ge=0), limit: int = Query(500, ge=1, le=MAX_PAGE)) -> dict[str, Any]:
    _require_run(run_id)
    return {"run_id": run_id, "updates": _reader().table(run_id, "updates", offset, limit)}


@router.get("/runs/{run_id}/evaluations")
def get_run_evaluations(run_id: str, offset: int = Query(0, ge=0), limit: int = Query(500, ge=1, le=MAX_PAGE)) -> dict[str, Any]:
    _require_run(run_id)
    return {"run_id": run_id, "evaluations": _reader().table(run_id, "evaluations", offset, limit)}


@router.get("/runs/{run_id}/checkpoints")
def get_run_checkpoints(run_id: str) -> dict[str, Any]:
    _require_run(run_id)
    return {"run_id": run_id, "checkpoints": _reader().checkpoints(run_id)}


@router.get("/runs/{run_id}/export")
def export_run(run_id: str) -> StreamingResponse:
    """Newline-delimited JSON: a ``run`` header line, then one ``step`` line per transition."""
    run = _require_run(run_id)

    def lines() -> Iterator[str]:
        yield json.dumps({"type": "run", **run}) + _NL
        for step in _reader().iter_steps(run_id):
            yield json.dumps({"type": "step", **step}) + _NL

    return StreamingResponse(lines(), media_type="application/x-ndjson", headers={"Content-Disposition": f'attachment; filename="{run_id}.jsonl"'})


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


@router.post("/sessions/{session_id}/control")
def set_human_control(session_id: str, request: ControlRequest) -> dict[str, Any]:
    """Take or release manual control. While taken, submitted actions replace the agent's."""
    return manager.get(session_id).set_human_control(request.active)


@router.post("/sessions/{session_id}/brain")
def set_brain_view(session_id: str, request: BrainRequest) -> dict[str, Any]:
    """Include the policy's action probabilities / Q-values in every simulation frame."""
    return manager.get(session_id).set_brain_view(request.enabled)


@router.post("/sessions/{session_id}/chaos")
def set_chaos(session_id: str, request: ChaosRequest) -> dict[str, Any]:
    """Turn chaos mode on or off and set its intensity (0 to 1) and enabled disturbances."""
    return manager.get(session_id).set_chaos(request.enabled, request.intensity, request.kinds)


@router.post("/sessions/{session_id}/chaos/trigger")
def trigger_chaos(session_id: str, request: ChaosTriggerRequest) -> dict[str, Any]:
    """Inject one disturbance on the next step, whether or not chaos mode is on."""
    return manager.get(session_id).trigger_chaos(request.kind)


@router.post("/sessions/{session_id}/action")
def submit_action(session_id: str, request: ActionRequest) -> dict[str, Any]:
    """Submit one manual action (HTTP path; the WebSocket ``action`` message is the low-latency one)."""
    return manager.get(session_id).submit_human_action(request.action)


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

    The client may send ``{"type": "ping", "t": <number>}``; the server echoes
    ``{"type": "pong", "t": <same number>}`` so the client can measure the real
    round-trip latency of this connection. ``{"type": "action", "action": <a>}``
    submits a manual action while manual control is active and is answered with
    ``action_ack`` or ``action_rejected``.
    """
    try:
        session = manager.get(session_id)
    except Exception:  # noqa: BLE001 - unknown session at the socket boundary
        await websocket.close(code=4404)
        return
    await websocket.accept()
    outbox: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=64)

    async def read_client() -> None:
        try:
            while True:
                raw = await websocket.receive_text()
                try:
                    message = json.loads(raw)
                except ValueError:
                    continue
                if not isinstance(message, dict):
                    continue
                stamp = message.get("t")
                reply: dict[str, Any] | None = None
                if message.get("type") == "ping" and isinstance(stamp, (int, float)) and not isinstance(stamp, bool):
                    reply = {"type": "pong", "t": stamp}
                elif message.get("type") == "action":
                    try:
                        session.submit_human_action(message.get("action"))
                        reply = {"type": "action_ack", "accepted": True}
                    except StudioError as exc:
                        reply = {"type": "action_rejected", "reason": exc.message[:120]}
                if reply is not None:
                    with contextlib.suppress(asyncio.QueueFull):
                        outbox.put_nowait(reply)
        except (WebSocketDisconnect, RuntimeError):
            return

    reader = asyncio.create_task(read_client())
    try:
        snapshot = session.snapshot()
        await websocket.send_json({"type": "snapshot", "payload": snapshot})
        last_seq = snapshot["seq"]
        last_frame = (session.hub.latest_frame() or {}).get("frame_seq", 0)
        while not reader.done():
            while not outbox.empty():
                await websocket.send_json(outbox.get_nowait())
            events, _gap = session.hub.since(last_seq)
            for event in events:
                await websocket.send_json(event)
                last_seq = event["seq"]
            frame = session.hub.latest_frame()
            if frame is not None and frame["frame_seq"] != last_frame:
                last_frame = frame["frame_seq"]
                await websocket.send_json(frame)
            await asyncio.sleep(STREAM_INTERVAL_S)
    except (WebSocketDisconnect, RuntimeError):
        # Peer closed the socket while we were sending.
        return
    finally:
        reader.cancel()
