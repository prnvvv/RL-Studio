# Contributing to Self-Healing RL Studio

## Local Setup

1. Install Python dependencies:
   ```bash
   pip install -e ".[dev]"
   ```
2. Install Node.js dependencies:
   ```bash
   cd frontend && npm ci
   ```

## Branch and Commit Conventions

- **Always work on the `backend3` branch.** Never commit directly to `main`.
- Use conventional commit messages: `<type>: <description>`.
- Types: `feat`, `fix`, `docs`, `style`, `refactor`, `test`, `chore`.
- Commit messages must be a single line.
- Before creating a commit, inspect `git status --short` and stage only relevant files.
- Never include unrelated changes or another contributor's work without obtaining the appropriate approval.

## Formatting, Linting, and Testing

- Run formatting: `ruff format` / `black`
- Run lint: `ruff check`
- Run type check: `mypy .`
- Run unit tests: `pytest -x -v` (or `pytest -m "not slow"` to skip slow/RL tests)
- Run integration tests: `pytest -x -v tests/integration/`
- Run end-to-end tests: `pytest -x -v tests/end_to_end/`

## Pull Request Expectations

- Fill in the PR template
- Ensure all checks pass
- Address reviewer feedback promptly
- Keep commits focused and descriptive (one logical purpose per commit)
- Source branch: `backend3`; target branch: `main`
- Never create a PR from `main` to `backend3`
- Do not merge the PR unless the repository owner explicitly requests and authorizes the merge

## Issue Reporting

- Use the issue templates for bug reports and feature requests
- Include reproduction steps and environment details
- Redact secrets and personal information from logs
- Follow the repository-wide `AGENTS.md` for contract and ownership rules

## License Contributions

All contributions to this repository are governed by the project's proprietary license.
Contributions require explicit written authorization from Self-Healing RL Studio.