"""Database foundation for persistence layer."""
from __future__ import annotations

import sqlite3
import hashlib
from pathlib import Path
from typing import Any, Dict, Optional, List


class ArtifactRegistry:
    """Registry for tracking artifact lineage and integrity."""

    def __init__(self, db_path: str = "artifacts.db") -> None:
        self.db_path = Path(db_path)
        self._init_db()

    def _init_db(self) -> None:
        """Initialize the database with required tables."""
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS artifacts (
                artifact_id TEXT PRIMARY KEY,
                checkpoint_hash TEXT NOT NULL,
                environment_version TEXT NOT NULL,
                algorithm TEXT NOT NULL,
                seed INTEGER,
                created_at TEXT DEFAULT (datetime('now')),
                metadata TEXT DEFAULT '{}'
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS checkpoint_metadata (
                checkpoint_id TEXT PRIMARY KEY,
                hash TEXT NOT NULL,
                environment_version TEXT NOT NULL,
                algorithm TEXT NOT NULL,
                required_metadata TEXT DEFAULT '{}',
                created_at TEXT DEFAULT (datetime('now')),
                integrity_valid INTEGER DEFAULT 1
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS artifact_lineage (
                lineage_id TEXT PRIMARY KEY,
                source_artifact_id TEXT NOT NULL,
                target_artifact_id TEXT,
                run_id TEXT NOT NULL,
                transition_reason TEXT,
                created_at TEXT DEFAULT (datetime('now')),
                integrity_valid INTEGER DEFAULT 1
            )
        """)
        conn.commit()
        conn.close()

    def ArtifactMetadata(self, artifact_id: str, checkpoint_hash: str,
                        environment_version: str, algorithm: str,
                        seed: Optional[int] = None,
                        metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Create artifact metadata record."""
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        metadata_json = str(metadata) if metadata else "{}"
        cursor.execute(
            "INSERT OR REPLACE INTO artifacts (artifact_id, checkpoint_hash, environment_version, algorithm, seed, metadata) VALUES (?, ?, ?, ?, ?, ?)",
            (artifact_id, checkpoint_hash, environment_version, algorithm, seed, metadata_json),
        )
        conn.commit()
        conn.close()
        return {"artifact_id": artifact_id, "status": "recorded"}

    def CheckpointMetadata(self, checkpoint_id: str, hash: str,
                          environment_version: str, algorithm: str,
                          required_metadata: Optional[Dict[str, Any]] = None,
                          integrity_valid: int = 1) -> Dict[str, Any]:
        """Create checkpoint metadata record."""
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        required_json = str(required_metadata) if required_metadata else "{}"
        cursor.execute(
            "INSERT OR REPLACE INTO checkpoint_metadata (checkpoint_id, hash, environment_version, algorithm, required_metadata, integrity_valid) VALUES (?, ?, ?, ?, ?, ?)",
            (checkpoint_id, hash, environment_version, algorithm, required_json, integrity_valid),
        )
        conn.commit()
        conn.close()
        return {"checkpoint_id": checkpoint_id, "status": "recorded"}

    def ArtifactLineage(self, lineage_id: str, source_artifact_id: str,
                       target_artifact_id: Optional[str], run_id: str,
                       transition_reason: Optional[str] = None) -> Dict[str, Any]:
        """Create artifact lineage record."""
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        cursor.execute(
            "INSERT OR REPLACE INTO artifact_lineage (lineage_id, source_artifact_id, target_artifact_id, run_id, transition_reason, created_at) VALUES (?, ?, ?, ?, ?, datetime('now'))",
            (lineage_id, source_artifact_id, target_artifact_id, run_id, transition_reason),
        )
        conn.commit()
        conn.close()
        return {"lineage_id": lineage_id, "status": "recorded"}


# Global registry instance
registry = ArtifactRegistry()
