# CLI Reference

Complete reference for all Orion Agent CLI commands and options.

## Starting Orion

```bash
# Start interactive REPL
orion

# Start with specific workspace
orion --workspace /path/to/project

# Start in specific mode
orion --mode pro

# Show version
orion --version

# Show help
orion --help
```

## Slash Commands

All commands start with `/` and are processed by Orion's command system.

### Workspace Management

#### `/workspace <path>`

Set the active workspace directory. AEGIS enforces all file operations stay within this boundary.

```
> /workspace /home/user/my-project
Workspace set: /home/user/my-project
```

**Arguments:**
- `<path>` -- Absolute or relative path to a directory

**Notes:**
- Path must exist and be a directory
- Changing workspace clears session memory
- Project memory is tied to the workspace

#### `/map`

Display the repository structure as a tree.

```
> /map

src/
├── auth/
│   ├── login.py (45 lines)
│   └── register.py (62 lines)
├── api/
│   └── routes.py (120 lines)
└── tests/
    └── test_auth.py (85 lines)
```

### Governance

#### `/mode <mode>`

Set the governance mode. Controls what operations Orion is allowed to perform.

```
> /mode safe
> /mode pro
> /mode project
```

**Modes:**

| Mode | Read | Write | Execute | Description |
|------|------|-------|---------|-------------|
| `safe` | Yes | No | No | Read-only analysis |
| `pro` | Yes | Yes (approval) | No | Development with approval gates |
| `project` | Yes | Yes | Yes (allowlist) | Full automation |

### Configuration

#### `/settings`

Display current configuration.

```
> /settings

Current Settings:
  Provider: openai
  Model: gpt-4o
  Mode: pro
  Workspace: /home/user/project
  Table of Three: enabled
  Memory: 89 project patterns, 234 institutional
```

#### `/settings key <provider> <key>`

Set an API key for a provider. Keys are stored encrypted.

```
> /settings key openai sk-your-key-here
> /settings key anthropic sk-ant-your-key-here
```

**Supported providers:** openai, anthropic, google, groq, mistral, cohere, together, perplexity, fireworks, deepseek, elevenlabs

#### `/settings provider <name>`

Set the active LLM provider.

```
> /settings provider openai
> /settings provider ollama
```

#### `/settings model <name>`

Set the active model.

```
> /settings model gpt-4o
> /settings model claude-3-5-sonnet-20241022
> /settings model llama3
```

#### `/settings temperature <value>`

Set the LLM temperature (0.0 to 2.0).

```
> /settings temperature 0.3
```

### Diagnostics

#### `/doctor`

Run system diagnostic checks.

```
> /doctor

Running 15 diagnostic checks...
  [PASS] Python version: 3.11.5
  [PASS] Git available: 2.42.0
  [PASS] Workspace valid
  [PASS] LLM provider configured
  [PASS] API key valid
  [PASS] Memory engine healthy
  [WARN] Docker not available (sandbox limited to local mode)
  ...

14 passed, 1 warning, 0 failed
```

#### `/health`

Check the health of all configured integrations.

```
> /health

Integration Health:
  OpenAI:     HEALTHY (230ms)
  Anthropic:  HEALTHY (180ms)
  Ollama:     NOT RUNNING
  ElevenLabs: API KEY MISSING
```

### Memory

#### `/memory`

Display memory status across all tiers.

```
> /memory

Memory Status:
  Session (Tier 1): 23 items
  Project (Tier 2): 147 patterns
  Institutional (Tier 3): 892 patterns
```

#### `/memory search <query>`

Search memory for relevant patterns.

```
> /memory search error handling

Found 12 patterns:
  [T3] Always wrap async calls in try/catch (conf: 0.95)
  [T2] This project uses AuthError exceptions (conf: 0.85)
```

#### `/memory clear <tier>`

Clear memory for a specific tier.

```
> /memory clear session
Session memory cleared.
```

### Version Control

#### `/undo`

Revert the last file change using git savepoints.

```
> /undo

Reverted last change:
  File: src/auth/login.py
  Restored from savepoint sp-20250210-142352
```

#### `/diff`

Show the current diff of uncommitted changes.

```
> /diff
```

### Connection (Web UI)

#### `/connect`

Connect to the API server from the CLI.

```
> /connect
Connected to Orion API at http://localhost:8001
```

#### `/disconnect`

Disconnect from the API server.

```
> /disconnect
Disconnected from API server.
```

### Messaging Bridges

#### `/bridge enable <platform> <token>`

Enable a messaging bridge (Telegram, Slack, Discord).

```
> /bridge enable telegram <bot-token>
Bridge enabled. Passphrase: <generated>
```

#### `/bridge disable <platform>`

Disable a messaging bridge.

```
> /bridge disable telegram
```

#### `/bridge status`

Show status of all bridges.

```
> /bridge status

Bridges:
  Telegram: ACTIVE (1 user)
  Slack:    DISABLED
  Discord:  DISABLED
```

#### `/bridge revoke <platform> <user_id>`

Revoke access for a specific user.

```
> /bridge revoke telegram 123456789
```

### General

#### `/help`

Display available commands.

```
> /help
```

#### `/quit` or `/exit`

Exit Orion.

```
> /quit
Goodbye.
```

## Natural Language Input

Any input that doesn't start with `/` is treated as a natural language request:

```
> Explain the authentication flow
> Fix the bug in the payment module
> Add unit tests for the User model
> Refactor database.py to use connection pooling
```

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `OPENAI_API_KEY` | OpenAI API key | None |
| `ANTHROPIC_API_KEY` | Anthropic API key | None |
| `GOOGLE_API_KEY` | Google AI API key | None |
| `GROQ_API_KEY` | Groq API key | None |
| `OLLAMA_HOST` | Ollama server URL | `http://localhost:11434` |
| `ORION_HOME` | Orion config directory | `~/.orion` |
| `ORION_LOG_LEVEL` | Logging level | `INFO` |
| `ORION_MODE` | Default governance mode | `safe` |

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Normal exit |
| 1 | General error |
| 2 | Configuration error |
| 3 | Missing dependency |

---

**Next:** [API Reference](API_REFERENCE.md) | [User Guide](USER_GUIDE.md)
