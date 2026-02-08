# Contributing to Orion

## Development Setup

```bash
git clone https://github.com/orion-agent/orion.git
cd orion-agent
python -m venv .venv
.venv\Scripts\activate  # Windows
pip install -e ".[dev]"
```

## Running Tests

```bash
pytest                          # All tests
pytest tests/unit               # Unit tests only
pytest -m "not slow"            # Skip slow tests
pytest --cov=src/orion          # With coverage
```

## Code Style

We use `ruff` for linting:

```bash
ruff check src/ tests/
ruff format src/ tests/
```

## Project Structure

```
src/orion/
├── cli/           # CLI interface
├── core/          # Engine modules
│   ├── agents/    # Builder, Reviewer, Governor
│   ├── memory/    # Three-tier memory system
│   ├── learning/  # Evolution engine
│   ├── editing/   # Edit validation pipeline
│   ├── context/   # Repo map, AST analysis
│   ├── governance/# AEGIS safety gate
│   ├── llm/       # LLM provider routing
│   └── production/# Health, metrics, shutdown
├── integrations/  # 79 connectors
├── api/           # REST + WebSocket server
├── security/      # Credential store, sandbox
└── plugins/       # Plugin lifecycle API
```

## Pull Request Process

1. Create a feature branch from `main`
2. Write tests for new functionality
3. Ensure all tests pass: `pytest`
4. Ensure code style: `ruff check`
5. Update CHANGELOG.md
6. Submit PR with clear description
