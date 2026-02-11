# Getting Started with Orion Agent

Get Orion running in 5 minutes.

## Prerequisites

- **Python 3.10 or higher**
- **Git** (for workspace safety features)
- **An LLM API key** (OpenAI, Anthropic, or use free Ollama)

## Step 1: Install Orion

### Option A: pip (Recommended)
```bash
pip install orion-agent
```

### Option B: pip with all integrations
```bash
pip install orion-agent[all]
```

### Option C: From source
```bash
git clone https://github.com/phoenixlink-cloud/orion-agent.git
cd orion-agent
pip install -e ".[dev]"
```

## Step 2: Configure Your LLM

### Option A: OpenAI (Recommended for beginners)
```bash
export OPENAI_API_KEY="sk-your-key-here"
```

### Option B: Anthropic
```bash
export ANTHROPIC_API_KEY="sk-ant-your-key-here"
```

### Option C: Ollama (Free, local)
```bash
# Install Ollama from https://ollama.ai
ollama pull llama3
```

## Step 3: Start Orion
```bash
orion
```

You should see:
```
Orion Agent v7.1.0
Governed AI Coding Assistant

Type /help for commands
Type /quit to exit

>
```

## Step 4: Set Your Workspace

Tell Orion which project to work on:
```
> /workspace /path/to/your/project
Workspace set: /path/to/your/project
```

## Step 5: Choose a Mode

Orion has three governance modes:

| Mode | Can Read | Can Edit | Can Run Commands |
|------|----------|----------|------------------|
| `safe` | Yes | No | No |
| `pro` | Yes | Yes (with approval) | No |
| `project` | Yes | Yes | Yes (allowlisted) |

Start with `pro` mode:
```
> /mode pro
Mode set: pro
```

## Step 6: Try It Out

### Ask a question
```
> What does the main function in app.py do?
```

Orion will analyze your code and explain it.

### Request a change
```
> Add input validation to the login function
```

Orion will:
1. Analyze the current code
2. Propose specific changes
3. Show you a diff
4. Wait for your approval

### Approve or reject
```
Apply these changes? [y/n/e(dit)]: y
Changes applied to src/auth/login.py
```

## Step 7: Explore Commands

Type `/help` to see all commands:
```
> /help

Available Commands:
  /workspace <path>  Set project directory
  /mode <mode>       Set governance mode (safe|pro|project)
  /settings          Manage configuration
  /doctor            Run diagnostics
  /memory            View memory status
  /map               Show repository structure
  /undo              Revert last change
  /help              Show this help
  /quit              Exit Orion
```

## What's Next?

- **[User Guide](USER_GUIDE.md)** -- Complete usage documentation
- **[CLI Reference](CLI_REFERENCE.md)** -- All commands explained
- **[AEGIS](AEGIS.md)** -- Understand the governance system
- **[Configuration](CONFIGURATION.md)** -- Advanced configuration options

## Troubleshooting

### "No API key found"

Set your API key as an environment variable:
```bash
export OPENAI_API_KEY="sk-your-key"
```

Or configure it in Orion:
```
> /settings key openai sk-your-key
```

### "Workspace not set"

You must set a workspace before Orion can read or modify files:
```
> /workspace /path/to/project
```

### "Permission denied"

Switch to a mode that allows the operation:
```
> /mode pro       # For file editing
> /mode project   # For command execution
```

### More Issues?

See [Troubleshooting](TROUBLESHOOTING.md) for common problems and solutions.

---

**Next:** [User Guide](USER_GUIDE.md) | [CLI Reference](CLI_REFERENCE.md)
