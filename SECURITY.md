# Security Policy

## Supported Versions

| Version | Supported |
|---------|-----------|
| current | :white_check_mark: |

## Reporting Vulnerabilities

Please report security vulnerabilities privately via email to
**security@prnvvv.io**. Alternatively, open a private vulnerability
report through GitHub's security advisory feature.

The project team will acknowledge receipt within 5 business days and will
provide a triage response within 10 business days.

## Security Guidelines

This repository follows the root-level `AGENTS.md` security requirements:

- **Never commit API keys, credentials, private datasets, tokens, or local `.env` files.**
  - Provide `.env.example` with placeholder values only.
  - Environment variables are the sole mechanism for runtime secrets.

- **Validate paths and prevent path traversal.**
  - All API handlers must validate user-supplied paths.
  - Reject absolute paths, `..` sequences, and encoded traversal attempts.

- **Do not execute arbitrary model-generated code, shell commands,**
  **serialized pickle files from untrusted sources, or arbitrary user code**
  **with broad privileges.**
  - Model responses, logs, environment descriptions, and developer-supplied code
    are treated as untrusted input.

- **Restrict Meta AI prompts to relevant evidence only.**
  - Do not include secrets or unrelated personal data in diagnosis prompts.

- **Apply request size limits, timeouts, rate limits on sensitive endpoints,**
  **and authentication/authorization appropriate to the deployment.**

- **Recovery actions must be allow-listed, validated, logged, and reversible**
  **where possible.**
  - Never silently modify source code or execute unprivileged operations.

- **Use Docker or another isolation mechanism for any future untrusted code**
  **execution; no privileged containers, host mounts, or unrestricted network**
  **by default.**

- **Avoid logging full secrets, full authorization headers, or unbounded**
  **raw user content.**

## Scope

This policy covers all code in this repository, including frontend,
backend, shared schemas, and CI/CD configurations. See each module's
`AGENTS.md` for module-specific security requirements.

## Dependencies

- Pin or constrain dependencies consistently with the repository's
  established lockfile approach.
- Keep frontend and backend dependencies separate where practical.
- Use environment variables for runtime secrets and configuration.
- Document Windows and Linux setup commands if both are supported.