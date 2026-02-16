# Orion Agent
# Copyright (C) 2025 Phoenix Link (Pty) Ltd. All Rights Reserved.
#
# This file is part of Orion Agent.
#
# Orion Agent is dual-licensed:
#
# 1. Open Source: GNU Affero General Public License v3.0 (AGPL-3.0)
# 2. Commercial: Available from Phoenix Link (Pty) Ltd
#
# Contributions require a signed CLA. See COPYRIGHT.md and CLA.md.
"""
Tier 3 Seed Knowledge — foundational patterns learned during development.

These are pre-verified patterns and anti-patterns that Orion ships with.
They represent real debugging experience and architectural decisions,
structured as institutional memory that Orion can query at runtime.

Called once on first run (or when DB is empty) to bootstrap wisdom.
Source: ARA-005 Context Loss Investigation & Resolution.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger("orion.memory.seed")

# ─── Learned Patterns (things that work) ─────────────────────────────────

SEED_PATTERNS: list[dict[str, Any]] = [
    {
        "id": "p-read-before-write",
        "description": "Always read existing file content before generating new content for it",
        "context": "file_operations, autonomous_execution, multi_task",
        "example": (
            "When editing a file in a multi-task session, the executor reads the current "
            "file content from the sandbox and includes it in the LLM prompt. The LLM then "
            "produces the COMPLETE updated file with changes applied, preserving all existing "
            "functionality. This prevents blind overwrites that discard previous work."
        ),
        "confidence": 0.98,
    },
    {
        "id": "p-inter-task-context",
        "description": "Pass completed task summaries to subsequent tasks in multi-step workflows",
        "context": "autonomous_execution, task_sequencing, context_passing",
        "example": (
            "After each completed task, feed a summary (task_id, title, output snippet) to "
            "the executor. The executor injects these summaries into every LLM prompt so the "
            "model knows what has already been built. Without this, each task operates in a "
            "vacuum and may duplicate or contradict earlier work."
        ),
        "confidence": 0.97,
    },
    {
        "id": "p-explicit-file-naming",
        "description": "Task descriptions must name their target file explicitly",
        "context": "goal_decomposition, task_planning, llm_prompting",
        "example": (
            "The decomposition prompt enforces: 'Each task description MUST state which file "
            "it targets.' Instead of 'Add game loop' (ambiguous), the LLM produces 'Add game "
            "loop to game.html' (actionable). This allows the executor to reliably identify "
            "which file to read and edit."
        ),
        "confidence": 0.95,
    },
    {
        "id": "p-write-vs-edit-distinction",
        "description": "Use write_file only for first creation; use edit_file for all subsequent modifications",
        "context": "goal_decomposition, file_operations, action_types",
        "example": (
            "The decomposition prompt enforces: 'write_file ONLY for the FIRST task that "
            "creates a new file. edit_file for ALL subsequent modifications.' This signals "
            "to the executor whether to generate from scratch or merge into existing content."
        ),
        "confidence": 0.95,
    },
    {
        "id": "p-regression-guard",
        "description": "Reject edits that shrink a file by more than 50% — likely content loss",
        "context": "file_operations, quality_validation, autonomous_execution",
        "example": (
            "After an LLM generates an edited file, compare line count to the original. "
            "If new_lines < old_lines * 0.5 and old_lines > 20, the edit likely lost content. "
            "Keep the original and log a warning. This catches LLMs that summarize instead of edit."
        ),
        "confidence": 0.93,
    },
    {
        "id": "p-sandbox-inventory",
        "description": "Include a live inventory of sandbox files in every LLM prompt",
        "context": "autonomous_execution, llm_prompting, context_grounding",
        "example": (
            "Before every LLM call, scan the sandbox directory and list all files with their "
            "sizes. Inject this as context: 'Current sandbox files: game.html (5000 bytes), "
            "style.css (1200 bytes)'. This grounds the LLM in the actual project state."
        ),
        "confidence": 0.92,
    },
    {
        "id": "p-archive-before-overwrite",
        "description": "Always archive existing files before overwriting during promotion",
        "context": "file_operations, promotion, workspace_safety",
        "example": (
            "Before promoting sandbox files to the workspace, check if destination files "
            "already exist. If so, move them to .orion-archive/<session>_<timestamp>/ with "
            "a _manifest.json describing what was archived and why. Users can always recover."
        ),
        "confidence": 0.94,
    },
    {
        "id": "p-clean-sandbox-security",
        "description": "Each new session starts with a clean sandbox by default",
        "context": "security, session_management, sandbox_isolation",
        "example": (
            "New sessions get an empty sandbox at ~/.orion/sessions/<id>/sandbox/. No files "
            "carry over from previous sessions. To build on existing work, the user must "
            "explicitly choose 'continue' mode, which copies workspace files into the sandbox. "
            "This prevents stale or malicious files from persisting between sessions."
        ),
        "confidence": 0.96,
    },
    {
        "id": "p-universal-file-targeting",
        "description": "Use open pattern matching for file targeting — never whitelist extensions",
        "context": "file_operations, extensibility, universal_design",
        "example": (
            "The file targeting system uses 4 tiers: (1) extract ANY filename.ext from task "
            "description via open regex, (2) score sandbox files by stem + extension relevance, "
            "(3) single-file fallback, (4) most recently modified file. Works for .html, .py, "
            ".pdf, .blend, .docx — any file type without a whitelist."
        ),
        "confidence": 0.91,
    },
    {
        "id": "p-provider-agnostic",
        "description": "Route all LLM calls through a unified provider interface — never hardcode a specific provider",
        "context": "llm_integration, architecture, extensibility",
        "example": (
            "The task executor reads provider and model from the user's RoleConfig via "
            "load_model_config(). All calls go through call_provider() which supports 11 "
            "providers. Role model_override takes precedence. This allows the same executor "
            "to work with Ollama, OpenAI, Anthropic, Google, or any other provider."
        ),
        "confidence": 0.95,
    },
]

# ─── Learned Anti-Patterns (things that fail) ────────────────────────────

SEED_ANTI_PATTERNS: list[dict[str, Any]] = [
    {
        "id": "ap-blind-overwrite",
        "description": "Writing to a file without reading its current content first",
        "context": "file_operations, autonomous_execution",
        "failure_reason": (
            "In a multi-task session, each write_file task generated content from scratch "
            "without reading the existing file. Task 4's output replaced Task 3's output "
            "completely. After 13 tasks, only the last task's 125 lines survived instead of "
            "the expected 300+ cumulative lines. Silent data loss with false success signals."
        ),
        "severity": 0.98,
    },
    {
        "id": "ap-no-inter-task-context",
        "description": "Running sequential tasks without passing context between them",
        "context": "autonomous_execution, task_sequencing",
        "failure_reason": (
            "Each task executed in isolation — Task N+1 had zero knowledge of what Task N "
            "produced. The LLM regenerated similar code from scratch each time, unable to "
            "build incrementally. Tasks could duplicate work or contradict each other because "
            "neither the executor nor the LLM knew what had already been accomplished."
        ),
        "severity": 0.95,
    },
    {
        "id": "ap-all-writes-no-edits",
        "description": "Using write_file for every file operation instead of distinguishing create vs edit",
        "context": "goal_decomposition, action_types",
        "failure_reason": (
            "The decomposition prompt generated write_file for every task, even modifications "
            "to existing files. The executor treated write_file as 'generate from scratch,' "
            "so every task that should have EDITED a file instead REPLACED it entirely. "
            "The fix: enforce write_file for creation only, edit_file for modifications."
        ),
        "severity": 0.93,
    },
    {
        "id": "ap-hardcoded-provider",
        "description": "Hardcoding a specific LLM provider or model instead of using configuration",
        "context": "llm_integration, architecture",
        "failure_reason": (
            "The original executor was locked to Ollama with 'qwen2.5:14b' hardcoded. "
            "Users with OpenAI, Anthropic, or other providers couldn't use ARA at all. "
            "The fix: read provider/model from user config via load_model_config(), route "
            "through the unified call_provider() interface."
        ),
        "severity": 0.85,
    },
    {
        "id": "ap-orphaned-snippets",
        "description": "Generating code output without persisting it to the target file",
        "context": "autonomous_execution, file_operations",
        "failure_reason": (
            "The generic task executor sometimes produced code in its LLM response but only "
            "returned it as a string in the task output. The code was never written to disk. "
            "Subsequent tasks couldn't build on it because the file didn't exist in the "
            "sandbox. The fix: always persist generated content to the target file."
        ),
        "severity": 0.88,
    },
    {
        "id": "ap-silent-overwrite-promotion",
        "description": "Overwriting workspace files during promotion without backup",
        "context": "promotion, workspace_safety",
        "failure_reason": (
            "When promoting sandbox files to the workspace, existing files were silently "
            "replaced. If a user had files from a previous project with the same name, they "
            "were permanently lost. The fix: archive to .orion-archive/ with timestamped "
            "directories and _manifest.json before overwriting."
        ),
        "severity": 0.90,
    },
    {
        "id": "ap-hardcoded-filenames",
        "description": "Hardcoding specific filenames like 'game.html' in file targeting logic",
        "context": "file_operations, extensibility",
        "failure_reason": (
            "The original _guess_target_file had 'if game in desc: return game.html'. This "
            "broke for any non-game project. A user asking to 'build a Flask web app' would "
            "get their code written to 'game.html'. The fix: use open pattern matching "
            "against actual sandbox contents, no hardcoded filenames."
        ),
        "severity": 0.82,
    },
    {
        "id": "ap-extension-whitelist",
        "description": "Using a whitelist of file extensions instead of open matching",
        "context": "file_operations, universal_design",
        "failure_reason": (
            "The file targeting regex only matched a specific set of developer extensions "
            "(.html, .py, .js, etc.). General users working with .pdf, .docx, .blend, .psd, "
            "or any other file type were not supported. The fix: match ANY filename.ext "
            "pattern with a false-positive filter, not a whitelist."
        ),
        "severity": 0.80,
    },
    {
        "id": "ap-validate-existence-not-quality",
        "description": "Validating that output files exist without checking their content quality",
        "context": "quality_validation, autonomous_execution",
        "failure_reason": (
            "The validation task checked that files existed and weren't too small, but didn't "
            "verify that cumulative features were preserved. A file with 125 lines passed "
            "validation even though it should have had 300+ lines. The fix: add regression "
            "guards that compare output size to expected size based on task history."
        ),
        "severity": 0.85,
    },
]

# ─── Domain Expertise ────────────────────────────────────────────────────

SEED_DOMAINS: list[dict[str, Any]] = [
    {
        "domain": "autonomous_execution",
        "project_count": 1,
        "success_rate": 0.92,
        "learned_patterns": [
            "p-read-before-write",
            "p-inter-task-context",
            "p-regression-guard",
            "p-sandbox-inventory",
        ],
    },
    {
        "domain": "file_operations",
        "project_count": 1,
        "success_rate": 0.90,
        "learned_patterns": [
            "p-read-before-write",
            "p-archive-before-overwrite",
            "p-universal-file-targeting",
            "p-clean-sandbox-security",
        ],
    },
    {
        "domain": "llm_prompting",
        "project_count": 1,
        "success_rate": 0.88,
        "learned_patterns": [
            "p-explicit-file-naming",
            "p-write-vs-edit-distinction",
            "p-sandbox-inventory",
            "p-provider-agnostic",
        ],
    },
]


# ─── Seeding function ────────────────────────────────────────────────────


def seed_institutional_memory(memory: Any) -> int:
    """Populate institutional memory with foundational knowledge.

    Args:
        memory: An InstitutionalMemory instance.

    Returns:
        Number of items seeded.
    """
    import json
    import sqlite3

    db_path = memory.db_path
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    ts = datetime.now(timezone.utc).isoformat()
    seeded = 0

    # Seed patterns
    for p in SEED_PATTERNS:
        existing = c.execute("SELECT id FROM learned_patterns WHERE id = ?", (p["id"],)).fetchone()
        if not existing:
            c.execute(
                "INSERT INTO learned_patterns "
                "(id, description, context, example, success_count, last_used, confidence) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (p["id"], p["description"], p["context"], p["example"], 5, ts, p["confidence"]),
            )
            seeded += 1

    # Seed anti-patterns
    for ap in SEED_ANTI_PATTERNS:
        existing = c.execute(
            "SELECT id FROM learned_anti_patterns WHERE id = ?", (ap["id"],)
        ).fetchone()
        if not existing:
            c.execute(
                "INSERT INTO learned_anti_patterns "
                "(id, description, context, failure_reason, occurrence_count, last_seen, severity) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    ap["id"],
                    ap["description"],
                    ap["context"],
                    ap["failure_reason"],
                    3,
                    ts,
                    ap["severity"],
                ),
            )
            seeded += 1

    # Seed domain expertise
    for d in SEED_DOMAINS:
        existing = c.execute(
            "SELECT domain FROM domain_expertise WHERE domain = ?", (d["domain"],)
        ).fetchone()
        if not existing:
            c.execute(
                "INSERT INTO domain_expertise "
                "(domain, project_count, success_rate, learned_patterns, last_project) "
                "VALUES (?, ?, ?, ?, ?)",
                (
                    d["domain"],
                    d["project_count"],
                    d["success_rate"],
                    json.dumps(d["learned_patterns"]),
                    ts,
                ),
            )
            seeded += 1

    conn.commit()
    conn.close()

    if seeded > 0:
        logger.info("Seeded institutional memory with %d foundational items", seeded)
    return seeded
