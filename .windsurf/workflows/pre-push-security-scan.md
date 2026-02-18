---
description: Security scan before any git push to GitHub — checks for personal data, secrets, and local paths
---

# Pre-Push Security Scan

**Run this workflow EVERY TIME before pushing code to GitHub.** This prevents accidental exposure of personal data, secrets, API keys, or local machine paths.

## Steps

1. **Scan for API keys and tokens** in all staged/committed files:
   ```
   git grep -iE "ghp_[a-zA-Z0-9]{10,}|sk-[a-zA-Z0-9]{20,}|AKIA[0-9A-Z]{16}|AIza[0-9A-Za-z_-]{35}|xox[bps]-[a-zA-Z0-9-]+" HEAD
   ```
   - If any matches are found (outside of test fixture files with obviously fake values), **STOP and remove them before pushing**.

2. **Scan for local machine paths** that reveal personal directory structure:
   ```
   git grep -iE "D:\\\\|C:\\\\Users\\\\|/home/[a-z]{2,}[^/]|/Users/[a-z]" HEAD -- "*.py" "*.ts" "*.tsx" "*.md" "*.json" "*.yaml" "*.yml" "*.toml"
   ```
   - **Allowed:** Generic examples like `/home/user/project`, `/home/orion`, Docker paths
   - **Not allowed:** Real local paths like `D:\multi_agent_cli\...`, `C:\Users\JohnDoe\...`, `/home/actualusername/...`
   - If real local paths are found, **STOP and replace with generic paths before pushing**.

3. **Scan for personal information** (non-company emails, names, phone numbers, IPs):
   ```
   git grep -iE "[a-z0-9._%+-]+@(gmail|yahoo|hotmail|outlook|proton)\.[a-z]{2,}" HEAD
   git grep -E "\b[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\b" HEAD -- "*.py" "*.ts" "*.tsx" "*.md"
   ```
   - **Allowed:** Company emails (`@phoenixlink.co.za`), example IPs (`192.168.x.x`, `127.0.0.1`), localhost
   - **Not allowed:** Personal email addresses, real public IP addresses
   - If found, **STOP and remove before pushing**.

4. **Scan for passwords and connection strings**:
   ```
   git grep -iE "password\s*=\s*['\"][^'\"]{4,}['\"]|postgres://[^:]+:[^@]+@|mongodb\+srv://[^:]+:[^@]+@" HEAD
   ```
   - **Allowed:** Obviously fake test values (e.g., `password="test123"` in test files)
   - **Not allowed:** Real credentials
   - If found, **STOP and remove before pushing**.

5. **Verify .gitignore coverage** — confirm these are gitignored:
   - `.local/` (internal docs, audits, planning)
   - `.env`, `.env.local`, `.env.production`
   - `secrets.json`, `credentials.json`
   - `*.db`, `*.sqlite`

6. If all scans pass, proceed with the push.

## Important Notes

- This scan must run against `HEAD` (committed content), not just the working directory
- Test files with **obviously fake** values (e.g., `ghp_ABCDEFGHIJ...`, `T00000000/B00000000`) are acceptable
- When in doubt, ask the user before pushing
- GitHub Push Protection will also block known secret patterns, but this workflow catches things GitHub doesn't (local paths, personal info)
