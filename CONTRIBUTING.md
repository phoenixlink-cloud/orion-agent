# Contributing to Orion Agent

Thank you for your interest in contributing to Orion!

## Before You Contribute

### Step 1: Sign the Contributor License Agreement (CLA)

All contributors must sign a CLA before any code can be merged. **No exceptions.**

**Why?** Orion uses dual licensing (AGPL-3.0 + commercial). The CLA grants Phoenix Link the rights needed to offer both licenses while you retain rights to your original work.

**To sign the CLA:**

1. Email **info@phoenixlink.co.za** with:
   - Your GitHub username
   - Your full legal name
   - Brief description of your intended contribution (optional)
2. We'll send the CLA document within 48 hours
3. Sign electronically and return
4. We'll confirm your GitHub username is approved
5. You're cleared to contribute!

**For corporate contributions** (work done as part of your employment): A Corporate CLA is required. Your employer must sign. Contact info@phoenixlink.co.za.

See [CLA.md](./CLA.md) for the full agreement text.

---

## Understanding Your Rights as a Contributor

### What You Keep

When you contribute to Orion, **you retain full copyright ownership of your original work**. This means:

| Your Right | Explanation |
|------------|-------------|
| **Use in other projects** | Your code remains yours. Use it anywhere you want. |
| **License to others** | You can license your original code to anyone under any terms. |
| **Commercial use** | You can sell, license, or commercialize your original code independently. |
| **Attribution** | You'll be credited in the contributors list (if desired). |

### What You Grant Phoenix Link

The CLA grants Phoenix Link a license to:
- Include your contribution in Orion (open source and commercial versions)
- Sublicense your contribution as part of Orion
- Modify and create derivative works of your contribution within Orion

### What This Means in Practice

**Example 1: You build a "Redis caching" module for Orion**
- You can use that same caching code in your own unrelated projects
- You can sell that caching module to other companies for their projects
- Phoenix Link can include it in commercial Orion licenses
- You cannot sell "Orion + your module" commercially (that's Orion's commercial license territory)

**Example 2: You fix a bug in Orion's memory engine**
- You can reference/discuss your fix publicly
- You retain authorship credit
- Phoenix Link can include the fix in commercial licenses
- The fix is now part of Orion's codebase, governed by Orion's dual license

**Example 3: You want to fork Orion and sell it**
- You can fork under AGPL-3.0 (must keep it open source)
- You cannot sell a proprietary fork (that requires Phoenix Link's commercial license)
- If you want to build a commercial product on Orion, talk to us about partnership

---

## Partnership & Commercial Opportunities

We believe contributors who add significant value should benefit. Phoenix Link offers several paths:

### Bounty Program

For specific features on our roadmap, we may offer bounties. Check [GitHub Issues](https://github.com/phoenixlink-cloud/orion-agent/labels/bounty) for bounty-tagged issues.

### Revenue Sharing

For major features that drive commercial sales, we're open to revenue-sharing arrangements. Contact **info@phoenixlink.co.za** to discuss:
- Significant new integrations (new LLM providers, enterprise connectors)
- Major subsystems (new agent types, specialized workflows)
- Industry-specific adaptations

### Contractor Relationships

Proven contributors may be invited to paid contract work on:
- Priority features for enterprise customers
- Custom integrations
- Support and maintenance

### Acquisition of External Projects

Built something that complements Orion? We may be interested in:
- Acquiring your project
- Licensing it for inclusion in Orion
- Joint development partnerships

**Contact:** info@phoenixlink.co.za

---

## Contribution Types

| Contribution Type | Process |
|-------------------|---------|
| Bug fixes | Sign CLA -> Submit PR |
| Documentation improvements | Sign CLA -> Submit PR |
| Test additions | Sign CLA -> Submit PR |
| Performance improvements | Sign CLA -> Submit PR |
| **New features** | Open Issue first -> Discuss -> Sign CLA -> Submit PR |
| **Architectural changes** | Open Issue first -> Get maintainer approval -> Sign CLA -> Submit PR |
| **Core system changes** (AEGIS, Memory, Router) | Open Issue first -> Detailed discussion required -> Sign CLA -> Submit PR |

For significant work, please discuss with maintainers before investing time. We want to ensure your contribution aligns with the project roadmap and explore whether a partnership arrangement makes sense.

---

## Development Setup
```bash
# Clone the repository
git clone https://github.com/phoenixlink-cloud/orion-agent.git
cd orion-agent

# Install in development mode with all dependencies
pip install -e ".[dev,web,training]"

# Run tests to verify setup
pytest tests/

# Run linting
ruff check .
```

## Code Standards

### Before Submitting

- [ ] All tests pass: `pytest tests/`
- [ ] Linting passes: `ruff check .`
- [ ] New functionality has tests
- [ ] Code follows existing patterns
- [ ] Commit messages are clear and descriptive

### Style Guidelines

- Follow existing code patterns in the module you're modifying
- Use type hints for function signatures
- Add docstrings to public functions and classes
- Keep functions focused -- single responsibility
- Prefer clarity over cleverness

### Commit Messages
```
<type>: <short description>

<optional longer description>

<optional references to issues>
```

Types: `feat`, `fix`, `docs`, `test`, `refactor`, `perf`, `chore`

## Pull Request Process

1. **Ensure CLA is signed** -- PRs from unsigned contributors will not be reviewed
2. **Create a feature branch** from `main`
3. **Make your changes** with clear, atomic commits
4. **Run tests and linting** locally
5. **Push and open a PR** with a clear description
6. **Respond to review feedback** promptly
7. **Squash and merge** once approved

---

## What Happens After Your Contribution Is Merged

Your contribution becomes part of Orion Agent under the project's dual-licensing model:

| Outcome | Details |
|---------|---------|
| **Open source availability** | Available to everyone under AGPL-3.0 |
| **Commercial inclusion** | May be included in commercial licenses sold by Phoenix Link |
| **Your ongoing rights** | You retain copyright; can use your original code elsewhere |
| **Attribution** | Credited in contributors list (optional) |

---

## Getting Help

| Topic | Contact |
|-------|---------|
| Technical questions | GitHub Issues |
| CLA, licensing, partnerships | info@phoenixlink.co.za |
| Technical support | support@phoenixlink.co.za |

---

## Code of Conduct

Be respectful, constructive, and professional. We're building something together.

---

**Thank you for contributing to Orion Agent!**
