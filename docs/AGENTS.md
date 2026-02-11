# Multi-Agent System

Orion uses a multi-agent architecture where specialized agents collaborate to produce higher-quality results than any single agent could achieve alone.

## Overview

Instead of sending your request directly to an LLM, Orion routes it through a deliberation system:

```
User Request
     │
     ▼
┌─────────┐
│  Scout  │ -- Analyzes complexity
└────┬────┘
     │
     ├──── Simple ──── FastPath (direct LLM response)
     │
     └──── Complex ─── Table of Three (multi-agent deliberation)
                            │
                            ├── Builder (generates solution)
                            ├── Reviewer (critiques solution)
                            └── Governor (makes final decision)
```

## The Scout (Router)

The Scout is the first agent to see your request. It analyzes:

- **Complexity** -- Is this a simple question or a complex task?
- **Risk level** -- Does this involve file modifications or command execution?
- **Domain** -- What area of the codebase is involved?

Based on this analysis, the Scout routes to:

| Route | Criteria | Path |
|-------|----------|------|
| **FastPath** | Simple questions, explanations, small edits | Direct to LLM |
| **Council** | Complex tasks, multi-file changes, architectural decisions | Table of Three |
| **Escalation** | High-risk operations, ambiguous requests | Human confirmation |

## FastPath

FastPath handles simple requests directly -- no multi-agent overhead.

**When used:**
- Code explanations
- Simple questions
- Single-file small edits
- Configuration lookups

**How it works:**
1. Scout classifies request as simple
2. Request goes directly to the configured LLM
3. Response is returned with AEGIS validation
4. Memory context is injected for personalization

**Performance:** FastPath is 3-5x faster than the full council.

## Table of Three

The Table of Three is Orion's multi-agent deliberation system for complex tasks.

### Builder

**Role:** Creator

**Responsibility:** Generate the code solution.

**Process:**
1. Receives the user request + workspace context + memory patterns
2. Analyzes relevant code files
3. Generates a complete solution
4. Outputs structured proposal (files to modify, new code, rationale)

**Configuration:**
```yaml
agents:
  builder:
    provider: openai
    model: gpt-4o
    temperature: 0.3
```

**Key features:**
- Constraint extraction from natural language
- Multi-file awareness
- Memory-informed generation (uses known patterns)
- Async execution for all providers

### Reviewer

**Role:** Critic

**Responsibility:** Analyze the Builder's output for correctness and quality.

**Process:**
1. Receives Builder's proposal
2. Checks for correctness, edge cases, security issues
3. Issues a verdict: APPROVE, REVISE_AND_APPROVE, or BLOCK

**Verdicts:**

| Verdict | Meaning | Action |
|---------|---------|--------|
| **APPROVE** | Solution is correct and complete | Proceed to Governor |
| **REVISE_AND_APPROVE** | Minor issues, but acceptable with notes | Proceed with revision notes |
| **BLOCK** | Significant issues found | Return to Builder or escalate |

**What the Reviewer checks:**
- Syntax correctness
- Logic errors
- Missing error handling
- Security vulnerabilities
- Edge cases
- Code style consistency
- Test coverage gaps

### Governor

**Role:** Authority

**Responsibility:** Make the final decision using deterministic logic.

**Key design choice:** The Governor is **not** an LLM. It uses deterministic rules, memory, and quality gates to make decisions. This prevents the "LLM approving another LLM" problem.

**Process:**
1. Receives Builder's proposal + Reviewer's verdict
2. Checks against AEGIS governance rules
3. Consults memory for relevant patterns/anti-patterns
4. Applies quality gates (confidence scoring)
5. Makes final decision: EXECUTE, MODIFY, or REJECT

**Hard Boundaries (never autonomous):**
- Financial transactions
- Legal commitments
- Ethical violations
- Production deployments
- Security credential exposure
- User data deletion

These always require human confirmation regardless of mode.

## Request Lifecycle

Complete flow for a complex request:

```
1. User submits request
2. Scout analyzes complexity -> routes to Council
3. Builder generates solution
   - Reads relevant files
   - Injects memory context
   - Generates code proposal
4. Reviewer critiques solution
   - Checks correctness
   - Identifies edge cases
   - Issues verdict (APPROVE/REVISE/BLOCK)
5. Governor makes final decision
   - Validates against AEGIS
   - Checks memory for anti-patterns
   - Applies quality gates
   - Decision: EXECUTE/MODIFY/REJECT
6. If EXECUTE:
   - AEGIS validates all file operations
   - Changes presented to user for approval (in pro mode)
   - User approves -> changes applied
   - Outcome recorded in memory
7. If MODIFY:
   - Builder revises based on feedback
   - Cycle repeats (max 3 iterations)
8. If REJECT:
   - User informed with reason
   - Suggestion for alternative approach
```

## Configuration

### Enable/Disable Table of Three

```yaml
agents:
  enable_table_of_three: true  # false = all requests use FastPath
```

### Per-Agent LLM Configuration

You can use different LLMs for different agents:

```yaml
agents:
  builder:
    provider: openai
    model: gpt-4o
    temperature: 0.3
  reviewer:
    provider: anthropic
    model: claude-3-5-sonnet-20241022
    temperature: 0.2
  # Governor uses deterministic logic (no LLM needed)
```

## Source Files

| File | Description | Lines |
|------|-------------|-------|
| `src/orion/core/agents/builder.py` | Builder agent | 408 |
| `src/orion/core/agents/reviewer.py` | Reviewer agent | 173 |
| `src/orion/core/agents/governor.py` | Governor (deterministic) | 147 |
| `src/orion/core/agents/table.py` | Table of Three orchestration | 203 |
| `src/orion/core/router.py` | Scout/Router | ~500 |
| `src/orion/core/fast_path.py` | FastPath direct route | ~300 |

---

**Next:** [Architecture](ARCHITECTURE.md) | [Memory System](MEMORY_SYSTEM.md)
