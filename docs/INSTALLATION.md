# Installation Guide

Detailed instructions for installing Orion Agent on all supported platforms.

## Requirements

- **Python 3.10 or higher** (3.11+ recommended)
- **pip** (included with Python)
- **Git** (for workspace safety features and version control)
- **An LLM provider** (API key or local Ollama installation)

### Optional Requirements

- **Docker** -- For sandboxed code execution
- **Node.js 18+** -- For the Web UI
- **tree-sitter** -- For advanced code analysis (installed automatically)

## Quick Install

```bash
pip install orion-agent
```

## Installation Methods

### Method 1: pip (Recommended)

```bash
# Basic installation
pip install orion-agent

# With all integrations (voice, image, messaging, etc.)
pip install orion-agent[all]

# Specific integration groups
pip install orion-agent[voice]      # Voice TTS/STT providers
pip install orion-agent[image]      # Image generation providers
pip install orion-agent[messaging]  # Messaging connectors
pip install orion-agent[dev]        # Development dependencies
```

### Method 2: From Source (Development)

```bash
# Clone the repository
git clone https://github.com/phoenixlink-cloud/orion-agent.git
cd orion-agent

# Create virtual environment
python -m venv .venv

# Activate virtual environment
# Windows:
.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate

# Install in development mode
pip install -e ".[dev]"

# Verify installation
orion --version
pytest
```

### Method 3: Docker

```bash
# Pull the image
docker pull ghcr.io/phoenix-link/orion-agent:latest

# Run with API keys
docker run -it \
  -e OPENAI_API_KEY=sk-your-key \
  -v $(pwd):/workspace \
  ghcr.io/phoenix-link/orion-agent:latest

# Or use docker-compose
docker-compose up -d
```

## Platform-Specific Notes

### Windows

```powershell
# Install Python from python.org or Microsoft Store
# Ensure "Add Python to PATH" is checked during installation

# Create and activate virtual environment
python -m venv .venv
.venv\Scripts\activate

# Install Orion
pip install orion-agent
```

**Known Windows issues:**
- Use `python` instead of `python3`
- Some voice providers require Visual C++ Build Tools
- Use PowerShell or Windows Terminal (not cmd.exe) for best experience

### macOS

```bash
# Install Python via Homebrew
brew install python@3.11

# Install Orion
pip3 install orion-agent
```

### Linux

```bash
# Debian/Ubuntu
sudo apt update
sudo apt install python3.11 python3.11-venv python3-pip git

# Install Orion
pip3 install orion-agent
```

## LLM Provider Setup

You need at least one LLM provider configured.

### Option A: OpenAI (Recommended for beginners)

1. Get an API key from [platform.openai.com](https://platform.openai.com)
2. Set the environment variable:
```bash
# Linux/macOS
export OPENAI_API_KEY="sk-your-key-here"

# Windows PowerShell
$env:OPENAI_API_KEY="sk-your-key-here"

# Or set it permanently in your shell profile
```

3. Or configure within Orion:
```
> /settings key openai sk-your-key-here
```

### Option B: Anthropic

```bash
export ANTHROPIC_API_KEY="sk-ant-your-key-here"
```

### Option C: Ollama (Free, Local)

No API key needed -- runs entirely on your machine.

```bash
# Install Ollama from https://ollama.ai
# Pull a model
ollama pull llama3

# Configure Orion to use Ollama
> /settings provider ollama
> /settings model llama3
```

### Option D: Other Providers

Orion supports 11 LLM providers. See [Configuration](CONFIGURATION.md#llm-providers) for the full list.

## Verifying Installation

```bash
# Check version
orion --version

# Run diagnostics
orion
> /doctor
```

The `/doctor` command runs 15 diagnostic checks and reports any issues.

## Upgrading

```bash
# Upgrade to latest version
pip install --upgrade orion-agent

# Upgrade from source
cd orion-agent
git pull
pip install -e ".[dev]"
```

## Uninstalling

```bash
pip uninstall orion-agent
```

To also remove configuration and memory:
```bash
# Remove Orion config directory
# Linux/macOS
rm -rf ~/.orion

# Windows
rmdir /s %USERPROFILE%\.orion
```

## Troubleshooting Installation

### "pip: command not found"

Python's pip may not be in your PATH:
```bash
python -m pip install orion-agent
```

### "Permission denied"

Use a virtual environment instead of system Python:
```bash
python -m venv .venv
source .venv/bin/activate  # or .venv\Scripts\activate on Windows
pip install orion-agent
```

### "No matching distribution found"

Ensure you have Python 3.10+:
```bash
python --version
```

### Build errors on Windows

Some dependencies require build tools:
```powershell
# Install Visual C++ Build Tools
winget install Microsoft.VisualStudio.2022.BuildTools
```

See [Troubleshooting](TROUBLESHOOTING.md) for more solutions.

---

**Next:** [Getting Started](GETTING_STARTED.md) | [Configuration](CONFIGURATION.md)
