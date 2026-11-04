from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from backend.database.config import DatabaseConfig
from backend.database.connection import Database
from backend.database.exceptions import (
    ArtifactPathError,
    OperationLockedError,
)
from backend.database.paths import normalize_artifact_path, resolve_artifact_path
from backend.database.repositories import artifacts, audit, locks, runs
from backend.database.utils import sha256_file


class DatabaseFoundationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        self.config = DatabaseConfig.for_tests(self.root)
        self.db = Database(self.config)
        self.db.initialize()

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def test_migrations_are_idempotent_and_recorded(self) -> None:
        self.db.initialize()
        with self.db.read() as conn:
            rows = conn.execute(
                "SELECT version, name FROM schema_migrations ORDER BY version"
            ).fetchall()
        self.assertEqual([row["version"] for row in rows], [1, 2, 3, 4, 5, 6])
        self.assertEqual(rows[0]["name"], "initial_person4_schema")

    def test_write_transaction_rolls_back(self) -> None:
        with self.assertRaises(RuntimeError), self.db.write() as conn:
            runs.create_run(conn, run_id="run_rollback")
            raise RuntimeError("force rollback")
        with self.db.read() as conn:
            self.assertIsNone(runs.get_run(conn, "run_rollback"))

    def test_artifact_registry_round_trip_and_hash(self) -> None:
        artifact_file = self.config.artifact_root / "run_1" / "checkpoint.zip"
        artifact_file.parent.mkdir(parents=True, exist_ok=True)
        artifact_file.write_bytes(b"checkpoint-bytes")
        digest = sha256_file(artifact_file)

        with self.db.write() as conn:
            runs.create_run(
                conn,
                run_id="run_1",
                environment_id="warehouse",
                environment_version="v1",
            )
            created = artifacts.create_artifact(
                conn,
                artifact_id="artifact_1",
                run_id="run_1",
                artifact_type="checkpoint",
                artifact_path="run_1/checkpoint.zip",
                artifact_hash=digest,
                artifact_status="available",
                integrity_status="verified",
                checkpoint_id="checkpoint_1",
                timestep=100,
                included_state_components=["policy", "optimizer"],
                metadata={"note": "fixture"},
            )

        self.assertEqual(created["artifact_hash"], digest)
        self.assertEqual(created["included_state_components"], ["policy", "optimizer"])
        self.assertEqual(created["metadata"]["note"], "fixture")
        with self.db.read() as conn:
            loaded = artifacts.get_artifact(conn, "artifact_1")
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded["checkpoint_id"], "checkpoint_1")

    def test_audit_events_are_append_only(self) -> None:
        with self.db.write() as conn:
            audit_id = audit.append_audit(
                conn,
                entity_type="recovery",
                entity_id="recovery_1",
                action="created",
                status="proposed",
            )
        with self.assertRaises(sqlite3.IntegrityError), self.db.write() as conn:
            conn.execute(
                "UPDATE audit_events SET status = 'completed' WHERE audit_id = ?",
                (audit_id,),
            )
        with self.assertRaises(sqlite3.IntegrityError), self.db.write() as conn:
            conn.execute("DELETE FROM audit_events WHERE audit_id = ?", (audit_id,))

    def test_path_traversal_is_rejected(self) -> None:
        for value in ("../secret", "/etc/passwd", "a/../../b", "a\\b", ""):
            with self.assertRaises(ArtifactPathError):
                normalize_artifact_path(value)
        self.assertEqual(
            resolve_artifact_path(self.config.artifact_root, "run_1/cp.zip").name,
            "cp.zip",
        )

    def test_operation_lock_blocks_concurrent_owner(self) -> None:
        with self.db.write() as conn:
            owner = locks.acquire_lock(conn, lock_key="recovery:run_1", owner_id="a")
        self.assertEqual(owner, "a")
        with self.assertRaises(OperationLockedError), self.db.write() as conn:
            locks.acquire_lock(
                conn, lock_key="recovery:run_1", owner_id="b"
            )
        with self.db.write() as conn:
            locks.release_lock(conn, lock_key="recovery:run_1", owner_id="a")
            locks.acquire_lock(conn, lock_key="recovery:run_1", owner_id="b")


if __name__ == "__main__":
    unittest.main()
