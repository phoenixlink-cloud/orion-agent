# Getting Started with Orion

## Quick Install

```bash
pip install orion-agent
```

Or with all optional dependencies:

```bash
pip install orion-agent[all]
```

## First Run

```bash
orion
```

This starts the interactive REPL. Set a workspace and start coding:

```
/workspace /path/to/your/project
hello orion, what does this codebase do?
```

## Configuration

Copy `.env.example` to `.env` and add your API keys:

```bash
cp .env.example .env
```

At minimum, you need one LLM provider. For free/local:
- Install [Ollama](https://ollama.ai) -- no API key needed

For cloud:
- `OPENAI_API_KEY` for GPT-4o
- `ANTHROPIC_API_KEY` for Claude

## Modes

| Mode | Description |
|------|-------------|
| `safe` | Read-only analysis and conversation (default) |
| `pro` | File editing enabled with approval gates |
| `project` | Full autonomy including command execution |

Switch modes: `/mode pro`

## Key Commands

| Command | Description |
|---------|-------------|
| `/workspace <path>` | Set project directory |
| `/mode <safe\|pro\|project>` | Switch governance mode |
| `/doctor` | Run system diagnostics |
| `/health` | Check integration health |
| `/undo` | Revert last edit |
| `/quit` | Exit |
