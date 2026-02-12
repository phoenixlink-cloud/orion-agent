<div align="center">

# Orion Agent

**Self-improving, multi-agent AI coding assistant with persistent memory, governed execution, and continuous learning.**

[![License: AGPL-3.0](https://img.shields.io/badge/License-AGPL--3.0-blue.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/downloads/)
[![Tests](https://img.shields.io/badge/tests-412%20passing-green.svg)](tests/)
[![Code Style: Ruff](https://img.shields.io/badge/code%20style-ruff-000000.svg)](https://github.com/astral-sh/ruff)
[![Status: Beta](https://img.shields.io/badge/status-beta-orange.svg)](#)

[Getting Started](#-quick-start) |
[Documentation](docs/README.md) |
[AEGIS Governance](#-aegis-governance) |
[Contributing](CONTRIBUTING.md) |
[Support Development](#-support-orion-development)

</div>

> **Beta Software** -- Orion Agent is under active development. Core features are functional and tested (412 passing tests), but you may encounter rough edges, incomplete integrations, or breaking changes between versions. We welcome feedback and bug reports via [GitHub Issues](https://github.com/phoenixlink-cloud/orion-agent/issues).

---

## What is Orion?

Orion is an **AI coding assistant** that goes beyond simple code generation. It combines:

- **Multi-Agent Architecture** -- Three specialized agents deliberate on every task
- **Persistent Memory** -- Learns and remembers across sessions, projects, and time
- **AEGIS Governance** -- Hardened security gate that prevents unsafe operations
- **Continuous Learning** -- Improves from your feedback, building institutional knowledge

Unlike single-shot AI tools, Orion develops understanding of your codebase, your patterns, and your preferences over time.

---

## Key Features

### Multi-Agent Deliberation

Every request flows through three specialized agents:

| Agent | Role | Responsibility |
|-------|------|----------------|
| **Builder** | Creator | Generates code solutions using your chosen LLM |
| **Reviewer** | Critic | Analyzes Builder's output for correctness, quality, and edge cases |
| **Governor** | Authority | Makes final decisions using memory, quality gates, and governance rules |

This "Table of Three" approach catches errors that single-agent systems miss.

### Three-Tier Memory System

Orion remembers -- not just within a conversation, but across your entire development history:

| Tier | Storage | Duration | Purpose |
|------|---------|----------|---------|
| **Session** | RAM | Current session | Immediate context and conversation state |
| **Project** | JSON | Days to weeks | Workspace patterns, decisions, and preferences |
| **Institutional** | SQLite | Months to years | Cross-project wisdom and proven patterns |

### AEGIS Governance

AEGIS (Autonomous Execution Governance and Integrity System) is Orion's security core:

- **Workspace Confinement** -- Cannot operate outside your project directory
- **Mode Enforcement** -- Graduated permissions (safe -> pro -> project)
- **Action Validation** -- Every file operation is checked before execution
- **External Access Control** -- Network operations require explicit approval
- **Shell Injection Prevention** -- Blocks dangerous command patterns

[Learn more about AEGIS ->](docs/AEGIS.md)

### Continuous Learning

Orion learns from every interaction:

1. **You rate responses** (1-5 stars)
2. **Good patterns** (4-5) are stored as success templates
3. **Bad patterns** (1-2) are stored as anti-patterns to avoid
4. **Evolution tracking** monitors improvement over time

---

## Comparison

| Feature | Orion |
|---------|-------|-------|-------------|----------------|
| Multi-agent deliberation | 3 agents | Single | Single | Single |
| Persistent memory | 3 tiers | Session only | Session only | None |
| Learns from feedback | Yes | No | No | No |
| Governance/safety gate | AEGIS | Basic | Basic | None |
| Edit validation | Pre-write scoring | Format-specific | Basic | None |
| LLM providers | 11 providers | Limited | Claude only | OpenAI only |
| Self-hosted option | Full | Full | No | No |
| Open source | AGPL-3.0 | Apache-2.0 | No | No |

---

## Quick Start

### Installation
```bash
# Basic installation
pip install orion-agent

# With all integrations
pip install orion-agent[all]
```

### First Run
```bash
orion
```

### Basic Usage
```
> /workspace /path/to/your/project
Workspace set: /path/to/your/project

> /mode pro
Mode set: pro (read + write with approval)

> Explain what the main function does
[Orion analyzes your code and provides explanation]

> Add error handling to the database connection
[Orion proposes changes, waits for your approval]
```

### Configuration
```bash
# Set your API key
/settings key openai sk-your-key-here

# Choose your model
/settings model gpt-4o

# Or use local Ollama (free)
/settings provider ollama
/settings model llama3
```

[Full installation guide ->](docs/INSTALLATION.md)

---

## AEGIS Governance

AEGIS is what makes Orion safe for production use. It's a **pure-function security gate** with six invariants:

1. **Workspace Confinement** -- All file operations must stay within the workspace
2. **Mode Enforcement** -- Actions must be permitted by the current mode
3. **Action Scope** -- Only approved operation types are allowed
4. **Risk Validation** -- High-risk operations require human confirmation
5. **Command Execution** -- Shell commands are validated for safety
6. **External Access** -- Network operations follow read/write approval rules

AEGIS cannot be bypassed, disabled, or reconfigured by AI agents.

[Complete AEGIS documentation ->](docs/AEGIS.md)

---

## Integrations

Orion connects to 79+ external services:

| Category | Count | Examples |
|----------|-------|----------|
| **LLM Providers** | 11 | OpenAI, Anthropic, Google, Ollama, Groq, Mistral, Cohere |
| **Voice TTS** | 8 | ElevenLabs, OpenAI TTS, Edge-TTS, Piper |
| **Voice STT** | 6 | Whisper, Vosk, Deepgram, AssemblyAI |
| **Image Generation** | 8 | DALL-E 3, Stability AI, Midjourney, Replicate |
| **Messaging** | 15 | Slack, Discord, Telegram, Teams, WhatsApp |
| **Dev Tools** | 10+ | GitHub, GitLab, Jira, Linear, Notion |

[Complete integration catalog ->](docs/INTEGRATIONS.md)

---

## Documentation

| Document | Description |
|----------|-------------|
| [Getting Started](docs/GETTING_STARTED.md) | Quick start guide for new users |
| [Installation](docs/INSTALLATION.md) | Detailed installation instructions |
| [User Guide](docs/USER_GUIDE.md) | Complete user documentation |
| [CLI Reference](docs/CLI_REFERENCE.md) | All commands and options |
| [API Reference](docs/API_REFERENCE.md) | REST and WebSocket API |
| [Architecture](docs/ARCHITECTURE.md) | System design deep-dive |
| [AEGIS](docs/AEGIS.md) | Governance system documentation |
| [Memory System](docs/MEMORY_SYSTEM.md) | Three-tier memory explained |
| [Security](docs/SECURITY.md) | Security model and practices |
| [Deployment](docs/DEPLOYMENT.md) | Production deployment guide |
| [FAQ](docs/FAQ.md) | Frequently asked questions |

---

## Architecture
```
┌─────────────────────────────────────────────────────────────┐
│                      USER INTERFACES                         │
│   ┌─────────┐    ┌─────────────┐    ┌─────────────────┐     │
│   │   CLI   │    │  REST API   │    │   Web Frontend  │     │
│   │  (REPL) │    │  (FastAPI)  │    │    (Next.js)    │     │
│   └────┬────┘    └──────┬──────┘    └────────┬────────┘     │
└────────┼────────────────┼────────────────────┼──────────────┘
         │                │                    │
         ▼                ▼                    ▼
┌─────────────────────────────────────────────────────────────┐
│                     REQUEST ROUTER                           │
│   Scout analyzes complexity -> routes to appropriate path    │
│   FastPath (simple) | Council (complex) | Escalation (risky) │
└────────────────────────────┬────────────────────────────────┘
                             │
         ┌───────────────────┼───────────────────┐
         ▼                   ▼                   ▼
┌─────────────┐    ┌─────────────────┐    ┌─────────────┐
│  FastPath   │    │  Table of Three │    │  Escalation │
│  (direct)   │    │    (council)    │    │  (human)    │
└──────┬──────┘    └────────┬────────┘    └──────┬──────┘
       │                    │                    │
       └────────────────────┼────────────────────┘
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                    AEGIS GOVERNANCE GATE                     │
│   Workspace Confinement | Mode Enforcement | Risk Validation │
└────────────────────────────┬────────────────────────────────┘
                             │
         ┌───────────────────┼───────────────────┐
         ▼                   ▼                   ▼
┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│  LLM Layer  │    │   Memory    │    │  Learning   │
│ (11 provs)  │    │  (3-tier)   │    │ (KD + Evo)  │
└─────────────┘    └─────────────┘    └─────────────┘
```

[Complete architecture documentation ->](docs/ARCHITECTURE.md)

---

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

---

## Development

```bash
git clone https://github.com/phoenixlink-cloud/orion-agent.git
cd orion-agent
python -m venv .venv
.venv\Scripts\activate
pip install -e ".[dev]"
pytest
```

---

## Contributing

We welcome contributions! Please read our guidelines first:

- [CONTRIBUTING.md](CONTRIBUTING.md) -- How to contribute
- [CLA.md](CLA.md) -- Contributor License Agreement (required)
- [COPYRIGHT.md](COPYRIGHT.md) -- Ownership and IP terms
- [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md) -- Community guidelines

**Note:** All contributions require a signed CLA before code can be merged.

---

## License & Copyright
```
Copyright (C) 2025 Phoenix Link (Pty) Ltd. All Rights Reserved.
```

Orion Agent is dual-licensed:

| License | Use Case | Requirements |
|---------|----------|--------------|
| [**AGPL-3.0**](LICENSE) | Open source, personal use, AGPL-compatible projects | Copyleft -- share modifications under AGPL-3.0 |
| [**Commercial**](LICENSE-ENTERPRISE.md) | Proprietary software, SaaS, enterprise | Contact Phoenix Link for licensing |

**Using Orion in a commercial product or SaaS?** Contact info@phoenixlink.co.za

---

## Support Orion Development

Orion is free and open-source. If it has benefited you and you'd like to see continued development, please consider making a voluntary financial contribution.

| Tier | Amount | Description | Link |
|------|--------|-------------|------|
| **One-Time Support** | R400 | Supports ongoing development, documentation, and testing of Orion Agent and governed AI tooling. | [![Support](https://img.shields.io/badge/Support-R400-blue?style=flat-square)](https://payf.st/jkza6) |
| **Development Sponsor** | R1,500 | Supports feature development, performance improvements, integrations, and security hardening. | [![Sponsor](https://img.shields.io/badge/Sponsor-R1500-green?style=flat-square)](https://payf.st/vhjfz) |
| **Infrastructure Sponsor** | R8,000 | Helps fund infrastructure, CI/CD pipelines, security audits, and long-term sustainability. | [![Sponsor](https://img.shields.io/badge/Sponsor-R8000-orange?style=flat-square)](https://payf.st/qil2v) |

**This is a voluntary contribution, not a purchase.** See [FUNDING.md](FUNDING.md) for full details.

*Other ways to help: Star the repo | Report bugs | Improve docs | Contribute code*

---

## Contact

| Purpose | Contact |
|---------|---------|
| General inquiries, licensing, partnerships | info@phoenixlink.co.za |
| Technical support | support@phoenixlink.co.za |

**Website:** [phoenixlink.co.za](https://phoenixlink.co.za)

---

<div align="center">

**Built by [Phoenix Link (Pty) Ltd](https://phoenixlink.co.za)**

*Governed AI for the real world.*

</div>
