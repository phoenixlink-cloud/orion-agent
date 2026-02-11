# 🌟 Orion Agent

**Self-improving, multi-agent AI coding assistant with persistent memory and continuous learning.**

[![CI](https://github.com/phoenix-link/orion-agent/actions/workflows/ci.yml/badge.svg)](https://github.com/phoenix-link/orion-agent/actions)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/downloads/)
[![License: AGPL-3.0](https://img.shields.io/badge/License-AGPL--3.0-blue.svg)](LICENSE)

---

## What Makes Orion Different

| Feature | Orion |
|---------|-------|-------|-------------|
| **Multi-agent architecture** | 3 agents deliberate on every task | Single agent | Single agent |
| **Persistent memory** | 3-tier system across sessions | Session only | Session only |
| **Continuous learning** | Learns from your feedback | None | None |
| **Edit validation** | Pre-write confidence scoring | Format-specific | Basic |
| **79 integrations** | LLM, voice, image, messaging, etc. | LLM only | LLM only |
| **Production ready** | Health probes, metrics, Docker | CLI only | CLI only |

### Table of Three

Every task runs through three agents:

- **Builder** -- Generates the code solution (configurable: GPT-4o, Claude, Ollama, etc.)
- **Reviewer** -- Critiques the Builder's output for correctness and quality
- **Governor** -- Orion's own decision layer that makes the final call using memory and quality gates

### Three-Tier Memory

Orion remembers across sessions, projects, and time:

| Tier | Storage | Duration | Purpose |
|------|---------|----------|---------|
| **Session** | RAM | Minutes | Current request context |
| **Project** | JSON | Days–weeks | Workspace patterns and decisions |
| **Institutional** | SQLite | Months–years | Cross-project wisdom |

### Continuous Learning

Every time you rate Orion's output (1–5), it learns:
- **Good outcomes** (4–5) -> success patterns stored permanently
- **Bad outcomes** (1–2) -> anti-patterns stored to avoid repeating mistakes
- **Evolution tracking** -> performance trends, self-improvement recommendations

---

## Quick Start

### Install

```bash
pip install orion-agent
```

With all integrations:

```bash
pip install orion-agent[all]
```

### Run

```bash
orion
```

### Configure

```bash
cp .env.example .env
# Add your API keys (or use Ollama for free/local)
```

### Basic Usage

```
/workspace /path/to/your/project
/mode pro

> Fix the authentication bug in auth.py
> Add unit tests for the user model
> Explain how the payment flow works
```

---

## Architecture

```
┌──────────────────────────────────────────────────────┐
│                    USER REQUEST                       │
└──────────────────┬───────────────────────────────────┘
                   ▼
┌──────────────────────────────────────────────────────┐
│          Orion Orchestrator                           │
│  Memory Engine ← -> Quality Gate ← -> Learning Loop   │
└──────────────────┬───────────────────────────────────┘
                   ▼
┌──────────────────────────────────────────────────────┐
│              TABLE OF THREE                           │
│  Builder (LLM 1) -> Reviewer (LLM 2) -> Governor      │
└──────────────────┬───────────────────────────────────┘
                   ▼
┌──────────────────────────────────────────────────────┐
│  Edit Validator -> Git Safety Net -> File System       │
└──────────────────────────────────────────────────────┘
```

## Project Structure

```
src/orion/
├── cli/               # Interactive REPL and commands
├── core/
│   ├── agents/        # Builder, Reviewer, Governor, Table of Three
│   ├── memory/        # Three-tier memory engine
│   ├── learning/      # Evolution engine, feedback, patterns
│   ├── editing/       # Edit validator, format selector, git safety
│   ├── context/       # Repo map (tree-sitter), Python AST, code quality
│   ├── governance/    # AEGIS safety gate, execution authority
│   ├── llm/           # Provider routing, model config, prompts
│   └── production/    # Health probes, metrics, shutdown, logging
├── integrations/      # 79 connectors (LLM, voice, image, messaging, ...)
├── api/               # FastAPI REST + WebSocket server
├── security/          # Encrypted store, Docker sandbox
└── plugins/           # Plugin lifecycle API (8 hooks)
```

## Commands

| Command | Description |
|---------|-------------|
| `/workspace <path>` | Set project directory |
| `/mode safe\|pro\|project` | Set governance mode |
| `/doctor` | Run 15 system diagnostic checks |
| `/health` | Check all integration health |
| `/undo` | Revert last edit (git savepoint) |
| `/map` | Show repository structure |
| `/settings` | Manage API keys and models |

## Modes

| Mode | Can Read | Can Edit | Can Run Commands |
|------|----------|----------|-----------------|
| **safe** | ✅ | ❌ | ❌ |
| **pro** | ✅ | ✅ (with approval) | ❌ |
| **project** | ✅ | ✅ | ✅ (allowlisted) |

## Integrations (79)

| Category | Count | Examples |
|----------|-------|---------|
| LLM Providers | 11 | OpenAI, Anthropic, Google, Ollama, Groq, Mistral |
| Voice TTS | 8 | ElevenLabs, OpenAI TTS, Edge-TTS, Piper |
| Voice STT | 6 | Whisper, Vosk, Deepgram, AssemblyAI |
| Image Gen | 8 | DALL-E 3, Stability AI, SDXL, Replicate |
| Video Gen | 7 | HeyGen, Runway, Pika, Synthesia |
| Messaging | 15 | Slack, Discord, Telegram, Teams, WhatsApp |
| Social | 5 | YouTube, X/Twitter, Reddit, TikTok, LinkedIn |
| Automation | 5 | n8n, Zapier, Make, Pipedream |
| Storage | 4 | Dropbox, OneDrive, SharePoint |
| Dev Tools | 10+ | GitHub, GitLab, VS Code, Docker |

## Development

```bash
git clone https://github.com/phoenix-link/orion-agent.git
cd orion-agent
python -m venv .venv
.venv\Scripts\activate
pip install -e ".[dev]"
pytest
```

## License & Copyright
```
Copyright (C) 2025 Phoenix Link (Pty) Ltd. All Rights Reserved.
```

Orion Agent is dual-licensed:

| License | Use Case | Requirements |
|---------|----------|--------------|
| [**AGPL-3.0**](./LICENSE) | Open source, personal projects, AGPL-compatible software | Copyleft -- share modifications under AGPL-3.0 |
| [**Commercial**](./LICENSE-ENTERPRISE.md) | Proprietary software, SaaS, enterprise | Contact Phoenix Link for licensing |

### Quick Guide

- **Using Orion for personal projects?** AGPL-3.0 is free
- **Contributing to open source?** AGPL-3.0 is free
- **Building a commercial product?** [Contact us](mailto:licensing@phoenixlink.co.za) for commercial licensing
- **Offering Orion as SaaS?** [Contact us](mailto:licensing@phoenixlink.co.za) for commercial licensing

### Contributing

All contributions require a signed Contributor License Agreement (CLA).

- [COPYRIGHT.md](./COPYRIGHT.md) -- Ownership and IP terms
- [CONTRIBUTING.md](./CONTRIBUTING.md) -- How to contribute
- [CLA.md](./CLA.md) -- Contributor License Agreement
- **CLA signing:** cla@phoenixlink.co.za

### Contact

| Purpose | Contact |
|---------|---------|
| Commercial licensing | licensing@phoenixlink.co.za |
| Legal questions | legal@phoenixlink.co.za |
| CLA signing | cla@phoenixlink.co.za |
| Website | [phoenixlink.co.za](https://phoenixlink.co.za) |

---

## Support Orion Development

Orion is free and open-source under AGPL-3.0. If it has benefited you in any way and you would like to see its continued development, please consider making a voluntary financial contribution.

[![Support Orion Development](https://img.shields.io/badge/Support-Orion%20Development-blue?style=for-the-badge)](https://payf.st/t2pmo)

Your contribution helps fund:
- Core development and new features
- Security audits and AEGIS governance
- Documentation and community support
- Long-term project sustainability

**This is a voluntary contribution, not a purchase.** See [FUNDING.md](./FUNDING.md) for details.

*Other ways to help: Star the repo | Report bugs | Improve docs | Contribute code*
