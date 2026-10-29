"""WebSocket and Server-Sent Events for real-time updates."""

from __future__ import annotations

import asyncio
from typing import AsyncGenerator, Dict

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse

from backend.events.service import EventPublisher


router = APIRouter(prefix="/api/v1", tags=["realtime"])


@router.websocket("/events/{run_id}")
async def ws_events_endpoint(websocket: WebSocket, run_id: str) -> None:
    """WebSocket endpoint for real-time event streaming."""
    await websocket.accept()
    publisher = EventPublisher()
    try:
        while True:
            # Get recent events for this run
            events = EventPublisher.get_recent_events(run_id, limit=20)
            if events:
                for event in events:
                    await websocket.send_json(
                        {
                            "event_id": event.event_id,
                            "event_type": event.event_type,
                            "run_id": event.run_id,
                            "episode_id": event.episode_id,
                            "timestep": event.timestep,
                            "actual_reward": event.actual_reward,
                            "timestamp": event.timestamp.isoformat() if event.timestamp else None,
                        }
                    )
            await asyncio.sleep(0.5)  # poll interval
    except WebSocketDisconnect:
        pass


@router.get("/events/{run_id}/sse")
async def sse_events(run_id: str) -> StreamingResponse:
    """Server-Sent Events endpoint for real-time event streaming."""

    async def event_generator() -> AsyncGenerator[Dict[str, Any], None]:
        publisher = EventPublisher()
        seen_ids: set = set()
        while True:
            events = EventPublisher.get_recent_events(run_id, limit=10)
            for event in events:
                if event.event_id not in seen_ids:
                    seen_ids.add(event.event_id)
                    yield {
                        "event": event.event_type,
                        "data": event.model_dump(mode="json"),
                        "id": event.event_id,
                    }
            await asyncio.sleep(0.5)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )
