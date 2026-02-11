# Security Model

Comprehensive documentation of Orion Agent's security architecture, threat model, and controls.

## Security Philosophy

Orion operates on the principle of **governed autonomy** -- AI agents are powerful but operate within strict, non-negotiable boundaries. Security is not a feature; it's an architectural invariant.

## Threat Model

### Threats We Protect Against

| Threat | Vector | Mitigation |
|--------|--------|------------|
| Path traversal | `../` in file paths | AEGIS 6-layer path confinement |
| Unauthorized file access | Reading files outside workspace | Workspace confinement |
| Unauthorized modification | Writing files without permission | Mode enforcement + approval gates |
| Shell injection | Dangerous commands | Command pattern validation |
| Credential theft | API key exposure | Encrypted SecureStore |
| Prompt injection | Manipulating agent behavior | Persona compilation, Governor determinism |
| Unauthorized network access | Exfiltrating data | External access control |
| Privilege escalation | Agent bypassing AEGIS | Pure-function design, no state |

### Threats We Do NOT Protect Against

| Threat | Reason | Recommendation |
|--------|--------|----------------|
| Malware in dependencies | Out of scope | Use dependency scanning tools |
| Compromised LLM API | Third-party risk | Monitor API usage, use local Ollama |
| Physical access | OS-level concern | Use OS-level security |
| Network interception | Transport-level | Use HTTPS/TLS in production |

## Security Layers

### Layer 1: AEGIS Governance

The primary security gate. See [AEGIS documentation](AEGIS.md) for full details.

- 6 invariants enforced on every operation
- Pure-function design (no state, no bypass)
- 6-layer path traversal defense
- 46 security tests

### Layer 2: Mode Enforcement

Graduated permissions that limit what operations are possible:

| Mode | Allowed Operations |
|------|-------------------|
| `safe` | Read files, analyze code, explain |
| `pro` | Read + write (with human approval for each change) |
| `project` | Read + write + execute (allowlisted commands only) |

Mode enforcement is part of AEGIS and cannot be bypassed.

### Layer 3: Credential Store

API keys and sensitive data are stored encrypted:

- **Encryption:** Fernet symmetric encryption (AES-128-CBC)
- **Key derivation:** Machine-specific key derived from hardware identifiers
- **Storage:** `~/.orion/credentials.enc`
- **Access logging:** Every credential access is logged with caller information (module:function:line)

```python
# Credential access is audited
store = SecureStore()
key = store.get_key("openai")  # Logged: orion.core.llm.providers:call_provider:45
```

### Layer 4: Workspace Sandbox

File operations are isolated to the workspace:

- **Local mode:** Temp-directory copy with subprocess restrictions
- **Docker mode:** Full container isolation with mounted files
- **Edit-review-promote cycle:** Changes are staged before being applied

### Layer 5: Code Execution Sandbox

Untrusted code runs in Docker containers:

- **Per-language images:** python:3.11-slim, node:20-slim, ubuntu:22.04
- **Network isolation:** `--network=none` by default
- **Timeout:** 60 seconds default
- **No persistent state:** Containers are ephemeral

### Layer 6: External Access Control

Network operations follow strict rules:

| Method | Auto-Approved | Requires Approval |
|--------|---------------|-------------------|
| GET/HEAD/OPTIONS | Yes (read-only) | No |
| POST/PUT/PATCH/DELETE | Never | Always |
| Known safe POST URLs | Yes (e.g., Notion search) | No |
| No approval callback | All writes BLOCKED | N/A |

### Layer 7: Audit Logging

All security-relevant events are logged:

- AEGIS validation decisions (pass/fail with reason)
- Credential access (with caller tracking)
- File operations (path, operation, outcome)
- Command execution (command, approval status)
- External API calls (URL, method, approval)

Log location: `~/.orion/logs/`

## Credential Handling

### API Key Security

- Keys are **never** logged or included in error messages
- Keys are **never** sent to LLM providers in prompts
- Keys are stored encrypted at rest (SecureStore)
- Environment variables are read once and not persisted by Orion

### Setting API Keys

**Recommended (environment variable):**
```bash
export OPENAI_API_KEY="sk-..."
```

**Alternative (encrypted store):**
```
> /settings key openai sk-your-key
# Key is encrypted and stored in ~/.orion/credentials.enc
```

### Key Rotation

Simply set a new key -- the old one is overwritten:
```
> /settings key openai sk-new-key
```

## Security Best Practices

### For Users

1. **Start with safe mode** -- Use `safe` for unfamiliar codebases
2. **Review all changes** -- Use `pro` mode for active development
3. **Limit project mode** -- Only use `project` mode when needed
4. **Rotate API keys** -- Change keys periodically
5. **Check doctor** -- Run `/doctor` to verify security configuration
6. **Use Ollama** -- For maximum privacy, run models locally

### For Deployment

1. **Use HTTPS** -- Always use TLS in production
2. **Enable authentication** -- Use the API authentication middleware
3. **Rate limiting** -- Configure rate limiting for public deployments
4. **Network segmentation** -- Isolate the Orion API server
5. **Log monitoring** -- Monitor AEGIS and audit logs
6. **Regular updates** -- Keep Orion updated for security patches

## Incident Response

### Reporting Vulnerabilities

**Do not report security vulnerabilities through public GitHub issues.**

Report via email: **info@phoenixlink.co.za**

Include:
- Description of the vulnerability
- Steps to reproduce
- Potential impact
- Suggested fix (if any)

### Response Timeline

- **Acknowledgment:** Within 48 hours
- **Detailed response:** Within 7 days
- **Fix timeline:** Depends on severity

### Severity Classification

| Severity | Definition | Response Time |
|----------|-----------|---------------|
| Critical | Remote code execution, credential exposure | 24 hours |
| High | Privilege escalation, path traversal bypass | 72 hours |
| Medium | Information disclosure, denial of service | 7 days |
| Low | Minor issues, hardening suggestions | Next release |

## Source Files

| File | Description |
|------|-------------|
| `src/orion/core/governance/aegis.py` | AEGIS governance gate |
| `src/orion/security/store.py` | Encrypted credential store |
| `src/orion/security/sandbox.py` | Docker code execution sandbox |
| `src/orion/security/workspace_sandbox.py` | Workspace isolation |
| `src/orion/api/server.py` | Rate limiting + auth middleware |
| `tests/unit/test_governance.py` | AEGIS security tests (46 tests) |

---

**Next:** [AEGIS](AEGIS.md) | [Deployment](DEPLOYMENT.md)
