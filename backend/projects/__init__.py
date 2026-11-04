"""Project management: projects, intent documents and project-level requirements.

Projects sit between the landing page and the Studio workspace. This package adds *no* verification logic:
project requirements are ordinary Phase 3 records (``backend.verification``) scoped to the pseudo-run
``project:<project_id>`` until they are bound to a real run and verified by the same deterministic engine.
"""
