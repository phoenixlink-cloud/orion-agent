# API Reference

Complete reference for Orion Agent's REST and WebSocket API.

## Base URL

```
http://localhost:8001
```

## Authentication

Authentication is optional and configured via the `ORION_AUTH_TOKEN` environment variable. When enabled, include the token in requests:

```
Authorization: Bearer <token>
```

## Health Endpoints

### GET /health

Basic health check.

**Response:**
```json
{
  "status": "healthy",
  "version": "7.1.0"
}
```

### GET /ready

Kubernetes readiness probe.

**Response:**
```json
{
  "ready": true
}
```

### GET /live

Kubernetes liveness probe.

**Response:**
```json
{
  "alive": true
}
```

## Chat

### WebSocket /ws/chat

Real-time chat interface via WebSocket.

**Connection:**
```javascript
const ws = new WebSocket('ws://localhost:8001/ws/chat')
```

**Send message:**
```json
{
  "type": "message",
  "content": "Explain the main function",
  "workspace": "/path/to/project",
  "mode": "pro"
}
```

**Receive events:**

| Event Type | Description |
|-----------|-------------|
| `routing` | Scout routing decision |
| `streaming` | Streaming LLM response chunk |
| `complete` | Final complete response |
| `error` | Error occurred |
| `status` | Status update (e.g., "analyzing code...") |
| `council` | Table of Three deliberation update |
| `escalation` | Human approval required |

**Streaming response example:**
```json
{"type": "streaming", "content": "The main function ", "meta": {}}
{"type": "streaming", "content": "initializes the ", "meta": {}}
{"type": "streaming", "content": "application...", "meta": {}}
{"type": "complete", "content": "The main function initializes the application...", "meta": {"tokens": 150, "model": "gpt-4o"}}
```

## Settings

### GET /settings

Get current settings.

**Response:**
```json
{
  "provider": "openai",
  "model": "gpt-4o",
  "mode": "pro",
  "temperature": 0.3,
  "max_tokens": 4096,
  "enable_table_of_three": true,
  "workspace": "/path/to/project"
}
```

### PUT /settings

Update settings.

**Request:**
```json
{
  "provider": "anthropic",
  "model": "claude-3-5-sonnet-20241022"
}
```

**Response:**
```json
{
  "status": "updated",
  "settings": { ... }
}
```

### GET /settings/keys

Get API key configuration status (does not return actual keys).

**Response:**
```json
{
  "keys": [
    {"provider": "openai", "configured": true, "description": "OpenAI API"},
    {"provider": "anthropic", "configured": false, "description": "Anthropic API"},
    {"provider": "ollama", "configured": true, "description": "Ollama (local)"}
  ]
}
```

### POST /settings/keys

Set an API key.

**Request:**
```json
{
  "provider": "openai",
  "key": "sk-your-key-here"
}
```

## Mode

### GET /mode

Get current governance mode.

**Response:**
```json
{
  "mode": "pro",
  "permissions": {
    "read": true,
    "write": true,
    "execute": false,
    "approval_required": true
  }
}
```

### PUT /mode

Set governance mode.

**Request:**
```json
{
  "mode": "project"
}
```

## Doctor

### GET /doctor

Run diagnostic checks.

**Response:**
```json
{
  "checks": [
    {"name": "python_version", "status": "pass", "detail": "3.11.5"},
    {"name": "git_available", "status": "pass", "detail": "2.42.0"},
    {"name": "workspace_valid", "status": "pass", "detail": "/path/to/project"},
    {"name": "llm_provider", "status": "pass", "detail": "openai (gpt-4o)"},
    {"name": "docker_available", "status": "warn", "detail": "Not installed"}
  ],
  "summary": {
    "passed": 14,
    "warnings": 1,
    "failed": 0
  }
}
```

## Git

### GET /git/status

Get git status for the workspace.

**Response:**
```json
{
  "branch": "main",
  "clean": false,
  "modified": ["src/main.py"],
  "untracked": ["new_file.py"],
  "ahead": 2,
  "behind": 0
}
```

### GET /git/diff

Get current diff.

**Response:**
```json
{
  "diff": "--- a/src/main.py\n+++ b/src/main.py\n@@ -1,3 +1,4 @@..."
}
```

## Memory

### GET /memory/stats

Get memory statistics.

**Response:**
```json
{
  "session": {"count": 23},
  "project": {"count": 147, "workspace": "/path/to/project"},
  "institutional": {"count": 892}
}
```

## Evolution

### GET /evolution

Get evolution metrics.

**Response:**
```json
{
  "total_tasks": 847,
  "approval_rate": 0.823,
  "quality_trend": "improving",
  "strengths": [
    {"task_type": "bug_fix", "approval_rate": 0.89}
  ],
  "weaknesses": [
    {"task_type": "test_gen", "approval_rate": 0.68}
  ]
}
```

## Context

### GET /context/files

Get workspace file listing.

**Response:**
```json
{
  "files": [
    {"path": "src/main.py", "lines": 120, "language": "python"},
    {"path": "src/utils.py", "lines": 85, "language": "python"}
  ],
  "total_files": 47,
  "total_lines": 3420
}
```

## Error Responses

All error responses follow this format:

```json
{
  "detail": "Error description",
  "status_code": 400
}
```

| Status Code | Meaning |
|-------------|---------|
| 400 | Bad request (invalid parameters) |
| 401 | Unauthorized (missing/invalid auth token) |
| 404 | Not found |
| 422 | Validation error |
| 429 | Rate limited |
| 500 | Internal server error |

## ARA Skills Endpoints

### GET /api/ara/skills

List all available skills with metadata.

**Response:**
```json
{
  "success": true,
  "data": {
    "skills": [
      {
        "name": "code-review",
        "description": "Review code for quality...",
        "version": "1.0.0",
        "source": "bundled",
        "trust_level": "verified",
        "aegis_approved": true,
        "tags": ["quality", "review"]
      }
    ]
  }
}
```

### GET /api/ara/skills/{skill_name}

Get full skill detail including SKILL.md instructions.

**Response:**
```json
{
  "success": true,
  "data": {
    "name": "code-review",
    "description": "Review code for quality...",
    "version": "1.0.0",
    "source": "bundled",
    "trust_level": "verified",
    "aegis_approved": true,
    "tags": ["quality", "review"],
    "instructions": "## Code Review Procedure\n\n1. Read the diff..."
  }
}
```

### PUT /api/ara/skills/{skill_name}

Update a skill's description, instructions, or tags. Bundled seed skills cannot be edited.

**Request body:**
```json
{
  "description": "Updated description",
  "instructions": "## Updated Instructions\n\nNew content...",
  "tags": ["quality", "review", "new-tag"]
}
```

All fields are optional. Only provided fields are updated.

**Response (success):**
```json
{
  "success": true,
  "message": "Skill 'code-review' updated (changed: description, instructions)"
}
```

**Response (bundled skill):**
```json
{
  "success": false,
  "message": "Skill 'code-review' is a bundled seed skill and cannot be edited."
}
```

---

## Rate Limiting

Default: 60 requests per minute per IP.

Rate limit headers:
```
X-RateLimit-Limit: 60
X-RateLimit-Remaining: 58
X-RateLimit-Reset: 1707580800
```

## CORS

CORS is configured to allow requests from:
- `http://localhost:3000`
- `http://localhost:3001`

Additional origins can be configured via `ORION_CORS_ORIGINS`.

---

**Next:** [CLI Reference](CLI_REFERENCE.md) | [Architecture](ARCHITECTURE.md)
