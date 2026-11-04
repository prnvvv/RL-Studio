"""Build verification input from persisted Studio training data.

Everything here is read from the Studio trajectory store, the canonical event store and the
provenance registry. Nothing is invented: when evidence is absent, partial or inconsistent the
payload says so (``evidence_complete`` is ``False`` and ``missing_evidence`` lists why), so the
deterministic engine reports UNKNOWN instead of PASS. No ``reward.expected`` is ever supplied
unless the caller passes one that came from a confirmed requirement.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from backend.events.service import EventPublisher
from backend.provenance.exceptions import RunNotFoundError
from backend.provenance.service import ProvenanceService
from backend.studio.provenance_bridge import config_fingerprint
from backend.studio.store import TrajectoryReader
from backend.verification.evidence_validator import (
    DEFAULT_MAX_EVENTS,
    DEFAULT_MAX_METRICS,
)
from backend.verification.input.input_adapter import adapt_input
from backend.verification.models import VerificationInput

_PAGE = 1000


class StudioRunNotFoundError(LookupError):
    """The requested run does not exist in the Studio store."""


@dataclass
class StudioEvidence:
    payload: dict[str, Any]
    missing_evidence: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_verification_input(self) -> VerificationInput:
        """Validate against the real ``VerificationInput`` schema."""
        return adapt_input(self.payload)


def _all(fetch: Any) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    while True:
        page = fetch(len(rows), _PAGE)
        rows += page
        if len(page) < _PAGE:
            return rows


def build_studio_evidence(
    run_id: str,
    *,
    reader: TrajectoryReader,
    provenance: ProvenanceService | None = None,
    developer_intent: str | None = None,
    expected_reward: float | None = None,
) -> StudioEvidence:
    """Assemble a ``VerificationInput`` payload for ``run_id`` from persisted data.

    ``expected_reward`` must come from a developer-confirmed requirement; it is never derived
    from observed data.
    """
    run = reader.get_run(run_id)
    if run is None:
        raise StudioRunNotFoundError(run_id)

    missing: list[str] = []
    warnings: list[str] = []
    config = run["config"]

    episodes = _all(lambda off, lim: reader.episodes(run_id, off, lim))
    updates = _all(lambda off, lim: reader.table(run_id, "updates", off, lim))
    evaluations = _all(lambda off, lim: reader.table(run_id, "evaluations", off, lim))
    checkpoints = reader.checkpoints(run_id)
    events = EventPublisher.list_run_events(run_id)

    # ---- completeness ---------------------------------------------------------------------
    status = run["status"]
    if status != "completed":
        missing.append(f"run_not_completed:{status}")
    if run.get("error"):
        missing.append("run_error_recorded")
    if not episodes:
        missing.append("no_episodes")
    if not events:
        missing.append("no_canonical_events")

    # ---- environment version consistency ----------------------------------------------------
    versions = {e.environment_version for e in events if e.environment_version}
    if events and any(e.environment_version is None for e in events):
        missing.append("environment_version_missing")
    if provenance is not None:
        with provenance.database.read() as conn:
            row = conn.execute("SELECT environment_version FROM runs WHERE run_id = ?", (run_id,)).fetchone()
        if row is None:
            missing.append("run_not_registered_in_provenance")
        elif row["environment_version"] is None:
            missing.append("environment_version_missing")
        else:
            versions.add(row["environment_version"])
        try:
            artifacts = provenance.list_run_artifacts(run_id).artifacts
        except RunNotFoundError:
            artifacts = []
        versions |= {a.environment_version for a in artifacts if a.environment_version}
        registered = {a.artifact_id for a in artifacts}
        for ckpt in checkpoints:
            if ckpt["checkpoint_id"] not in registered:
                missing.append(f"checkpoint_not_in_provenance:{ckpt['checkpoint_id']}")
    environment_version = next(iter(versions)) if len(versions) == 1 else None
    if len(versions) > 1:
        missing.append("environment_version_mismatch")
        warnings.append(f"conflicting environment versions recorded: {sorted(versions)}")

    # ---- episodes / events / metrics ----------------------------------------------------------
    by_episode = {e.episode_id: e for e in events if e.event_type == "episode_end"}
    if events and len(by_episode) != len(episodes):
        missing.append("episode_events_incomplete")
    episode_records = []
    for ep in episodes:
        episode_id = f"{run_id}_e{ep['episode']}"
        event = by_episode.get(episode_id)
        record: dict[str, Any] = {
            "episode_id": episode_id,
            "steps": ep["length"],
            "reward": ep["reward"],
            "success": ep["success"],
            "termination_reason": ep["reason"],
            "collisions": ep["collisions"],
            "terminated": event.terminated if event else None,
            "truncated": event.truncated if event else None,
        }
        if ep["reason"] == "goal_reached":
            record["goal_reached"] = True
        elif config["environment"] == "warehouse":
            record["goal_reached"] = False
        episode_records.append(record)

    canonical = [
        {**e.model_dump(), "sequence": i + 1} for i, e in enumerate(events)
    ]
    if len(canonical) > DEFAULT_MAX_EVENTS:
        # keep lifecycle/checkpoint events and the most recent episodes within the engine bound
        structural = [e for e in canonical if e["event_type"] != "episode_end"]
        recent = [e for e in canonical if e["event_type"] == "episode_end"]
        room = max(0, DEFAULT_MAX_EVENTS - len(structural))
        selected = sorted(structural + recent[len(recent) - room :], key=lambda e: e["sequence"])
        missing.append(f"events_truncated:{len(selected)}_of_{len(canonical)}")
        canonical = selected

    metrics = [
        {"id": f"{run_id}_m{i + 1}", "name": "episode_reward", "value": ep["reward"], "episode_id": ep_rec["episode_id"]}
        for i, (ep, ep_rec) in enumerate(zip(episodes, episode_records, strict=True))
    ][-DEFAULT_MAX_METRICS:]
    if len(episodes) > DEFAULT_MAX_METRICS:
        missing.append(f"metrics_truncated:{DEFAULT_MAX_METRICS}_of_{len(episodes)}")

    evidence: dict[str, Any] = {
        "run_id": run_id,
        "environment_id": config["environment"],
        "environment_version": environment_version,
        "episodes": episode_records,
        "events": canonical,
        "metrics": metrics,
        "checkpoints": [
            {"checkpoint_id": c["checkpoint_id"], "timestep": c["timestep"], "sha256": c["sha256"]} for c in checkpoints
        ],
        "training_summary": {
            "status": status,
            "step_count": run["step_count"],
            "episode_count": run["episode_count"],
            "update_count": len(updates),
            "evaluation_count": len(evaluations),
        },
        "missing_evidence": missing,
        "evidence_complete": not missing,
    }
    if episode_records:
        last = by_episode.get(episode_records[-1]["episode_id"])
        reward: dict[str, Any] = {"observed": episode_records[-1]["reward"]}
        if last is not None:
            reward["event_id"] = last.event_id
        if expected_reward is not None:
            reward["expected"] = expected_reward
        evidence["reward"] = reward

    payload: dict[str, Any] = {
        "agent_metadata": {
            "agent_id": config["agent"],
            "agent_type": config["agent"],
            "configuration_fingerprint": config_fingerprint(config),
        },
        "environment_config": dict(config.get("env_params") or {}),
        "training_config": {**(config.get("training") or {}), "agent_params": config.get("agent_params") or {}},
        "execution_evidence": evidence,
    }
    if developer_intent:
        payload["developer_intent"] = developer_intent
    return StudioEvidence(payload=payload, missing_evidence=missing, warnings=warnings)
