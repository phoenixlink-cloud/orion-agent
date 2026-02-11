# Orion Memory System

Orion's three-tier memory system enables persistent learning across sessions, projects, and time -- a key differentiator from single-shot AI tools.

## Overview

Most AI assistants forget everything after a conversation ends. Orion is different:

| What Others Do | What Orion Does |
|----------------|-----------------|
| Forget after session | Remember across sessions |
| No project context | Learn project patterns |
| Same mistakes repeated | Avoid known anti-patterns |
| Generic responses | Personalized to your codebase |

## The Three Tiers
```
┌─────────────────────────────────────────────────────────────┐
│                    MEMORY ARCHITECTURE                       │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │              TIER 1: SESSION MEMORY                  │   │
│  │                     (RAM)                            │   │
│  │                                                      │   │
│  │  - Current conversation context                      │   │
│  │  - Immediate task state                              │   │
│  │  - Duration: Current session only                    │   │
│  └─────────────────────────────────────────────────────┘   │
│                          │                                  │
│                          ▼ (valuable items promoted)        │
│  ┌─────────────────────────────────────────────────────┐   │
│  │              TIER 2: PROJECT MEMORY                  │   │
│  │                    (JSON files)                      │   │
│  │                                                      │   │
│  │  - Workspace-specific patterns                       │   │
│  │  - Recent decisions and rationale                    │   │
│  │  - Duration: Days to weeks                           │   │
│  └─────────────────────────────────────────────────────┘   │
│                          │                                  │
│                          ▼ (proven patterns promoted)       │
│  ┌─────────────────────────────────────────────────────┐   │
│  │            TIER 3: INSTITUTIONAL MEMORY              │   │
│  │                    (SQLite)                          │   │
│  │                                                      │   │
│  │  - Cross-project wisdom                              │   │
│  │  - Proven patterns and anti-patterns                 │   │
│  │  - Duration: Months to years                         │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

## Tier 1: Session Memory

**Purpose:** Immediate context for the current conversation.

**Storage:** RAM (Python objects)

**Duration:** Current session only

**Contents:**
- Current conversation history
- Active task state
- Temporary variables
- Recent file contents

**Example:**
```
You: Fix the bug in auth.py
Orion: [analyzes auth.py, finds the issue]
You: Also add logging
Orion: [remembers we're working on auth.py, adds logging to the fix]
```

Session memory allows Orion to maintain context within a conversation without re-reading files or re-analyzing code.

## Tier 2: Project Memory

**Purpose:** Workspace-specific knowledge that persists across sessions.

**Storage:** JSON files in `.orion/memory/`

**Duration:** Days to weeks (configurable)

**Contents:**
- Project structure understanding
- Coding patterns specific to this codebase
- Recent decisions and their rationale
- User preferences for this project

**Example:**
```json
{
  "patterns": [
    {
      "id": "auth-error-handling",
      "content": "This project uses custom AuthError exceptions",
      "confidence": 0.85,
      "access_count": 12,
      "created": "2025-02-01T10:30:00Z"
    }
  ]
}
```

**Promotion criteria:**
- High confidence (>=0.7)
- Frequently accessed (>=3 times)
- Positive user feedback (rating >=4)

## Tier 3: Institutional Memory

**Purpose:** Cross-project wisdom that represents proven knowledge.

**Storage:** SQLite database (`~/.orion/institutional.db`)

**Duration:** Months to years (permanent until explicitly removed)

**Contents:**
- Proven patterns that work across projects
- Anti-patterns to avoid
- Language/framework best practices
- User's coding style preferences

**Promotion criteria:**
- Very high confidence (>=0.85)
- Verified across multiple projects
- Consistent positive feedback

## How Learning Works

### Step 1: You Rate Responses

After Orion provides a response, you can rate it:
```
> Add error handling to the API endpoint

[Orion provides solution]

Rate this response (1-5, or skip): 5
Feedback recorded. Pattern stored.
```

### Step 2: Patterns Are Extracted

High-rated responses (4-5) generate success patterns:
- What was the task?
- What approach worked?
- What was the context?

Low-rated responses (1-2) generate anti-patterns:
- What went wrong?
- What should be avoided?
- What was the context?

### Step 3: Patterns Are Stored

New patterns enter Tier 2 (Project Memory) with initial confidence based on rating.

### Step 4: Patterns Are Promoted

Over time, patterns that prove valuable are promoted:
```
Tier 1 (Session)
    | (rated 4-5)
    v
Tier 2 (Project)
    | (high confidence + frequent access)
    v
Tier 3 (Institutional)
```

### Step 5: Patterns Inform Future Responses

When you ask Orion a question, it:

1. Searches all three tiers for relevant patterns
2. Injects relevant context into the prompt
3. Weighs responses against known anti-patterns
4. Generates a response informed by past learning

## Memory Commands

### View Memory Status
```
> /memory

Memory Status:
  Session (Tier 1): 23 items
  Project (Tier 2): 147 patterns
  Institutional (Tier 3): 892 patterns

  Last consolidation: 2 hours ago
  Next auto-promote: 4 hours
```

### View Specific Patterns
```
> /memory search error handling

Found 12 patterns:
  [T3] Always wrap async calls in try/catch (conf: 0.95)
  [T3] Use custom error types over generic (conf: 0.88)
  [T2] This project uses AuthError for auth failures (conf: 0.85)
  ...
```

### Clear Session Memory
```
> /memory clear session
Session memory cleared. Project and institutional memory preserved.
```

## Configuration

### Memory Locations
```
~/.orion/
├── memory/
│   └── institutional.db    # Tier 3 SQLite database
└── workspaces/
    └── <project-hash>/
        └── memory.json     # Tier 2 project memory
```

### Settings
```yaml
# ~/.orion/config.yaml
memory:
  tier2_retention_days: 30      # How long to keep project patterns
  promotion_threshold: 0.85     # Confidence needed for T2->T3
  auto_consolidate: true        # Automatically clean old patterns
  consolidation_interval: 24h   # How often to consolidate
```

## Privacy Considerations

Memory contains information about your code and patterns. Considerations:

- **Local storage** -- All memory is stored locally, never sent to external servers
- **Per-project isolation** -- Project memory is isolated per workspace
- **Clearable** -- You can clear any tier at any time
- **No telemetry** -- Orion doesn't report memory contents anywhere

## Technical Details

### Relevance Scoring

When recalling patterns, Orion scores relevance:
```python
score = (
    keyword_overlap * 0.4 +
    semantic_similarity * 0.3 +
    tier_weight * 0.2 +
    recency * 0.1
)
```

Higher-tier patterns get priority (Tier 3 > Tier 2 > Tier 1).

### Consolidation

Periodic consolidation:
- Removes low-confidence, low-access patterns from Tier 2
- Merges duplicate patterns
- Updates confidence scores based on access patterns

### Source Files

- `src/orion/core/memory_engine.py` -- Three-tier memory implementation (590 lines)
- `tests/test_memory_evolution.py` -- Memory tests (69 tests)

---

*Memory is what separates Orion from tools that forget.*

**Next:** [Learning System](LEARNING_SYSTEM.md) | [Architecture](ARCHITECTURE.md)
