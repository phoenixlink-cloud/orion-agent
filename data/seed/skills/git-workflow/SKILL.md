---
name: git-workflow
description: "Branch strategy, commit conventions, and PR best practices"
version: "1.0.0"
author: "Orion"
tags: ["general", "git", "workflow"]
source: "bundled"
trust_level: "verified"
---

## Git Workflow

### 1. Branch Strategy
- `main` — production-ready code, always stable
- `develop` — integration branch for features (if used)
- `feature/<name>` — one branch per feature or task
- `fix/<name>` — bug fix branches
- `release/<version>` — release preparation

### 2. Commit Conventions
Use conventional commits:
```
<type>(<scope>): <short description>

<body — optional, explains WHY>

<footer — optional, references issues>
```

Types: `feat`, `fix`, `docs`, `style`, `refactor`, `test`, `chore`, `perf`, `ci`

Examples:
- `feat(auth): add OAuth2 login flow`
- `fix(api): handle null response from payment provider`
- `docs(readme): add deployment instructions`

### 3. Branch Workflow
1. Create branch from `main`: `git checkout -b feature/<name>`
2. Make small, focused commits
3. Push and create PR when ready
4. Request review from at least one team member
5. Squash merge to main after approval
6. Delete the feature branch

### 4. PR Best Practices
- Title matches the conventional commit format
- Description explains WHAT changed and WHY
- Link related issues
- Keep PRs small (<400 lines changed)
- Include screenshots for UI changes
- Ensure CI passes before requesting review
