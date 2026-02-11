# Learning System

Orion's continuous learning system enables the agent to improve over time through feedback, pattern recognition, and knowledge distillation.

## Overview

Unlike traditional AI tools that start from scratch every session, Orion:

1. **Records outcomes** -- Every task is tracked with its result
2. **Extracts patterns** -- Success and failure patterns are identified
3. **Promotes knowledge** -- Proven patterns are elevated to permanent storage
4. **Evolves behavior** -- Future responses are informed by past learning

## Components

### Evolution Engine

The Evolution Engine tracks Orion's performance over time.

**Key metrics:**
- **Approval rate** -- Percentage of responses rated 4-5
- **Quality trend** -- Direction of quality over time (improving/stable/declining)
- **Task-type analysis** -- Performance breakdown by task category
- **Improvement recommendations** -- Self-generated suggestions

```
> /evolution

Evolution Summary:
  Total tasks: 847
  Approval rate: 82.3%
  Quality trend: Improving (+3.2% this month)
  
  Strengths:
    - Python refactoring (94% approval)
    - Bug fixing (89% approval)
  
  Weaknesses:
    - Test generation (68% approval)
    - Documentation (71% approval)
  
  Recommendations:
    [HIGH] Improve test generation by studying project test patterns
    [MEDIUM] Review documentation style preferences
```

### Knowledge Distillation

Knowledge Distillation (KD) is the process of extracting reusable knowledge from individual interactions.

**Pipeline:**
```
User Interaction
      │
      ▼
┌─────────────┐
│ Record Task │ -- task type, context, result
└──────┬──────┘
       │
       ▼
┌─────────────────┐
│ Extract Pattern │ -- what worked / what didn't
└──────┬──────────┘
       │
       ▼
┌─────────────────┐
│  Score Pattern  │ -- confidence based on rating + context
└──────┬──────────┘
       │
       ▼
┌──────────────────┐
│ Store in Tier 2  │ -- project memory
└──────┬───────────┘
       │ (if high confidence + frequent access)
       ▼
┌──────────────────┐
│ Promote to Tier 3│ -- institutional memory
└──────────────────┘
```

### Feedback Loop

The feedback loop connects user ratings to pattern storage:

| Rating | Interpretation | Action |
|--------|---------------|--------|
| 5 | Excellent | Store as strong success pattern (conf: 0.9) |
| 4 | Good | Store as success pattern (conf: 0.7) |
| 3 | Acceptable | No pattern stored |
| 2 | Poor | Store as anti-pattern (conf: 0.7) |
| 1 | Bad | Store as strong anti-pattern (conf: 0.9) |

## How Patterns Are Used

### Context Injection

When processing a new request, Orion:

1. Analyzes the request to determine relevant categories
2. Searches memory for matching patterns
3. Injects relevant patterns into the LLM prompt
4. Weights anti-patterns as things to avoid

**Example prompt injection:**
```
[Memory Context]
Success patterns for this task type:
- This project uses custom exception classes for error handling
- Always include type hints in function signatures
- Tests follow pytest conventions with fixtures

Anti-patterns to avoid:
- Don't use bare except clauses (rated 1/5 on 2025-01-15)
- Don't modify __init__.py without checking circular imports
```

### Decision Influence

The Governor uses patterns when making decisions:

- **Success patterns** increase confidence in similar approaches
- **Anti-patterns** flag potential issues for review
- **Pattern conflicts** trigger escalation to human

## Evolution Tracking

### Milestones

The system tracks automatic milestones:

| Milestone | Trigger | Significance |
|-----------|---------|--------------|
| First 10 tasks | 10 completed tasks | Baseline established |
| 50 tasks | 50 completed tasks | Pattern library building |
| 100 tasks | 100 completed tasks | Reliable personalization |
| 80% approval | Approval rate hits 80% | Quality threshold met |
| 90% approval | Approval rate hits 90% | High-quality assistance |

### Timeline
```
> /evolution timeline

Timeline:
  2025-01-01: First task completed
  2025-01-05: 10 tasks milestone
  2025-01-15: 50 tasks milestone
  2025-01-20: 80% approval rate achieved
  2025-02-01: 100 tasks milestone
  2025-02-08: 90% approval rate achieved
```

### Per-Task-Type Analysis
```
> /evolution analyze

Task Type Analysis:
  bug_fix:        89% approval (142 tasks)
  refactor:       85% approval (98 tasks)
  code_gen:       82% approval (203 tasks)
  explanation:    91% approval (287 tasks)
  test_gen:       68% approval (67 tasks)  <- needs improvement
  documentation:  71% approval (50 tasks)  <- needs improvement
```

## Configuration

```yaml
learning:
  # Enable/disable learning
  enabled: true
  
  # Minimum rating to store success pattern
  success_threshold: 4
  
  # Maximum rating to store anti-pattern
  anti_pattern_threshold: 2
  
  # Enable evolution tracking
  evolution_tracking: true
  
  # Days of data for rolling metrics
  metrics_window_days: 30
```

## Privacy

- All learning data is stored locally
- No interaction data is sent to external servers
- You can clear all learning data at any time
- Learning can be disabled entirely via configuration

## Source Files

| File | Description | Lines |
|------|-------------|-------|
| `src/orion/core/evolution_engine.py` | Evolution tracking | 470 |
| `src/orion/core/memory_engine.py` | Memory + pattern storage | 590 |
| `tests/test_memory_evolution.py` | Tests | 69 |

---

**Next:** [Memory System](MEMORY_SYSTEM.md) | [Agents](AGENTS.md)
