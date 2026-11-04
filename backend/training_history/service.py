"""Persistent, project-scoped training history.

The ``training_runs`` catalog is the authoritative record of every training run: which project, agent, environment
and experiment it belongs to, the exact configuration snapshots it used, its lifecycle status and *why* it ended,
and its final metrics. Studio's own trajectory store keeps the bulky per-episode/step data; this catalog is what every
page uses to find a run, and each row points at that data by ``run_id``.

Rules enforced here (not in the UI):

* A run belongs to exactly one project (or is explicitly legacy: ``project_id IS NULL``, never auto-assigned).
* Agents and environment configurations are persistent project entities, reused when a run's configuration matches and
  versioned (earlier configurations kept) when an explicit entity is re-trained with a changed configuration. A run keeps
  its own snapshots, so editing an entity later never rewrites history.
* A stopped run is ``stopped`` with reason ``user_requested_stop`` - never ``completed``. A run found non-terminal after
  a restart is ``interrupted`` (``unexpected_interruption``), never silently completed.
* Entity and continuation references are validated against the project: another project's ids are rejected.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from datetime import datetime
from typing import Any

from backend.database.connection import Database
from backend.database.utils import utc_now_iso

ACTIVE_STATUSES = ("initializing", "running", "paused", "stopping")
TERMINAL_STATUSES = ("completed", "stopped", "failed", "interrupted")
STATUSES = ("queued", *ACTIVE_STATUSES, *TERMINAL_STATUSES)

REASON_COMPLETED = "natural_completion"
REASON_USER_STOP = "user_requested_stop"
REASON_FAILURE = "training_failure"
REASON_INTERRUPTED = "unexpected_interruption"

MAX_PAGE = 200
INTERRUPTED_NOTE = (
    "The backend stopped before this run finished; its history up to the last recorded progress is preserved."
)
_SORTS = {
    "recent": "COALESCE(r.started_at, r.created_at) DESC, r.rowid DESC",
    "oldest": "COALESCE(r.started_at, r.created_at) ASC, r.rowid ASC",
    "timesteps": "COALESCE(r.total_timesteps, 0) DESC, r.rowid DESC",
}


class HistoryError(Exception):
    """Base class; ``status`` maps to an HTTP status in the router."""

    status = 400
    code = "history_error"

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class NotFound(HistoryError):
    status = 404
    code = "not_found"


class Invalid(HistoryError):
    status = 422
    code = "invalid"


class Conflict(HistoryError):
    status = 409
    code = "conflict"


def _fingerprint(payload: Any) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()[:16]


def _loads(text: str | None, default: Any) -> Any:
    try:
        return json.loads(text) if text else default
    except ValueError:
        return default


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def _run_view(row: sqlite3.Row) -> dict[str, Any]:
    r = dict(row)
    return {
        "run_id": r["run_id"], "project_id": r["project_id"], "experiment_id": r["experiment_id"],
        "experiment_name": r.get("experiment_name"), "agent_id": r["agent_id"], "agent_name": r.get("agent_name"),
        "agent_version": r["agent_version"], "environment_config_id": r["environment_config_id"],
        "environment_config_name": r.get("environment_config_name"),
        "environment_config_version": r["environment_config_version"], "session_id": r["session_id"],
        "name": r["name"], "algorithm": r["algorithm"], "environment_name": r["environment_name"], "seed": r["seed"],
        "status": r["status"], "termination_reason": r["termination_reason"], "continues_run_id": r["continues_run_id"],
        "started_at": r["started_at"], "finished_at": r["finished_at"], "duration_seconds": r["duration_seconds"],
        "total_timesteps": r["total_timesteps"], "total_episodes": r["total_episodes"],
        "final_metrics": _loads(r["final_metrics_json"], {}), "error": r["error"],
        "last_progress_at": r["last_progress_at"], "created_at": r["created_at"], "updated_at": r["updated_at"],
        "active": r["status"] in ACTIVE_STATUSES,
    }


_RUN_SELECT = """
SELECT r.*, a.name AS agent_name, e.name AS environment_config_name, x.name AS experiment_name
FROM training_runs r
LEFT JOIN project_agents a ON a.agent_id = r.agent_id
LEFT JOIN project_environment_configs e ON e.environment_config_id = r.environment_config_id
LEFT JOIN project_experiments x ON x.experiment_id = r.experiment_id
"""


class TrainingHistory:
    def __init__(self, database: Database) -> None:
        self.database = database

    # ------------------------------------------------------------------ entities
    @staticmethod
    def _overrides(params: dict[str, Any] | None, specs: Any) -> dict[str, Any]:
        """Only the values that differ from the catalog default. A validated run config has every default filled in,
        so comparing raw dicts would call an unchanged entity "changed"; comparing overrides does not."""
        defaults = {getattr(s, "key", None): getattr(s, "default", None) for s in (specs or ())}
        return {k: v for k, v in (params or {}).items() if k not in defaults or defaults[k] != v}

    @classmethod
    def _agent_payload(cls, config: dict[str, Any]) -> dict[str, Any]:
        try:
            from backend.studio.catalog import AGENTS

            specs = AGENTS[str(config.get("agent"))].params
        except Exception:  # noqa: BLE001 - a custom/unknown agent: keep the parameters as given
            specs = None
        return {"agent": config.get("agent"), "agent_params": cls._overrides(config.get("agent_params"), specs)}

    @classmethod
    def _env_payload(cls, config: dict[str, Any]) -> dict[str, Any]:
        try:
            from backend.studio import custom

            specs = custom.resolve_environment(config["environment"]).params
        except Exception:  # noqa: BLE001
            specs = None
        return {"environment": config.get("environment"), "env_params": cls._overrides(config.get("env_params"), specs)}

    def _entity(self, conn: sqlite3.Connection, table: str, id_col: str, project_id: str, entity_id: str) -> sqlite3.Row:
        row = conn.execute(f"SELECT * FROM {table} WHERE {id_col} = ? AND project_id = ?", (entity_id, project_id)).fetchone()
        if row is None:  # identical for "missing" and "another project's": ids are not an oracle
            raise NotFound(f"{table[:-1].replace('project_', '')} not found in this project")
        return row

    def _resolve(self, conn: sqlite3.Connection, *, table: str, id_col: str, prefix: str, project_id: str,
                 explicit_id: str | None, name_base: str, payload: dict[str, Any], extra: dict[str, Any]) -> tuple[str, int]:
        """Reuse the entity whose configuration matches; version an explicit one whose configuration changed."""
        fp = _fingerprint(payload)
        now = utc_now_iso()
        if explicit_id is not None:
            row = self._entity(conn, table, id_col, project_id, explicit_id)
            if row["config_fingerprint"] == fp:
                return row[id_col], row["version"]
            revisions = _loads(row["revisions_json"], [])
            revisions.append({"version": row["version"], "config": _loads(row["config_json"], {}),
                              "superseded_at": now})
            conn.execute(
                f"UPDATE {table} SET config_json = ?, config_fingerprint = ?, version = version + 1, revisions_json = ?, "
                f"updated_at = ? WHERE {id_col} = ?", (json.dumps(payload, default=str), fp, json.dumps(revisions), now, explicit_id))
            return explicit_id, row["version"] + 1
        row = conn.execute(f"SELECT {id_col}, version FROM {table} WHERE project_id = ? AND config_fingerprint = ?"
                           " ORDER BY created_at LIMIT 1", (project_id, fp)).fetchone()
        if row is not None:
            return row[id_col], row["version"]
        count = conn.execute(f"SELECT COUNT(*) FROM {table} WHERE project_id = ? AND name LIKE ?",
                             (project_id, f"{name_base}%")).fetchone()[0]
        name = name_base if count == 0 else f"{name_base} #{count + 1}"
        entity_id = _new_id(prefix)
        cols = ["project_id", "name", "config_json", "config_fingerprint", "version", "created_at", "updated_at", id_col,
                *extra]
        vals = [project_id, name, json.dumps(payload, default=str), fp, 1, now, now, entity_id, *extra.values()]
        conn.execute(f"INSERT INTO {table}({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})", vals)
        return entity_id, 1

    # ------------------------------------------------------------------ run lifecycle
    def register_run(self, *, run_id: str, project_id: str | None, session_id: str | None, name: str | None,
                     config: dict[str, Any], started_at: str | None, experiment_id: str | None = None,
                     agent_id: str | None = None, environment_config_id: str | None = None,
                     continues_run_id: str | None = None) -> dict[str, Any]:
        """One transaction: resolve/version the agent and environment entities, validate every reference, insert the run."""
        now = utc_now_iso()
        training = config.get("training") or {}
        with self.database.write() as conn:
            existing = conn.execute("SELECT run_id FROM training_runs WHERE run_id = ?", (run_id,)).fetchone()
            if existing is not None:
                raise Conflict("this run is already registered")
            agent_ref: tuple[str | None, int | None] = (None, None)
            env_ref: tuple[str | None, int | None] = (None, None)
            if project_id is None:
                if any((experiment_id, agent_id, environment_config_id, continues_run_id)):
                    raise Invalid("entity references require a project")
            else:
                if experiment_id is not None:
                    self._entity(conn, "project_experiments", "experiment_id", project_id, experiment_id)
                if continues_run_id is not None:
                    prev = conn.execute("SELECT status FROM training_runs WHERE run_id = ? AND project_id = ?",
                                        (continues_run_id, project_id)).fetchone()
                    if prev is None:
                        raise NotFound("the run to continue was not found in this project")
                    if prev["status"] in ACTIVE_STATUSES:
                        raise Conflict("the run to continue is still active")
                agent_ref = self._resolve(
                    conn, table="project_agents", id_col="agent_id", prefix="agt", project_id=project_id,
                    explicit_id=agent_id, name_base=str(config.get("agent")), payload=self._agent_payload(config),
                    extra={"algorithm": str(config.get("agent"))})
                env_ref = self._resolve(
                    conn, table="project_environment_configs", id_col="environment_config_id", prefix="env",
                    project_id=project_id, explicit_id=environment_config_id, name_base=str(config.get("environment")),
                    payload=self._env_payload(config), extra={"environment_kind": "environment"})
                conn.execute("UPDATE project_agents SET latest_run_id = ?, updated_at = ? WHERE agent_id = ?",
                             (run_id, now, agent_ref[0]))
                conn.execute("UPDATE project_environment_configs SET latest_run_id = ?, updated_at = ? "
                             "WHERE environment_config_id = ?", (run_id, now, env_ref[0]))
            conn.execute(
                """INSERT INTO training_runs(run_id, project_id, experiment_id, agent_id, environment_config_id,
                   agent_version, environment_config_version, session_id, name, algorithm, environment_name, seed,
                   agent_snapshot_json, environment_snapshot_json, training_snapshot_json, status, continues_run_id,
                   started_at, total_timesteps, total_episodes, created_at, updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (run_id, project_id, experiment_id, agent_ref[0], env_ref[0], agent_ref[1], env_ref[1], session_id, name,
                 config.get("agent"), config.get("environment"), training.get("seed"),
                 json.dumps({"agent": config.get("agent"), "agent_params": config.get("agent_params") or {}}, default=str),
                 json.dumps({"environment": config.get("environment"), "env_params": config.get("env_params") or {}}, default=str),
                 json.dumps(training, default=str), "running", continues_run_id, started_at, 0, 0, now, now))
        run = self.get_any(run_id)
        assert run is not None
        return run

    def progress(self, run_id: str, *, timestep: int, episodes: int, metrics: dict[str, Any] | None = None,
                 status: str | None = None) -> None:
        sets = ["total_timesteps = MAX(COALESCE(total_timesteps, 0), ?)", "total_episodes = MAX(COALESCE(total_episodes, 0), ?)",
                "last_progress_at = ?", "updated_at = ?"]
        now = utc_now_iso()
        args: list[Any] = [int(timestep), int(episodes), now, now]
        if metrics is not None:
            sets.append("final_metrics_json = ?")
            args.append(json.dumps(metrics, default=str))
        if status is not None:
            sets.append("status = ?")
            args.append(status)
        with self.database.write() as conn:
            # a finished run is never reopened by a late progress write
            conn.execute(f"UPDATE training_runs SET {', '.join(sets)} WHERE run_id = ? AND status NOT IN "
                         "('completed','stopped','failed','interrupted')", (*args, run_id))

    def set_status(self, run_id: str, status: str) -> None:
        with self.database.write() as conn:
            conn.execute("UPDATE training_runs SET status = ?, updated_at = ? WHERE run_id = ? AND status NOT IN "
                         "('completed','stopped','failed','interrupted')", (status, utc_now_iso(), run_id))
            conn.execute("UPDATE runs SET status = ?, updated_at = ? WHERE run_id = ? AND status NOT IN "
                         "('completed','stopped','failed','interrupted')", (status, utc_now_iso(), run_id))

    def finish(self, run_id: str, *, status: str, reason: str, finished_at: str, duration_seconds: float | None,
               timestep: int, episodes: int, metrics: dict[str, Any] | None, error: str | None) -> None:
        if status not in TERMINAL_STATUSES:
            raise Invalid(f"{status!r} is not a terminal status")
        now = utc_now_iso()
        with self.database.write() as conn:
            conn.execute(
                """UPDATE training_runs SET status = ?, termination_reason = ?, finished_at = ?, duration_seconds = ?,
                   total_timesteps = MAX(COALESCE(total_timesteps, 0), ?), total_episodes = MAX(COALESCE(total_episodes, 0), ?),
                   final_metrics_json = COALESCE(?, final_metrics_json), error = ?, updated_at = ? WHERE run_id = ?""",
                (status, reason, finished_at, duration_seconds, int(timestep), int(episodes),
                 None if metrics is None else json.dumps(metrics, default=str), error, now, run_id))
            # the provenance ``runs`` row must not stay "running" forever
            conn.execute("UPDATE runs SET status = ?, updated_at = ? WHERE run_id = ?", (status, now, run_id))

    def reconcile(self, live_run_ids: set[str]) -> list[str]:
        """After a restart: any run still marked active but not alive in this process was abandoned. Mark it
        ``interrupted`` at its last known progress; never ``completed``. Returns the reconciled run ids."""
        with self.database.read() as conn:
            rows = conn.execute("SELECT run_id, started_at, last_progress_at FROM training_runs WHERE status IN "
                                "('queued','initializing','running','paused','stopping')").fetchall()
        done: list[str] = []
        for row in rows:
            if row["run_id"] in live_run_ids:
                continue
            end = row["last_progress_at"] or row["started_at"] or utc_now_iso()
            duration = None
            try:
                if row["started_at"]:
                    duration = max(0.0, (datetime.fromisoformat(end) - datetime.fromisoformat(row["started_at"])).total_seconds())
            except ValueError:
                duration = None
            now = utc_now_iso()
            with self.database.write() as conn:
                conn.execute(
                    "UPDATE training_runs SET status = 'interrupted', termination_reason = ?, finished_at = ?, "
                    "duration_seconds = ?, error = COALESCE(error, ?), updated_at = ? WHERE run_id = ? AND status IN "
                    "('queued','initializing','running','paused','stopping')",
                    (REASON_INTERRUPTED, end, duration, INTERRUPTED_NOTE, now, row["run_id"]))
                conn.execute("UPDATE runs SET status = 'interrupted', updated_at = ? WHERE run_id = ?", (now, row["run_id"]))
            done.append(row["run_id"])
        return done

    def validate_refs(self, project_id: str, *, experiment_id: str | None = None, agent_id: str | None = None,
                      environment_config_id: str | None = None, continues_run_id: str | None = None) -> None:
        """Reject, before a session exists, any reference that is not this project's (identical error for all)."""
        with self.database.read() as conn:
            for table, col, value in (("project_experiments", "experiment_id", experiment_id),
                                      ("project_agents", "agent_id", agent_id),
                                      ("project_environment_configs", "environment_config_id", environment_config_id)):
                if value is not None:
                    self._entity(conn, table, col, project_id, value)
            if continues_run_id is not None:
                row = conn.execute("SELECT status FROM training_runs WHERE run_id = ? AND project_id = ?",
                                   (continues_run_id, project_id)).fetchone()
                if row is None:
                    raise NotFound("the run to continue was not found in this project")
                if row["status"] in ACTIVE_STATUSES:
                    raise Conflict("the run to continue is still active")

    def snapshots(self, run_id: str) -> dict[str, Any]:
        """The exact configuration the run used (never the entity's current configuration)."""
        with self.database.read() as conn:
            row = conn.execute("SELECT agent_snapshot_json, environment_snapshot_json, training_snapshot_json "
                               "FROM training_runs WHERE run_id = ?", (run_id,)).fetchone()
        if row is None:
            return {}
        return {"agent": _loads(row["agent_snapshot_json"], {}), "environment": _loads(row["environment_snapshot_json"], {}),
                "training": _loads(row["training_snapshot_json"], {})}

    # ------------------------------------------------------------------ queries
    def get_any(self, run_id: str) -> dict[str, Any] | None:
        with self.database.read() as conn:
            row = conn.execute(_RUN_SELECT + " WHERE r.run_id = ?", (run_id,)).fetchone()
        return _run_view(row) if row else None

    def get_run(self, project_id: str, run_id: str) -> dict[str, Any] | None:
        run = self.get_any(run_id)
        return run if run and run["project_id"] == project_id else None

    def list_runs(self, project_id: str, *, agent_id: str | None = None, environment_config_id: str | None = None,
                  experiment_id: str | None = None, status: str | None = None, q: str | None = None,
                  sort: str = "recent", limit: int = 50, offset: int = 0) -> dict[str, Any]:
        where, args = ["r.project_id = ?"], [project_id]
        for column, value in (("r.agent_id", agent_id), ("r.environment_config_id", environment_config_id),
                              ("r.experiment_id", experiment_id), ("r.status", status)):
            if value:
                where.append(f"{column} = ?")
                args.append(value)
        if q and q.strip():
            like = f"%{q.strip()[:80]}%"
            where.append("(r.run_id LIKE ? OR r.name LIKE ? OR a.name LIKE ? OR r.environment_name LIKE ?)")
            args += [like, like, like, like]
        clause = " WHERE " + " AND ".join(where)
        order = _SORTS.get(sort, _SORTS["recent"])
        limit = max(1, min(int(limit), MAX_PAGE))
        with self.database.read() as conn:
            total = conn.execute("SELECT COUNT(*) FROM training_runs r LEFT JOIN project_agents a ON a.agent_id = r.agent_id"
                                 + clause, args).fetchone()[0]
            rows = conn.execute(_RUN_SELECT + clause + f" ORDER BY {order} LIMIT ? OFFSET ?",
                                (*args, limit, max(0, int(offset)))).fetchall()
        return {"total": total, "limit": limit, "offset": max(0, int(offset)), "items": [_run_view(r) for r in rows]}

    def latest_run(self, project_id: str, *, agent_id: str | None = None) -> dict[str, Any] | None:
        page = self.list_runs(project_id, agent_id=agent_id, limit=1)
        return page["items"][0] if page["items"] else None

    # ------------------------------------------------------------------ entity CRUD
    def _entity_view(self, row: sqlite3.Row, id_col: str) -> dict[str, Any]:
        r = dict(row)
        view = {k: r[k] for k in r if not k.endswith("_json")}
        view["id"] = r[id_col]
        view["config"] = _loads(r["config_json"], {})
        view["revisions"] = _loads(r["revisions_json"], [])
        return view

    def list_agents(self, project_id: str) -> list[dict[str, Any]]:
        with self.database.read() as conn:
            rows = conn.execute(
                "SELECT a.*, (SELECT COUNT(*) FROM training_runs t WHERE t.agent_id = a.agent_id) AS run_count "
                "FROM project_agents a WHERE a.project_id = ? ORDER BY a.updated_at DESC, a.rowid DESC", (project_id,)).fetchall()
        return [self._entity_view(r, "agent_id") for r in rows]

    def list_environments(self, project_id: str) -> list[dict[str, Any]]:
        with self.database.read() as conn:
            rows = conn.execute(
                "SELECT e.*, (SELECT COUNT(*) FROM training_runs t WHERE t.environment_config_id = e.environment_config_id) "
                "AS run_count FROM project_environment_configs e WHERE e.project_id = ? "
                "ORDER BY e.updated_at DESC, e.rowid DESC", (project_id,)).fetchall()
        return [self._entity_view(r, "environment_config_id") for r in rows]

    def create_agent(self, project_id: str, *, name: str, algorithm: str, params: dict[str, Any]) -> dict[str, Any]:
        payload = {"agent": algorithm, "agent_params": params}
        now = utc_now_iso()
        agent_id = _new_id("agt")
        with self.database.write() as conn:
            conn.execute("INSERT INTO project_agents(agent_id, project_id, name, algorithm, config_json, config_fingerprint,"
                         " version, created_at, updated_at) VALUES (?,?,?,?,?,?,1,?,?)",
                         (agent_id, project_id, name.strip(), algorithm, json.dumps(payload), _fingerprint(payload), now, now))
        return next(a for a in self.list_agents(project_id) if a["agent_id"] == agent_id)

    def create_environment(self, project_id: str, *, name: str, environment: str, params: dict[str, Any]) -> dict[str, Any]:
        payload = {"environment": environment, "env_params": params}
        now = utc_now_iso()
        env_id = _new_id("env")
        with self.database.write() as conn:
            conn.execute("INSERT INTO project_environment_configs(environment_config_id, project_id, name, environment_kind,"
                         " config_json, config_fingerprint, version, created_at, updated_at) VALUES (?,?,?,?,?,?,1,?,?)",
                         (env_id, project_id, name.strip(), "environment", json.dumps(payload), _fingerprint(payload), now, now))
        return next(e for e in self.list_environments(project_id) if e["environment_config_id"] == env_id)

    def rename(self, project_id: str, table: str, id_col: str, entity_id: str, name: str) -> None:
        with self.database.write() as conn:
            self._entity(conn, table, id_col, project_id, entity_id)
            conn.execute(f"UPDATE {table} SET name = ?, updated_at = ? WHERE {id_col} = ?",
                         (name.strip(), utc_now_iso(), entity_id))

    def list_experiments(self, project_id: str) -> list[dict[str, Any]]:
        with self.database.read() as conn:
            rows = conn.execute(
                "SELECT x.*, (SELECT COUNT(*) FROM training_runs t WHERE t.experiment_id = x.experiment_id) AS run_count "
                "FROM project_experiments x WHERE x.project_id = ? ORDER BY x.updated_at DESC, x.rowid DESC",
                (project_id,)).fetchall()
        return [dict(r) for r in rows]

    def create_experiment(self, project_id: str, *, name: str, description: str | None) -> dict[str, Any]:
        now = utc_now_iso()
        experiment_id = _new_id("exp")
        with self.database.write() as conn:
            conn.execute("INSERT INTO project_experiments(experiment_id, project_id, name, description, created_at, updated_at)"
                         " VALUES (?,?,?,?,?,?)", (experiment_id, project_id, name.strip(), description, now, now))
        return next(x for x in self.list_experiments(project_id) if x["experiment_id"] == experiment_id)

    # ------------------------------------------------------------------ comparison
    def compare(self, project_id: str, run_ids: list[str]) -> dict[str, Any]:
        runs = []
        for rid in run_ids:
            run = self.get_run(project_id, rid)
            if run is None:
                raise NotFound("a run was not found in this project")
            runs.append(run)
        reasons: list[str] = []
        if len(runs) < 2:
            reasons.append("select at least two runs")
        if len({r["environment_name"] for r in runs}) > 1:
            reasons.append("the runs use different environments, so their rewards are not comparable")
        for r in runs:
            if r["final_metrics"].get("mean_reward") is None:
                reasons.append(f"run {r['run_id']} has no recorded reward")
        return {"comparable": not reasons, "reasons": list(dict.fromkeys(reasons)), "runs": runs}
