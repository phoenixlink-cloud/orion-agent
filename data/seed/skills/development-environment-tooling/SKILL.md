---
name: development-environment-tooling
description: "Setting up and maintaining an effective development environment with modern tooling"
version: "1.0.0"
author: "Phoenix Link"
tags:
  - development
  - coding
  - junior-developer
  - tooling
  - environment
---

# Development Environment & Tooling

The ability to set up, configure, and maintain a productive development environment.
Covers IDE configuration, version managers, package managers, linters, formatters,
terminal workflows, and local development best practices.

STEP-BY-STEP PROCEDURE

STEP 1: SET UP YOUR IDE / EDITOR
  Your editor is your primary tool — invest time in learning it:

  Essential configuration:
  - Install language-specific extensions (Python, TypeScript, Rust, etc.)
  - Enable format-on-save with the project's formatter
  - Enable lint-on-save with the project's linter
  - Configure the integrated terminal
  - Set up keyboard shortcuts for: go-to-definition, find references,
    rename symbol, run tests, toggle terminal
  - Enable auto-import and import organisation
  - Use workspace settings (.vscode/settings.json or equivalent) so
    the whole team has consistent configuration

  Productivity features to learn:
  - Multi-cursor editing: Edit multiple lines simultaneously
  - Code snippets: Common patterns with a few keystrokes
  - Integrated debugger: Breakpoints, step-through, watch variables
  - Source control panel: Stage, commit, diff, blame inline
  - Search: Project-wide search with regex and file filters
  - Refactoring tools: Rename, extract method, extract variable

STEP 2: MANAGE LANGUAGE VERSIONS
  Never rely on the OS-installed language version:
  - Python: Use pyenv (Unix) or pyenv-win (Windows) to manage versions
  - Node.js: Use nvm (Unix) or nvm-windows, or fnm (cross-platform)
  - Ruby: Use rbenv or rvm
  - Java: Use SDKMAN or jenv
  - Rust: Use rustup (built-in version management)
  - Go: Use goenv or download from golang.org

  Best practices:
  - Pin the language version in the project (.python-version, .nvmrc,
    .tool-versions, rust-toolchain.toml)
  - Match the version used in CI/CD and production
  - Update regularly but test thoroughly after upgrading

STEP 3: USE PACKAGE MANAGERS EFFECTIVELY
  Every language has a package manager — learn yours deeply:

  Python: pip + venv (standard), or Poetry, or uv
  - Always use a virtual environment (python -m venv .venv)
  - Pin exact versions in requirements.txt or pyproject.toml
  - Use a lock file (poetry.lock, uv.lock) for reproducible builds

  Node.js: npm, yarn, or pnpm
  - Use a lock file (package-lock.json, yarn.lock, pnpm-lock.yaml)
  - Prefer exact versions or ~ (patch updates only)
  - Run npm audit / yarn audit regularly for security

  General rules:
  - Never commit node_modules, .venv, or equivalent to version control
  - Document setup in the README: "Run X to install dependencies"
  - Keep dependencies up to date; use Dependabot or Renovate

STEP 4: CONFIGURE LINTING & FORMATTING
  Automate code quality enforcement:
  - Linter catches bugs and style issues BEFORE they reach code review
  - Formatter enforces consistent style AUTOMATICALLY

  Setup checklist:
  1. Install the linter and formatter for your language
  2. Add a config file to the project root (.eslintrc, pyproject.toml,
     .rustfmt.toml, etc.)
  3. Configure your IDE to run both on save
  4. Add both to CI — the build should fail on lint errors
  5. Add a pre-commit hook to run linter + formatter before every commit

  Pre-commit hooks (using pre-commit or husky):
  - Run linter and formatter on staged files
  - Run type checker if applicable
  - Prevent commits with failing tests (optional, can be slow)

STEP 5: LOCAL DEVELOPMENT WORKFLOW
  Establish a smooth daily workflow:

  Starting work:
  1. Pull latest changes from the main branch
  2. Create a feature branch from main (feature/description or JIRA-123)
  3. Set up / activate the virtual environment
  4. Install any new dependencies
  5. Run the test suite to confirm a clean baseline

  During development:
  - Save frequently — auto-format and lint will run
  - Run related tests after each meaningful change
  - Commit often in small, logical increments
  - Push to remote regularly as a backup

  Before opening a PR:
  - Rebase/merge latest main
  - Run the full test suite
  - Run the linter and formatter
  - Self-review the diff

STEP 6: TERMINAL & SHELL PRODUCTIVITY
  The terminal is faster than the GUI for many tasks:
  - Learn 10-15 essential commands for your OS and shell
  - Use aliases for commands you run frequently
  - Use a modern terminal: Windows Terminal, iTerm2, Warp, Alacritty
  - Use shell history search (Ctrl+R) to recall previous commands
  - Use tab completion for file paths and commands
  - Learn to pipe commands together for quick data processing

TOOLS & RESOURCES
- IDEs: VS Code (free, extensible), JetBrains (PyCharm, WebStorm, IntelliJ)
- Version managers: pyenv, nvm, rustup, SDKMAN
- Package managers: pip/uv, npm/pnpm, cargo, go modules
- Pre-commit: pre-commit (Python) or husky + lint-staged (Node.js)
- Containerisation: Docker for consistent dev environments
- Dotfiles: Maintain a personal dotfiles repo for shell config

QUALITY STANDARDS
- Development environment can be set up from scratch in < 30 minutes
- IDE configured with format-on-save and lint-on-save
- Language version pinned and matching CI/production
- All dependencies locked with exact versions
- Pre-commit hooks enforce linting and formatting
- README contains complete setup instructions
- No "works on my machine" issues — environment is reproducible
