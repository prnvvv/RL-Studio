"""Forward-only SQLite migrations.

Migrations are immutable once applied.  To change a deployed schema, append a
new migration rather than editing an existing one.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable
from dataclasses import dataclass

from .utils import utc_now_iso


@dataclass(frozen=True)
class Migration:
    version: int
    name: str
    statements: tuple[str, ...]


MIGRATION_1_STATEMENTS: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS schema_migrations (
        version INTEGER PRIMARY KEY,
        name TEXT NOT NULL,
        applied_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS runs (
        run_id TEXT PRIMARY KEY,
        project_id TEXT,
        experiment_id TEXT,
        environment_id TEXT,
        environment_version TEXT,
        agent_config_fingerprint TEXT,
        status TEXT NOT NULL DEFAULT 'created',
        metadata_json TEXT NOT NULL DEFAULT '{}',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS artifacts (
        artifact_id TEXT PRIMARY KEY,
        run_id TEXT NOT NULL,
        artifact_type TEXT NOT NULL,
        artifact_path TEXT NOT NULL,
        artifact_hash TEXT,
        artifact_version TEXT,
        artifact_status TEXT NOT NULL,
        artifact_created_at TEXT NOT NULL,
        parent_artifact_id TEXT,
        checkpoint_id TEXT,
        checkpoint_path TEXT,
        policy_version TEXT,
        trajectory_id TEXT,
        experience_id TEXT,
        policy_update_id TEXT,
        environment_id TEXT,
        environment_version TEXT,
        agent_config_fingerprint TEXT,
        episode_id TEXT,
        timestep INTEGER,
        update_index INTEGER,
        included_state_components_json TEXT NOT NULL DEFAULT '[]',
        integrity_status TEXT NOT NULL,
        metadata_schema_version TEXT NOT NULL DEFAULT '1.0',
        metadata_json TEXT NOT NULL DEFAULT '{}',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_artifacts_run ON artifacts(run_id)",
    "CREATE INDEX IF NOT EXISTS idx_artifacts_type ON artifacts(artifact_type)",
    "CREATE INDEX IF NOT EXISTS idx_artifacts_parent ON artifacts(parent_artifact_id)",
    "CREATE INDEX IF NOT EXISTS idx_artifacts_checkpoint ON artifacts(checkpoint_id)",
    "CREATE INDEX IF NOT EXISTS idx_artifacts_trajectory ON artifacts(trajectory_id)",
    "CREATE INDEX IF NOT EXISTS idx_artifacts_update ON artifacts(policy_update_id)",
    """
    CREATE TABLE IF NOT EXISTS artifact_links (
        link_id TEXT PRIMARY KEY,
        run_id TEXT NOT NULL,
        from_artifact_id TEXT NOT NULL,
        to_artifact_id TEXT NOT NULL,
        relation TEXT NOT NULL,
        created_at TEXT NOT NULL,
        UNIQUE(from_artifact_id, to_artifact_id, relation)
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_artifact_links_run ON artifact_links(run_id)",
    """
    CREATE TABLE IF NOT EXISTS incidents (
        incident_id TEXT PRIMARY KEY,
        run_id TEXT NOT NULL,
        verification_id TEXT,
        environment_id TEXT,
        environment_version TEXT,
        requirement_id TEXT,
        status TEXT NOT NULL,
        severity TEXT,
        detection_method TEXT,
        summary TEXT,
        evidence_ids_json TEXT NOT NULL DEFAULT '[]',
        details_json TEXT NOT NULL DEFAULT '{}',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_incidents_run ON incidents(run_id)",
    """
    CREATE TABLE IF NOT EXISTS incident_faults (
        incident_id TEXT PRIMARY KEY,
        source_environment_version TEXT,
        corruption_start_timestep INTEGER,
        corruption_end_timestep INTEGER,
        fault_type TEXT,
        created_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS provenance_records (
        provenance_id TEXT PRIMARY KEY,
        run_id TEXT NOT NULL UNIQUE,
        provenance_status TEXT NOT NULL,
        lineage_completeness TEXT NOT NULL,
        source_environment_version TEXT,
        artifact_count INTEGER NOT NULL DEFAULT 0,
        warnings_json TEXT NOT NULL DEFAULT '[]',
        evidence_ids_json TEXT NOT NULL DEFAULT '[]',
        details_json TEXT NOT NULL DEFAULT '{}',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS impact_analyses (
        impact_id TEXT PRIMARY KEY,
        incident_id TEXT NOT NULL,
        run_id TEXT NOT NULL,
        impact_status TEXT NOT NULL,
        impact_score REAL,
        source_environment_version TEXT,
        corruption_start_timestep INTEGER,
        corruption_end_timestep INTEGER,
        affected_artifact_ids_json TEXT NOT NULL DEFAULT '[]',
        affected_trajectory_ids_json TEXT NOT NULL DEFAULT '[]',
        affected_policy_update_ids_json TEXT NOT NULL DEFAULT '[]',
        affected_checkpoint_ids_json TEXT NOT NULL DEFAULT '[]',
        evidence_ids_json TEXT NOT NULL DEFAULT '[]',
        warnings_json TEXT NOT NULL DEFAULT '[]',
        errors_json TEXT NOT NULL DEFAULT '[]',
        details_json TEXT NOT NULL DEFAULT '{}',
        created_at TEXT NOT NULL,
        completed_at TEXT
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_impact_incident ON impact_analyses(incident_id, created_at)",
    """
    CREATE TABLE IF NOT EXISTS recovery_assessments (
        recovery_assessment_id TEXT PRIMARY KEY,
        incident_id TEXT NOT NULL,
        recovery_eligibility TEXT NOT NULL,
        recovery_strategy TEXT NOT NULL,
        recovery_reason TEXT,
        source_checkpoint_id TEXT,
        target_environment_version TEXT,
        target_agent_config_fingerprint TEXT,
        compatibility_json TEXT NOT NULL DEFAULT '[]',
        lineage_gaps_json TEXT NOT NULL DEFAULT '[]',
        evidence_ids_json TEXT NOT NULL DEFAULT '[]',
        warnings_json TEXT NOT NULL DEFAULT '[]',
        errors_json TEXT NOT NULL DEFAULT '[]',
        details_json TEXT NOT NULL DEFAULT '{}',
        idempotency_key TEXT UNIQUE,
        created_at TEXT NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_assessment_incident ON recovery_assessments(incident_id)",
    """
    CREATE TABLE IF NOT EXISTS recoveries (
        recovery_id TEXT PRIMARY KEY,
        incident_id TEXT NOT NULL,
        assessment_id TEXT,
        recovery_status TEXT NOT NULL,
        recovery_strategy TEXT NOT NULL,
        recovery_reason TEXT,
        source_checkpoint_id TEXT,
        recovery_artifact_id TEXT,
        recovered_checkpoint_id TEXT,
        target_environment_version TEXT,
        target_agent_config_fingerprint TEXT,
        recovery_started_at TEXT,
        recovery_completed_at TEXT,
        proposed_actions_json TEXT NOT NULL DEFAULT '[]',
        executed_actions_json TEXT NOT NULL DEFAULT '[]',
        preflight_json TEXT NOT NULL DEFAULT '{}',
        failure_reason TEXT,
        evidence_ids_json TEXT NOT NULL DEFAULT '[]',
        warnings_json TEXT NOT NULL DEFAULT '[]',
        errors_json TEXT NOT NULL DEFAULT '[]',
        details_json TEXT NOT NULL DEFAULT '{}',
        idempotency_key TEXT UNIQUE,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_recoveries_incident ON recoveries(incident_id)",
    """
    CREATE TABLE IF NOT EXISTS evaluations (
        evaluation_id TEXT PRIMARY KEY,
        incident_id TEXT NOT NULL,
        recovery_id TEXT,
        baseline_run_id TEXT,
        recovered_run_id TEXT,
        evaluation_status TEXT NOT NULL,
        evaluation_environment_version TEXT,
        baseline_mean_reward REAL,
        recovered_mean_reward REAL,
        baseline_success_rate REAL,
        recovered_success_rate REAL,
        baseline_episode_length REAL,
        recovered_episode_length REAL,
        reward_improvement REAL,
        success_rate_improvement REAL,
        evaluation_metrics_json TEXT NOT NULL DEFAULT '{}',
        comparison_results_json TEXT NOT NULL DEFAULT '{}',
        acceptance_criteria_json TEXT NOT NULL DEFAULT '{}',
        recovery_verification_status TEXT NOT NULL,
        recovery_verified INTEGER NOT NULL DEFAULT 0,
        episode_count INTEGER,
        seeds_json TEXT NOT NULL DEFAULT '[]',
        evidence_ids_json TEXT NOT NULL DEFAULT '[]',
        warnings_json TEXT NOT NULL DEFAULT '[]',
        errors_json TEXT NOT NULL DEFAULT '[]',
        details_json TEXT NOT NULL DEFAULT '{}',
        idempotency_key TEXT UNIQUE,
        created_at TEXT NOT NULL,
        completed_at TEXT
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_evaluations_incident ON evaluations(incident_id)",
    """
    CREATE TABLE IF NOT EXISTS audit_events (
        audit_id TEXT PRIMARY KEY,
        entity_type TEXT NOT NULL,
        entity_id TEXT NOT NULL,
        action TEXT NOT NULL,
        status TEXT NOT NULL,
        actor TEXT,
        correlation_id TEXT,
        details_json TEXT NOT NULL DEFAULT '{}',
        created_at TEXT NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_audit_entity ON audit_events(entity_type, entity_id)",
    """
    CREATE TABLE IF NOT EXISTS operation_locks (
        lock_key TEXT PRIMARY KEY,
        owner_id TEXT NOT NULL,
        acquired_at TEXT NOT NULL,
        expires_at TEXT NOT NULL
    )
    """,
    """
    CREATE TRIGGER IF NOT EXISTS audit_events_no_update
    BEFORE UPDATE ON audit_events
    BEGIN
        SELECT RAISE(ABORT, 'audit_events is append-only');
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS audit_events_no_delete
    BEFORE DELETE ON audit_events
    BEGIN
        SELECT RAISE(ABORT, 'audit_events is append-only');
    END
    """,
)


#: Phase 3 (Person 3): intent interpretation, requirement lifecycle, persisted verifications and the
#: verification -> incident association. Additive only; no Person 4 table is altered. Incidents are
#: still written through ``ProvenanceService.register_incident`` - ``verification_incident_links`` only
#: records which incident a verification produced (and the handoff outcome).
MIGRATION_2_STATEMENTS: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS verification_intents (
        intent_id TEXT PRIMARY KEY,
        run_id TEXT NOT NULL,
        environment_id TEXT,
        environment_version TEXT,
        original_text TEXT NOT NULL,
        context_json TEXT NOT NULL DEFAULT '{}',
        status TEXT NOT NULL,
        status_reason TEXT,
        interpretation_json TEXT NOT NULL DEFAULT '{}',
        ai_json TEXT NOT NULL DEFAULT '{}',
        source_refs_json TEXT NOT NULL DEFAULT '{}',
        idempotency_key TEXT NOT NULL,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_vintents_run ON verification_intents(run_id, created_at)",
    "CREATE INDEX IF NOT EXISTS idx_vintents_key ON verification_intents(idempotency_key)",
    """
    CREATE TABLE IF NOT EXISTS verification_requirements (
        requirement_id TEXT PRIMARY KEY,
        intent_id TEXT NOT NULL,
        run_id TEXT NOT NULL,
        environment_id TEXT,
        environment_version TEXT,
        category TEXT NOT NULL,
        source_statement TEXT NOT NULL,
        description TEXT NOT NULL,
        criterion TEXT,
        comparison_operator TEXT,
        expected_value_json TEXT,
        tolerance REAL,
        evidence_required_json TEXT NOT NULL DEFAULT '[]',
        lifecycle_status TEXT NOT NULL,
        validation_status TEXT NOT NULL,
        validation_json TEXT NOT NULL DEFAULT '{}',
        requirement_json TEXT NOT NULL,
        last_verification_id TEXT,
        last_result_status TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        confirmed_at TEXT
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_vreq_intent ON verification_requirements(intent_id)",
    "CREATE INDEX IF NOT EXISTS idx_vreq_run ON verification_requirements(run_id, created_at)",
    """
    CREATE TABLE IF NOT EXISTS verifications (
        verification_id TEXT PRIMARY KEY,
        run_id TEXT NOT NULL,
        intent_id TEXT,
        environment_id TEXT,
        environment_version TEXT,
        overall_status TEXT NOT NULL,
        contract_status TEXT,
        idempotency_key TEXT NOT NULL UNIQUE,
        requirement_ids_json TEXT NOT NULL DEFAULT '[]',
        traceability_json TEXT NOT NULL DEFAULT '{}',
        output_json TEXT NOT NULL,
        created_at TEXT NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_verifications_run ON verifications(run_id, created_at)",
    """
    CREATE TABLE IF NOT EXISTS verification_results (
        verification_id TEXT NOT NULL,
        requirement_id TEXT NOT NULL,
        status TEXT NOT NULL,
        contract_status TEXT,
        expected_json TEXT,
        actual_json TEXT,
        tolerance REAL,
        evidence_refs_json TEXT NOT NULL DEFAULT '[]',
        details_json TEXT NOT NULL DEFAULT '{}',
        is_mandatory INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL,
        PRIMARY KEY (verification_id, requirement_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS verification_incident_links (
        verification_id TEXT PRIMARY KEY,
        run_id TEXT NOT NULL,
        incident_id TEXT,
        handoff_status TEXT NOT NULL,
        failed_requirement_ids_json TEXT NOT NULL DEFAULT '[]',
        error_code TEXT,
        attempts INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_vlinks_incident ON verification_incident_links(incident_id)",
)


#: Project management. Additive only: ``runs.project_id`` (migration 1) is the run -> project association,
#: and every project requirement/intent is a normal Phase 3 record in ``verification_intents`` /
#: ``verification_requirements`` scoped to the pseudo-run ``project:<project_id>``; the tables below only add
#: the project-level metadata, revision history and the project <-> run verification association.
#: Deleting a project is a soft delete (``status = 'deleted'``): no run, evidence, incident or verification
#: record is ever removed.
MIGRATION_3_STATEMENTS: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS projects (
        project_id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        description TEXT,
        status TEXT NOT NULL DEFAULT 'active',
        agent_json TEXT NOT NULL DEFAULT '{}',
        environment_json TEXT NOT NULL DEFAULT '{}',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        deleted_at TEXT
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_projects_status ON projects(status, updated_at)",
    "CREATE INDEX IF NOT EXISTS idx_runs_project ON runs(project_id)",
    """
    CREATE TABLE IF NOT EXISTS project_documents (
        document_id TEXT PRIMARY KEY,
        project_id TEXT NOT NULL,
        filename TEXT NOT NULL,
        content_type TEXT NOT NULL,
        size_bytes INTEGER NOT NULL,
        sha256 TEXT NOT NULL,
        storage_reference TEXT NOT NULL,
        extraction_status TEXT NOT NULL,
        extraction_error TEXT,
        extracted_text TEXT,
        text_chars INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_pdocs_project ON project_documents(project_id, created_at)",
    """
    CREATE TABLE IF NOT EXISTS project_intent_links (
        intent_id TEXT PRIMARY KEY,
        project_id TEXT NOT NULL,
        stage TEXT NOT NULL,
        run_id TEXT,
        document_ids_json TEXT NOT NULL DEFAULT '[]',
        source_json TEXT NOT NULL DEFAULT '{}',
        created_at TEXT NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_pintents_project ON project_intent_links(project_id, created_at)",
    """
    CREATE TABLE IF NOT EXISTS project_requirement_links (
        requirement_id TEXT PRIMARY KEY,
        project_id TEXT NOT NULL,
        requirement_key TEXT NOT NULL,
        requirement_revision INTEGER NOT NULL,
        supersedes_requirement_id TEXT,
        stage TEXT NOT NULL,
        source_json TEXT NOT NULL DEFAULT '{}',
        created_at TEXT NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_preqs_project ON project_requirement_links(project_id, requirement_key)",
    """
    CREATE TABLE IF NOT EXISTS project_run_bindings (
        requirement_id TEXT NOT NULL,
        run_id TEXT NOT NULL,
        project_id TEXT NOT NULL,
        run_requirement_id TEXT NOT NULL,
        intent_id TEXT NOT NULL,
        created_at TEXT NOT NULL,
        PRIMARY KEY (requirement_id, run_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS project_run_verifications (
        project_id TEXT NOT NULL,
        run_id TEXT NOT NULL,
        verification_id TEXT NOT NULL,
        requirement_id TEXT NOT NULL,
        requirement_revision INTEGER NOT NULL,
        run_requirement_id TEXT NOT NULL,
        evaluation_status TEXT NOT NULL,
        stage TEXT NOT NULL,
        run_status TEXT,
        evidence_references_json TEXT NOT NULL DEFAULT '[]',
        evaluation_window_json TEXT NOT NULL DEFAULT '{}',
        created_at TEXT NOT NULL,
        PRIMARY KEY (verification_id, requirement_id)
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_prv_project_run ON project_run_verifications(project_id, run_id, created_at)",
)


MIGRATIONS: tuple[Migration, ...] = (
    Migration(version=1, name="initial_person4_schema", statements=MIGRATION_1_STATEMENTS),
    Migration(version=2, name="person3_verification_lifecycle", statements=MIGRATION_2_STATEMENTS),
    Migration(version=3, name="project_management", statements=MIGRATION_3_STATEMENTS),
)


def _applied_versions(conn: sqlite3.Connection) -> set[int]:
    try:
        rows = conn.execute("SELECT version FROM schema_migrations").fetchall()
    except sqlite3.OperationalError:
        return set()
    return {int(row[0]) for row in rows}


def apply_migrations(conn: sqlite3.Connection, migrations: Iterable[Migration] = MIGRATIONS) -> list[int]:
    applied = _applied_versions(conn)
    newly_applied: list[int] = []
    for migration in sorted(migrations, key=lambda item: item.version):
        if migration.version in applied:
            continue
        for statement in migration.statements:
            conn.execute(statement)
        conn.execute(
            "INSERT INTO schema_migrations(version, name, applied_at) VALUES (?, ?, ?)",
            (migration.version, migration.name, utc_now_iso()),
        )
        newly_applied.append(migration.version)
    return newly_applied
