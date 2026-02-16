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
"""ARA Task Executor — provider-agnostic, context-aware task execution.

Replaces OllamaTaskExecutor with a universal executor that:
- Routes through the unified call_provider (supports all 11 AI providers)
- Reads existing sandbox files before every LLM call (context-aware)
- Persists ALL code output to target files (no orphaned snippets)
- Accepts inter-task context from the execution loop
- Uses sandbox inventory to ground the LLM in current project state

See ARA-001 §9 for design.
"""

from __future__ import annotations

import json
import logging
import re
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger("orion.ara.task_executor")


def _sandbox_inventory(sandbox_dir: Path) -> str:
    """Build a text inventory of all files currently in the sandbox."""
    if not sandbox_dir.exists():
        return "Sandbox is empty — no files created yet."
    files = sorted(f for f in sandbox_dir.rglob("*") if f.is_file())
    if not files:
        return "Sandbox is empty — no files created yet."
    lines = ["Current sandbox files:"]
    for f in files:
        rel = f.relative_to(sandbox_dir)
        size = f.stat().st_size
        lines.append(f"  - {rel} ({size} bytes)")
    return "\n".join(lines)


def _read_sandbox_file(sandbox_dir: Path, filename: str) -> str:
    """Read a file from the sandbox, returning empty string if not found."""
    path = sandbox_dir / filename
    if path.exists():
        try:
            return path.read_text(encoding="utf-8")
        except Exception:
            return ""
    return ""


def _guess_target_file(task_desc: str, task_title: str, sandbox_dir: Path) -> str | None:
    """Infer which file a task targets based on description and existing sandbox files.

    Uses a 3-tier strategy — universal, no extension whitelist:
      Tier 1: Extract ANY explicit filename.ext from task description
      Tier 2: Score ALL sandbox files by stem + extension relevance
      Tier 3: Single-file sandbox fallback

    Returns the relative filename or None if we can't determine it.
    """
    desc = task_desc.lower()
    title = task_title.lower()
    combined = f"{title} {desc}"

    # Common abbreviations / non-filename patterns to ignore
    _false_positives = {"e.g", "i.e", "etc", "vs", "dr", "mr", "ms", "st", "no"}

    # --- Tier 1: Extract ANY filename.extension from description ---
    # Matches word.ext where ext is 1-12 alphanumeric chars (any file type)
    for m in re.finditer(r'([\w\-]+\.[a-zA-Z0-9]{1,12})\b', combined):
        candidate = m.group(1)
        # Filter out false positives (abbreviations, version numbers)
        if candidate in _false_positives:
            continue
        # Must have at least one letter in the extension
        ext_part = candidate.rsplit(".", 1)[-1]
        if not re.search(r'[a-zA-Z]', ext_part):
            continue  # Skip pure numeric like "python3.11"
        return candidate

    # --- Tier 2: Score ALL sandbox files against task description ---
    sandbox_files = {
        str(f.relative_to(sandbox_dir)): f
        for f in sandbox_dir.rglob("*") if f.is_file()
    }

    if sandbox_files:
        # Bonus keyword map for well-known extensions (not a gate — just extra signal)
        _ext_bonus: dict[str, list[str]] = {
            ".html": ["html", "web", "page", "ui", "frontend", "site"],
            ".css":  ["style", "stylesheet", "design", "theme", "layout"],
            ".js":   ["javascript", "logic", "node", "react"],
            ".ts":   ["typescript", "angular"],
            ".py":   ["python", "backend", "server", "api", "flask", "django"],
            ".go":   ["golang", "backend"],
            ".rs":   ["rust", "cargo"],
            ".java": ["java", "spring"],
            ".json": ["config", "settings", "data", "package"],
            ".yaml": ["yaml", "docker", "kubernetes"],
            ".yml":  ["docker", "compose", "actions"],
            ".sql":  ["database", "query", "migration", "schema"],
            ".md":   ["readme", "documentation", "docs"],
            ".txt":  ["readme", "notes", "text", "license"],
            ".sh":   ["bash", "shell", "deploy"],
            ".csv":  ["data", "spreadsheet"],
            ".xml":  ["config", "manifest"],
        }

        best_file = None
        best_score = 0
        for rel_path in sandbox_files:
            score = 0
            ext = Path(rel_path).suffix.lower()
            stem = Path(rel_path).stem.lower()

            # Primary signal: filename stem appears in the task description
            if len(stem) >= 2 and stem in combined:
                score += 10

            # Secondary signal: the bare extension name appears in description
            # Works for ANY extension — "pdf", "blend", "docx", "png", etc.
            ext_bare = ext.lstrip(".")
            if ext_bare and ext_bare in combined:
                score += 5

            # Bonus signal: well-known keyword associations (additive, not required)
            bonus_keywords = _ext_bonus.get(ext, [])
            for kw in bonus_keywords:
                if kw in combined:
                    score += 2

            if score > best_score:
                best_score = score
                best_file = rel_path

        if best_file and best_score >= 2:
            return best_file

    # --- Tier 3: Single-file fallback ---
    if len(sandbox_files) == 1:
        return next(iter(sandbox_files))

    # --- Tier 4: Most recently modified file ---
    # When task description is vague and sandbox has multiple files,
    # the most recently modified file is most likely the active target.
    if sandbox_files:
        by_mtime = sorted(
            sandbox_files.items(),
            key=lambda kv: kv[1].stat().st_mtime,
            reverse=True,
        )
        # Prefer non-README files (those are support files, not main targets)
        for rel_path, fpath in by_mtime:
            if not rel_path.lower().startswith("readme"):
                return rel_path
        # All files are READMEs — just return the most recent
        return by_mtime[0][0]

    return None


async def _call_llm(
    provider: str,
    model: str,
    system_prompt: str,
    user_prompt: str,
    max_tokens: int = 8000,
    temperature: float = 0.3,
) -> str:
    """Call any supported LLM provider via the unified router."""
    from orion.core.llm.config import RoleConfig
    from orion.core.llm.providers import call_provider

    role_config = RoleConfig(provider=provider, model=model)
    return await call_provider(
        role_config=role_config,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        max_tokens=max_tokens,
        component="ara_executor",
        temperature=temperature,
    )


class ARATaskExecutor:
    """Provider-agnostic, context-aware task executor for ARA sessions.

    Key improvements over OllamaTaskExecutor:
    - Uses unified call_provider (all 11 providers)
    - Reads existing sandbox files before every write (no blind overwrites)
    - Persists code output from every task to the target file
    - Receives inter-task context (completed task summaries)
    - Tracks sandbox inventory for LLM grounding
    - Queries Tier 3 institutional memory for learned patterns (teach-student cycle)
    - Feeds task outcomes back to institutional memory for continuous learning
    """

    def __init__(
        self,
        provider: str = "ollama",
        model: str = "qwen2.5:14b",
        sandbox_dir: Path | None = None,
        goal: str = "",
        institutional_memory: Any | None = None,
    ):
        self.provider = provider
        self.model = model
        self.sandbox_dir = sandbox_dir or Path.cwd()
        self.sandbox_dir.mkdir(parents=True, exist_ok=True)
        self.goal = goal
        self._generated_files: dict[str, str] = {}
        # Inter-task context: filled by execution loop after each task
        self._completed_task_summaries: list[str] = []
        # Tier 3 institutional memory (teach-student cycle)
        self._institutional = institutional_memory

    def add_task_context(self, task_id: str, title: str, output: str) -> None:
        """Record a completed task's output for inter-task context."""
        summary = f"[{task_id}] {title}: {output[:300]}"
        self._completed_task_summaries.append(summary)

    def learn_from_task_outcome(
        self, task_id: str, action_type: str, title: str,
        success: bool, output: str, confidence: float,
    ) -> None:
        """Feed task outcome back to institutional memory (teach-student WRITE path).

        Successful tasks reinforce patterns; failed tasks reinforce anti-patterns.
        Over time, Orion learns which approaches work for which task types.
        """
        if not self._institutional:
            return
        try:
            quality = confidence if success else max(0.1, 1.0 - confidence)
            self._institutional.learn_from_outcome(
                action_type=action_type,
                context=f"[ARA] {title}: {output[:200]}",
                outcome=output[:500] if success else f"FAILED: {output[:500]}",
                quality_score=quality,
                domain="autonomous_execution",
            )
            logger.debug(
                "Institutional memory updated: %s %s (quality=%.2f)",
                task_id, "success" if success else "failure", quality,
            )
        except Exception as e:
            logger.debug("Could not update institutional memory: %s", e)

    def _build_context_block(self) -> str:
        """Build the context block injected into every LLM prompt.

        Includes: sandbox inventory, inter-task summaries, and institutional wisdom.
        """
        parts = []
        # Sandbox inventory
        parts.append(_sandbox_inventory(self.sandbox_dir))
        # Previous task summaries
        if self._completed_task_summaries:
            parts.append("\nCompleted tasks so far:")
            for s in self._completed_task_summaries[-10:]:  # Last 10
                parts.append(f"  {s}")
        # Tier 3 institutional wisdom (teach-student cycle: READ path)
        if self._institutional:
            try:
                from orion.core.learning.patterns import get_learnings_for_prompt
                wisdom = get_learnings_for_prompt(
                    self._institutional, self.goal, max_items=5
                )
                if wisdom:
                    parts.append(f"\n{wisdom}")
            except Exception as e:
                logger.debug("Could not load institutional wisdom: %s", e)
        return "\n".join(parts)

    async def execute(self, task: Any) -> dict[str, Any]:
        """Execute a single task. Returns {success, output, confidence, cost}."""
        action = getattr(task, "action_type", "unknown")
        title = getattr(task, "title", "Unknown")
        desc = getattr(task, "description", "")
        logger.info("Executing task: %s (%s) — %s", task.task_id, action, title)

        start = time.time()
        try:
            if action == "analyze":
                result = await self._execute_analyze(task)
            elif action in ("write_file", "write_files"):
                result = await self._execute_write_file(task)
            elif action == "edit_file":
                result = await self._execute_edit_file(task)
            elif action in ("run_tests", "validate"):
                result = await self._execute_validate(task)
            elif action == "read_files":
                result = {"success": True, "output": f"Analyzed: {desc}", "confidence": 0.9}
            else:
                result = await self._execute_generic(task)

            elapsed = time.time() - start
            logger.info(
                "Task %s completed in %.1fs: success=%s",
                task.task_id, elapsed, result.get("success"),
            )
            return result

        except Exception as e:
            logger.error("Task %s failed: %s", task.task_id, e)
            return {"success": False, "error": str(e), "confidence": 0.0}

    # =========================================================================
    # ANALYZE
    # =========================================================================

    async def _execute_analyze(self, task: Any) -> dict[str, Any]:
        """Analyze requirements — no file output, just understanding."""
        system_prompt = (
            "You are a software architect analyzing requirements. "
            "Provide a brief analysis of what needs to be built. "
            "Be concise — max 200 words."
        )
        context = self._build_context_block()
        response = await _call_llm(
            self.provider, self.model, system_prompt,
            f"Goal: {self.goal}\n\nTask: {task.description}\n\n{context}",
            max_tokens=1000, temperature=0.3,
        )
        return {"success": True, "output": response[:500], "confidence": 0.9}

    # =========================================================================
    # WRITE FILE (context-aware — reads existing before generating)
    # =========================================================================

    async def _execute_write_file(self, task: Any) -> dict[str, Any]:
        """Generate or UPDATE a file — reads existing content if present."""
        desc = task.description.lower()
        title = task.title.lower()

        # Figure out which file this task targets
        target = _guess_target_file(task.description, task.title, self.sandbox_dir)
        if target is None:
            target = self._default_target_file(desc, title)

        # Read existing content (the key fix — context awareness)
        existing = _read_sandbox_file(self.sandbox_dir, target)

        if existing:
            # File exists — treat as an edit (merge new work into existing)
            return await self._merge_into_file(task, target, existing)
        else:
            # New file — generate from scratch
            return await self._generate_new_file(task, target)

    def _default_target_file(self, desc: str, title: str) -> str:
        """Fallback target filename inferred from task context.

        Strategy (universal — no extension whitelist):
        1. Check if any file extension is mentioned directly in the text
           (e.g. "html", "pdf", "docx", "blend", "png" → use that extension)
        2. Map well-known tool/framework names to their primary extension
           (e.g. "python" → .py, "react" → .js)
        3. Fall back to .txt for truly unknown cases
        4. Derive the filename stem from the goal text
        """
        combined = f"{title} {desc}"
        goal_combined = f"{combined} {self.goal.lower()}"

        # Special case
        if "readme" in combined or "documentation" in combined:
            return "README.txt"

        # --- Step 1: Direct extension mention ---
        # Look for words that ARE file extensions (e.g. "create an html file",
        # "generate a pdf", "write a docx report", "edit the blend file")
        # Search for a standalone word that looks like an extension
        ext_match = re.search(
            r'\b(html?|css|jsx?|tsx?|py|rb|go|rs|java|kt|cs|swift|dart|'
            r'lua|sql|sh|bat|ps1|json|ya?ml|toml|xml|ini|csv|'
            r'pdf|docx?|xlsx?|pptx?|odt|ods|rtf|tex|latex|'
            r'png|jpe?g|gif|svg|ico|webp|bmp|tiff?|psd|ai|'
            r'mp[34]|wav|ogg|flac|avi|mkv|mov|webm|'
            r'zip|tar|gz|rar|7z|'
            r'blend|fbx|obj|stl|gltf|glb|'
            r'ipynb|rmd|'
            r'[a-z]{1,8})\s+file\b', combined
        )
        if ext_match:
            ext = ext_match.group(1)
            # Normalize common variants
            if ext == "htm": ext = "html"
            if ext == "jpeg" or ext == "jpg": ext = "jpg"
        else:
            # Also check for "file_type file" at end, or just a bare ext word
            # after action verbs: "create a pdf", "generate png", "write sql"
            ext_match2 = re.search(
                r'\b(?:create|generate|write|make|build|produce|export)\b.*?\b'
                r'([a-z]{1,8})\b\s*$', combined
            )
            ext = None
            if ext_match2:
                candidate = ext_match2.group(1)
                # Only use it if it looks like an extension (not a regular word)
                if len(candidate) <= 5 and candidate not in {
                    "a", "an", "the", "this", "that", "file", "new", "code",
                    "it", "for", "and", "with", "from", "into", "task",
                }:
                    ext = candidate

        # --- Step 2: Framework/tool name → extension (slim, for ambiguous cases) ---
        if ext is None:
            _tool_to_ext = {
                "python": "py", "flask": "py", "django": "py", "fastapi": "py",
                "javascript": "js", "node": "js", "react": "jsx", "express": "js",
                "typescript": "ts", "angular": "ts",
                "ruby": "rb", "rails": "rb",
                "golang": "go",
                "rust": "rs", "cargo": "rs",
                "kotlin": "kt",
                "csharp": "cs", "dotnet": "cs",
                "swiftui": "swift",
                "flutter": "dart",
                "blender": "blend",
                "photoshop": "psd",
                "docker": "dockerfile",
                "kubernetes": "yaml",
                "latex": "tex",
            }
            for tool, tool_ext in _tool_to_ext.items():
                if tool in goal_combined:
                    ext = tool_ext
                    break

        # --- Step 3: Fallback ---
        if ext is None:
            ext = "txt"

        # --- Step 4: Derive filename stem from goal ---
        goal_words = re.findall(r'[a-zA-Z]+', self.goal.lower())
        stem = goal_words[0] if goal_words else "output"
        skip = {"create", "build", "make", "write", "generate", "a", "an", "the",
                "add", "update", "modify", "edit", "implement", "set", "up"}
        while stem in skip and goal_words:
            goal_words.pop(0)
            stem = goal_words[0] if goal_words else "main"

        return f"{stem}.{ext}"

    async def _generate_new_file(self, task: Any, target: str) -> dict[str, Any]:
        """Generate a brand new file."""
        context = self._build_context_block()

        if target.endswith(".html"):
            system_prompt = (
                "You are an expert developer. Generate a COMPLETE, standalone HTML file "
                "with embedded CSS and JavaScript. The file must work by double-clicking it "
                "in any browser — no external dependencies, no CDN links, no imports.\n\n"
                "Output ONLY the HTML file content, starting with <!DOCTYPE html> and ending "
                "with </html>. No markdown fences, no explanation — just the raw HTML."
            )
        elif target.lower().startswith("readme"):
            system_prompt = (
                "You are a technical writer. Write a brief README file for the project. "
                "Include: title, how to use, features, and credits. "
                "Output ONLY the README text content, no markdown fences."
            )
        else:
            system_prompt = (
                "You are a developer. Generate the requested file content. "
                "Output ONLY the file content, no markdown fences or explanation."
            )

        user_prompt = (
            f"Goal: {self.goal}\n\n"
            f"Task: {task.title}\nDescription: {task.description}\n\n"
            f"Target file: {target}\n\n"
            f"{context}"
        )

        response = await _call_llm(
            self.provider, self.model, system_prompt, user_prompt,
            max_tokens=16000, temperature=0.4,
        )

        content = self._extract_file_content(response, target)
        filepath = self.sandbox_dir / target
        filepath.parent.mkdir(parents=True, exist_ok=True)
        filepath.write_text(content, encoding="utf-8")
        self._generated_files[target] = str(filepath)

        lines = len(content.splitlines())
        size_kb = len(content.encode()) / 1024
        logger.info("Generated %s: %d lines, %.1f KB", target, lines, size_kb)

        confidence = 0.85 if lines > 50 else 0.6
        return {
            "success": True,
            "output": f"Generated {target} ({lines} lines, {size_kb:.1f} KB)",
            "confidence": confidence,
        }

    async def _merge_into_file(
        self, task: Any, target: str, existing: str,
    ) -> dict[str, Any]:
        """Merge new work into an existing file (the core context-aware edit)."""
        context = self._build_context_block()
        old_lines = len(existing.splitlines())

        system_prompt = (
            "You are an expert developer editing an existing file. "
            "You will be given the CURRENT file content and a task description. "
            "You must output the COMPLETE updated file with the requested changes applied. "
            "CRITICAL RULES:\n"
            "1. PRESERVE ALL existing functionality — do NOT remove or simplify existing code.\n"
            "2. Only ADD the new features described in the task.\n"
            "3. The output must be the COMPLETE file, not a fragment or diff.\n"
            "4. Output ONLY the file content, no markdown fences, no explanation."
        )
        user_prompt = (
            f"Overall goal: {self.goal}\n\n"
            f"Task: {task.title}\nDescription: {task.description}\n\n"
            f"CURRENT FILE ({target}) — {old_lines} lines:\n"
            f"```\n{existing}\n```\n\n"
            f"Apply the changes described in the task. "
            f"Output the COMPLETE updated file.\n\n"
            f"{context}"
        )

        response = await _call_llm(
            self.provider, self.model, system_prompt, user_prompt,
            max_tokens=16000, temperature=0.3,
        )

        new_content = self._extract_file_content(response, target)

        # Regression guard: reject if file shrank drastically
        new_lines = len(new_content.splitlines())
        if new_lines < old_lines * 0.5 and old_lines > 20:
            logger.warning(
                "Edit shrank %s from %d to %d lines — keeping larger version",
                target, old_lines, new_lines,
            )
            if len(new_content) < len(existing) * 0.5:
                new_content = existing

        filepath = self.sandbox_dir / target
        filepath.write_text(new_content, encoding="utf-8")
        self._generated_files[target] = str(filepath)

        new_lines = len(new_content.splitlines())
        size_kb = len(new_content.encode()) / 1024
        logger.info("Merged into %s: %d→%d lines, %.1f KB", target, old_lines, new_lines, size_kb)

        confidence = 0.85 if new_lines >= old_lines else 0.65
        return {
            "success": True,
            "output": f"Updated {target} ({old_lines}→{new_lines} lines, {size_kb:.1f} KB)",
            "confidence": confidence,
        }

    # =========================================================================
    # EDIT FILE (explicit edit — same logic as merge)
    # =========================================================================

    async def _execute_edit_file(self, task: Any) -> dict[str, Any]:
        """Edit an existing file — reads current content and merges."""
        target = _guess_target_file(task.description, task.title, self.sandbox_dir)
        if target is None:
            target = self._default_target_file(task.description.lower(), task.title.lower())

        existing = _read_sandbox_file(self.sandbox_dir, target)
        if not existing:
            # No file to edit — create it
            return await self._generate_new_file(task, target)

        return await self._merge_into_file(task, target, existing)

    # =========================================================================
    # VALIDATE
    # =========================================================================

    async def _execute_validate(self, task: Any) -> dict[str, Any]:
        """Validate generated files exist and look reasonable."""
        issues: list[str] = []
        for name, path in self._generated_files.items():
            p = Path(path)
            if not p.exists():
                issues.append(f"{name}: file missing")
            elif p.stat().st_size < 100:
                issues.append(f"{name}: file too small ({p.stat().st_size} bytes)")

        if issues:
            return {
                "success": False,
                "error": "Validation issues: " + "; ".join(issues),
                "confidence": 0.3,
            }

        files_summary = ", ".join(
            f"{n} ({Path(p).stat().st_size / 1024:.1f} KB)"
            for n, p in self._generated_files.items()
        )
        return {
            "success": True,
            "output": f"Validated: {files_summary}",
            "confidence": 0.95,
        }

    # =========================================================================
    # GENERIC (also writes to file if code is produced)
    # =========================================================================

    async def _execute_generic(self, task: Any) -> dict[str, Any]:
        """Generic task — if it produces code, persist it to the target file."""
        context = self._build_context_block()
        target = _guess_target_file(task.description, task.title, self.sandbox_dir)

        # If we can identify a target and it exists, do a merge
        if target:
            existing = _read_sandbox_file(self.sandbox_dir, target)
            if existing:
                return await self._merge_into_file(task, target, existing)

        system_prompt = (
            "You are an autonomous coding assistant. Execute the given task. "
            "If your output is code, output ONLY the code with no markdown fences."
        )
        response = await _call_llm(
            self.provider, self.model, system_prompt,
            f"Goal: {self.goal}\n\nTask: {task.title}\n{task.description}\n\n{context}",
            max_tokens=8000, temperature=0.4,
        )

        # If response looks like code and we have a target, persist it
        if target and self._looks_like_code(response):
            existing = _read_sandbox_file(self.sandbox_dir, target)
            if existing:
                return await self._merge_into_file(task, target, existing)
            else:
                content = self._extract_file_content(response, target)
                filepath = self.sandbox_dir / target
                filepath.parent.mkdir(parents=True, exist_ok=True)
                filepath.write_text(content, encoding="utf-8")
                self._generated_files[target] = str(filepath)
                lines = len(content.splitlines())
                return {
                    "success": True,
                    "output": f"Generated {target} ({lines} lines)",
                    "confidence": 0.8,
                }

        return {"success": True, "output": response[:500], "confidence": 0.8}

    # =========================================================================
    # HELPERS
    # =========================================================================

    @staticmethod
    def _looks_like_code(text: str) -> bool:
        """Heuristic: does this text look like code?"""
        code_signals = [
            "function ", "def ", "class ", "const ", "let ", "var ",
            "import ", "from ", "<html", "<div", "<script", "<!DOCTYPE",
            "if (", "for (", "while (",
        ]
        return any(sig in text for sig in code_signals)

    @staticmethod
    def _extract_file_content(text: str, target: str) -> str:
        """Extract file content from LLM response, handling markdown fences."""
        if target.endswith(".html"):
            return ARATaskExecutor._extract_html(text)

        # Strip markdown fences
        cleaned = re.sub(r"^```\w*\n?", "", text.strip())
        cleaned = re.sub(r"\n?```$", "", cleaned.strip())
        return cleaned

    @staticmethod
    def _extract_html(text: str) -> str:
        """Extract HTML from LLM response, stripping markdown fences."""
        match = re.search(
            r"```(?:html)?\s*(<!DOCTYPE.*?</html>)\s*```",
            text, re.DOTALL | re.IGNORECASE,
        )
        if match:
            return match.group(1).strip()

        match = re.search(
            r"(<!DOCTYPE.*?</html>)", text, re.DOTALL | re.IGNORECASE,
        )
        if match:
            return match.group(1).strip()

        if "<html" in text.lower():
            return text.strip()

        return (
            f"<!DOCTYPE html>\n<html>\n<head><title>Generated</title></head>\n"
            f"<body>\n{text}\n</body>\n</html>"
        )
