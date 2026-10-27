"""Schema-validated event emission with IDs, UTC timestamps, sequence ordering."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from shared.schemas import SCHEMA_VERSION, new_uuid
from shared.schemas.events import (
    EpisodeEndedEvent,
    EpisodeStartedEvent,
    RewardObservedEvent,
    SourceComponent,
)


class EventEmitter:
    def __init__(self, run_id: str, sequence_start: int = 0):
        self.run_id = run_id
        self._seq = int(sequence_start)
        self.events = []

    def _next_seq(self) -> int:
        s = self._seq
        self._seq += 1
        return s

    def emit_episode_start(self, episode_id: str, environment_id: str, environment_version: str, seed: Optional[int] = None) -> EpisodeStartedEvent:
        ev = EpisodeStartedEvent(
            schema_version=SCHEMA_VERSION,
            event_id=new_uuid(),
            event_type="episode_started",
            run_id=self.run_id,
            episode_id=episode_id,
            environment_id=environment_id,
            environment_version=environment_version,
            sequence=self._next_seq(),
            timestamp=datetime.now(timezone.utc),
            source_component=SourceComponent.ENVIRONMENT,
            payload={"seed": seed},
        )
        self.events.append(ev)
        return ev

    def emit_reward(self, episode_id: str, timestep: int, actual_reward: float, environment_version: str, requirement_id: Optional[str] = None, expected_reward: Optional[float] = None) -> RewardObservedEvent:
        ev = RewardObservedEvent(
            schema_version=SCHEMA_VERSION,
            event_id=new_uuid(),
            event_type="reward_observed",
            run_id=self.run_id,
            episode_id=episode_id,
            timestep=int(timestep),
            environment_version=environment_version,
            sequence=self._next_seq(),
            timestamp=datetime.now(timezone.utc),
            source_component=SourceComponent.ENVIRONMENT,
            payload={
                "actual_reward": float(actual_reward),
                "expected_reward": expected_reward,
                "reward_kind": "other",
                "requirement_id": requirement_id,
            },
        )
        self.events.append(ev)
        return ev

    def emit_episode_end(self, episode_id: str, environment_id: str, environment_version: str, total_reward: float, length: int, success: bool = False, terminated: bool = False, truncated: bool = False) -> EpisodeEndedEvent:
        ev = EpisodeEndedEvent(
            schema_version=SCHEMA_VERSION,
            event_id=new_uuid(),
            event_type="episode_ended",
            run_id=self.run_id,
            episode_id=episode_id,
            environment_id=environment_id,
            environment_version=environment_version,
            sequence=self._next_seq(),
            timestamp=datetime.now(timezone.utc),
            source_component=SourceComponent.ENVIRONMENT,
            payload={
                "total_reward": float(total_reward),
                "steps": int(length),
                "terminated": bool(terminated),
                "truncated": bool(truncated),
                "success": bool(success),
            },
        )
        self.events.append(ev)
        return ev
