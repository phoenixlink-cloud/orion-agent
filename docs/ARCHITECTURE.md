# Orion Architecture

Deep-dive into Orion Agent's system design, component relationships, and data flow.

## System Overview

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
│   Action Scope | Command Execution | External Access Control │
└────────────────────────────┬────────────────────────────────┘
                             │
         ┌───────────────────┼───────────────────┐
         ▼                   ▼                   ▼
┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│  LLM Layer  │    │   Memory    │    │  Learning   │
│ (11 provs)  │    │  (3-tier)   │    │ (KD + Evo)  │
└─────────────┘    └─────────────┘    └─────────────┘
```

## Module Organization

```
src/orion/
├── cli/                    # User interface layer
│   ├── repl.py            # Interactive REPL loop
│   └── commands.py        # Slash command handlers
│
├── core/                   # Core business logic
│   ├── router.py          # Request routing (Scout)
│   ├── fast_path.py       # FastPath direct LLM route
│   ├── agents/            # Multi-agent system
│   │   ├── builder.py     # Code generation agent
│   │   ├── reviewer.py    # Code review agent
│   │   ├── governor.py    # Deterministic decision maker
│   │   └── table.py       # Table of Three orchestration
│   ├── governance/        # Security layer
│   │   ├── aegis.py       # AEGIS governance gate
│   │   └── commitment.py  # Execution authority tracking
│   ├── llm/               # LLM abstraction
│   │   ├── providers.py   # Provider routing (call_provider)
│   │   ├── models.py      # Model configuration
│   │   └── prompts.py     # Prompt templates
│   ├── memory/            # Persistence
│   │   └── memory_engine.py  # Three-tier memory system
│   ├── learning/          # Continuous improvement
│   │   └── evolution_engine.py  # Evolution tracking
│   ├── editing/           # File modification
│   │   ├── edit_validator.py  # Pre-write validation
│   │   └── format_selector.py # Edit format selection
│   ├── context/           # Code understanding
│   │   ├── repo_map.py    # Repository structure (tree-sitter)
│   │   └── code_quality.py # Quality analysis
│   └── production/        # Production infrastructure
│       └── production.py  # Health probes, metrics, logging
│
├── api/                    # REST/WebSocket server
│   ├── server.py          # FastAPI app + middleware
│   └── routes/            # Route modules
│       ├── chat.py        # WebSocket chat
│       ├── settings.py    # Settings CRUD
│       ├── git.py         # Git operations
│       ├── doctor.py      # Diagnostics
│       └── ...            # Other route modules
│
├── integrations/           # External service connectors
│   ├── voice/             # TTS/STT (8+6 providers)
│   ├── image_gen/         # Image generation (8 providers)
│   ├── video_gen/         # Video generation (7 providers)
│   ├── messaging/         # Messaging (15 connectors)
│   ├── social/            # Social platforms (5)
│   ├── automation/        # Automation hubs (5)
│   └── storage/           # Storage platforms (4)
│
├── bridges/                # Messaging bridges
│   ├── base.py            # Bridge manager + ABC
│   ├── telegram_bridge.py # Telegram bridge
│   ├── slack_bridge.py    # Slack bridge
│   └── discord_bridge.py  # Discord bridge
│
├── security/               # Security infrastructure
│   ├── store.py           # Encrypted credential store
│   ├── sandbox.py         # Docker code execution sandbox
│   └── workspace_sandbox.py # Workspace isolation
│
└── plugins/                # Plugin system
    └── __init__.py        # EventBus, PluginBase, 8 hooks
```

## Component Deep-Dive

### User Interface Layer

Three entry points, all converging on the same core:

**CLI (REPL):** Interactive terminal interface. `repl.py` manages the input loop, `commands.py` handles slash commands. Natural language input is forwarded to the Router.

**REST API (FastAPI):** `server.py` exposes HTTP/WebSocket endpoints. Routes are organized into modules under `api/routes/`. Middleware provides CORS, rate limiting, and optional authentication.

**Web Frontend (Next.js):** React-based UI in `orion-web/`. Communicates via WebSocket for chat and REST for settings/configuration.

### Request Router (Scout)

The Router (`router.py`) is the central orchestrator:

1. Receives a request from any interface
2. Classifies complexity and risk
3. Routes to the appropriate execution path
4. Returns the result to the caller

**Routing decision matrix:**

| Complexity | Risk | Route |
|-----------|------|-------|
| Low | Low | FastPath |
| Low | High | FastPath + AEGIS escalation |
| High | Low | Table of Three |
| High | High | Table of Three + human approval |

### LLM Layer

All LLM calls go through `call_provider()` in `providers.py`:

```python
async def call_provider(
    provider: str,
    model: str,
    messages: List[Dict],
    temperature: float = 0.3,
    max_tokens: int = 4096,
    stream: bool = False
) -> Union[str, AsyncIterator[str]]:
```

This function:
- Routes to the correct provider SDK
- Handles retries and timeouts
- Normalizes response formats
- Supports streaming for real-time output

**Supported providers:** OpenAI, Anthropic, Google, Ollama, Groq, Mistral, Cohere, Together, Perplexity, Fireworks, DeepSeek

### AEGIS Governance

AEGIS (`aegis.py`) is a pure-function security gate. See [AEGIS documentation](AEGIS.md) for the full specification.

Key architectural decision: AEGIS has **no state** and **no side effects**. Every validation is an independent function call. This makes it impossible for agents to accumulate permissions or bypass checks.

### Memory System

Three-tier architecture. See [Memory System](MEMORY_SYSTEM.md) for details.

**Data flow:**
```
Request -> recall_for_prompt() -> relevant patterns injected into LLM prompt
Response -> user rating -> pattern extraction -> store in Tier 2
Tier 2 pattern (high confidence) -> auto-promote -> Tier 3
```

### Edit Validation

Before any file modification:

1. **Syntax validation** -- AST parsing for Python, bracket balancing
2. **Content sanity** -- Checks for LLM artifacts, placeholders
3. **Confidence scoring** -- Composite score (0.0 - 1.0)
4. **Auto-recovery** -- Fixes common issues (markdown fences, indentation)

Files with confidence below threshold require human confirmation.

### Plugin System

8 lifecycle hooks for extending Orion:

| Hook | Trigger |
|------|---------|
| `on_request` | New user request received |
| `on_route` | Router makes routing decision |
| `on_build` | Builder generates solution |
| `on_review` | Reviewer completes critique |
| `on_govern` | Governor makes decision |
| `on_execute` | Action is executed |
| `on_feedback` | User provides rating |
| `on_error` | Error occurs |

Plugins are discovered via manifest files and loaded by `PluginLoader`.

## Data Flow

### Complete Request Lifecycle

```
1. User Input (CLI/API/Web)
       │
2. Command Parser
       │ (slash command or natural language)
       │
3. Router (Scout)
       │ (classify -> route)
       │
4. Agent Execution
       │ (FastPath or Table of Three)
       │
5. AEGIS Validation
       │ (all proposed actions validated)
       │
6. User Approval (pro mode)
       │
7. File System / Command Execution
       │
8. Memory Recording
       │ (outcome stored, patterns extracted)
       │
9. Response to User
```

### WebSocket Chat Flow

```
Client                    Server
  │                         │
  ├── connect ──────────────>│
  │                         │
  ├── message ──────────────>│
  │                         │ (route to agent)
  │<──────── routing_info ──┤
  │                         │ (agent processing)
  │<──────── stream_chunk ──┤
  │<──────── stream_chunk ──┤
  │<──────── stream_chunk ──┤
  │                         │ (complete)
  │<──────── complete ──────┤
  │                         │
```

## Digital Agent Architecture (Phase 2 + Phase 3)

The Digital Agent Architecture governs how Orion operates autonomously inside a Docker sandbox with network-level security enforcement.

### Execution Model

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

**Key property:** All trusted components (config, proxy, DNS, approval, orchestrator) run on the host. The container is untrusted -- it can only reach the internet through the egress proxy.

### Boot Sequence

The SandboxOrchestrator executes a 6-step governed boot:

1. **AEGIS Config** -- Read and validate governance rules (host)
2. **Docker Build** -- Verify Docker daemon, build images (host)
3. **Egress Proxy** -- Start HTTP proxy with domain whitelist (host)
4. **Approval Queue** -- Start human gate for write operations (host)
5. **DNS Filter** -- Start UDP DNS proxy (host)
6. **Container Launch** -- Start Orion in governed container (sandbox)

Teardown is reverse-order. If any step fails, all previous steps are rolled back.

### Network Flow

```
Container App ──HTTP──> Egress Proxy ──check whitelist──> Internet
                             │
                        Content Inspector
                        (credential patterns)
                             │
                        Rate Limiter
                        (per-domain RPM)
                             │
                        Audit Logger
                        (JSONL on host)

Container DNS ──UDP──> DNS Filter ──check whitelist──> Upstream DNS
                             │
                        Non-whitelisted = NXDOMAIN
```

### Docker Network Topology

```
┌─────────────────────────────────────────┐
│             orion-egress                │
│  ┌─────────────┐   ┌────────────────┐  │
│  │ Egress Proxy│   │  DNS Filter    │  │
│  └──────┬──────┘   └───────┬────────┘  │
│         │                  │            │
│  ┌──────┴──────────────────┴─────────┐  │
│  │         orion-internal            │  │
│  │  ┌───────────────────────────┐    │  │
│  │  │    Orion Container        │    │  │
│  │  │  (no direct internet)     │    │  │
│  │  └───────────────────────────┘    │  │
│  └───────────────────────────────────┘  │
└─────────────────────────────────────────┘
```

## Security Architecture

Defense in depth with 7 layers:

| Layer | Component | Protection |
|-------|-----------|------------|
| 1 | AEGIS Configuration | Governance rules on host, read-only mount |
| 2 | Docker Network Isolation | Kernel namespaces, no direct internet |
| 3 | Egress Proxy | Domain whitelist, content inspection, credential leak detection |
| 4 | Filesystem Isolation | Docker volumes, read-only config mounts |
| 5 | Approval Queue | Host-side human gate for write operations |
| 6 | Credential Isolation | Access token only, no refresh token in container |
| 7 | Orion Self-Governance | Software-level AEGIS checks (least trusted layer) |

## Technology Stack

| Component | Technology |
|-----------|-----------|
| Language | Python 3.10+ |
| CLI | Custom REPL |
| API Server | FastAPI + Uvicorn |
| Web Frontend | Next.js 14 + React |
| Database | SQLite (memory), JSON (project) |
| Code Analysis | tree-sitter |
| Sandboxing | Docker |
| Testing | pytest |
| Linting | Ruff |
| CI/CD | GitHub Actions |

## Source Files Reference

| Category | Key Files |
|----------|-----------|
| Entry points | `cli/repl.py`, `api/server.py` |
| Routing | `core/router.py`, `core/fast_path.py` |
| Agents | `core/agents/builder.py`, `reviewer.py`, `governor.py`, `table.py` |
| Security | `core/governance/aegis.py`, `security/store.py` |
| Memory | `core/memory_engine.py` |
| Learning | `core/evolution_engine.py` |
| LLM | `core/llm/providers.py` |
| Editing | `core/editing/edit_validator.py` |

---

**Next:** [Agents](AGENTS.md) | [AEGIS](AEGIS.md) | [Memory System](MEMORY_SYSTEM.md)
