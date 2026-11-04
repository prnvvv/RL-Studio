"""Register a DELIBERATE, clearly labelled demonstration fault on an existing run so the recovery flow can be demoed.

A failed requirement carries no corruption interval, so Person 4's fail-closed policy refuses to restore any checkpoint
for it. This script declares an injected fault (reward scaling) that starts after the run's first checkpoint, through the
normal incident registration contract. It writes no metrics, episodes or verdicts: the incident is labelled as injected
in its id, summary and details, and re-running it is idempotent.

    python -m scripts.seed_demo_fault --run ses_cc20e4ef_r1
"""

from __future__ import annotations

import argparse

from backend.database.config import DatabaseConfig
from backend.database.connection import Database
from backend.database.repositories import artifacts as artifacts_repo
from backend.database.repositories import runs as runs_repo
from backend.provenance.models import IncidentRegistration
from backend.provenance.service import ProvenanceService


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", required=True, help="run id with at least two checkpoints")
    args = parser.parse_args()
    db = Database(DatabaseConfig.from_env())
    db.initialize()
    with db.read() as conn:
        run = runs_repo.get_run(conn, args.run)
        checkpoints = sorted((a for a in artifacts_repo.list_artifacts_for_run(conn, args.run)
                              if a["artifact_type"] == "checkpoint" and not (a.get("metadata") or {}).get("recovery_id")),
                             key=lambda a: a.get("timestep") or 0)
    if run is None or len(checkpoints) < 2:
        raise SystemExit("The run must exist and have at least two checkpoints.")
    healthy, first_affected = checkpoints[0], checkpoints[1]
    start = int(healthy["timestep"]) + 1
    incident_id = f"inc_demo_fault_{args.run}"
    incident = ProvenanceService(db).register_incident(IncidentRegistration(
        incident_id=incident_id, run_id=args.run, environment_id=run.get("environment_id"),
        environment_version=run.get("environment_version"), source_environment_version=run.get("environment_version"),
        corruption_start_timestep=start, corruption_end_timestep=int(checkpoints[-1]["timestep"]) + 1,
        severity="high", fault_type="reward_scaling", detection_method="demo_fault_injection",
        summary="DELIBERATE DEMONSTRATION FAULT (injected): reward scaling declared from step "
                f"{start}. Not a detected training failure.",
        evidence_ids=[f"checkpoint:{first_affected['checkpoint_id']}"],
        details={"demonstration": True, "injected": True, "healthy_checkpoint": healthy["checkpoint_id"]}))
    print(f"incident: {incident.incident_id}")
    print(f"restore this healthy checkpoint in the recovery workflow: {healthy['checkpoint_id']} (step {healthy['timestep']})")


if __name__ == "__main__":
    main()
