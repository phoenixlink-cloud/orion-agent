<div align="center">

# Orion Agent

**Self-improving, multi-agent AI coding assistant with natural language understanding, autonomous role execution, persistent memory, and governed security.**

[![License: AGPL-3.0](https://img.shields.io/badge/License-AGPL--3.0-blue.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/downloads/)
[![Tests](https://img.shields.io/badge/tests-1609%20passing-brightgreen.svg)](tests/)
[![Code Style: Ruff](https://img.shields.io/badge/code%20style-ruff-000000.svg)](https://github.com/astral-sh/ruff)
[![Status: Stable](https://img.shields.io/badge/status-10.0.0-brightgreen.svg)](#)

[Getting Started](#-quick-start) |
[NLA](#-natural-language-architecture) |
[ARA](#-autonomous-role-architecture) |
[Skills](#-skills-system) |
[Web UI](#-web-ui) |
[AEGIS Governance](#-aegis-governance) |
[Network Security](#-network-security) |
[Documentation](docs/README.md) |
[Contributing](CONTRIBUTING.md)

</div>

> **v10.0.0** -- Orion Agent is under active development. Core features are functional and tested (1,609+ passing tests). Phase 2 adds Docker-based network security with an egress proxy, DNS filter, approval queue, and AEGIS Invariant 7. The Autonomous Role Architecture (ARA) is complete with 37 CLI commands, 106+ API endpoints, Skills system, and a full React Web UI. We welcome feedback and bug reports via [GitHub Issues](https://github.com/phoenixlink-cloud/orion-agent/issues).

---

## What is Orion?

Orion is an **AI coding assistant** that goes beyond simple code generation. It combines:

- **Natural Language Architecture (NLA)** -- Intent classification, clarification detection, and adaptive prompt engineering
- **Autonomous Role Architecture (ARA)** -- Background task execution with configurable roles, AEGIS-gated promotion, and daemon management
- **Multi-Agent Deliberation** -- Three specialized agents deliberate on every task
- **Persistent Memory** -- Learns and remembers across sessions, projects, and time
- **AEGIS Governance** -- Hardened security gate that prevents unsafe operations (7 invariants)
- **Network Security** -- Egress proxy, DNS filter, content inspection, and approval queue in Docker sandbox
- **Slim Persona System** -- Tiered prompt engineering (50–120 tokens) matched to intent complexity

Unlike single-shot AI tools, Orion develops understanding of your codebase, your patterns, and your preferences over time.

---

## Key Features

### Natural Language Architecture (NLA)

Orion understands *what you mean*, not just what you type:

| Component | Purpose |
|-----------|----------|
| **ExemplarBank** | 200+ seed exemplars for intent matching with cosine similarity |
| **IntentClassifier** | Embedding + keyword hybrid classification (coding, question, conversational) |
| **ClarificationDetector** | Detects ambiguous requests and generates targeted follow-up questions |
| **BriefBuilder** | Converts natural language into structured `TaskBrief` objects |
| **RequestAnalyzer** | Full pipeline: classify → clarify → brief → route |
| **EnglishFoundation** | Linguistic pre-processing (contractions, negation, entity extraction) |
| **LearningBridge** | Feedback loop: user ratings → new exemplars → improved classification |

### Autonomous Role Architecture (ARA)

Orion can work autonomously in the background with configurable roles (28 modules, 671+ ARA tests):

| Component | Purpose |
|-----------|----------|
| **RoleProfile** | YAML-based role configuration with 3-tier authority, confidence thresholds, competencies, risk tolerance |
| **AegisGate** | Pre-promotion security: secret scanning, write limits, scope checks, auth |
| **SessionEngine** | State machine with heartbeat, cost tracking, and 5 stop conditions |
| **GoalEngine** | LLM-powered task DAG decomposition with action validation |
| **ExecutionLoop** | Sequential task runner with confidence gating and checkpointing |
| **TaskExecutor** | File generation/editing in sandbox with context-aware LLM calls |
| **PromotionManager** | Sandbox branch creation, file diff, conflict detection, git-tagged promote/reject/undo |
| **GoalQueue** | Multi-goal FIFO queue with priority interrupts, dependencies, and reorder |
| **MorningDashboard** | 7-section CLI TUI: overview, approvals, tasks, files, budget, AEGIS, actions |
| **PromptGuard** | 12-pattern prompt injection defence with sanitization |
| **AuditLog** | HMAC-SHA256 hash chain, append-only JSONL, tamper detection |
| **KeychainStore** | OS-native credential storage (Windows/macOS) with encrypted fallback |
| **UserIsolation** | Multi-user OS-user scoping, per-user containers and branches |
| **SkillLibrary** | AgentSkills-compatible SKILL.md system with CRUD, integrity verification, and role assignment |
| **SkillGuard** | 22+ pattern security scanner with NFKC normalization and evasion hardening |
| **Daemon + CLI** | Background process with 37 commands including setup wizard |
| **Notifications** | Email (SMTP), webhook, and desktop toast delivery with rate limiting |
| **REST + WebSocket API** | 106+ endpoints for web UI integration and real-time updates |

**Starter roles included:** `game-developer`, `night-coder`, `researcher`, `devops-runner`, `full-auto`

### Skills System

Orion uses the [AgentSkills](https://agentskills.io) open standard for extensible agent capabilities (8 bundled skills, 145 tests):

| Component | Purpose |
|-----------|----------|
| **SKILL.md Format** | YAML frontmatter + markdown instructions, compatible with Claude Code and Windsurf |
| **SkillLibrary** | Central registry with CRUD, import, rescan, role resolution, integrity verification (SHA-256) |
| **SkillGuard** | Security scanner: 22+ patterns, NFKC normalization, prompt injection detection |
| **Skill Groups** | Organize skills into assignable groups with role mapping |
| **8 Bundled Skills** | `code-review`, `write-tests`, `write-documentation`, `deploy-to-staging`, `docker-setup`, `git-workflow`, `debug-issue`, `refactor-safely` |

### Web UI

A full-featured React (Next.js) dashboard for managing ARA sessions:

| Feature | Description |
|---------|-------------|
| **Dashboard** | Stats grid, status hero, activity feed, task queue, progress ring |
| **Consent Gates** | Approve/reject with GitHub-PR-style diff viewer (file tree + unified diffs) |
| **New Session** | Start work sessions from the UI with role selection and goal input |
| **Job Roles** | Create, edit, delete roles with scope/auth/description |
| **Skills** | Browse, create, delete skills; assign/unassign to roles; security scan |
| **Chat** | WebSocket chat sidebar connected to Orion's full NLA pipeline |
| **Settings** | ARA settings, API keys, workspace configuration |
| **Notifications** | Real-time notification badge with unread count |

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

AEGIS (Autonomous Execution Governance and Integrity System) is Orion's security core (v7.0.0, 7 invariants):

- **Invariant 1: Workspace Confinement** -- Cannot operate outside your project directory
- **Invariant 2: Mode Enforcement** -- Graduated permissions (safe -> pro -> project)
- **Invariant 3: Action Validation** -- Every file operation is checked before execution
- **Invariant 4: Risk Validation** -- Risk scoring with configurable thresholds
- **Invariant 5: Command Execution** -- Shell injection prevention, dangerous pattern blocking
- **Invariant 6: External Access Control** -- Network operations require explicit approval
- **Invariant 7: Network Access Control** -- Hardcoded domain whitelist, blocked Google services, protocol enforcement

[Learn more about AEGIS ->](docs/AEGIS.md)

### Network Security

Phase 2 introduces Docker-based network isolation with defence in depth:

| Layer | Component | Purpose |
|-------|-----------|----------|
| **L1** | Egress Proxy | Domain whitelist with hardcoded LLM endpoints, rate limiting |
| **L2** | DNS Filter | NXDOMAIN for non-whitelisted domains |
| **L3** | Content Inspector | 12 credential patterns blocked in outbound payloads |
| **L4** | Approval Queue | Human-in-the-loop gate for write operations |
| **L5** | AEGIS Invariant 7 | Hardcoded blocked Google services (Drive, Gmail, Calendar, YouTube) |
| **L6** | Docker Isolation | Dual-network architecture (orion-internal + orion-egress) |
| **L7** | Google Credentials | Scope-enforced OAuth with blocked-scope rejection |

### Continuous Learning

Orion learns from every interaction:

1. **You rate responses** (1-5 stars)
2. **Good patterns** (4-5) are stored as success templates
3. **Bad patterns** (1-2) are stored as anti-patterns to avoid
4. **Evolution tracking** monitors improvement over time

---

## Why Orion?

| Feature | Orion |
|---------|-------|
| Natural language understanding | NLA: intent classification, clarification, adaptive prompts |
| Autonomous background tasks | ARA: roles, daemon, checkpoints, drift detection, recovery |
| Web UI | Full React dashboard with consent gates, diff viewer, session management |
| Skills system | AgentSkills-compatible SKILL.md, 8 bundled, SkillGuard security |
| Multi-agent deliberation | 3 specialized agents (Builder, Reviewer, Governor) |
| Persistent memory | 3 tiers (session, project, institutional) |
| Learns from feedback | Evolves based on your approval/rejection patterns |
| Governance/safety gate | AEGIS v7.0.0 -- 7 hardened security invariants |
| Network firewall | Egress proxy + DNS filter + content inspection in Docker sandbox |
| Edit validation | Pre-write confidence scoring + auto-recovery |
| LLM providers | 11 providers including local Ollama (BYOK) |
| Self-hosted | Runs entirely on your machine |
| Open source | AGPL-3.0 |

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
┌─────────────────────────────────────────────────────────────────┐
│                       USER INTERFACES                           │
│  ┌─────────┐  ┌───────────┐  ┌───────────┐  ┌──────────────┐   │
│  │  CLI    │  │ Web UI    │  │ WebSocket │  │ ARA Daemon   │   │
│  │ (REPL)  │  │ (Next.js) │  │ (realtime)│  │ (background) │   │
│  └────┬────┘  └─────┬─────┘  └─────┬─────┘  └──────┬───────┘   │
└───────┼─────────────┼──────────────┼───────────────┼───────────┘
        │             │              │               │
        ▼             ▼              ▼               ▼
┌─────────────────────────────────────────────────────────────────┐
│          FastAPI Server (10 route modules, 106+ endpoints)       │
│              REST API │ WebSocket │ CORS │ Auth                  │
└───────────────────────────┬─────────────────────────────────────┘
                            │
        ┌───────────────────┼───────────────────┐
        ▼                   ▼                   ▼
┌─────────────────┐ ┌─────────────────┐ ┌─────────────────────┐
│  NLA Pipeline   │ │  ARA Engine     │ │  Skills System      │
│  ExemplarBank   │ │  Sessions       │ │  SkillLibrary       │
│  IntentClassify │ │  Daemon         │ │  SkillGuard (22+)   │
│  BriefBuilder   │ │  TaskExecutor   │ │  8 bundled skills   │
│  FastPath/ToT   │ │  Promotion      │ │  SKILL.md format    │
└────────┬────────┘ │  GoalQueue      │ └─────────────────────┘
         │          │  Dashboard      │
         ▼          └────────┬────────┘
┌─────────────────────────────┼───────────────────────────────────┐
│                    AEGIS GOVERNANCE GATE                         │
│  Workspace Confinement │ Secret Scanning │ Write Limits          │
│  Mode Enforcement │ Risk Validation │ Auth (PIN/TOTP)           │
│  PromptGuard │ AuditLog (HMAC) │ KeychainStore                 │
└───────────────────────────┬─────────────────────────────────────┘
                            │
        ┌───────────────────┼───────────────────┐
        ▼                   ▼                   ▼
┌─────────────┐   ┌─────────────────┐   ┌─────────────────┐
│  LLM Layer  │   │   Memory        │   │  Integrations   │
│ (11 provs)  │   │  (3-tier)       │   │  79 connectors  │
│ + Ollama    │   │  Institutional  │   │  LLM, voice,    │
│             │   │  Teaching       │   │  image, msg, dev │
└─────────────┘   └─────────────────┘   └─────────────────┘
```

[Complete architecture documentation ->](docs/ARCHITECTURE.md)

---

## Project Structure

```
src/orion/
├── cli/               # Interactive REPL and commands
├── core/
│   ├── agents/        # Builder, Reviewer, Governor, Table of Three, FastPath
│   ├── understanding/ # NLA: intent, clarification, brief, analyzer, english
│   ├── memory/        # Three-tier memory engine + institutional memory + teaching
│   ├── learning/      # Evolution engine, feedback, patterns, learning bridge
│   ├── editing/       # Edit validator, format selector, git safety
│   ├── context/       # Repo map (tree-sitter), Python AST, code quality
│   ├── governance/    # AEGIS safety gate, execution authority
│   ├── llm/           # Provider routing, model config, slim persona prompts
│   └── production/    # Health probes, metrics, shutdown, logging
├── ara/               # Autonomous Role Architecture (28 modules)
│   ├── role_profile   # YAML role configuration + 3-tier authority + 5 starter templates
│   ├── auth           # PIN + TOTP authentication
│   ├── aegis_gate     # Pre-promotion security gate
│   ├── session        # State machine with heartbeat + cost tracking
│   ├── goal_engine    # LLM-powered task DAG decomposition
│   ├── execution      # Sequential task runner with checkpointing
│   ├── task_executor  # Context-aware file generation/editing in sandbox
│   ├── daemon         # Background process + IPC control
│   ├── daemon_launcher# Session launcher from pending state
│   ├── cli_commands   # 37 commands: work/status/review/promote/skills/roles/setup/...
│   ├── promotion      # Sandbox → workspace merge with git tags + undo
│   ├── dashboard      # Morning Dashboard TUI (7 sections) + pending review detection
│   ├── goal_queue     # Multi-goal FIFO queue with priority interrupts
│   ├── prompt_guard   # Prompt injection defence (12 patterns)
│   ├── audit_log      # HMAC-SHA256 hash chain tamper-proof log
│   ├── keychain       # OS-native credential storage
│   ├── user_isolation  # Multi-user OS-user scoping
│   ├── notifications  # Email, webhook, desktop providers
│   ├── feedback_store # Outcome recording + confidence calibration
│   ├── skill          # Skill + SkillGroup dataclasses, SKILL.md parser, validation
│   ├── skill_guard    # SkillGuard security scanner (22+ patterns, NFKC hardening)
│   ├── skill_library  # Central skill registry with CRUD, import, integrity verification
│   ├── ollama_provider# Local LLM integration for task execution
│   ├── checkpoint     # Git-based session snapshots
│   ├── drift_monitor  # External workspace change detection
│   ├── recovery       # Failure handling + retry policy
│   └── lifecycle      # Session cleanup + health reporting
├── api/               # FastAPI REST + WebSocket server (10 route modules, 106+ endpoints)
│   └── routes/        # ara, auth, chat, gdpr, health, models, platforms, settings, tools, training
├── integrations/      # 79 connectors (LLM, voice, image, messaging, ...)
├── security/          # Encrypted store, Docker sandbox, secret scanner
└── plugins/           # Plugin lifecycle API (8 hooks)

orion-web/             # React (Next.js) Web UI
├── src/app/
│   ├── page.tsx       # Home page
│   ├── ara/page.tsx   # ARA Dashboard (consent gates, diff viewer, sessions, roles, skills)
│   ├── chat/page.tsx  # Chat interface
│   ├── aegis/page.tsx # AEGIS governance info
│   └── settings/page.tsx # Full settings panel
└── src/components/    # ChatInterface, SettingsPanel, AegisApprovalModal
```

---

## Development

```bash
# Backend
git clone https://github.com/phoenixlink-cloud/orion-agent.git
cd orion-agent
python -m venv .venv
.venv\Scripts\activate
pip install -e ".[dev]"
pytest                        # 1,348 tests

# API Server
uvicorn orion.api.server:app --port 8001

# Web UI
cd orion-web
npm install
npm run dev                   # http://localhost:3000
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
