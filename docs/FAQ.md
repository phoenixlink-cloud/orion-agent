# Frequently Asked Questions

## General

### What is Orion Agent?

Orion is an open-source, multi-agent AI coding assistant. It uses three specialized agents (Builder, Reviewer, Governor) to generate, review, and govern code changes. Unlike single-shot AI tools, Orion has persistent memory and learns from your feedback over time.

### What makes Orion different from other AI coding tools?

Key differentiators:
- **Multi-agent deliberation** -- Three agents collaborate instead of one
- **Persistent memory** -- Learns across sessions, projects, and time
- **AEGIS governance** -- Hardened security gate prevents unsafe operations
- **11 LLM providers** -- Use any provider, including local Ollama
- **Self-hosted** -- Runs entirely on your machine

### Is Orion free?

Yes. Orion is released under AGPL-3.0 and is free to use, modify, and distribute under those terms. You still need to pay for LLM API usage (OpenAI, Anthropic, etc.) unless you use Ollama (free, local).

### Do I need an API key?

You need at least one LLM provider. Options:
- **Paid:** OpenAI, Anthropic, Google, Groq, Mistral, etc.
- **Free (local):** Ollama -- no API key, runs on your hardware

### What languages does Orion support?

Orion can work with any programming language. It has enhanced support for:
- **Python** -- AST analysis, syntax validation, import checking
- **JavaScript/TypeScript** -- tree-sitter parsing
- **Other languages** -- General code analysis and generation

## Security

### Is my code sent to external servers?

Your code is sent to the LLM provider you choose (OpenAI, Anthropic, etc.) for processing. If you want complete privacy, use Ollama -- everything stays on your machine.

Orion itself does not collect, transmit, or store any telemetry.

### Can Orion delete my files?

Only if:
1. You are in `pro` or `project` mode
2. AEGIS validates the operation
3. You approve the change (in `pro` mode)

In `safe` mode, Orion cannot modify or delete any files.

### Can Orion execute arbitrary commands?

Only in `project` mode, and only allowlisted commands. AEGIS blocks dangerous patterns like `rm -rf`, shell injection, and pipe chains.

### What is AEGIS?

AEGIS (Autonomous Execution Governance and Integrity System) is Orion's security core. It validates every operation against six invariants: workspace confinement, mode enforcement, action scope, risk validation, command execution safety, and external access control.

See [AEGIS documentation](AEGIS.md) for full details.

### Can I disable AEGIS?

No. AEGIS cannot be disabled, bypassed, or reconfigured by AI agents or users. This is by design.

## Usage

### How do I set up my workspace?

```
> /workspace /path/to/your/project
```

### What modes are available?

| Mode | Can Read | Can Write | Can Execute |
|------|----------|-----------|-------------|
| `safe` | Yes | No | No |
| `pro` | Yes | Yes (approval) | No |
| `project` | Yes | Yes | Yes (allowlist) |

### How do I switch LLM providers?

```
> /settings provider openai
> /settings model gpt-4o
```

### Can I use different models for different agents?

Yes. Configure per-agent models in `~/.orion/config.yaml`:
```yaml
agents:
  builder:
    provider: openai
    model: gpt-4o
  reviewer:
    provider: anthropic
    model: claude-3-5-sonnet-20241022
```

### How do I undo a change?

```
> /undo
```

Orion creates git savepoints before changes, so you can always revert.

### How does the rating system work?

After Orion completes a task, you can rate it 1-5:
- **5** -- Excellent, exactly what I needed
- **4** -- Good, minor adjustments needed
- **3** -- Acceptable, could be better
- **2** -- Poor, significant issues
- **1** -- Bad, completely wrong

Ratings drive the learning system -- high ratings become success patterns, low ratings become anti-patterns.

## Memory

### What does Orion remember?

Three tiers of memory:
- **Session** -- Current conversation (RAM, lost on exit)
- **Project** -- Workspace-specific patterns (JSON, days to weeks)
- **Institutional** -- Cross-project wisdom (SQLite, months to years)

### Where is memory stored?

- Project memory: `.orion/memory/` in each workspace
- Institutional memory: `~/.orion/institutional.db`

### Can I clear memory?

Yes:
```
> /memory clear session        # Clear current session
> /memory clear project        # Clear project patterns
> /memory clear institutional  # Clear all learned patterns
```

### Is memory shared between projects?

- Session memory: No (current conversation only)
- Project memory: No (per-workspace)
- Institutional memory: Yes (shared across all projects)

## Web UI

### How do I start the Web UI?

1. Start the API server: `uvicorn orion.api.server:app --port 8001`
2. Start the web frontend: `cd orion-web && npm run dev`
3. Open `http://localhost:3001`

### The Web UI says "Not connected"

Ensure the API server is running and the port matches the `.env.local` configuration. See [Troubleshooting](TROUBLESHOOTING.md#connection-issues).

## Licensing

### Can I use Orion in a commercial product?

Under AGPL-3.0, you must share your modifications. For proprietary use without AGPL obligations, contact info@phoenixlink.co.za for a commercial license.

### Can I use Orion as a SaaS?

AGPL-3.0 requires that users of your SaaS have access to the source code. For SaaS without this requirement, you need a commercial license.

### Do I need to sign a CLA to contribute?

Yes. All contributions require a signed Contributor License Agreement. See [CLA.md](../CLA.md).

## Performance

### Why is Orion slow?

Common causes:
- **LLM latency** -- Cloud providers add network latency. Try Ollama for local inference.
- **Table of Three** -- Multi-agent deliberation takes 3x a single call. Disable with `enable_table_of_three: false` for speed.
- **Large codebase** -- Repository mapping takes time on large projects.

### How can I speed things up?

1. Use a faster model (GPT-3.5-turbo, Groq's Llama 3)
2. Disable Table of Three for simple tasks
3. Use Ollama for zero network latency
4. Reduce `max_tokens`

## Contributing

### How do I contribute?

See [CONTRIBUTING.md](../CONTRIBUTING.md). Key steps:
1. Fork the repository
2. Sign the CLA
3. Create a feature branch
4. Submit a pull request

### Where do I report bugs?

[GitHub Issues](https://github.com/phoenixlink-cloud/orion-agent/issues)

### Where do I report security issues?

**Do not use GitHub Issues for security vulnerabilities.**

Email: info@phoenixlink.co.za

---

**Next:** [Troubleshooting](TROUBLESHOOTING.md) | [Getting Started](GETTING_STARTED.md)
