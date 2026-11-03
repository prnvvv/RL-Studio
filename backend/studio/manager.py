"""Registry of studio sessions with bounded retention and a single-trainer guard."""

from __future__ import annotations

import json
import logging
import re
import threading
import uuid
from typing import Any

from backend.database.exceptions import ConflictError, NotFoundError, ValidationError

from .session import ACTIVE, Status, TrainingSession, data_dir, validate_config

logger = logging.getLogger(__name__)

MAX_SESSIONS = 20
_SESSION_ID = re.compile(r"^ses_[0-9a-f]{8}$")
_BATTLE_ID = re.compile(r"^bat_[0-9a-f]{8}$")
BATTLE_SIDES = ("a", "b")


class SessionManager:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._sessions: dict[str, TrainingSession] = {}
        self._battles: dict[str, dict[str, str]] = {}

    def create(self, raw: dict[str, Any], name: str | None = None) -> TrainingSession:
        config = validate_config(raw)
        clean_name = (name or "").strip()[:80] or None
        with self._lock:
            self._evict_if_full()
            session = TrainingSession(f"ses_{uuid.uuid4().hex[:8]}", config, clean_name)
            self._sessions[session.session_id] = session
            return session

    def get(self, session_id: str) -> TrainingSession:
        with self._lock:
            session = self._sessions.get(session_id) if _SESSION_ID.match(session_id) else None
        if session is None:
            raise NotFoundError("Session not found", details={"session_id": session_id[:40]})
        return session

    def list(self) -> list[dict[str, Any]]:
        with self._lock:
            sessions = list(self._sessions.values())
        return [s.summary() for s in sorted(sessions, key=lambda s: s.created_at, reverse=True)]

    def start(self, session_id: str) -> dict[str, Any]:
        session = self.get(session_id)
        with self._lock:
            busy = [
                s
                for s in self._sessions.values()
                if s is not session and s.status in ACTIVE and not (session.battle_id and s.battle_id == session.battle_id)
            ]
            if busy and session.status == Status.INITIALIZED:
                raise ConflictError(
                    "Another session is already training; stop it before starting a new one",
                    details={"active_session_id": busy[0].session_id},
                )
            return session.start()

    # ----------------------------------------------------------------- battles

    def create_battle(self, raw: dict[str, Any], name: str | None = None) -> dict[str, Any]:
        """Two sessions on the same environment, environment settings, seed and training budget."""
        shared = {key: raw.get(key) for key in ("environment", "env_params", "training")}
        configs: dict[str, dict[str, Any]] = {}
        for side in BATTLE_SIDES:
            entry = raw.get(side) or {}
            try:
                configs[side] = validate_config({**shared, "agent": entry.get("agent"), "agent_params": entry.get("agent_params")})
            except ValidationError as exc:
                exc.details = {**exc.details, "side": side}
                raise
        clean_name = (name or "").strip()[:60] or None
        battle_id = f"bat_{uuid.uuid4().hex[:8]}"
        with self._lock:
            self._evict_if_full()
            self._evict_if_full()
            sessions = {}
            for side in BATTLE_SIDES:
                label = f"{side.upper()} · {configs[side]['agent']} on {configs[side]['environment']}"
                session = TrainingSession(f"ses_{uuid.uuid4().hex[:8]}", configs[side], f"{clean_name} — {label}" if clean_name else label, battle_id=battle_id, battle_side=side)
                self._sessions[session.session_id] = session
                sessions[side] = session.session_id
            self._battles[battle_id] = sessions
        return self.battle_snapshot(battle_id)

    def _battle(self, battle_id: str) -> dict[str, TrainingSession]:
        with self._lock:
            ids = self._battles.get(battle_id) if _BATTLE_ID.match(battle_id) else None
            sessions = {side: self._sessions.get(ids[side]) for side in BATTLE_SIDES} if ids else None
        if not sessions or any(s is None for s in sessions.values()):
            raise NotFoundError("Battle not found", details={"battle_id": battle_id[:40]})
        return sessions  # type: ignore[return-value]

    def battle_snapshot(self, battle_id: str) -> dict[str, Any]:
        sessions = self._battle(battle_id)
        snapshots = {side: sessions[side].snapshot() for side in BATTLE_SIDES}
        return {"battle_id": battle_id, "a": snapshots["a"], "b": snapshots["b"], "comparison": compare_sessions(snapshots["a"], snapshots["b"])}

    def battle_start(self, battle_id: str) -> dict[str, Any]:
        sessions = self._battle(battle_id)
        with self._lock:
            not_ready = [side for side in BATTLE_SIDES if sessions[side].status != Status.INITIALIZED]
            if not_ready:
                raise ConflictError("Both sides must be initialized to start the battle", details={"sides": not_ready})
            outsiders = [s for s in self._sessions.values() if s.status in ACTIVE and s.battle_id != battle_id]
            if outsiders:
                raise ConflictError(
                    "Another session is already training; stop it before starting a battle",
                    details={"active_session_id": outsiders[0].session_id},
                )
            return {"battle_id": battle_id, **{side: sessions[side].start() for side in BATTLE_SIDES}}

    def battle_command(self, battle_id: str, command: str, **kwargs: Any) -> dict[str, Any]:
        """Apply pause/resume/stop/reset/set_speed to both sides; a side that cannot comply reports why."""
        sessions = self._battle(battle_id)
        results: dict[str, Any] = {"battle_id": battle_id}
        errors = 0
        for side in BATTLE_SIDES:
            try:
                results[side] = getattr(sessions[side], command)(**kwargs)
            except (ConflictError, ValidationError) as exc:
                errors += 1
                results[side] = {"error": exc.message, "status": sessions[side].status.value}
                if isinstance(exc, ValidationError):
                    raise
        if errors == len(BATTLE_SIDES):
            raise ConflictError(f"Neither side can {command} right now", details={"battle_id": battle_id})
        return results

    def active_references(self) -> set[str]:
        """Agent and environment keys used by sessions that are currently running."""
        with self._lock:
            live = [s for s in self._sessions.values() if s.status in ACTIVE]
        return {s.config["agent"] for s in live} | {s.config["environment"] for s in live}

    def _evict_if_full(self) -> None:
        if len(self._sessions) < MAX_SESSIONS:
            return
        evictable = sorted(
            (s for s in self._sessions.values() if s.status not in ACTIVE),
            key=lambda s: s.created_at,
        )
        if not evictable:
            raise ConflictError("Too many active sessions")
        victim = evictable[0]
        del self._sessions[victim.session_id]
        if victim.battle_id:
            self._battles.pop(victim.battle_id, None)

    def history(self) -> list[dict[str, Any]]:
        """Persisted experiment records, newest first (summary only)."""
        directory = data_dir() / "sessions"
        if not directory.is_dir():
            return []
        records: list[dict[str, Any]] = []
        for path in sorted(directory.glob("ses_*.json"), key=lambda p: p.stat().st_mtime, reverse=True)[:50]:
            try:
                data = json.loads(path.read_text())
            except (OSError, ValueError):
                logger.warning("Skipping unreadable experiment record %s", path.name)
                continue
            records.append({k: data.get(k) for k in ("session_id", "run_id", "name", "status", "agent", "environment", "created_at", "finished_at", "progress", "checkpoints", "error")})
        return records

    def history_record(self, run_id: str) -> dict[str, Any]:
        if not re.match(r"^ses_[0-9a-f]{8}_r[0-9]{1,4}$", run_id):
            raise NotFoundError("Experiment record not found")
        path = data_dir() / "sessions" / f"{run_id}.json"
        try:
            return json.loads(path.read_text())
        except (OSError, ValueError):
            raise NotFoundError("Experiment record not found") from None


_COMPARED = ("timestep", "episodes", "current_reward_avg", "best_reward", "success_rate", "reward_per_step", "steps_per_second")


def compare_sessions(a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any]:
    """Side-by-side numbers taken from each session's own progress; no new estimates.

    ``leader`` is simply who has the higher moving-average reward right now. It
    is not a significance test and is null until both sides have finished an episode.
    """
    progress = {"a": a["progress"], "b": b["progress"]}
    metrics = {side: {key: progress[side].get(key) for key in _COMPARED} for side in BATTLE_SIDES}
    leader = None
    avg_a, avg_b = metrics["a"]["current_reward_avg"], metrics["b"]["current_reward_avg"]
    if avg_a is not None and avg_b is not None and avg_a != avg_b:
        leader = "a" if avg_a > avg_b else "b"
    return {
        "metrics": metrics,
        "leader": leader,
        "leader_basis": "current_reward_avg",
        "same_environment": a["config"]["environment"] == b["config"]["environment"] and a["config"]["env_params"] == b["config"]["env_params"],
        "same_seed": a["config"]["training"]["seed"] == b["config"]["training"]["seed"],
    }


manager = SessionManager()
