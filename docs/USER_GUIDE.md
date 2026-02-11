# Orion Agent User Guide

Complete guide to using Orion Agent for day-to-day development.

## Overview

Orion is an interactive AI coding assistant. You communicate with it through natural language, and it performs code analysis, generation, editing, and explanation tasks on your behalf -- governed by AEGIS to ensure safety.

## Starting Orion

### CLI Mode
```bash
orion
```

### API Server Mode
```bash
uvicorn orion.api.server:app --port 8001
```

### Web UI
```bash
cd orion-web
npm run dev
```

## Core Concepts

### Workspaces

A workspace is the project directory Orion operates within. AEGIS enforces that all file operations stay inside this boundary.

```
> /workspace /home/user/my-project
Workspace set: /home/user/my-project
```

**Rules:**
- Orion cannot read or modify files outside the workspace
- You can change workspaces at any time
- Project memory is tied to the workspace

### Modes

Modes control what Orion is allowed to do. They are enforced by AEGIS and cannot be bypassed.

| Mode | Description | Best For |
|------|-------------|----------|
| **safe** | Read-only. Orion can analyze and explain code but cannot modify anything. | Code review, learning, exploration |
| **pro** | Read + write with approval. Orion proposes changes and you approve each one. | Active development (recommended) |
| **project** | Full access including command execution. Orion can run allowlisted commands. | Automation, CI/CD integration |

```
> /mode safe       # Maximum safety
> /mode pro        # Balanced (recommended)
> /mode project    # Maximum autonomy
```

### The Table of Three

For complex tasks, Orion uses three agents working together:

1. **Builder** -- Generates the solution using your configured LLM
2. **Reviewer** -- Analyzes the Builder's output for correctness, quality, and edge cases
3. **Governor** -- Makes the final decision using memory, quality gates, and governance rules

Simple tasks (explanations, small edits) use FastPath -- a direct route that skips the full council for speed.

## Common Workflows

### Code Explanation
```
> Explain what the AuthMiddleware class does

Orion analyzes src/middleware/auth.py and provides:
- What the class does
- How it integrates with the request pipeline
- Key methods and their purposes
```

### Code Generation
```
> Create a REST API endpoint for user registration

Orion will:
1. Analyze existing code patterns
2. Generate the endpoint code
3. Show you the proposed changes
4. Wait for approval (in pro mode)
```

### Bug Fixing
```
> The login endpoint returns 500 when email is missing

Orion will:
1. Read the relevant code
2. Identify the root cause
3. Propose a fix with proper error handling
4. Show the diff for approval
```

### Code Review
```
> Review the changes in src/api/payments.py for security issues

Orion will:
1. Read the file
2. Analyze for common security issues
3. Report findings with severity levels
4. Suggest improvements
```

### Refactoring
```
> Refactor the database module to use async/await

Orion will:
1. Analyze current synchronous code
2. Plan the refactoring steps
3. Apply changes file by file
4. Each change requires your approval
```

## Approval Flow

In `pro` mode, Orion shows you proposed changes before applying them:

```
Proposed changes to src/auth/login.py:

--- src/auth/login.py (original)
+++ src/auth/login.py (modified)
@@ -15,6 +15,10 @@
 def login(email, password):
+    if not email:
+        raise ValueError("Email is required")
+    if not password:
+        raise ValueError("Password is required")
     user = db.find_user(email)

Apply these changes? [y/n/e(dit)]:
```

Options:
- **y** -- Apply the changes
- **n** -- Reject and start over
- **e** -- Open in your editor for manual adjustment

## Memory and Learning

### How Orion Learns

After completing a task, Orion may ask for feedback:
```
Rate this response (1-5, or skip): 4
```

Ratings drive learning:
- **4-5** -- Success pattern stored (what worked)
- **1-2** -- Anti-pattern stored (what to avoid)
- **3** -- Neutral, no pattern stored
- **skip** -- No feedback recorded

### Viewing Memory
```
> /memory

Memory Status:
  Session (Tier 1): 15 items
  Project (Tier 2): 89 patterns
  Institutional (Tier 3): 234 patterns
```

### Memory Benefits

Over time, Orion:
- Remembers your coding style preferences
- Avoids mistakes it made before
- Understands your project's patterns
- Provides increasingly relevant suggestions

See [Memory System](MEMORY_SYSTEM.md) for details.

## Settings Management

### View Current Settings
```
> /settings
```

### Configure API Keys
```
> /settings key openai sk-your-key-here
> /settings key anthropic sk-ant-your-key-here
```

### Change LLM Provider
```
> /settings provider openai
> /settings model gpt-4o
```

### Other Settings
```
> /settings temperature 0.3
> /settings max_tokens 4096
```

## Diagnostics

### Doctor
```
> /doctor

Running 15 diagnostic checks...
  [PASS] Python version: 3.11.5
  [PASS] Git available: 2.42.0
  [PASS] Workspace valid: /home/user/project
  [PASS] LLM provider: openai (gpt-4o)
  [PASS] API key configured
  [WARN] Ollama not installed (optional)
  [PASS] Memory engine: healthy
  ...
```

### Health Check
```
> /health

Integration Health:
  OpenAI:     HEALTHY (latency: 230ms)
  Anthropic:  HEALTHY (latency: 180ms)
  Ollama:     NOT CONFIGURED
  ElevenLabs: API KEY MISSING
  ...
```

## Repository Navigation

### Map
```
> /map

Repository Structure:
src/
├── auth/
│   ├── login.py (45 lines)
│   ├── register.py (62 lines)
│   └── middleware.py (38 lines)
├── api/
│   ├── routes.py (120 lines)
│   └── models.py (85 lines)
└── db/
    ├── connection.py (30 lines)
    └── queries.py (95 lines)
```

### Undo
```
> /undo

Reverted last change:
  File: src/auth/login.py
  Restored from git savepoint
```

## Web UI

The Web UI provides the same functionality as the CLI in a browser-based interface.

### Starting the Web UI

1. Start the API server:
```bash
uvicorn orion.api.server:app --port 8001
```

2. Start the web frontend:
```bash
cd orion-web
npm run dev
```

3. Open `http://localhost:3001` in your browser

### Web UI Features

- Chat-based interface
- Real-time streaming responses
- Settings panel
- Mode switching
- Workspace selection

## Tips and Best Practices

### Start with Safe Mode

Use `safe` mode to explore a new codebase without risk:
```
> /mode safe
> Explain the architecture of this project
```

### Be Specific

More context leads to better results:
```
# Less effective
> Fix the bug

# More effective
> Fix the TypeError in src/api/users.py line 45 where user.email is None
```

### Use Pro Mode for Development

`pro` mode gives you the best balance of productivity and safety:
- Orion can read and analyze freely
- All file changes require your approval
- You maintain full control

### Rate Responses

Regular feedback improves Orion over time. Even a quick 1-5 rating helps the learning system identify what works for you.

### Check Doctor Regularly

Run `/doctor` after configuration changes to verify everything is working:
```
> /doctor
```

---

**Next:** [CLI Reference](CLI_REFERENCE.md) | [Configuration](CONFIGURATION.md)
