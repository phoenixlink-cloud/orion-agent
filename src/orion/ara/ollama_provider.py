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
"""ARA LLM Provider — real LLM integration for goal decomposition.

Implements the LLMProvider protocol from goal_engine.py.
Routes through the unified call_provider (supports all 11 AI providers).
Task execution is handled by ARATaskExecutor in task_executor.py.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

logger = logging.getLogger("orion.ara.llm_provider")


async def _call_llm(
    provider: str,
    model: str,
    system_prompt: str,
    user_prompt: str,
    max_tokens: int = 8000,
    temperature: float = 0.4,
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
        component="ara_decomposer",
        temperature=temperature,
    )


def _extract_json(text: str) -> list[dict[str, Any]]:
    """Extract a JSON array from LLM response text, handling markdown fences."""
    # Try to find JSON array in markdown code blocks
    match = re.search(r"```(?:json)?\s*(\[.*?\])\s*```", text, re.DOTALL)
    if match:
        return json.loads(match.group(1))
    # Try to find raw JSON array
    match = re.search(r"\[.*\]", text, re.DOTALL)
    if match:
        return json.loads(match.group(0))
    raise ValueError(f"No JSON array found in LLM response: {text[:200]}")


class ARALLMProvider:
    """Provider-agnostic LLM provider for goal decomposition.

    Implements the LLMProvider protocol from goal_engine.py.
    Routes through the unified call_provider (supports all 11 AI providers).
    """

    def __init__(self, provider: str = "ollama", model: str = "qwen2.5:14b"):
        self.provider = provider
        self.model = model
        self._call_count = 0

    async def decompose_goal(self, goal: str, context: str = "") -> list[dict[str, Any]]:
        """Decompose a goal into a list of task dicts."""
        self._call_count += 1
        system_prompt = (
            "You are a task planner for an autonomous coding agent. "
            "Given a goal, decompose it into a sequence of atomic tasks. "
            "Each task must have: task_id (string like 'task-1'), title (short name), "
            "description (what to do — MUST name the target file explicitly, e.g. 'game.html'), "
            "action_type (one of: write_file, read_files, run_tests, analyze, edit_file), "
            "dependencies (list of task_id strings this task depends on), "
            "and estimated_minutes (number).\n\n"
            "CRITICAL RULES FOR action_type:\n"
            "- Use 'write_file' ONLY for the FIRST task that creates a new file.\n"
            "- Use 'edit_file' for ALL subsequent tasks that modify an existing file.\n"
            "- Example: task-3 creates game.html (write_file), then task-4 adds a game loop "
            "to game.html (edit_file), task-5 adds sprites to game.html (edit_file), etc.\n"
            "- NEVER use write_file for a file that was already created by an earlier task.\n"
            "- Each task description MUST state which file it targets.\n\n"
            "Return ONLY a JSON array of task objects. No extra text."
        )
        user_prompt = f"Goal: {goal}"
        if context:
            user_prompt += f"\n\nContext: {context}"

        try:
            response = await _call_llm(
                self.provider, self.model, system_prompt, user_prompt,
                max_tokens=4000, temperature=0.3,
            )
            tasks = _extract_json(response)
            logger.info("Decomposed goal into %d tasks via %s/%s", len(tasks), self.provider, self.model)
            return tasks
        except Exception as e:
            logger.error("Goal decomposition failed: %s", e)
            return self._fallback_decomposition(goal)

    async def replan(
        self,
        goal: str,
        completed: list[dict] | None = None,
        failed: list[dict] | None = None,
        remaining: list[dict] | None = None,
    ) -> list[dict[str, Any]]:
        """Re-plan remaining tasks given progress."""
        if remaining:
            return remaining
        return []

    @staticmethod
    def _fallback_decomposition(goal: str) -> list[dict[str, Any]]:
        """Provide a sensible fallback if LLM decomposition fails."""
        return [
            {
                "task_id": "task-1",
                "title": "Analyze requirements",
                "description": f"Understand the goal: {goal[:200]}",
                "action_type": "analyze",
                "dependencies": [],
                "estimated_minutes": 2,
            },
            {
                "task_id": "task-2",
                "title": "Generate main file",
                "description": "Create the primary output file based on requirements",
                "action_type": "write_file",
                "dependencies": ["task-1"],
                "estimated_minutes": 15,
            },
            {
                "task_id": "task-3",
                "title": "Generate documentation",
                "description": "Create README.txt with instructions",
                "action_type": "write_file",
                "dependencies": ["task-2"],
                "estimated_minutes": 3,
            },
            {
                "task_id": "task-4",
                "title": "Validate output",
                "description": "Check all sandbox files are complete and correct",
                "action_type": "run_tests",
                "dependencies": ["task-3"],
                "estimated_minutes": 2,
            },
        ]


# Backward-compatible aliases
OllamaLLMProvider = ARALLMProvider
