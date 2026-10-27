"""Schema-validated event emission with IDs, UTC timestamps, sequence ordering."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional

from shared.schemas import SCHEMA_VERSION, new_uuid
from shared.schemas.events import (
    EpisodeEndedEvent,
    EpisodeStartedEvent,
    ExecutionEvent,
    ExecutionEventType,
    RewardObservedEvent,
    SourceComponent,
)


class EventEmitter:
    def __init__(self, run_id: str, sequence_start: int = 0, fail_on_error: bool = True):
        self.run_id = run_id
        self._seq = int(sequence_start)
        self.fail_on_error = bool(fail_on_error)
        self.events: list[ExecutionEvent] = []

    def _next_seq(self) -> int:
        s = self._seq
        self._seq += 1
        return s

    def emit_episode_start(self, episode_id: str, environment_id: str, environment_version: str, **extra) -> EpisodeStartedEvent:
        ev = EpisodeStartedEvent(
            schema_version=SCHEMA_VERSION,
            event_id=new_uuid(),
            run_id=self.run_id,
            episode_id=episode_id,
            environment_id=environment_id,
            environment_version=environment_version,
            sequence=self._next_seq(),
            timestamp=datetime.now(timezone.utc),
            source_component=SourceComponent.ENVIRONMENT,
            **extra,
        )
        self.events.append(ev)
        return ev

    def emit_reward(self, episode_id: str, timestep: int, actual_reward: float, environment_version: str, requirement_id: Optional[str] = None, expected_reward: Optional[float] = None, **extra) -> RewardObservedEvent:
        ev = RewardObservedEvent(
            schema_version=SCHEMA_VERSION,
            event_id=new_uuid(),
            run_id=self.run_id,
            episode_id=episode_id,
            timestep=int(timestep),
            actual_reward=float(actual_reward),
            environment_version=environment_version,
            requirement_id=requirement_id,
            expected_reward=expected_reward,
            sequence=self._next_seq(),
            timestamp=datetime.now(timezone.utc),
            source_component=SourceComponent.ENVIRONMENT,
            **extra,
        )
        self.events.append(ev)
        return ev

    def emit_episode_end(self, episode_id: str, environment_id: str, environment_version: str, total_reward: float, length: int, success: bool = False, **extra) -> EpisodeEndedEvent:
        ev = EpisodeEndedEvent(
            schema_version=SCHEMA_VERSION,
            event_id=new_uuid(),
            run_id=self.run_id,
            episode_id=episode_id,
            environment_id=environment_id,
            environment_version=environment_version,
            total_reward=float(total_reward),
            length=int(length),
            success=bool(success),
            sequence=self._next_seq(),
            timestamp=datetime.now(timezone.utc),
            source_component=SourceComponent.ENVIRONMENT,
            **extra,
        )
        self.events.append(ev)
        return ev
