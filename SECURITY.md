# Security Policy

## Supported Versions

| Version | Supported |
|---------|-----------|
| 7.x.x | Yes |
| < 7.0 | No |

## Reporting a Vulnerability

**Please do not report security vulnerabilities through public GitHub issues.**

Instead, please report them via email to:

**security@phoenixlink.co.za**

Include:
- Description of the vulnerability
- Steps to reproduce
- Potential impact
- Suggested fix (if any)

We will acknowledge receipt within 48 hours and provide a detailed response within 7 days.

## Security Measures

Orion implements multiple security layers:

- **AEGIS Governance** -- Hardened security gate with 6 invariants
- **Workspace Confinement** -- Operations cannot escape project directory
- **Mode Enforcement** -- Graduated permissions system (safe/pro/project)
- **Credential Encryption** -- API keys encrypted at rest via SecureStore
- **Audit Logging** -- All security-relevant events logged
- **External Access Control** -- Network operations require approval for writes
- **Code Sandbox** -- Docker-isolated execution environment

See [docs/SECURITY.md](docs/SECURITY.md) for complete security documentation.
See [docs/AEGIS.md](docs/AEGIS.md) for governance system documentation.

## Disclosure Policy

We follow responsible disclosure:

1. Reporter submits vulnerability
2. We acknowledge and investigate
3. We develop and test fix
4. We release fix and credit reporter (if desired)
5. We publish advisory after users have time to update

## Severity Response Times

| Severity | Definition | Target Response |
|----------|-----------|-----------------|
| Critical | Remote code execution, credential exposure | 24 hours |
| High | Privilege escalation, path traversal bypass | 72 hours |
| Medium | Information disclosure, denial of service | 7 days |
| Low | Minor hardening suggestions | Next release |
