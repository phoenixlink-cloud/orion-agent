# ARA-005: Context Loss in Multi-Task Execution — Investigation & Resolution

**Status:** Resolved  
**Date:** 2026-02-15  
**Author:** Phoenix Link Development (Teacher → Orion Institutional Memory)  
**Domain:** ARA autonomous execution, file operations, LLM prompting  
**Severity:** Critical — caused complete loss of cumulative work  

---

## Purpose

This document captures a real debugging investigation as **Tier 3 institutional knowledge**.
It is structured as a lesson: problem → investigation → root causes → fixes → principles.
Orion should internalize these patterns and anti-patterns for all future autonomous execution.

---

## 1. The Problem

### Observed Behavior
During a game development test session, Orion ARA decomposed a goal into 13 tasks and executed them sequentially. Results:

- 13 tasks executed, 12 completed successfully
- Each `edit_file` / `write_file` task logged completion with high confidence
- Final output file (`game.html`) contained only ~125 lines
- Features from tasks 5-9 (gravity flip, levels, collision, sprites) were **absent**
- Only the last file-writing task's output appeared to survive

### Expected Behavior
- Each task should build upon previous tasks' work
- Final file should contain cumulative work from all tasks
- A 13-task game build should produce 300+ lines, not 125

### Impact
**Total loss of cumulative work.** The system appeared to work (all tasks "succeeded") but produced output equivalent to a single task. This is the worst kind of bug — silent data loss with false success signals.

---

## 2. Investigation

### 2.1 Files Examined

| File | Purpose | Key Finding |
|------|---------|-------------|
| `src/orion/ara/ollama_provider.py` | LLM calls + task execution | `write_file` never read existing content |
| `src/orion/ara/execution.py` | Task loop + sequencing | No inter-task context passing |
| `src/orion/ara/daemon_launcher.py` | Session startup | Hardcoded to Ollama only |
| `src/orion/ara/daemon.py` | Daemon lifecycle | No executor reference passed |
| `src/orion/ara/promotion.py` | Sandbox → workspace | No archive on overwrite |
| `src/orion/ara/goal_engine.py` | Goal decomposition | Task DAG structure |
| `src/orion/core/llm/providers.py` | Unified LLM router | 11 providers supported |
| `src/orion/core/llm/config.py` | Model configuration | RoleConfig/ModelConfiguration |

### 2.2 The Execution Flow (Before Fix)

```
Goal: "Build a snake game with levels and sprites"
  ↓
GoalEngine.decompose() → 13 tasks
  ↓
ExecutionLoop runs tasks sequentially:
  Task 1: analyze requirements       → output: text summary
  Task 2: write_file game.html       → output: 80 lines of HTML ← FILE CREATED
  Task 3: edit_file add game loop    → output: 120 lines ← FILE OVERWRITTEN (lost task 2 work!)
  Task 4: edit_file add controls     → output: 100 lines ← FILE OVERWRITTEN (lost task 3 work!)
  ...
  Task 12: edit_file final polish    → output: 125 lines ← ONLY THIS SURVIVES
  Task 13: validate                  → "looks good" (checked file exists, not content)
```

### 2.3 Root Causes Identified

#### Root Cause A: Blind File Overwrites
**The `write_file` executor never read the existing file before calling the LLM.**

```python
# BEFORE (broken):
async def _execute_write_file(self, task):
    response = await self._call_ollama(system_prompt, task.description)
    # ← No read of existing file!
    filepath.write_text(response)  # ← Blind overwrite
```

The LLM received only the task description, not the current file content. It generated a fresh file from scratch every time, discarding all previous work.

**Lesson:** Any write operation to a file that may already exist MUST read the current content first.

#### Root Cause B: Decomposition Prompt Didn't Distinguish Create vs. Edit
The LLM decomposition used `write_file` for every file-touching task, even modifications. The executor treated every `write_file` as "generate from scratch."

```
Task 3: write_file — "Add game loop to game.html"     ← Should be edit_file!
Task 4: write_file — "Add keyboard controls"            ← Should be edit_file!
```

**Lesson:** The decomposition prompt must enforce: `write_file` = first creation only, `edit_file` = all subsequent modifications.

#### Root Cause C: No Inter-Task Context
Task N+1 had zero knowledge of what Task N produced. The execution loop ran tasks in isolation:

```python
# BEFORE (broken):
for task in tasks:
    result = await executor(task)  # Each task starts with blank slate
    task.output = result
    # ← Never told the next task what happened
```

**Lesson:** Completed task summaries must be passed to the executor so the LLM knows what has already been built.

#### Root Cause D: Hardcoded Provider
The executor was locked to Ollama with a hardcoded model. Users with OpenAI, Anthropic, or other providers couldn't use ARA at all.

**Lesson:** Never hardcode a specific provider. Always route through the unified provider interface.

#### Root Cause E: Orphaned Code Snippets
The `_execute_generic()` catch-all sometimes produced code output but didn't persist it to any file. The code existed in the task's output string but was never written to disk.

**Lesson:** Any task that produces code output must persist it to the target file, not just return it as a string.

#### Root Cause F: Workspace Overwrites on Promotion
When promoting sandbox files to the workspace, existing files were silently overwritten with no backup. If a user had files from a previous project with the same name, they were lost.

**Lesson:** Always archive before overwriting. Use timestamped backups with manifests.

---

## 3. The Fixes

### Fix A: Context-Aware File Operations
**Principle: READ BEFORE WRITE**

```python
# AFTER (fixed):
async def _execute_write_file(self, task):
    target = _guess_target_file(task.description, task.title, self.sandbox_dir)
    existing = _read_sandbox_file(self.sandbox_dir, target)  # ← READ FIRST

    if existing:
        return await self._merge_into_file(task, target, existing)  # ← MERGE
    else:
        return await self._generate_new_file(task, target)  # ← CREATE ONLY IF NEW
```

The merge prompt tells the LLM:
- Here is the CURRENT file content (N lines)
- Here is the task to apply
- Output the COMPLETE updated file with changes applied
- PRESERVE ALL existing functionality

### Fix B: Smart Decomposition Prompt
```
CRITICAL RULES FOR action_type:
- Use 'write_file' ONLY for the FIRST task that creates a new file.
- Use 'edit_file' for ALL subsequent tasks that modify an existing file.
- NEVER use write_file for a file that was already created by an earlier task.
- Each task description MUST state which file it targets.
```

### Fix C: Unified Provider Routing
All LLM calls now go through `call_provider()` from `src/orion/core/llm/providers.py`, supporting all 11 providers (Ollama, OpenAI, Anthropic, Google, Cohere, Mistral, Together, Groq, OpenRouter, DeepSeek, local).

### Fix D: Provider-Aware Executor
The executor reads the user's model configuration from `RoleConfig` instead of hardcoding:
```python
model_cfg = load_model_config()
builder_rc = model_cfg.get_builder()
provider = builder_rc.provider  # Could be "openai", "anthropic", "ollama", etc.
model = builder_rc.model
```

### Fix E: Inter-Task Context Passing
After each completed task, the execution loop feeds a summary to the executor:
```python
if task_result.get("success"):
    executor.add_task_context(task.task_id, task.title, task.output)
```

The executor injects these summaries into every subsequent LLM prompt:
```
Completed tasks so far:
  [task-1] Analyze requirements: Identified need for canvas-based rendering...
  [task-2] Create game.html: Generated game.html (150 lines, 5.2 KB)
  [task-3] Add game loop: Updated game.html (150→210 lines, 7.8 KB)
```

### Fix F: Persist All Outputs
Every task that produces content writes it to the target file. The generic catch-all also persists:
```python
async def _execute_generic(self, task):
    target = _guess_target_file(...)
    if target:
        existing = _read_sandbox_file(self.sandbox_dir, target)
        if existing:
            return await self._merge_into_file(task, target, existing)
    # ... LLM call ...
    # Always persist if we produced content
```

### Fix G: Archive System for Promotion
Before overwriting workspace files during promotion:
```
.orion-archive/
  <session>_<timestamp>/
    game.html          ← backed up copy
    README.txt         ← backed up copy
    _manifest.json     ← what was archived and why
```

### Fix H: Project Continuity Check
At session start, Orion scans the workspace and asks the user:
- **New project** → clean sandbox (security: no stale files)
- **Continue** → copies workspace files into sandbox (builds on existing)

### Fix I: Universal File Targeting (4-Tier)
No hardcoded filenames. Works for any file type:

| Tier | Strategy | Example |
|------|----------|---------|
| 1 | Extract ANY `filename.ext` from task description | "Edit report.pdf" → `report.pdf` |
| 2 | Score sandbox files: stem match (+10), extension match (+5), keyword bonus (+2) | Task says "styling" + sandbox has `app.css` → match |
| 3 | Single file in sandbox → use it | Only `index.html` → use it |
| 4 | Most recently modified non-README file | Last touched `game.html` → use it |

### Fix J: Regression Guard
Rejects LLM edits that shrink a file by >50%, preventing accidental content loss:
```python
if new_lines < old_lines * 0.5 and old_lines > 20:
    logger.warning("Edit shrank %s — keeping larger version", target)
    new_content = existing  # Keep the original
```

---

## 4. Derived Principles (Tier 3 Institutional Knowledge)

These are the universal principles Orion should internalize:

### P1: Read Before Write
**Always read the current state of a file before generating new content for it.**
Never assume a file is empty. Never generate from scratch when editing. The LLM must see what already exists to produce correct incremental changes.

### P2: Cumulative Work Must Be Preserved
**Every task in a multi-step workflow must build on the output of previous tasks.**
If Task 3 produces 200 lines and Task 4 produces 150 lines, something went wrong. Edits should grow or maintain file size, not shrink it.

### P3: Explicit Over Implicit
**Task descriptions must name their target file explicitly.**
"Add game loop" is ambiguous. "Add game loop to game.html" is actionable. The decomposition prompt must enforce this.

### P4: Inter-Task Context Is Non-Negotiable
**Every executor call must include summaries of what previous tasks accomplished.**
Without this, each task operates in a vacuum and may duplicate or contradict earlier work.

### P5: No Hardcoded Assumptions
**Never hardcode file types, provider names, filenames, or tool-specific values.**
Use dynamic discovery: read configs, scan directories, infer from context. What works for "game.html" breaks for "app.py", "report.pdf", or "data.csv".

### P6: Silent Failures Are Worse Than Loud Failures
**A task that "succeeds" but produces wrong output is worse than a task that fails.**
The regression guard (reject >50% shrinkage) catches this. Always validate output quality, not just output existence.

### P7: Archive Before Overwrite
**Never silently overwrite a file the user may care about.**
Use timestamped archives with manifests so the user can recover previous versions.

### P8: Clean Sandboxes Are a Security Feature
**Each session starts with a clean sandbox by default.**
No stale files carry over. No malicious files persist. The user must explicitly opt in to inherit files.

### P9: Universal Design Over Special Cases
**Build for "any file type" rather than "these specific file types."**
A whitelist of extensions will always be incomplete. Use open pattern matching with fallback heuristics.

### P10: The LLM Is Not Reliable — Add Guard Rails
**LLMs may not follow instructions perfectly. Always add programmatic safety checks.**
The decomposition prompt says "use edit_file for modifications" but the LLM might still use write_file. The executor handles both cases correctly regardless.

---

## 5. Files Modified

| File | Change |
|------|--------|
| `src/orion/ara/task_executor.py` | **NEW** — Universal, context-aware executor |
| `src/orion/ara/ollama_provider.py` | Renamed to ARALLMProvider, improved prompt |
| `src/orion/ara/execution.py` | Inter-task context passing |
| `src/orion/ara/daemon.py` | Executor reference passthrough |
| `src/orion/ara/daemon_launcher.py` | Provider-agnostic, sandbox seeding |
| `src/orion/ara/cli_commands.py` | Project continuity check |
| `src/orion/ara/promotion.py` | Archive system |

---

## 6. Verification

| Scenario | Status |
|----------|--------|
| Task creates new file | ✅ |
| Task edits file from previous task | ✅ |
| Continue existing project (workspace seeding) | ✅ |
| Vague task description + multi-file sandbox | ✅ (Tier 4 fallback) |
| Inter-task knowledge transfer | ✅ |
| Regression guard (prevents shrinkage) | ✅ |
| Archive on promotion | ✅ |
| Binary files | ⚠️ LLM limitation — cannot generate binary content |

---

*This document is part of Orion's Tier 3 institutional memory. The patterns and anti-patterns described here should be applied to all future autonomous execution workflows.*
