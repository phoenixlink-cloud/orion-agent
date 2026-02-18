# AEGIS: Autonomous Execution Governance and Integrity System

AEGIS is Orion's security core -- a hardened governance gate that ensures all AI operations are safe, authorized, and confined to appropriate boundaries.

## Why AEGIS Exists

AI coding assistants are powerful but dangerous. Without proper governance, they can:

- Modify files outside your project
- Execute arbitrary shell commands
- Access sensitive data without permission
- Make changes you didn't authorize

AEGIS prevents all of these by enforcing **strict invariants** that cannot be bypassed, disabled, or reconfigured by AI agents.

## Design Philosophy

AEGIS is designed as a **pure-function security gate**:

- **No side effects** -- AEGIS only validates; it never performs actions
- **No state** -- Every validation is independent
- **No bypass** -- There is no "admin mode" or override
- **Defense in depth** -- Multiple layers protect against different attack vectors

## The Seven Invariants

AEGIS enforces seven fundamental security rules (v7.0.0):

### Invariant 1: Workspace Confinement

**All file operations must stay within the workspace directory.**
```
/home/user/project/src/main.py     (inside workspace -- PASS)
/home/user/project/../.ssh/id_rsa  (escapes workspace -- FAIL)
/etc/passwd                         (absolute path outside -- FAIL)
```

AEGIS uses a 6-layer defense against path traversal:

| Layer | Attack | Defense |
|-------|--------|---------|
| 1 | Case mismatch (Windows) | `os.path.normcase()` |
| 2 | Prefix collision | `Path.relative_to()` structural check |
| 3 | Null byte injection | Explicit `\x00` rejection |
| 4 | Reserved devices (CON, NUL) | Frozen set validation |
| 5 | NTFS Alternate Data Streams | Colon rejection in paths |
| 6 | Symlink traversal | `Path.resolve()` before check |

### Invariant 2: Mode Enforcement

**Actions must be permitted by the current governance mode.**

| Mode | Read Files | Write Files | Execute Commands |
|------|------------|-------------|------------------|
| `safe` | Yes | No | No |
| `pro` | Yes | Yes (approval required) | No |
| `project` | Yes | Yes | Yes (allowlisted) |

### Invariant 3: Action Scope

**Only approved operation types are allowed.**

Valid operations:
- `read` -- Read file contents
- `create` -- Create new file
- `modify` -- Modify existing file
- `delete` -- Delete file
- `run` -- Execute command (project mode only)

Invalid operations are rejected immediately.

### Invariant 4: Risk Validation

**High-risk operations require human confirmation.**

Risk levels:
- **Low** -- Read operations, explanations
- **Medium** -- File modifications, new files
- **High** -- Deletions, multiple files, core config
- **Critical** -- System files, credentials, executables

Critical operations always require explicit human approval, even in `project` mode.

### Invariant 5: Command Execution Safety

**Shell commands are validated for dangerous patterns.**

Blocked operators:
```
&& || ; | > < ` $( ${
```

Blocked patterns:
```bash
rm -rf /           # Dangerous deletion
curl | bash        # Remote execution
chmod 777          # Unsafe permissions
> /dev/sda         # Device access
```

### Invariant 6: External Access Control

**Network operations follow read/write approval rules.**

| Operation Type | Auto-Approved | Requires Approval |
|----------------|---------------|-------------------|
| Read (GET) | Public APIs | Private/auth |
| Write (POST/PUT/DELETE) | Never | Always |

### Invariant 7: Network Access Control

**All network requests from governed contexts must pass through the egress proxy.** The proxy enforces:

- **Domain whitelist** (additive model) -- only explicitly allowed domains are reachable
- **Hardcoded LLM domains** -- cannot be removed (api.openai.com, api.anthropic.com, etc.)
- **Blocked Google services** -- Drive, Gmail, Calendar, YouTube, Photos, Docs, Sheets, Slides, People (default DENY, user can enable individually)
- **Content inspection** -- POST/PUT/PATCH requests to non-LLM domains are scanned for credential patterns
- **Rate limiting** -- Per-domain and global RPM limits
- **Audit logging** -- Every request logged to JSONL (host-side, unmodifiable by Orion)

This invariant ensures Orion cannot exfiltrate data, contact unauthorized services, or leak credentials -- even if compromised by prompt injection.

| Rule | Behaviour |
|------|-----------|
| Blocked Google service | **DENY** -- Drive, Gmail, Calendar, YouTube, Photos, People, Docs, Sheets, Slides |
| Allowed LLM domain | **ALLOW** -- generativelanguage.googleapis.com, api.openai.com, api.anthropic.com |
| Search API domain | **ALLOW** -- customsearch.googleapis.com, api.bing.microsoft.com, etc. |
| Research domain | **GET-only** -- user-configured, no POST/PUT/DELETE |
| Non-HTTPS protocol | **WARNING** -- logged but not blocked |
| Write method (POST/PUT/DELETE) | **WARNING** -- flagged for approval queue |
| Everything else | **BLOCKED** |

**Additive whitelist model:** The default config allows only hardcoded LLM provider domains. Users can add domains via the host-side config file, but cannot remove the hardcoded set. The container cannot modify the config.

**Seven security layers:**

| Layer | Component | Enforcement |
|-------|-----------|-------------|
| L1 | AEGIS Configuration | Host filesystem, read-only mount into container |
| L2 | Docker Network Isolation | Kernel namespaces, no direct internet |
| L3 | Egress Proxy | Domain whitelist, content inspection, rate limiting |
| L4 | Filesystem Isolation | Docker volumes, read-only config mount |
| L5 | Approval Queue | Host-side human gate for write operations |
| L6 | Credential Isolation | Access token only, no refresh token in container |
| L7 | Orion Self-Governance | Software-level AEGIS checks (least trusted layer) |

## Architectural Immutability

AEGIS configuration lives on the host filesystem at `~/.orion/egress_config.yaml`. Inside Docker, it is mounted as read-only (`:ro`). This means:

1. **Orion cannot modify its own rules** -- the config file is physically read-only
2. **Orion cannot approve its own requests** -- the approval queue runs on the host
3. **Orion cannot escalate permissions** -- the egress proxy runs on the host
4. **Prompt injection cannot change governance** -- AEGIS is outside the agent's execution context

This is not a software restriction. It is a physical boundary enforced by Linux kernel namespaces (Docker).

```
Host Machine (trusted)                    Docker Sandbox (untrusted)
┌─────────────────────────────┐          ┌──────────────────────────┐
│ AEGIS Config (~/.orion/)    │──:ro──>  │ Orion Agent              │
│ Egress Proxy (port 8888)    │<─HTTP──  │  ├── Builder Agent       │
│ DNS Filter (port 5353)      │<─UDP───  │  ├── Reviewer Agent      │
│ Approval Queue              │<─API───  │  └── Governor Agent      │
│ Sandbox Orchestrator        │──ctrl──> │                          │
│ Ollama / Cloud LLM          │<─proxy─  │ Workspace (/workspace)   │
└─────────────────────────────┘          └──────────────────────────┘
```

## How AEGIS Works

### Validation Flow
```
┌─────────────┐
│   Request   │
└──────┬──────┘
       │
       ▼
┌─────────────────────────────────────┐
│        AEGIS Validation             │
│                                     │
│  1. Check workspace exists          │
│  2. Validate mode permissions       │
│  3. Check operation type            │
│  4. Validate all paths confined     │
│  5. Check for dangerous patterns    │
│  6. Assess risk level               │
│  7. Check external access rules     │
│  8. Check network access control    │
│                                     │
│  Any failure -> REJECT              │
│  All pass -> APPROVE (or ASK)       │
└──────┬──────────────────────────────┘
       │
       ▼
┌─────────────┐
│   Result    │
│   PASS      │
│   FAIL      │
│   ASK       │
└──────────────┘
```

### Integration with Agents

AEGIS sits between the agent system and the execution layer:
```
Builder/Reviewer/Governor
           │
           ▼ (proposed actions)
       ┌───────┐
       │ AEGIS │ -- Pure function, no bypass
       └───┬───┘
           │
    ┌──────┴──────┐
    ▼             ▼
  PASS          FAIL
    │             │
    ▼             ▼
 Execute      Reject
```

Agents cannot:
- Disable AEGIS
- Modify AEGIS rules
- Bypass AEGIS checks
- Access AEGIS internals

## Configuration

AEGIS has minimal configuration -- by design. Most settings are hardcoded for safety.

### Mode Selection
```bash
/mode safe      # Read-only, maximum safety
/mode pro       # Read + write with approval
/mode project   # Full access with allowlisted commands
```

### Approval Timeout

When AEGIS requires human approval, it waits for a response. The timeout is configurable:
```python
# Default: 120 seconds
AEGIS_APPROVAL_TIMEOUT = 120
```

If timeout expires, the action is **denied** (secure default).

## Audit Logging

AEGIS logs all validation decisions:
```
2025-02-10 14:23:45 | AEGIS | PASS | read | src/main.py | mode=pro
2025-02-10 14:23:52 | AEGIS | PASS | modify | src/main.py | mode=pro | approved=user
2025-02-10 14:24:01 | AEGIS | FAIL | modify | /etc/passwd | reason=path_escape
2025-02-10 14:24:15 | AEGIS | FAIL | run | rm -rf / | reason=dangerous_pattern
```

Logs are stored in `~/.orion/logs/aegis.log`.

## Security Testing

AEGIS is tested against known attack vectors:

| Attack | Test | Status |
|--------|------|--------|
| Path traversal (`../`) | 21 regression tests | Protected |
| Case manipulation (Windows) | Normalization test | Protected |
| Null byte injection | Explicit check | Protected |
| Symlink escape | Resolution test | Protected |
| Shell injection | Pattern matching | Protected |
| Reserved devices | Frozen set check | Protected |
| NTFS ADS | Colon rejection | Protected |

## Limitations

AEGIS is not a complete security solution on its own:

- **Not antivirus** -- Doesn't detect malware in code
- **Not encryption** -- Doesn't protect data at rest
- **Not a replacement for OS permissions** -- Doesn't manage user accounts

AEGIS is one layer in a defense-in-depth strategy. Phase 2 adds Docker-based network isolation as a complementary layer.

## FAQ

### Can I disable AEGIS?

No. AEGIS cannot be disabled, bypassed, or reconfigured at runtime. This is intentional.

### Why is my operation being blocked?

Check the AEGIS log (`~/.orion/logs/aegis.log`) for the specific reason. Common causes:

- Path escapes workspace
- Mode doesn't permit operation
- Dangerous shell pattern detected

### Can I add exceptions?

No. AEGIS has no exception mechanism. If you need to perform a blocked operation, do it manually outside of Orion.

### Is AEGIS enough for production?

AEGIS provides strong governance but should be combined with:

- Proper file permissions
- Network segmentation
- Regular security audits
- Monitoring and alerting

## Technical Reference

### Source Files

- `src/orion/core/governance/aegis.py` -- Main AEGIS implementation (v7.0.0)
- `src/orion/security/egress/` -- Phase 2 network security modules
- `tests/unit/test_governance.py` -- AEGIS core test suite (46 tests)
- `tests/test_aegis_network_access.py` -- Invariant 7 tests (30 tests)
- `tests/test_phase2_e2e.py` -- Cross-component E2E tests (36 tests)

### Key Functions
```python
def validate_action_bundle(
    actions: List[Dict],
    workspace: str,
    mode: str
) -> AegisResult:
    """
    Validate a bundle of proposed actions.

    Returns:
        AegisResult with passed=True/False and reason
    """
```

### AegisResult
```python
@dataclass
class AegisResult:
    passed: bool
    reason: str
    risk_level: str  # low, medium, high, critical
    requires_approval: bool
```

---

*AEGIS: Because AI should be powerful, not dangerous.*

**Next:** [Security](SECURITY.md) | [Architecture](ARCHITECTURE.md)
