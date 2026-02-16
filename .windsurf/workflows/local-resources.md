---
description: How to handle debug scripts, audit tools, and one-off utility files
---

# Local Resources Convention

All debug scripts, audit tools, training utilities, and one-off helper files should be placed in the `.local/` directory at the project root.

## Rules

1. **Never create debug/audit/utility scripts in the project root.** Always place them in `.local/`.
2. `.local/` is in `.gitignore` — files here will never be committed or pushed to GitHub.
3. This keeps them available for future use without cluttering the repo or branches.

## Examples of files that belong in `.local/`

- `e2e_audit.py` — end-to-end audit scripts
- `check_training_db.py` — database inspection utilities
- `verify_flows.py` — flow verification scripts
- `train_*.py` — training/fine-tuning scripts
- `diagnose_*.py` — diagnostic tools
- `WINDSURF_TEST_REPORT.md` — test reports from Cascade sessions

## Usage

```bash
# Run a local resource script
python .local/e2e_audit.py

# Create a new debug script
# Always put it in .local/, e.g.:
#   .local/my_debug_script.py
```

## When creating new utility files

Before writing any one-off script to the project root, ask yourself:
- Is this a permanent part of the codebase? → Put it in `src/` or `tests/`
- Is this a temporary/debug/audit tool? → Put it in `.local/`
