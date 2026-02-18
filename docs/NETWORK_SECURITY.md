# Network Security Architecture

## Overview

Orion's network security is built on a zero-trust, additive whitelist model. By default, the sandbox container has NO internet access. Every domain must be explicitly whitelisted.

This document covers the network security components introduced in Phase 2 (Digital Agent Architecture) and Phase 3 (Graduated Services).

## The Narrow Door (Egress Proxy)

All HTTP/HTTPS traffic from the sandbox routes through the egress proxy -- a host-side process that Orion cannot modify or bypass.

**Source:** `src/orion/security/egress/proxy.py`

### 6-Stage Security Pipeline

Every request passes through these stages in order:

1. **Domain Check** -- Is the target domain on the whitelist?
2. **Protocol Check** -- Is the protocol allowed for this domain?
3. **Rate Limit** -- Has the per-domain or global RPM limit been exceeded?
4. **Method Check** -- Is this a write method (POST/PUT/PATCH/DELETE) to a non-LLM domain?
5. **Content Inspection** -- Does the request body contain credential patterns?
6. **Forward** -- Proxy the request to the upstream server

If any stage fails, the request is blocked and logged.

### Domain Categories

| Category | Examples | Policy |
|----------|----------|--------|
| Hardcoded LLM | api.openai.com, api.anthropic.com, generativelanguage.googleapis.com | Always allowed, cannot be removed |
| Search APIs | customsearch.googleapis.com, api.bing.microsoft.com, serpapi.com | Always allowed for LLM web search |
| User Whitelist | github.com, pypi.org | User adds via UI/API, full access |
| Research Domains | wikipedia.org, stackoverflow.com | User adds, GET-only (no POST/PUT/DELETE) |
| Google Services | drive.googleapis.com, mail.google.com | Default DENY, user enables individually |
| Everything Else | * | BLOCKED |

### Content Inspection

Non-GET requests to non-LLM domains are inspected for credential patterns:

| Pattern | Example |
|---------|---------|
| AWS Access Key | `AKIAIOSFODNN7EXAMPLE` |
| AWS Secret Key | `wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY` |
| GitHub PAT | `ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx` |
| OpenAI API Key | `sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx` |
| Anthropic API Key | `sk-ant-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx` |
| Google API Key | `AIzaSyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx` |
| Slack Token | `xoxb-xxxxxxxxxxxx-xxxxxxxxxxxx-xxxxxxxx` |
| Private SSH Key | `-----BEGIN RSA PRIVATE KEY-----` |

12 patterns total. See `src/orion/security/egress/inspector.py` for the full list.

**Source:** `src/orion/security/egress/inspector.py`

### Rate Limiting

- **Per-domain:** Configurable RPM per whitelisted domain (default: 60)
- **Global:** Configurable total RPM across all domains
- **Algorithm:** Sliding window with automatic cleanup

**Source:** `src/orion/security/egress/rate_limiter.py`

### Audit Logging

Every request is logged to a JSONL file on the host filesystem. Orion cannot modify these logs.

Each entry includes:
- `timestamp` -- Unix epoch
- `event_type` -- `request`, `blocked`, `rate_limited`, `credential_leak`, `error`
- `method` -- HTTP method (GET, POST, CONNECT, etc.)
- `hostname` -- Target domain
- `status_code` -- Response status (0 if blocked before sending)
- `duration_ms` -- Request round-trip time
- `request_size` / `response_size` -- Payload sizes in bytes
- `blocked_reason` -- Why the request was blocked (if applicable)
- `credential_patterns` -- Patterns detected (if any)

**Source:** `src/orion/security/egress/audit.py`

## DNS Filter

Container DNS queries are intercepted by the DNS filter (host-side). Non-whitelisted domains receive NXDOMAIN. This is defense-in-depth -- even if the egress proxy were bypassed, DNS would not resolve.

- **Protocol:** UDP on port 5353
- **Whitelisted domains:** Same list as egress proxy
- **Non-whitelisted:** Returns NXDOMAIN immediately
- **Whitelisted:** Forwards to upstream DNS and returns response

**Source:** `src/orion/security/egress/dns_filter.py`

## Approval Queue

Write operations (POST/PUT/PATCH/DELETE) to non-LLM domains require human approval via the approval queue. The queue runs on the host -- Orion cannot bypass or auto-approve.

- **Persistence:** JSON file on host filesystem
- **Timeout:** Configurable (default: 120s). Expired requests are automatically denied.
- **API:** Submit, approve, reject, list pending

**Source:** `src/orion/security/egress/approval_queue.py`

## Docker Network Isolation

The Docker Compose configuration creates two networks:

- **`orion-internal`** (`internal: true`) -- The container lives here. NO internet access.
- **`orion-egress`** -- Only the egress proxy and DNS filter have access to both networks.

The container can only reach the internet through the proxy. There is no other path.

```yaml
networks:
  orion-internal:
    internal: true    # No internet access
  orion-egress:
    driver: bridge    # Internet access for proxy only
```

**Source:** `docker/docker-compose.yml`

## Google Services (Graduated Access)

Phase 3 introduces per-service Google access control. Nine Google services are defined, each default DENY:

| Service | Domain | Risk Level |
|---------|--------|------------|
| Drive | drive.googleapis.com | High |
| Gmail | mail.google.com, gmail.googleapis.com | High |
| Calendar | calendar.googleapis.com | Medium |
| YouTube | youtube.googleapis.com | Medium |
| Photos | photoslibrary.googleapis.com | Medium |
| Docs | docs.googleapis.com | Medium |
| Sheets | sheets.googleapis.com | Medium |
| Slides | slides.googleapis.com | Medium |
| People | people.googleapis.com | Low |

Users can enable individual services via the Web UI or API. Enabling a service:
1. Updates the AEGIS whitelist config
2. Triggers orchestrator hot reload
3. Proxy and DNS filter pick up the new domain
4. Container can now reach that service

**Source:** `src/orion/security/orchestrator.py`

## LLM Web Search Routing

To support LLM web search capabilities, certain domains are auto-allowed:

### Search API Domains (always allowed)
- `customsearch.googleapis.com`
- `api.bing.microsoft.com`
- `serpapi.com`
- `api.tavily.com`
- `api.brave.com`

### Research Domains (user-configured, GET-only)
Users can add research domains (e.g., `wikipedia.org`, `stackoverflow.com`) that are allowed for GET requests only. POST/PUT/DELETE to research domains is blocked.

## Configuration

The egress config lives at `~/.orion/egress_config.yaml` (host-side). Default config is at `data/egress_config_default.yaml`.

Key fields:
- `proxy_port` -- Egress proxy listen port (default: 8888)
- `enforce` -- Whether to enforce blocking (true) or audit-only (false)
- `whitelist` -- List of allowed domains with per-domain settings
- `audit_log_path` -- Path to JSONL audit log
- `rate_limit_global_rpm` -- Global rate limit

## Automatic Sandbox Lifecycle

The sandbox boots automatically when Orion starts (CLI, Web UI, or API mode). No manual commands needed.

**Startup flow:**
1. Orion starts and shows the banner
2. `SandboxLifecycle` checks for Docker availability in the background
3. If Docker is available, the 6-step boot runs in a background thread
4. The REPL / API server is available immediately (no blocking)
5. When boot completes, a status message is printed

**Graceful degradation:** If Docker is not installed or not running, Orion continues in BYOK-only mode with a one-time warning. No crash, no blocking.

**Shutdown:** On `/quit`, SIGINT, or process exit, the lifecycle manager calls `orchestrator.stop()` for clean teardown. Signal handlers and `atexit` are registered to handle unexpected exits.

**Manual override:** `/sandbox stop` sets a manual-stop flag that prevents auto-restart. `/sandbox start` clears the flag and reboots.

**Source:** `src/orion/security/sandbox_lifecycle.py`

## Source Files

| File | Purpose |
|------|---------|
| `src/orion/security/sandbox_lifecycle.py` | Lifecycle manager (auto-boot, shutdown, signal handlers) |
| `src/orion/security/egress/proxy.py` | HTTP forward proxy with CONNECT tunneling |
| `src/orion/security/egress/config.py` | EgressConfig and DomainRule dataclasses |
| `src/orion/security/egress/inspector.py` | Content inspection (12 credential patterns) |
| `src/orion/security/egress/rate_limiter.py` | Sliding window rate limiter |
| `src/orion/security/egress/audit.py` | JSONL audit logging |
| `src/orion/security/egress/dns_filter.py` | UDP DNS filter |
| `src/orion/security/egress/approval_queue.py` | Human approval queue |
| `src/orion/security/egress/google_credentials.py` | Google OAuth credential management |
| `src/orion/security/egress/antigravity.py` | Antigravity headless browser integration |
| `src/orion/security/orchestrator.py` | SandboxOrchestrator (6-step boot) |
| `src/orion/core/governance/aegis.py` | AEGIS Invariant 7 (check_network_access) |
| `docker/docker-compose.yml` | Dual-network Docker topology |
| `data/egress_config_default.yaml` | Default egress configuration |

---

**Next:** [AEGIS](AEGIS.md) | [Architecture](ARCHITECTURE.md) | [Security](SECURITY.md)
