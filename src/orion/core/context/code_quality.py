"""
Orion Agent — Code Quality Prompt Bridge

Re-exports get_quality_context_for_prompt from the quality module
so that prompts.py can import from orion.core.context.code_quality.
"""

from orion.core.context.quality import get_quality_context_for_prompt

__all__ = ["get_quality_context_for_prompt"]
