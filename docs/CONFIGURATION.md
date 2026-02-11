# Configuration Reference

Complete reference for all Orion Agent configuration options.

## Configuration Methods

Orion can be configured through:

1. **Environment variables** -- Best for API keys and CI/CD
2. **CLI commands** -- Interactive configuration via `/settings`
3. **Config file** -- `~/.orion/config.yaml` for persistent settings
4. **`.env` file** -- Project-level environment overrides

## API Keys

### Setting API Keys

**Via environment variables (recommended):**
```bash
export OPENAI_API_KEY="sk-..."
export ANTHROPIC_API_KEY="sk-ant-..."
export GOOGLE_API_KEY="..."
export GROQ_API_KEY="gsk_..."
export MISTRAL_API_KEY="..."
export COHERE_API_KEY="..."
export ELEVENLABS_API_KEY="..."
```

**Via CLI:**
```
> /settings key openai sk-your-key-here
> /settings key anthropic sk-ant-your-key-here
```

**Via config file (`~/.orion/config.yaml`):**
```yaml
api_keys:
  openai: sk-...
  anthropic: sk-ant-...
```

> **Security note:** Keys configured via `/settings` are stored encrypted using Orion's SecureStore. Environment variables are not encrypted but are never written to disk by Orion.

## LLM Providers

### Supported Providers

| Provider | Models | API Key Required | Local |
|----------|--------|-----------------|-------|
| **OpenAI** | GPT-4o, GPT-4-turbo, GPT-3.5-turbo | Yes | No |
| **Anthropic** | Claude 3.5 Sonnet, Claude 3 Opus/Haiku | Yes | No |
| **Google** | Gemini Pro, Gemini Ultra | Yes | No |
| **Ollama** | Llama 3, Mistral, CodeLlama, Phi-3 | No | Yes |
| **Groq** | Llama 3 70B, Mixtral 8x7B | Yes | No |
| **Mistral** | Mistral Large, Medium, Small | Yes | No |
| **Cohere** | Command R+, Command R | Yes | No |
| **Together** | Various open models | Yes | No |
| **Perplexity** | pplx-7b, pplx-70b | Yes | No |
| **Fireworks** | Various open models | Yes | No |
| **DeepSeek** | DeepSeek Coder, Chat | Yes | No |

### Selecting a Provider and Model

```
> /settings provider openai
> /settings model gpt-4o
```

Or in config:
```yaml
llm:
  provider: openai
  model: gpt-4o
  temperature: 0.3
  max_tokens: 4096
```

### Ollama (Local/Free)

```bash
# Install Ollama
curl -fsSL https://ollama.ai/install.sh | sh

# Pull a model
ollama pull llama3
ollama pull codellama

# Configure Orion
> /settings provider ollama
> /settings model llama3
```

Ollama URL defaults to `http://localhost:11434`. Override with:
```yaml
llm:
  ollama_url: http://custom-host:11434
```

## Governance Modes

### Mode Configuration

| Mode | Read | Write | Execute | Use Case |
|------|------|-------|---------|----------|
| `safe` | Yes | No | No | Code review, exploration |
| `pro` | Yes | Yes (approval) | No | Active development |
| `project` | Yes | Yes | Yes (allowlist) | Full automation |

Set mode:
```
> /mode safe
> /mode pro
> /mode project
```

### Project Mode Command Allowlist

In `project` mode, only allowlisted commands can be executed:
```yaml
governance:
  mode: project
  allowed_commands:
    - pytest
    - python
    - pip
    - git
    - npm
    - node
```

## Memory Configuration

```yaml
memory:
  # Tier 2 retention (days)
  tier2_retention_days: 30

  # Confidence threshold for Tier 2 -> Tier 3 promotion
  promotion_threshold: 0.85

  # Automatic consolidation
  auto_consolidate: true
  consolidation_interval: 24h
```

### Memory Locations

| Data | Location |
|------|----------|
| Session memory | RAM (not persisted) |
| Project memory | `.orion/memory/` in workspace |
| Institutional memory | `~/.orion/institutional.db` |

## Table of Three Configuration

```yaml
agents:
  # Enable/disable multi-agent deliberation
  enable_table_of_three: true

  # Builder configuration
  builder:
    provider: openai
    model: gpt-4o
    temperature: 0.3

  # Reviewer configuration
  reviewer:
    provider: anthropic
    model: claude-3-5-sonnet-20241022
    temperature: 0.2

  # Governor uses deterministic logic (no LLM)
```

## Web UI Configuration

The web UI connects to the API server:

```yaml
# API server settings
api:
  host: 127.0.0.1
  port: 8001
  cors_origins:
    - http://localhost:3000
    - http://localhost:3001
```

Web UI environment (`.env.local` in `orion-web/`):
```
NEXT_PUBLIC_API_URL=http://localhost:8001
NEXT_PUBLIC_WS_URL=ws://localhost:8001/ws/chat
```

## Voice Configuration

```yaml
voice:
  # Text-to-Speech
  tts_provider: elevenlabs  # or openai, edge-tts, piper, etc.
  tts_voice: "Rachel"

  # Speech-to-Text
  stt_provider: whisper     # or vosk, deepgram, assemblyai, etc.
  stt_model: "base"
```

## Logging

```yaml
logging:
  level: INFO                    # DEBUG, INFO, WARNING, ERROR
  file: ~/.orion/logs/orion.log  # Log file location
  structured: false              # JSON structured logging
  max_size: 10MB                 # Max log file size
  backup_count: 5                # Number of backup files
```

## Sandbox Configuration

```yaml
sandbox:
  mode: auto          # auto, docker, local
  timeout: 60         # Seconds before execution timeout
  network: false      # Allow network access in sandbox
```

## Environment Variables Reference

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

## Config File Location

The main config file is located at:
- **Linux/macOS:** `~/.orion/config.yaml`
- **Windows:** `%USERPROFILE%\.orion\config.yaml`

### Example Complete Config

```yaml
# ~/.orion/config.yaml
llm:
  provider: openai
  model: gpt-4o
  temperature: 0.3
  max_tokens: 4096

governance:
  mode: pro

memory:
  tier2_retention_days: 30
  promotion_threshold: 0.85
  auto_consolidate: true

agents:
  enable_table_of_three: true

sandbox:
  mode: auto
  timeout: 60
  network: false

logging:
  level: INFO
  structured: false
```

---

**Next:** [User Guide](USER_GUIDE.md) | [CLI Reference](CLI_REFERENCE.md)
