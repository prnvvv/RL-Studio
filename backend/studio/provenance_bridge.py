"""Bridge from the Studio training pipeline to canonical events and provenance.

The Studio store (``backend.studio.store``) remains the single source of truth for
steps, episodes and metrics. This bridge only (a) publishes canonical lifecycle,
episode and checkpoint events, and (b) registers the run and its checkpoints with
the provenance service so downstream verification/recovery can link to them.

Training must never fail because of this bridge: every hook swallows and logs its
own errors, and the bridge records ``healthy``/``last_error`` instead.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import shutil
import threading
from pathlib import Path
from typing import Any

from backend.database.config import DatabaseConfig
from backend.database.connection import Database
from backend.events import service as events
from backend.events.service import EventPublisher
from backend.provenance.models import (
    ArtifactRegistration,
    ArtifactType,
    RunRegistration,
)
from backend.provenance.service import ProvenanceService

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_database: Database | None = None
_explicit = False
_ready = False


def configure(database: Database | None) -> None:
    """Use ``database`` for provenance and events (tests / app wiring); ``None`` resets."""
    global _database, _ready, _explicit
    with _lock:
        _database = database
        _explicit = database is not None
        _ready = database is not None
    events.configure(database)


def _db() -> Database:
    """Provenance database; follows the env-derived config unless explicitly configured."""
    global _database, _ready
    with _lock:
        if not _explicit:
            config = DatabaseConfig.from_env()
            if _database is None or _database.config != config:
                _database = Database(config)
                _ready = False
        assert _database is not None
        if not _ready:
            _database.initialize()
            _ready = True
        return _database


def resolve_environment_version(env: Any) -> str | None:
    """Version reported by the environment implementation itself, or ``None`` if it has none.

    Never fabricated: a warehouse env reports its immutable config version; Gymnasium envs
    report their registered spec id (which carries the ``-vN`` suffix).
    """
    unwrapped = getattr(env, "unwrapped", env)
    version = getattr(getattr(unwrapped, "config", None), "environment_version", None)
    if isinstance(version, str) and version:
        return version
    spec = getattr(unwrapped, "spec", None) or getattr(env, "spec", None)
    spec_id = getattr(spec, "id", None)
    return spec_id if isinstance(spec_id, str) and spec_id else None


def config_fingerprint(config: dict[str, Any]) -> str:
    canonical = json.dumps(config, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class RunBridge:
    """Per-run hooks called by ``TrainingSession``."""

    def __init__(
        self,
        run_id: str,
        *,
        environment_id: str,
        environment_version: str | None,
        agent_id: str,
        config: dict[str, Any],
        database: Database | None = None,
    ) -> None:
        self.run_id = run_id
        self.environment_id = environment_id
        self.environment_version = environment_version
        self.agent_id = agent_id
        self.config = config
        # Resolve once, at session start. Re-reading the environment on every hook would
        # let a finishing training thread write into whatever data root the process has
        # since switched to (tests) instead of the one this run belongs to.
        self._database = database if database is not None else _db()
        self.healthy = True
        self.last_error: str | None = None

    def _fail(self, hook: str, exc: Exception) -> None:
        self.healthy = False
        self.last_error = f"{hook}: {type(exc).__name__}"
        logger.warning("provenance bridge %s failed for %s: %s", hook, self.run_id, type(exc).__name__)

    def _publish(self, event_type: str, key: str, **kwargs: Any) -> str | None:
        return EventPublisher.publish(
            event_type,
            self.run_id,
            idempotency_key=f"{self.run_id}:{key}",
            environment_id=self.environment_id,
            environment_version=self.environment_version,
            agent_id=self.agent_id,
            database=self._database,
            **kwargs,
        )

    def run_started(self, *, timestep: int = 0, resumed: bool = False) -> None:
        try:
            ProvenanceService(self._database).register_run(
                RunRegistration(
                    run_id=self.run_id,
                    environment_id=self.environment_id,
                    environment_version=self.environment_version,
                    agent_config_fingerprint=config_fingerprint(self.config),
                    status="running",
                    metadata={"agent": self.agent_id, "source": "studio"},
                )
            )
            self._publish(
                "run_resumed" if resumed else "run_started",
                "resumed" if resumed else "started",
                timestep=timestep,
                metadata={"environment_version_known": self.environment_version is not None},
            )
        except Exception as exc:  # noqa: BLE001 - never break training
            self._fail("run_started", exc)

    def episode_ended(
        self, *, episode: int, timestep: int, reward: float, length: int, success: bool,
        reason: str, collisions: int, disturbances: int, truncated: bool | None = None,
    ) -> None:
        try:
            self._publish(
                "episode_end",
                f"episode:{episode}",
                episode_id=f"{self.run_id}_e{episode}",
                timestep=timestep,
                actual_reward=reward,
                terminated=None if truncated is None else not truncated,
                truncated=truncated,
                metrics={"length": length, "collisions": collisions, "disturbances": disturbances},
                metadata={"success": success, "termination_reason": reason},
            )
        except Exception as exc:  # noqa: BLE001
            self._fail("episode_ended", exc)

    def checkpoint_saved(self, record: dict[str, Any], source_file: Path) -> None:
        """Register a checkpoint as a provenance artifact (hash-verified) and emit an event."""
        try:
            database = self._database
            rel = f"checkpoints/{self.run_id}/{record['checkpoint_id']}.zip"
            target = database.config.artifact_root / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            if not target.exists():
                try:
                    os.link(source_file, target)
                except OSError:
                    shutil.copy2(source_file, target)
            artifact = ProvenanceService(database).register_artifact(
                ArtifactRegistration(
                    artifact_id=record["checkpoint_id"],
                    run_id=self.run_id,
                    artifact_type=ArtifactType.checkpoint,
                    artifact_path=rel,
                    artifact_hash=record["sha256"],
                    checkpoint_id=record["checkpoint_id"],
                    timestep=int(record["timestep"]),
                    environment_id=self.environment_id,
                    environment_version=self.environment_version,
                    agent_config_fingerprint=config_fingerprint(self.config),
                    metadata={"reason": record.get("reason"), "algorithm": record.get("algorithm")},
                )
            )
            self._publish(
                "checkpoint_saved",
                f"checkpoint:{record['checkpoint_id']}",
                timestep=int(record["timestep"]),
                metadata={
                    "checkpoint_id": record["checkpoint_id"],
                    "artifact_id": artifact.artifact_id,
                    "sha256": record["sha256"],
                    "reason": record.get("reason"),
                },
            )
        except Exception as exc:  # noqa: BLE001
            self._fail("checkpoint_saved", exc)

    def run_finished(self, *, status: str, timestep: int, error: str | None) -> None:
        try:
            event_type = {"completed": "run_completed", "stopped": "run_interrupted", "failed": "run_failed"}.get(
                status, f"run_{status}"
            )
            self._publish(
                event_type,
                f"finished:{status}",
                timestep=timestep,
                metadata={"status": status, "error": error},
            )
        except Exception as exc:  # noqa: BLE001
            self._fail("run_finished", exc)
