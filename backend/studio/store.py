"""Durable trajectory store for studio runs (SQLite, stdlib only).

Every run keeps: its configuration, every environment step (timestamp,
observation, action, reward, termination flags, next observation), episode
summaries, algorithm updates, evaluations and checkpoint metadata. That is the
data an offline-RL or replay consumer needs, queryable per run.

Schema (``SCHEMA_VERSION``)::

    runs(run_id PK, session_id, ...)            one row per run
    episodes(run_id, episode PK)                one row per finished episode
    steps(run_id, step_index PK)                one row per environment step
    updates(run_id, update_index PK)            algorithm statistics per update
    evaluations(run_id, eval_index PK)          deterministic evaluations
    checkpoints(checkpoint_id PK)               checkpoint metadata (+ private path)

Observations are stored as little-endian float32 BLOBs (``obs_shape`` on the
run row gives the layout) so a full trajectory is compact and loss-free for
float32 environments. Actions are JSON (an int, or a list for box spaces).
"""

from __future__ import annotations

import contextlib
import json
import logging
import sqlite3
import threading
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 1
STEP_FLUSH_ROWS = 500
STEP_FLUSH_SECONDS = 2.0
MAX_PAGE = 5000

_SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS runs (
    run_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    run_index INTEGER NOT NULL,
    name TEXT NOT NULL,
    agent TEXT NOT NULL,
    environment TEXT NOT NULL,
    mode TEXT NOT NULL,
    status TEXT NOT NULL,
    config_json TEXT NOT NULL,
    obs_shape TEXT,
    created_at TEXT NOT NULL,
    started_at TEXT,
    finished_at TEXT,
    error TEXT,
    step_count INTEGER NOT NULL DEFAULT 0,
    episode_count INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_runs_session ON runs(session_id, run_index);
CREATE TABLE IF NOT EXISTS episodes (
    run_id TEXT NOT NULL,
    episode INTEGER NOT NULL,
    start_step INTEGER NOT NULL,
    end_step INTEGER NOT NULL,
    started_at REAL NOT NULL,
    ended_at REAL NOT NULL,
    reward REAL NOT NULL,
    length INTEGER NOT NULL,
    success INTEGER NOT NULL,
    reason TEXT NOT NULL,
    collisions INTEGER NOT NULL,
    disturbances INTEGER NOT NULL,
    PRIMARY KEY (run_id, episode)
) WITHOUT ROWID;
CREATE TABLE IF NOT EXISTS steps (
    run_id TEXT NOT NULL,
    step_index INTEGER NOT NULL,
    episode INTEGER NOT NULL,
    episode_step INTEGER NOT NULL,
    ts REAL NOT NULL,
    obs BLOB,
    action TEXT NOT NULL,
    reward REAL NOT NULL,
    terminated INTEGER NOT NULL,
    truncated INTEGER NOT NULL,
    next_obs BLOB,
    PRIMARY KEY (run_id, step_index)
) WITHOUT ROWID;
CREATE INDEX IF NOT EXISTS idx_steps_episode ON steps(run_id, episode, episode_step);
CREATE TABLE IF NOT EXISTS updates (
    run_id TEXT NOT NULL,
    update_index INTEGER NOT NULL,
    step_index INTEGER NOT NULL,
    ts REAL NOT NULL,
    stats_json TEXT NOT NULL,
    PRIMARY KEY (run_id, update_index)
) WITHOUT ROWID;
CREATE TABLE IF NOT EXISTS evaluations (
    run_id TEXT NOT NULL,
    eval_index INTEGER NOT NULL,
    step_index INTEGER NOT NULL,
    ts REAL NOT NULL,
    stats_json TEXT NOT NULL,
    PRIMARY KEY (run_id, eval_index)
) WITHOUT ROWID;
CREATE TABLE IF NOT EXISTS checkpoints (
    checkpoint_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    step_index INTEGER NOT NULL,
    reason TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    size_bytes INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    algorithm TEXT NOT NULL,
    environment TEXT NOT NULL,
    path TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_checkpoints_run ON checkpoints(run_id, step_index);
"""


def _connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    # The recorder serialises every use of its connection with a lock, so it is
    # safe for the request thread (start_run) and training thread to share it.
    conn = sqlite3.connect(path, timeout=30, isolation_level=None, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.executescript(_SCHEMA)
    conn.execute("INSERT OR IGNORE INTO meta(key, value) VALUES ('schema_version', ?)", (str(SCHEMA_VERSION),))
    return conn


def _encode_obs(obs: Any) -> bytes | None:
    if obs is None:
        return None
    return np.asarray(obs, dtype="<f4").reshape(-1).tobytes()


def _decode_obs(blob: bytes | None) -> list[float] | None:
    if blob is None:
        return None
    return [float(v) for v in np.frombuffer(blob, dtype="<f4")]


class RunRecorder:
    """Write side: owned by one training thread, buffered, flushed in batches.

    Persistence failures never kill training, but they are never silent either:
    ``healthy`` turns false and ``last_error`` records the sanitised category so
    the session can surface it to the user.
    """

    def __init__(self, path: Path, run_id: str) -> None:
        self._path = path
        self.run_id = run_id
        self._conn: sqlite3.Connection | None = None
        self._lock = threading.Lock()
        self._steps: list[tuple[Any, ...]] = []
        self._last_flush = time.monotonic()
        self._episode = 1
        self._episode_start_step = 0
        self._episode_started_at: float | None = None
        self._step_count = 0
        self._episode_count = 0
        self._update_index = 0
        self._eval_index = 0
        self.healthy = True
        self.last_error: str | None = None

    # ------------------------------------------------------------------ helpers

    def _db(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = _connect(self._path)
        return self._conn

    def _guard(self, action: str, fn: Any) -> None:
        try:
            with self._lock:
                fn(self._db())
        except sqlite3.Error as exc:
            self.healthy = False
            self.last_error = f"{action}: {type(exc).__name__}"
            logger.exception("Trajectory store %s failed for %s", action, self.run_id)

    # -------------------------------------------------------------------- run

    def start_run(self, *, session_id: str, run_index: int, name: str, agent: str, environment: str, mode: str, config: dict[str, Any], obs_shape: list[int] | None, created_at: str, started_at: str) -> None:
        def write(db: sqlite3.Connection) -> None:
            db.execute("DELETE FROM runs WHERE run_id=?", (self.run_id,))
            db.execute(
                "INSERT INTO runs(run_id, session_id, run_index, name, agent, environment, mode, status, config_json, obs_shape, created_at, started_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (self.run_id, session_id, run_index, name, agent, environment, mode, "running", json.dumps(config, sort_keys=True), json.dumps(obs_shape), created_at, started_at),
            )

        self._guard("start_run", write)

    def finish_run(self, *, status: str, finished_at: str, error: str | None) -> None:
        self.flush()

        def write(db: sqlite3.Connection) -> None:
            db.execute(
                "UPDATE runs SET status=?, finished_at=?, error=?, step_count=?, episode_count=? WHERE run_id=?",
                (status, finished_at, error, self._step_count, self._episode_count, self.run_id),
            )

        self._guard("finish_run", write)
        with self._lock:
            if self._conn is not None:
                with contextlib.suppress(sqlite3.Error):
                    self._conn.close()
                self._conn = None

    # ------------------------------------------------------------------ steps

    def add_step(self, *, step_index: int, episode_step: int, obs: Any, action: Any, reward: float, terminated: bool, truncated: bool, next_obs: Any) -> None:
        now = time.time()
        if self._episode_started_at is None:
            self._episode_started_at = now
            self._episode_start_step = step_index
        self._steps.append(
            (self.run_id, step_index, self._episode, episode_step, now, _encode_obs(obs), json.dumps(action), float(reward), int(terminated), int(truncated), _encode_obs(next_obs))
        )
        self._step_count = step_index
        if len(self._steps) >= STEP_FLUSH_ROWS or time.monotonic() - self._last_flush >= STEP_FLUSH_SECONDS:
            self.flush()

    def end_episode(self, *, end_step: int, reward: float, length: int, success: bool, reason: str, collisions: int, disturbances: int) -> None:
        started = self._episode_started_at if self._episode_started_at is not None else time.time()
        row = (self.run_id, self._episode, self._episode_start_step, end_step, started, time.time(), float(reward), int(length), int(success), reason, int(collisions), int(disturbances))
        self._episode += 1
        self._episode_count += 1
        self._episode_started_at = None
        self.flush()
        self._guard("end_episode", lambda db: db.execute("INSERT OR REPLACE INTO episodes VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", row))

    def flush(self) -> None:
        batch, self._steps = self._steps, []
        self._last_flush = time.monotonic()
        if not batch:
            return

        def write(db: sqlite3.Connection) -> None:
            db.execute("BEGIN")
            try:
                db.executemany("INSERT OR REPLACE INTO steps VALUES (?,?,?,?,?,?,?,?,?,?,?)", batch)
                db.execute("UPDATE runs SET step_count=?, episode_count=? WHERE run_id=?", (self._step_count, self._episode_count, self.run_id))
                db.execute("COMMIT")
            except sqlite3.Error:
                db.execute("ROLLBACK")
                raise

        self._guard("flush", write)

    # ------------------------------------------------------------- side tables

    def add_update(self, step_index: int, stats: dict[str, Any]) -> None:
        self._update_index += 1
        row = (self.run_id, self._update_index, int(step_index), time.time(), json.dumps(stats, sort_keys=True))
        self._guard("add_update", lambda db: db.execute("INSERT OR REPLACE INTO updates VALUES (?,?,?,?,?)", row))

    def add_evaluation(self, step_index: int, stats: dict[str, Any]) -> None:
        self._eval_index += 1
        row = (self.run_id, self._eval_index, int(step_index), time.time(), json.dumps(stats, sort_keys=True))
        self._guard("add_evaluation", lambda db: db.execute("INSERT OR REPLACE INTO evaluations VALUES (?,?,?,?,?)", row))

    def add_checkpoint(self, record: dict[str, Any], path: str) -> None:
        row = (record["checkpoint_id"], self.run_id, int(record["timestep"]), record["reason"], record["sha256"], int(record["size_bytes"]), record["created_at"], record["algorithm"], record["environment"], path)
        self._guard("add_checkpoint", lambda db: db.execute("INSERT OR REPLACE INTO checkpoints VALUES (?,?,?,?,?,?,?,?,?,?)", row))


class TrajectoryReader:
    """Read side: short-lived connections, safe to use from API threads."""

    def __init__(self, path: Path) -> None:
        self._path = path

    @contextlib.contextmanager
    def _db(self) -> Iterator[sqlite3.Connection]:
        conn = _connect(self._path)
        try:
            yield conn
        finally:
            conn.close()

    @staticmethod
    def _run(row: sqlite3.Row) -> dict[str, Any]:
        data = dict(row)
        data["config"] = json.loads(data.pop("config_json"))
        data["obs_shape"] = json.loads(data["obs_shape"]) if data["obs_shape"] else None
        return data

    def list_runs(self, session_id: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        with self._db() as db:
            if session_id is None:
                rows = db.execute("SELECT * FROM runs ORDER BY created_at DESC, run_index DESC LIMIT ?", (limit,)).fetchall()
            else:
                rows = db.execute("SELECT * FROM runs WHERE session_id=? ORDER BY run_index", (session_id,)).fetchall()
        return [self._run(r) for r in rows]

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        with self._db() as db:
            row = db.execute("SELECT * FROM runs WHERE run_id=?", (run_id,)).fetchone()
        return self._run(row) if row else None

    def episodes(self, run_id: str, offset: int, limit: int) -> list[dict[str, Any]]:
        with self._db() as db:
            rows = db.execute("SELECT * FROM episodes WHERE run_id=? ORDER BY episode LIMIT ? OFFSET ?", (run_id, min(limit, MAX_PAGE), offset)).fetchall()
        return [{**dict(r), "success": bool(r["success"])} for r in rows]

    @staticmethod
    def _step(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "step_index": row["step_index"],
            "episode": row["episode"],
            "episode_step": row["episode_step"],
            "timestamp": row["ts"],
            "observation": _decode_obs(row["obs"]),
            "action": json.loads(row["action"]),
            "reward": row["reward"],
            "terminated": bool(row["terminated"]),
            "truncated": bool(row["truncated"]),
            "next_observation": _decode_obs(row["next_obs"]),
        }

    def steps(self, run_id: str, *, episode: int | None, offset: int, limit: int) -> list[dict[str, Any]]:
        query = "SELECT * FROM steps WHERE run_id=?"
        args: list[Any] = [run_id]
        if episode is not None:
            query += " AND episode=?"
            args.append(episode)
        query += " ORDER BY step_index LIMIT ? OFFSET ?"
        args += [min(limit, MAX_PAGE), offset]
        with self._db() as db:
            rows = db.execute(query, args).fetchall()
        return [self._step(r) for r in rows]

    def iter_steps(self, run_id: str, chunk: int = 1000) -> Iterator[dict[str, Any]]:
        last = -1
        while True:
            with self._db() as db:
                rows = db.execute("SELECT * FROM steps WHERE run_id=? AND step_index>? ORDER BY step_index LIMIT ?", (run_id, last, chunk)).fetchall()
            if not rows:
                return
            for row in rows:
                yield self._step(row)
            last = rows[-1]["step_index"]

    def table(self, run_id: str, table: str, offset: int, limit: int) -> list[dict[str, Any]]:
        order = {"updates": "update_index", "evaluations": "eval_index"}[table]
        with self._db() as db:
            rows = db.execute(f"SELECT * FROM {table} WHERE run_id=? ORDER BY {order} LIMIT ? OFFSET ?", (run_id, min(limit, MAX_PAGE), offset)).fetchall()
        out = []
        for r in rows:
            data = dict(r)
            data.update(json.loads(data.pop("stats_json")))
            out.append(data)
        return out

    def checkpoints(self, run_id: str) -> list[dict[str, Any]]:
        with self._db() as db:
            rows = db.execute("SELECT checkpoint_id, run_id, step_index AS timestep, reason, sha256, size_bytes, created_at, algorithm, environment FROM checkpoints WHERE run_id=? ORDER BY step_index", (run_id,)).fetchall()
        return [dict(r) for r in rows]
